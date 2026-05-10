"""Edge-case tests for orchestrator/nodes.py uncovered branches.

Targets:
  156   - respond_node: message without .type attribute → role = "user" fallback
  260-262 - summarise_thread_node: exception path → fallback narrative
  301   - _capture_signal: exception swallowed
  327   - _infer_action_type: reschedule branch
  333   - _infer_action_type: slack/dm branch
  363   - _fetch_style_examples: empty emails list → ""
  373-375 - _fetch_style_examples: per-email exception continues
  410   - draft_node: edit: prefix from approval_decision
  417-419 - draft_node: reuse existing action_type on edit loop re-entry
  496-497 - draft_node: bad start_dt → None
  501-502 - draft_node: bad end_dt → None
  506   - draft_node: non-list attendees → []
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    messages=None,
    briefing_narrative="Test briefing",
    active_user_id=1,
    preferences=None,
    approval_decision=None,
    pending_action=None,
):
    from daily.orchestrator.state import SessionState

    return SessionState(
        messages=messages or [HumanMessage(content="What emails do I have?")],
        briefing_narrative=briefing_narrative,
        active_user_id=active_user_id,
        preferences=preferences or {"tone": "conversational", "briefing_length": "standard"},
        approval_decision=approval_decision,
        pending_action=pending_action,
    )


def _make_openai_response(action: str, narrative: str, target_id: str | None = None):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "action": action,
        "narrative": narrative,
        "target_id": target_id,
    })
    return mock_resp


# ---------------------------------------------------------------------------
# Line 156: respond_node message without .type attribute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_node_message_without_type_attribute() -> None:
    """respond_node handles messages with no .type attribute (role fallback to 'user')."""
    from daily.orchestrator.nodes import respond_node

    # Create a message object that has no .type attribute
    typeless_msg = MagicMock(spec=[])  # empty spec — no attributes
    typeless_msg.content = "Hello without type"

    state = _make_state(messages=[typeless_msg])
    mock_response = _make_openai_response("answer", "Response with typeless message.")

    with patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await respond_node(state)

    messages = result.get("messages", [])
    assert len(messages) == 1
    assert messages[0].content == "Response with typeless message."


# ---------------------------------------------------------------------------
# Lines 260-262: summarise_thread_node exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarise_thread_node_exception_returns_fallback() -> None:
    """summarise_thread_node returns fallback narrative when adapter/LLM fails (lines 260-262)."""
    from langchain_core.messages import AIMessage

    from daily.orchestrator.nodes import summarise_thread_node

    # Adapter that raises on get_email_body
    mock_adapter = AsyncMock()
    mock_adapter.get_email_body = AsyncMock(side_effect=RuntimeError("adapter down"))

    state = _make_state(messages=[HumanMessage(content="Summarise thread abc123")])

    with (
        patch("daily.orchestrator.nodes.get_email_adapters", return_value=[mock_adapter]),
        patch("daily.orchestrator.nodes.AsyncOpenAI") as mock_client_class,
    ):
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await summarise_thread_node(state)
        await asyncio.sleep(0)  # let any create_task settle

    messages = result.get("messages", [])
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)
    assert "trouble" in messages[0].content


# ---------------------------------------------------------------------------
# Line 301: _capture_signal exception swallowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_signal_exception_is_swallowed() -> None:
    """_capture_signal swallows DB errors without raising (line 301)."""
    from daily.orchestrator.nodes import _capture_signal
    from daily.profile.signals import SignalType

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db error"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("daily.db.engine.async_session", return_value=mock_ctx):
        # Should not raise — exception is swallowed
        await _capture_signal(user_id=1, signal_type=SignalType.expand, target_id="msg1")


# ---------------------------------------------------------------------------
# Lines 327, 333: _infer_action_type pure-function branches
# ---------------------------------------------------------------------------


def test_infer_action_type_reschedule() -> None:
    """_infer_action_type returns reschedule_event for reschedule keywords (line 327)."""
    from daily.orchestrator.nodes import _infer_action_type
    from daily.actions.base import ActionType

    result = _infer_action_type("Please reschedule my 3pm meeting")
    assert result == ActionType.reschedule_event


def test_infer_action_type_move_meeting() -> None:
    """_infer_action_type returns reschedule_event for 'move meeting' keyword."""
    from daily.orchestrator.nodes import _infer_action_type
    from daily.actions.base import ActionType

    result = _infer_action_type("Can you move meeting to Friday?")
    assert result == ActionType.reschedule_event


def test_infer_action_type_slack_message() -> None:
    """_infer_action_type returns draft_message for slack keywords (line 333)."""
    from daily.orchestrator.nodes import _infer_action_type
    from daily.actions.base import ActionType

    result = _infer_action_type("Send a slack message to the team")
    assert result == ActionType.draft_message


def test_infer_action_type_dm() -> None:
    """_infer_action_type returns draft_message for ' dm ' keyword."""
    from daily.orchestrator.nodes import _infer_action_type
    from daily.actions.base import ActionType

    result = _infer_action_type("Please dm John about the project")
    assert result == ActionType.draft_message
