"""Edge-case tests for voice/loop.py uncovered branches.

Targets:
  91  – _handle_voice_approval: empty utterance defaults to 'reject'
  99  – _handle_voice_approval: edit: prefix sets edit_instruction in output
  133-134 – run_voice_session: missing deepgram_api_key prints error and returns
  137-138 – run_voice_session: missing cartesia_api_key prints error and returns
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Line 91: _handle_voice_approval empty utterance → reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_voice_approval_empty_utterance_rejects() -> None:
    """When wait_for_utterance returns empty string, decision defaults to 'reject' (line 91)."""
    from daily.voice.loop import _handle_voice_approval

    turn_manager = AsyncMock()
    turn_manager.speak = AsyncMock()
    turn_manager.wait_for_utterance = AsyncMock(return_value="")  # empty → reject

    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"messages": []})

    graph_state = MagicMock()
    graph_state.tasks = []

    result = await _handle_voice_approval(
        turn_manager=turn_manager,
        graph=graph,
        graph_state=graph_state,
        config={"configurable": {"thread_id": "test"}},
    )

    # ainvoke must be called with Command(resume="reject")
    call_args = graph.ainvoke.call_args
    command = call_args[0][0]
    assert command.resume == "reject"
    assert "edit_instruction" not in result


# ---------------------------------------------------------------------------
# Line 99: _handle_voice_approval edit: prefix sets edit_instruction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_voice_approval_edit_sets_edit_instruction() -> None:
    """When user says something other than confirm/reject, edit_instruction is set (line 99)."""
    from daily.voice.loop import _handle_voice_approval

    turn_manager = AsyncMock()
    turn_manager.speak = AsyncMock()
    turn_manager.wait_for_utterance = AsyncMock(return_value="make it shorter")

    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"messages": []})

    graph_state = MagicMock()
    graph_state.tasks = []

    result = await _handle_voice_approval(
        turn_manager=turn_manager,
        graph=graph,
        graph_state=graph_state,
        config={"configurable": {"thread_id": "test"}},
    )

    # decision is "edit:make it shorter", so edit_instruction should be set
    assert "edit_instruction" in result
    assert result["edit_instruction"] == "make it shorter"


# ---------------------------------------------------------------------------
# Lines 133-134: run_voice_session missing deepgram_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_voice_session_missing_deepgram_key_returns_early(capsys) -> None:
    """run_voice_session prints error and returns when deepgram_api_key is missing (lines 133-134)."""
    from daily.voice.loop import run_voice_session

    mock_settings = MagicMock()
    mock_settings.deepgram_api_key = ""  # falsy → early return

    with patch("daily.voice.loop.Settings", return_value=mock_settings):
        # Should return without raising or attempting DB/TTS/STT connections
        await run_voice_session(user_id=1)

    captured = capsys.readouterr()
    assert "DEEPGRAM_API_KEY" in captured.out


# ---------------------------------------------------------------------------
# Lines 137-138: run_voice_session missing cartesia_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_voice_session_missing_cartesia_key_returns_early(capsys) -> None:
    """run_voice_session prints error and returns when cartesia_api_key is missing (lines 137-138)."""
    from daily.voice.loop import run_voice_session

    mock_settings = MagicMock()
    mock_settings.deepgram_api_key = "valid-deepgram-key"
    mock_settings.cartesia_api_key = ""  # falsy → early return

    with patch("daily.voice.loop.Settings", return_value=mock_settings):
        await run_voice_session(user_id=1)

    captured = capsys.readouterr()
    assert "CARTESIA_API_KEY" in captured.out
