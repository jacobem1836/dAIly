"""Tests for daily.worker.llm_bridge — DailyLLMBridge.

RED phase: written before the implementation exists.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_gen(*items):
    """Yield items as an async generator."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streams_tokens():
    """stream_response yields token strings from astream_session."""
    from daily.worker.llm_bridge import DailyLLMBridge

    async def fake_astream(graph, user_input, config, initial_state=None):
        for tok in ["Hello", " ", "world"]:
            yield tok

    graph = MagicMock()
    config = {"configurable": {"thread_id": "user-1-2026-04-30"}}
    initial_state = {"briefing_narrative": "Morning", "active_user_id": 1}

    bridge = DailyLLMBridge(graph=graph, config=config, initial_state=initial_state)

    with patch("daily.worker.llm_bridge.astream_session", side_effect=fake_astream):
        tokens = []
        async for tok in bridge.stream_response("what's first?"):
            tokens.append(tok)

    assert tokens == ["Hello", " ", "world"]


@pytest.mark.asyncio
async def test_fallback_on_streaming_not_supported():
    """When astream_session raises StreamingNotSupported, falls back to run_session."""
    from daily.worker.llm_bridge import DailyLLMBridge
    from daily.orchestrator.session import StreamingNotSupported

    async def fake_astream_raises(graph, user_input, config, initial_state=None):
        raise StreamingNotSupported("non-respond intent")
        yield  # make it a generator

    fake_result = {"messages": [SimpleNamespace(content="fallback content")]}

    graph = MagicMock()
    # stream_response awaits graph.aget_state() after the run_session fallback
    # to check whether the graph paused at an approval interrupt. A plain
    # MagicMock attribute is not awaitable, so it must be an AsyncMock; return
    # a state with next=() (falsy) so the "not paused" branch runs and the
    # fallback content is yielded, matching this test's intent.
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(next=(), tasks=[]))
    config = {"configurable": {"thread_id": "user-1-2026-04-30"}}
    initial_state = {}

    bridge = DailyLLMBridge(graph=graph, config=config, initial_state=initial_state)

    with (
        patch("daily.worker.llm_bridge.astream_session", side_effect=fake_astream_raises),
        patch("daily.worker.llm_bridge.run_session", AsyncMock(return_value=fake_result)),
    ):
        tokens = []
        async for tok in bridge.stream_response("draft an email"):
            tokens.append(tok)

    assert tokens == ["fallback content"]


@pytest.mark.asyncio
async def test_initial_state_only_on_first_turn():
    """Full initial_state is passed on the first call; only the briefing
    narrative is carried forward on subsequent calls.

    Per commit b591174 ("fix: resolve 4 live-session bugs ... briefing
    context"), passing None on follow-up turns caused astream_session to
    fall back to "(no briefing loaded)" and lose context for questions like
    "tell me more about those emails". DailyLLMBridge now stores
    _briefing_narrative at construction and re-injects it (and only it) as
    stream_init on every non-first turn — this is intentional, not a leak
    of the full initial_state.
    """
    from daily.worker.llm_bridge import DailyLLMBridge

    captured_states = []

    async def fake_astream(graph, user_input, config, initial_state=None):
        captured_states.append(initial_state)
        yield "token"

    graph = MagicMock()
    config = {"configurable": {"thread_id": "user-1-2026-04-30"}}
    initial_state = {"briefing_narrative": "Morning", "active_user_id": 1}

    bridge = DailyLLMBridge(graph=graph, config=config, initial_state=initial_state)

    with patch("daily.worker.llm_bridge.astream_session", side_effect=fake_astream):
        # First call
        async for _ in bridge.stream_response("first question"):
            pass
        # Second call
        async for _ in bridge.stream_response("second question"):
            pass

    assert len(captured_states) == 2
    assert captured_states[0] == initial_state, "first turn should pass full initial_state"
    assert captured_states[1] == {"briefing_narrative": "Morning"}, (
        "second turn should carry forward only the briefing narrative, not the full initial_state"
    )
