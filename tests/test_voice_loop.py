"""Integration tests for voice session loop (Plan 05-04).

Tests cover:
- AsyncPostgresSaver wiring (D-11, Pitfall 4: psycopg URL)
- Briefing spoken on first turn (VOICE-03)
- Exit utterance ends session cleanly
- Approval flow by voice (T-05-10)
- CLI voice command registration
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_settings(deepgram_api_key="dg-key", cartesia_api_key="ca-key"):
    """Return a minimal mock Settings object."""
    s = MagicMock()
    s.deepgram_api_key = deepgram_api_key
    s.cartesia_api_key = cartesia_api_key
    s.database_url_psycopg = "postgresql://daily:daily_dev@localhost:5432/daily"
    s.redis_url = "redis://localhost:6379/0"
    s.vault_key = None
    return s


def make_turn_manager(utterances=None):
    """Return a mock VoiceTurnManager.

    Args:
        utterances: List of strings returned by wait_for_utterance in sequence.
                    Defaults to ["exit"] to end the loop after one call.
    """
    if utterances is None:
        utterances = ["exit"]

    tm = AsyncMock()
    tm.speak = AsyncMock(return_value=True)
    tm.wait_for_utterance = AsyncMock(side_effect=utterances)
    tm.start_stt = AsyncMock()
    tm.stop = AsyncMock()
    return tm


def make_graph(next_tasks=None, messages=None):
    """Return a mock compiled graph."""
    graph = AsyncMock()
    if messages is None:
        messages = [MagicMock(content="Hello! How can I help?")]

    # ainvoke returns state dict with messages
    graph.ainvoke = AsyncMock(return_value={"messages": messages})

    # aget_state returns a snapshot
    state = MagicMock()
    state.next = next_tasks  # truthy = interrupted
    state.tasks = []
    graph.aget_state = AsyncMock(return_value=state)
    return graph


# ---------------------------------------------------------------------------
# Test: AsyncPostgresSaver wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_session_uses_async_postgres_saver():
    """AsyncPostgresSaver.from_conn_string called with database_url_psycopg (Pitfall 4)."""
    settings = make_settings()

    checkpointer_cm = AsyncMock()
    checkpointer_instance = AsyncMock()
    checkpointer_instance.setup = AsyncMock()
    checkpointer_cm.__aenter__ = AsyncMock(return_value=checkpointer_instance)
    checkpointer_cm.__aexit__ = AsyncMock(return_value=None)

    turn_manager = make_turn_manager(utterances=["exit"])
    graph = make_graph()

    with (
        patch("daily.voice.loop.Settings", return_value=settings),
        patch("daily.voice.loop._resolve_email_adapters", new=AsyncMock(return_value=[])),
        patch("daily.voice.loop.set_email_adapters"),
        patch("daily.voice.loop.AsyncPostgresSaver") as mock_saver_cls,
        patch("daily.voice.loop.build_graph", return_value=graph),
        patch("daily.voice.loop.create_session_config", new=AsyncMock(return_value={"configurable": {"thread_id": "user-1-2026-04-13"}})),
        patch("daily.voice.loop.Redis") as mock_redis_cls,
        patch("daily.voice.loop.async_session") as mock_async_session,
        patch("daily.voice.loop.initialize_session_state", new=AsyncMock(return_value={"briefing_narrative": "", "email_context": []})),
        patch("daily.voice.loop.TTSPipeline"),
        patch("daily.voice.loop.STTPipeline"),
        patch("daily.voice.loop.VoiceTurnManager", return_value=turn_manager),
    ):
        mock_saver_cls.from_conn_string.return_value = checkpointer_cm
        mock_redis_cls.from_url.return_value = AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(), aclose=AsyncMock())
        mock_async_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_async_session.return_value.__aexit__ = AsyncMock(return_value=None)

        from daily.voice.loop import run_voice_session
        await run_voice_session(user_id=1)

    # Verify psycopg URL (NOT asyncpg URL) was used
    mock_saver_cls.from_conn_string.assert_called_once_with(
        settings.database_url_psycopg
    )
    assert "asyncpg" not in settings.database_url_psycopg, (
        "database_url_psycopg must NOT contain asyncpg driver (Pitfall 4)"
    )

    # Verify setup() was awaited (idempotent checkpointer init)
    checkpointer_instance.setup.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: Briefing spoken on first turn
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_briefing_spoken_on_first_turn():
    """Briefing narrative is spoken via TTS on first turn when cache hit occurs."""
    briefing_text = "Good morning. Here are three things that matter today."
    settings = make_settings()

    checkpointer_cm = AsyncMock()
    checkpointer_instance = AsyncMock()
    checkpointer_instance.setup = AsyncMock()
    checkpointer_cm.__aenter__ = AsyncMock(return_value=checkpointer_instance)
    checkpointer_cm.__aexit__ = AsyncMock(return_value=None)

    turn_manager = make_turn_manager(utterances=["exit"])
    graph = make_graph()

    with (
        patch("daily.voice.loop.Settings", return_value=settings),
        patch("daily.voice.loop._resolve_email_adapters", new=AsyncMock(return_value=[])),
        patch("daily.voice.loop.set_email_adapters"),
        patch("daily.voice.loop.AsyncPostgresSaver") as mock_saver_cls,
        patch("daily.voice.loop.build_graph", return_value=graph),
        patch("daily.voice.loop.create_session_config", new=AsyncMock(return_value={"configurable": {}})),
        patch("daily.voice.loop.Redis") as mock_redis_cls,
        patch("daily.voice.loop.async_session") as mock_async_session,
        patch(
            "daily.voice.loop.initialize_session_state",
            new=AsyncMock(return_value={"briefing_narrative": briefing_text, "email_context": []}),
        ),
        patch("daily.voice.loop.TTSPipeline"),
        patch("daily.voice.loop.STTPipeline"),
        patch("daily.voice.loop.VoiceTurnManager", return_value=turn_manager),
    ):
        mock_saver_cls.from_conn_string.return_value = checkpointer_cm
        mock_redis_cls.from_url.return_value = AsyncMock(aclose=AsyncMock())
        mock_async_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_async_session.return_value.__aexit__ = AsyncMock(return_value=None)

        from daily.voice.loop import run_voice_session
        await run_voice_session(user_id=1)

    # speak() must have been called at least once with the briefing text
    call_args = [call.args[0] for call in turn_manager.speak.call_args_list]
    assert briefing_text in call_args, (
        f"Expected briefing spoken on first turn. speak() calls: {call_args}"
    )


# ---------------------------------------------------------------------------
# Test: exit utterance ends session cleanly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_utterance_ends_session():
    """Utterance 'exit' ends the voice loop; turn_manager.stop() is called."""
    settings = make_settings()

    checkpointer_cm = AsyncMock()
    checkpointer_instance = AsyncMock()
    checkpointer_instance.setup = AsyncMock()
    checkpointer_cm.__aenter__ = AsyncMock(return_value=checkpointer_instance)
    checkpointer_cm.__aexit__ = AsyncMock(return_value=None)

    turn_manager = make_turn_manager(utterances=["exit"])
    graph = make_graph()

    with (
        patch("daily.voice.loop.Settings", return_value=settings),
        patch("daily.voice.loop._resolve_email_adapters", new=AsyncMock(return_value=[])),
        patch("daily.voice.loop.set_email_adapters"),
        patch("daily.voice.loop.AsyncPostgresSaver") as mock_saver_cls,
        patch("daily.voice.loop.build_graph", return_value=graph),
        patch("daily.voice.loop.create_session_config", new=AsyncMock(return_value={"configurable": {}})),
        patch("daily.voice.loop.Redis") as mock_redis_cls,
        patch("daily.voice.loop.async_session") as mock_async_session,
        patch(
            "daily.voice.loop.initialize_session_state",
            new=AsyncMock(return_value={"briefing_narrative": "", "email_context": []}),
        ),
        patch("daily.voice.loop.TTSPipeline"),
        patch("daily.voice.loop.STTPipeline"),
        patch("daily.voice.loop.VoiceTurnManager", return_value=turn_manager),
    ):
        mock_saver_cls.from_conn_string.return_value = checkpointer_cm
        mock_redis_cls.from_url.return_value = AsyncMock(aclose=AsyncMock())
        mock_async_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_async_session.return_value.__aexit__ = AsyncMock(return_value=None)

        from daily.voice.loop import run_voice_session
        await run_voice_session(user_id=1)

    # stop() must be called in finally block (clean shutdown)
    turn_manager.stop.assert_awaited_once()
    # run_session should NOT have been called (exit before any user turn)
    graph.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# Test: approval flow by voice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_flow_by_voice():
    """Voice approval: graph interrupt -> speak draft -> listen -> 'confirm' -> graph.ainvoke(Command)."""
    settings = make_settings()

    checkpointer_cm = AsyncMock()
    checkpointer_instance = AsyncMock()
    checkpointer_instance.setup = AsyncMock()
    checkpointer_cm.__aenter__ = AsyncMock(return_value=checkpointer_instance)
    checkpointer_cm.__aexit__ = AsyncMock(return_value=None)

    # Utterances: first ask a question, then say "confirm", then "exit"
    turn_manager = make_turn_manager(utterances=["draft a reply to Bob", "confirm", "exit"])

    # Graph: first call triggers interrupt, second call (ainvoke Command) completes
    interrupt_task = MagicMock()
    interrupt_task.interrupts = [MagicMock(value={"preview": "Hi Bob, here is my reply.", "action_type": "send_email"})]

    interrupted_state = MagicMock()
    interrupted_state.next = ("approval",)  # truthy — interrupted
    interrupted_state.tasks = [interrupt_task]

    resolved_state = MagicMock()
    resolved_state.next = None  # falsy — not interrupted
    resolved_state.tasks = []

    graph = AsyncMock()
    # run_session (first ainvoke) returns normal result
    graph.ainvoke = AsyncMock(side_effect=[
        {"messages": [MagicMock(content="Drafting reply...")]},  # run_session call
        {"messages": [MagicMock(content="Email sent!")]},        # Command(resume="confirm")
    ])
    # aget_state: first call returns interrupted, second returns resolved
    graph.aget_state = AsyncMock(side_effect=[interrupted_state, resolved_state])

    with (
        patch("daily.voice.loop.Settings", return_value=settings),
        patch("daily.voice.loop._resolve_email_adapters", new=AsyncMock(return_value=[])),
        patch("daily.voice.loop.set_email_adapters"),
        patch("daily.voice.loop.AsyncPostgresSaver") as mock_saver_cls,
        patch("daily.voice.loop.build_graph", return_value=graph),
        patch("daily.voice.loop.create_session_config", new=AsyncMock(return_value={"configurable": {"thread_id": "t1"}})),
        patch("daily.voice.loop.Redis") as mock_redis_cls,
        patch("daily.voice.loop.async_session") as mock_async_session,
        patch(
            "daily.voice.loop.initialize_session_state",
            new=AsyncMock(return_value={"briefing_narrative": "", "email_context": []}),
        ),
        patch("daily.voice.loop.TTSPipeline"),
        patch("daily.voice.loop.STTPipeline"),
        patch("daily.voice.loop.VoiceTurnManager", return_value=turn_manager),
    ):
        mock_saver_cls.from_conn_string.return_value = checkpointer_cm
        mock_redis_cls.from_url.return_value = AsyncMock(aclose=AsyncMock())
        mock_async_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_async_session.return_value.__aexit__ = AsyncMock(return_value=None)

        from daily.voice.loop import run_voice_session
        await run_voice_session(user_id=1)

    # Verify graph.ainvoke was called twice (run_session + Command(resume=...))
    assert graph.ainvoke.call_count == 2

    # Verify the second ainvoke was called with Command(resume="confirm")
    from langgraph.types import Command
    second_call_args = graph.ainvoke.call_args_list[1]
    command_arg = second_call_args.args[0] if second_call_args.args else second_call_args.kwargs.get("input")
    assert isinstance(command_arg, Command)
    assert command_arg.resume == "confirm"


# ---------------------------------------------------------------------------
# Test: voice command registered in CLI app
# ---------------------------------------------------------------------------

def test_voice_command_registered():
    """'voice' is a registered command in the CLI app."""
    from daily.cli import app

    # Typer commands are registered in app.registered_commands or similar
    command_names = [cmd.name or cmd.callback.__name__ for cmd in app.registered_commands]
    assert "voice" in command_names, (
        f"'voice' command not found in CLI. Registered commands: {command_names}"
    )
