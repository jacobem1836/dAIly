"""Voice session loop: top-level run_voice_session() mirroring _run_chat_session().

Wires VoiceTurnManager (mic + speaker I/O) with the existing orchestrator graph,
AsyncPostgresSaver for persistent session state, and Redis briefing cache.

Design decisions honoured:
- D-01: daily voice mirrors daily chat structure — voice is I/O only
- D-02: Same orchestrator graph (build_graph, run_session) — no separate agent
- D-11: AsyncPostgresSaver replaces MemorySaver for persistent state across turns

Threat mitigations:
- T-05-10: Approval flow reuses _parse_approval_decision — no bypass path
- T-05-11: AsyncPostgresSaver scoped by thread_id per user per day
- T-05-12: Transcripts pass through route_intent keyword filter (same as chat)
"""
import asyncio
import logging
import random
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis

from daily.cli import _parse_approval_decision, _resolve_email_adapters
from daily.config import Settings
from daily.db.engine import async_session
from daily.orchestrator.graph import build_graph
from daily.orchestrator.session import (
    StreamingNotSupported,
    astream_session,
    create_session_config,
    initialize_session_state,
    run_session,
    set_email_adapters,
)
from daily.voice.barge_in import VoiceTurnManager
from daily.voice.stt import STTPipeline
from daily.voice.tts import TTSPipeline

logger = logging.getLogger(__name__)

_SEPARATOR = "-" * 40
_ACKNOWLEDGEMENTS: list[str] = ["Got it.", "One sec.", "Sure.", "On it.", "Mmhm."]


async def _handle_voice_approval(
    turn_manager,
    graph,
    graph_state,
    config: dict,
) -> dict:
    """Handle the approval sub-loop by voice.

    Mirrors _handle_approval_flow() from cli.py but uses TTS/STT instead of
    print()/input(). Speaks the draft preview, prompts for decision, listens
    for the user's spoken response, and resumes the graph.

    Per T-05-10: Reuses _parse_approval_decision — same logic as CLI, no bypass.

    Args:
        turn_manager: VoiceTurnManager for speak/listen I/O.
        graph: Compiled LangGraph StateGraph with checkpointer.
        graph_state: LangGraph state snapshot with interrupted tasks.
        config: LangGraph config dict with thread_id.

    Returns:
        Dict with 'messages' from the resumed graph, and optionally
        'edit_instruction' if the user requested edits.
    """
    from langgraph.types import Command

    # Extract interrupt payload
    preview_text = ""
    action_type_str = "action"
    if graph_state.tasks:
        for task in graph_state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupt_value = task.interrupts[0].value
                if isinstance(interrupt_value, dict):
                    preview_text = interrupt_value.get("preview", "")
                    action_type_str = interrupt_value.get("action_type", "action")
                break

    # Speak the draft preview
    spoken_preview = f"Draft {action_type_str}. {preview_text}" if preview_text else f"Draft {action_type_str} ready."
    await turn_manager.speak(spoken_preview)
    await turn_manager.speak("Confirm, reject, or describe changes.")

    decision_input = await turn_manager.wait_for_utterance()
    if not decision_input:
        decision_input = "reject"

    decision = _parse_approval_decision(decision_input)

    # Resume graph with the decision
    result = await graph.ainvoke(Command(resume=decision), config=config)
    output = dict(result) if isinstance(result, dict) else {"messages": []}
    if decision.startswith("edit:"):
        output["edit_instruction"] = decision[len("edit:"):]
    return output


async def run_voice_session(user_id: int = 1) -> None:
    """Run an interactive voice session with the orchestrator.

    Mirrors _run_chat_session() from cli.py but replaces input()/print()
    with VoiceTurnManager (mic capture + TTS playback).

    Per D-01: daily voice CLI command mirrors daily chat structure.
    Per D-02: Same orchestrator graph (build_graph, run_session) — voice is I/O only.
    Per D-11: AsyncPostgresSaver replaces MemorySaver for persistent state.

    Session lifecycle:
      1. Validate API keys (Deepgram + Cartesia).
      2. Resolve email adapters from stored tokens.
      3. Build graph with AsyncPostgresSaver (persistent across voice turns).
      4. Load initial state (Redis briefing cache + profile preferences).
      5. Start STT listener background task.
      6. Speak briefing on first turn if cached (VOICE-03 sub-1s from cache).
      7. Voice loop: wait_for_utterance -> run_session -> speak response.
      8. Handle approval interrupts by voice (T-05-10).
      9. Clean shutdown on exit/quit utterance or Ctrl+C.

    Args:
        user_id: User ID for the session. Defaults to 1 (single-user M1).
    """
    import base64

    # 1. Load settings and validate API keys
    settings = Settings()

    if not settings.deepgram_api_key:
        print("Error: DEEPGRAM_API_KEY is not set in .env. Cannot start voice session.")
        return

    if not settings.cartesia_api_key:
        print("Error: CARTESIA_API_KEY is not set in .env. Cannot start voice session.")
        return

    # 2. Resolve email adapters (mirrors _run_chat_session)
    adapters = await _resolve_email_adapters(user_id, settings)
    set_email_adapters(adapters)

    # 3. Build graph with AsyncPostgresSaver (D-11: persistent state across turns)
    # Pitfall 4 (from RESEARCH.md): use database_url_psycopg (psycopg driver),
    # NOT database_url (asyncpg driver) — AsyncPostgresSaver requires psycopg.
    try:
        async with AsyncPostgresSaver.from_conn_string(settings.database_url_psycopg) as checkpointer:
            await checkpointer.setup()  # Idempotent — safe to call every session start
            graph = build_graph(checkpointer=checkpointer)

            # 4. Create session config and load initial state
            config = await create_session_config(user_id)
            redis = Redis.from_url(settings.redis_url)
            try:
                async with async_session() as db_sess:
                    initial_state = await initialize_session_state(user_id, redis, db_sess)
            finally:
                await redis.aclose()

            # 5. Voice I/O setup
            tts_pipeline = TTSPipeline(api_key=settings.cartesia_api_key)
            stt_pipeline = STTPipeline(api_key=settings.deepgram_api_key)
            turn_manager = VoiceTurnManager(tts=tts_pipeline, stt=stt_pipeline)

            listen_stop = asyncio.Event()
            await turn_manager.start_stt(listen_stop)

            # Wait briefly for STT connection to establish (surface errors early)
            try:
                await asyncio.wait_for(stt_pipeline.connected.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Check if the STT task already failed
                if turn_manager._stt_task and turn_manager._stt_task.done():
                    exc = turn_manager._stt_task.exception()
                    print(f"Error: STT connection failed — {exc}")
                    return
                print("Warning: STT connection taking longer than expected...")

            print("dAIly voice session started.")
            if adapters:
                print(f"  {len(adapters)} email adapter(s) connected.")
            else:
                print("  No email adapters connected. Run 'daily connect gmail' first.")
            print("  Say 'exit' or 'quit' to end the session.")
            print()

            # 6. First turn — speak briefing from cache (VOICE-03: sub-1s from cache)
            briefing_narrative = initial_state.get("briefing_narrative", "")
            if briefing_narrative:
                print("dAIly: [briefing spoken]")
                await turn_manager.speak(briefing_narrative)
            else:
                print("  No cached briefing. Run 'daily chat' first to generate one.")
                print()

            # 7. Main voice loop
            first_turn = True
            try:
                while True:
                    # Wait for user utterance from Deepgram STT
                    user_input = await turn_manager.wait_for_utterance()

                    # Backchannel filter — swallow "yeah", "ok", etc. during TTS
                    if not turn_manager.filter_utterance(user_input):
                        # Backchannel — let TTS continue; do not advance the turn.
                        continue

                    normalized = user_input.lower().strip()
                    if normalized in ("exit", "quit"):
                        print("Session ended.")
                        break

                    # Speak a brief acknowledgement while LLM processes (non-first turns only)
                    if not first_turn:
                        try:
                            await turn_manager.speak(random.choice(_ACKNOWLEDGEMENTS))
                        except Exception as ack_err:
                            # Non-fatal — log and proceed; user still gets the real response.
                            logger.debug("Acknowledgement TTS failed: %s", ack_err)

                    # Run through orchestrator — attempt streaming first, fall back to ainvoke.
                    streamed_text = ""
                    used_streaming = False
                    try:
                        token_iter = astream_session(
                            graph,
                            user_input,
                            config,
                            initial_state=initial_state if first_turn else None,
                        )

                        # Producer/consumer bridge: tee the LLM token stream to both
                        # (a) TTS playback and (b) an accumulator for downstream state.
                        token_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=64)

                        async def _produce() -> None:
                            nonlocal streamed_text
                            try:
                                async for delta in token_iter:
                                    streamed_text += delta
                                    await token_queue.put(delta)
                            finally:
                                await token_queue.put(None)  # sentinel

                        async def _tts_iter() -> AsyncIterator[str]:
                            while True:
                                item = await token_queue.get()
                                if item is None:
                                    return
                                yield item

                        await asyncio.gather(
                            _produce(),
                            turn_manager._tts.play_streaming_tokens(
                                _tts_iter(), turn_manager._stop_event
                            ),
                        )
                        used_streaming = True
                        result = None  # Streaming path bypasses graph state for respond turns
                        logger.debug("Streamed respond turn: %d chars", len(streamed_text))

                    except StreamingNotSupported:
                        logger.debug("Streaming not supported, fell back to run_session")
                        try:
                            result = await run_session(
                                graph,
                                user_input,
                                config,
                                initial_state=initial_state if first_turn else None,
                            )
                        except Exception as exc:
                            from openai import OpenAIError  # noqa: PLC0415
                            if isinstance(exc, OpenAIError):
                                error_msg = f"Sorry, there was an error: {exc}"
                                print(f"Error: {error_msg}")
                                await turn_manager.speak("Sorry, there was an API error. Please try again.")
                                break
                            raise

                    except Exception as exc:
                        from openai import OpenAIError  # noqa: PLC0415
                        if isinstance(exc, OpenAIError):
                            error_msg = f"Sorry, there was an error: {exc}"
                            print(f"Error: {error_msg}")
                            await turn_manager.speak("Sorry, there was an API error. Please try again.")
                            break
                        raise

                    first_turn = False

                    # Check for approval interrupt (T-05-10: same gate as CLI)
                    # Only applicable on the non-streaming path (result is None for streamed turns).
                    if result is not None:
                        graph_state = await graph.aget_state(config)
                        if graph_state.next:
                            # Voice approval flow: unlimited edit rounds (D-01)
                            while True:
                                approval_result = await _handle_voice_approval(
                                    turn_manager=turn_manager,
                                    graph=graph,
                                    graph_state=graph_state,
                                    config=config,
                                )

                                edit_instruction = approval_result.get("edit_instruction")
                                if not edit_instruction:
                                    # Confirm or reject — speak result and break
                                    ap_messages = approval_result.get("messages", [])
                                    if ap_messages:
                                        last_msg = ap_messages[-1]
                                        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                                        print(f"dAIly: {content}")
                                        await turn_manager.speak(content)
                                    break

                                # Edit decision: check if graph interrupted again at approval
                                graph_state = await graph.aget_state(config)
                                if not graph_state.next:
                                    # Graph completed without re-interrupting
                                    ap_messages = approval_result.get("messages", [])
                                    if ap_messages:
                                        last_msg = ap_messages[-1]
                                        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                                        print(f"dAIly: {content}")
                                        await turn_manager.speak(content)
                                    break
                        else:
                            # Normal (non-interrupted) response — speak it
                            messages = result.get("messages", [])
                            if messages:
                                last_msg = messages[-1]
                                content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                                print(f"dAIly: {content}")
                                await turn_manager.speak(content)

            finally:
                # 8. Clean shutdown
                listen_stop.set()
                await turn_manager.stop()
                print("Voice session ended.")

    except Exception as exc:
        logger.error("Voice session failed: %s", exc, exc_info=True)
        print(f"Error: Voice session failed — {exc}")
        raise
