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
import re

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis

from daily.cli import _parse_approval_decision, _resolve_email_adapters
from daily.config import Settings
from daily.logging_config import make_logger
from daily.db.engine import async_session
from daily.orchestrator.graph import build_graph
from daily.orchestrator.session import (
    create_session_config,
    initialize_session_state,
    run_session,
    set_email_adapters,
)
from daily.profile.signals import SignalType
from daily.voice.barge_in import VoiceTurnManager
from daily.voice.stt import STTPipeline
from daily.voice.tts import TTSPipeline

logger = make_logger(__name__, stage="voice")

_SEPARATOR = "-" * 40


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences — delegates to shared implementation.

    Uses daily.briefing.items._split_sentences for consistency with
    pipeline-time sentence range computation (Pitfall 5).
    """
    from daily.briefing.items import _split_sentences as _shared_split  # noqa: PLC0415
    return _shared_split(text)


async def _capture_signal_inline(
    user_id: int,
    signal_type: "SignalType",
    target_id: str | None = None,
) -> None:
    """Fire-and-forget signal capture from the voice loop.

    Mirrors _capture_signal in nodes.py but importable without circular deps.
    Per D-01: implicit skip in voice loop fires signal inline (no orchestrator round-trip).
    """
    try:
        from daily.db.engine import async_session as _async_session  # noqa: PLC0415
        from daily.profile.signals import append_signal  # noqa: PLC0415

        async with _async_session() as session:
            await append_signal(
                user_id=user_id,
                signal_type=signal_type,
                session=session,
                target_id=target_id,
            )
    except Exception as exc:
        logger.warning("_capture_signal_inline: failed to write signal: %s", exc)


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
            # Phase 12 D-01: sentence-by-sentence delivery with cursor tracking
            briefing_narrative = initial_state.get("briefing_narrative", "")
            if briefing_narrative:
                print("dAIly: [briefing spoken]")
                sentences = _split_sentences(briefing_narrative)
                briefing_interrupted = False
                briefing_cursor_val = None

                # Phase 13 D-03: Load item cursor for signal tracking
                briefing_items = initial_state.get("briefing_items", [])
                current_item_idx = 0
                implicit_skip_threshold = 2.0  # seconds of silence after barge-in

                for i, sentence in enumerate(sentences):
                    # Phase 13 D-03: Advance item cursor when sentence crosses item boundary
                    if briefing_items and current_item_idx < len(briefing_items):
                        item = briefing_items[current_item_idx]
                        item_end = (
                            item.get("sentence_range_end", 0)
                            if isinstance(item, dict)
                            else getattr(item, "sentence_range_end", 0)
                        )
                        if i >= item_end and current_item_idx < len(briefing_items) - 1:
                            current_item_idx += 1

                    completed = await turn_manager.speak(sentence)
                    if not completed:
                        # Barge-in detected — check for implicit skip (D-01)
                        try:
                            utterance = await asyncio.wait_for(
                                turn_manager.wait_for_utterance(),
                                timeout=implicit_skip_threshold,
                            )
                        except asyncio.TimeoutError:
                            utterance = None

                        if utterance is None or utterance.strip() == "":
                            # Silence after barge-in -> implicit skip (D-01)
                            sender = None
                            if briefing_items and current_item_idx < len(briefing_items):
                                item = briefing_items[current_item_idx]
                                sender = (
                                    item.get("sender")
                                    if isinstance(item, dict)
                                    else getattr(item, "sender", None)
                                )
                            asyncio.create_task(
                                _capture_signal_inline(user_id, SignalType.skip, target_id=sender)
                            )
                            logger.info("Implicit skip signal fired for item %d", current_item_idx)
                            # Advance to next item
                            if current_item_idx < len(briefing_items) - 1:
                                current_item_idx += 1
                            continue
                        else:
                            # User spoke — handle as interruption (existing flow)
                            briefing_cursor_val = i + 1
                            briefing_interrupted = True
                            await turn_manager.speak("Sure, I'll pick up your briefing after.")
                            # Store pending utterance for the first main loop turn
                            initial_state["_pending_utterance"] = utterance
                            break

                if not briefing_interrupted:
                    briefing_cursor_val = None  # fully delivered

                # Surface briefing_cursor and item cursor into initial_state for LangGraph
                initial_state["briefing_cursor"] = briefing_cursor_val
                initial_state["current_item_index"] = current_item_idx
            else:
                print("  No cached briefing. Run 'daily chat' first to generate one.")
                print()

            # 7. Main voice loop
            # Phase 9 INTEL-02: accumulate per-turn messages for end-of-session extraction.
            session_history: list[dict] = []
            first_turn = True
            try:
                while True:
                    # Wait for user utterance from Deepgram STT
                    user_input = await turn_manager.wait_for_utterance()

                    if user_input.lower().strip() in ("exit", "quit"):
                        session_history.append({"role": "user", "content": user_input})
                        print("Session ended.")
                        break

                    # Run through orchestrator (same as chat session)
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
                    first_turn = False

                    # Check for approval interrupt (T-05-10: same gate as CLI)
                    graph_state = await graph.aget_state(config)
                    if graph_state.next:
                        # Voice approval flow: unlimited edit rounds (D-01)
                        # turn_recorded guards against double-appending user_input for
                        # the same outer turn across multiple approval sub-loop iterations.
                        turn_recorded = False
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
                                    if not turn_recorded:
                                        session_history.append({"role": "user", "content": user_input})
                                        turn_recorded = True
                                    session_history.append({"role": "assistant", "content": content})
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
                                    if not turn_recorded:
                                        session_history.append({"role": "user", "content": user_input})
                                        turn_recorded = True
                                    session_history.append({"role": "assistant", "content": content})
                                break
                    else:
                        # Normal (non-interrupted) response — speak it
                        messages = result.get("messages", [])
                        if messages:
                            last_msg = messages[-1]
                            content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                            print(f"dAIly: {content}")
                            await turn_manager.speak(content)
                            session_history.append({"role": "user", "content": user_input})
                            session_history.append({"role": "assistant", "content": content})

                            # Phase 12: check briefing_cursor for auto-offer and resume re-entry
                            graph_state_snap = await graph.aget_state(config)
                            current_state = graph_state_snap.values if hasattr(graph_state_snap, "values") else {}
                            cursor = current_state.get("briefing_cursor")

                            # D-04: auto-offer briefing resume if cursor is set
                            if cursor is not None and "resuming your briefing" not in content.lower():
                                await turn_manager.speak("Want me to continue your briefing?")

                            # Re-enter sentence loop when resume_briefing_node was just invoked
                            if cursor is not None and "resuming your briefing" in content.lower():
                                briefing_text = current_state.get("briefing_narrative", "")
                                if briefing_text:
                                    sentences = _split_sentences(briefing_text)
                                    # Clamp cursor to valid range (T-12-01)
                                    safe_cursor = max(0, min(cursor, len(sentences) - 1))
                                    for j, sentence in enumerate(sentences[safe_cursor:], start=safe_cursor):
                                        completed = await turn_manager.speak(sentence)
                                        if not completed:
                                            # Re-interrupted — update cursor
                                            await graph.aupdate_state(config, {"briefing_cursor": j + 1})
                                            await turn_manager.speak("Sure, I'll pick up your briefing after.")
                                            break
                                    else:
                                        # Briefing fully delivered — clear cursor
                                        await graph.aupdate_state(config, {"briefing_cursor": None})

            finally:
                # 8. Clean shutdown
                listen_stop.set()
                await turn_manager.stop()

                # Phase 9 INTEL-02: fire-and-forget memory extraction (D-03).
                # Must NOT block voice shutdown — asyncio.create_task, no await.
                # Each task opens its own DB session (Pitfall 4: never share the
                # voice loop's session across the create_task boundary).
                if session_history:
                    from daily.db.engine import async_session as _async_session  # noqa: PLC0415
                    from daily.profile.memory import extract_and_store_memories  # noqa: PLC0415

                    thread_id = config.get("configurable", {}).get("thread_id", f"user-{user_id}")

                    async def _run_memory_extraction() -> None:
                        try:
                            async with _async_session() as mem_session:
                                await extract_and_store_memories(
                                    user_id=user_id,
                                    session_history=session_history,
                                    session_id=thread_id,
                                    db_session=mem_session,
                                )
                        except Exception as exc:
                            logger.warning(
                                "memory extraction task failed for user=%d: %s",
                                user_id, exc,
                            )

                    asyncio.create_task(_run_memory_extraction())

                print("Voice session ended.")

    except Exception as exc:
        logger.error("Voice session failed: %s", exc, exc_info=True)
        print(f"Error: Voice session failed — {exc}")
        raise
