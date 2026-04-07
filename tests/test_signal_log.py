"""Tests for signal log data layer, orchestrator state, and intent models.

Covers:
  - SignalType enum values (D-07)
  - SignalLog ORM structure
  - append_signal service (D-08 fire-and-forget pattern)
  - SessionState Pydantic model (D-09)
  - OrchestratorIntent validation (D-03/SEC-05)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# SignalType enum tests
# ---------------------------------------------------------------------------


def test_signal_type_enum_values():
    """SignalType enum contains exactly the required values."""
    from daily.profile.signals import SignalType

    values = {m.value for m in SignalType}
    assert values == {"skip", "correction", "re_request", "follow_up", "expand"}


def test_signal_type_skip():
    from daily.profile.signals import SignalType

    assert SignalType.skip == "skip"


def test_signal_type_correction():
    from daily.profile.signals import SignalType

    assert SignalType.correction == "correction"


def test_signal_type_re_request():
    from daily.profile.signals import SignalType

    assert SignalType.re_request == "re_request"


def test_signal_type_follow_up():
    from daily.profile.signals import SignalType

    assert SignalType.follow_up == "follow_up"


def test_signal_type_expand():
    from daily.profile.signals import SignalType

    assert SignalType.expand == "expand"


# ---------------------------------------------------------------------------
# SignalLog ORM structural tests (no DB required)
# ---------------------------------------------------------------------------


def test_signal_log_tablename():
    from daily.profile.signals import SignalLog

    assert SignalLog.__tablename__ == "signal_log"


def test_signal_log_has_required_columns():
    from daily.profile.signals import SignalLog

    columns = {c.name for c in SignalLog.__table__.columns}
    assert "id" in columns
    assert "user_id" in columns
    assert "signal_type" in columns
    assert "target_id" in columns
    assert "metadata_json" in columns
    assert "created_at" in columns


# ---------------------------------------------------------------------------
# append_signal service tests (mocked session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_signal_skip_creates_row():
    """append_signal with SignalType.skip adds a row and commits."""
    from daily.profile.signals import SignalType, append_signal

    mock_session = AsyncMock(spec=AsyncSession)

    await append_signal(
        user_id=1,
        signal_type=SignalType.skip,
        session=mock_session,
        target_id="msg-123",
    )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

    # Check the row that was added
    added_row = mock_session.add.call_args[0][0]
    assert added_row.user_id == 1
    assert added_row.signal_type == "skip"
    assert added_row.target_id == "msg-123"


@pytest.mark.asyncio
async def test_append_signal_follow_up_creates_row():
    """append_signal with SignalType.follow_up works."""
    from daily.profile.signals import SignalType, append_signal

    mock_session = AsyncMock(spec=AsyncSession)

    await append_signal(
        user_id=2,
        signal_type=SignalType.follow_up,
        session=mock_session,
    )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

    added_row = mock_session.add.call_args[0][0]
    assert added_row.user_id == 2
    assert added_row.signal_type == "follow_up"
    assert added_row.target_id is None


@pytest.mark.asyncio
async def test_append_signal_with_metadata():
    """append_signal stores optional metadata dict."""
    from daily.profile.signals import SignalType, append_signal

    mock_session = AsyncMock(spec=AsyncSession)
    meta = {"reason": "too long", "section": "email"}

    await append_signal(
        user_id=1,
        signal_type=SignalType.correction,
        session=mock_session,
        metadata=meta,
    )

    added_row = mock_session.add.call_args[0][0]
    assert added_row.metadata_json == meta


# ---------------------------------------------------------------------------
# OrchestratorIntent tests (SEC-05 — whitelist validation)
# ---------------------------------------------------------------------------


def test_orchestrator_intent_valid_actions():
    """OrchestratorIntent accepts all four valid actions."""
    from daily.orchestrator.models import OrchestratorIntent

    for action in ("answer", "summarise_thread", "skip", "clarify"):
        intent = OrchestratorIntent(action=action, narrative="test narrative")
        assert intent.action == action


def test_orchestrator_intent_rejects_execute_code():
    """OrchestratorIntent rejects arbitrary actions not in the whitelist (SEC-05)."""
    from daily.orchestrator.models import OrchestratorIntent

    with pytest.raises(ValidationError):
        OrchestratorIntent(action="execute_code", narrative="malicious")


def test_orchestrator_intent_rejects_send():
    """OrchestratorIntent rejects 'send' action."""
    from daily.orchestrator.models import OrchestratorIntent

    with pytest.raises(ValidationError):
        OrchestratorIntent(action="send", narrative="send email")


def test_orchestrator_intent_rejects_call():
    """OrchestratorIntent rejects 'call' action."""
    from daily.orchestrator.models import OrchestratorIntent

    with pytest.raises(ValidationError):
        OrchestratorIntent(action="call", narrative="call api")


def test_orchestrator_intent_target_id_optional():
    """OrchestratorIntent.target_id is optional."""
    from daily.orchestrator.models import OrchestratorIntent

    intent = OrchestratorIntent(action="answer", narrative="here is the answer")
    assert intent.target_id is None

    intent_with_target = OrchestratorIntent(
        action="summarise_thread", narrative="summary", target_id="thread-456"
    )
    assert intent_with_target.target_id == "thread-456"


# ---------------------------------------------------------------------------
# SessionState tests
# ---------------------------------------------------------------------------


def test_session_state_has_required_fields():
    """SessionState has all required fields with correct defaults."""
    from daily.orchestrator.state import SessionState

    state = SessionState()
    assert state.messages == []
    assert state.briefing_narrative == ""
    assert state.active_user_id == 0
    assert state.preferences == {}


def test_session_state_messages_field_uses_add_messages():
    """SessionState.messages is annotated with add_messages for LangGraph."""
    import typing

    from daily.orchestrator.state import SessionState

    # Verify the annotation on messages field includes add_messages
    hints = typing.get_type_hints(SessionState, include_extras=True)
    assert "messages" in hints
    # Annotated type should be present
    messages_hint = hints["messages"]
    assert hasattr(messages_hint, "__metadata__"), (
        "messages field should be Annotated[list, add_messages]"
    )


def test_session_state_active_user_id_field():
    """SessionState.active_user_id can be set."""
    from daily.orchestrator.state import SessionState

    state = SessionState(active_user_id=42)
    assert state.active_user_id == 42


def test_session_state_preferences_field():
    """SessionState.preferences accepts a dict."""
    from daily.orchestrator.state import SessionState

    state = SessionState(preferences={"tone": "casual"})
    assert state.preferences == {"tone": "casual"}


def test_session_state_briefing_narrative_field():
    """SessionState.briefing_narrative can be set."""
    from daily.orchestrator.state import SessionState

    state = SessionState(briefing_narrative="Good morning, you have 3 emails.")
    assert state.briefing_narrative == "Good morning, you have 3 emails."
