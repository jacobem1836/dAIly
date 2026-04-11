"""Tests for action layer: ActionDraft, ActionResult, ActionExecutor ABC, ActionLog ORM,
whitelist, OrchestratorIntent extension, SessionState extension, UserPreferences extension.

TDD RED phase — tests must fail until implementation is complete.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


class TestActionDraftModel:
    """Tests for ActionDraft Pydantic model."""

    def test_action_draft_validates_action_type(self):
        """ActionDraft validates action_type against ActionType enum."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(action_type=ActionType.draft_email, body="Hello world")
        assert draft.action_type == ActionType.draft_email

    def test_action_draft_rejects_invalid_action_type(self):
        """ActionDraft rejects strings not in ActionType enum."""
        from daily.actions.base import ActionDraft

        with pytest.raises(ValidationError):
            ActionDraft(action_type="send_and_delete", body="Hello")

    def test_action_draft_all_enum_values_valid(self):
        """All ActionType enum values are accepted by ActionDraft."""
        from daily.actions.base import ActionDraft, ActionType

        for at in ActionType:
            draft = ActionDraft(action_type=at, body="test body")
            assert draft.action_type == at

    def test_action_draft_optional_fields_default_none(self):
        """ActionDraft optional fields default to None."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(action_type=ActionType.draft_email, body="test")
        assert draft.recipient is None
        assert draft.subject is None
        assert draft.thread_id is None
        assert draft.channel_id is None
        assert draft.event_id is None

    def test_action_draft_attendees_defaults_to_empty_list(self):
        """ActionDraft attendees defaults to empty list."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(action_type=ActionType.schedule_event, body="meeting")
        assert draft.attendees == []

    def test_action_draft_card_text_email(self):
        """ActionDraft.card_text() returns formatted email display for draft_email."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(
            action_type=ActionType.draft_email,
            recipient="bob@example.com",
            subject="Hello",
            body="Hi Bob, how are you?",
        )
        text = draft.card_text()
        assert "bob@example.com" in text
        assert "Hello" in text
        assert "Hi Bob" in text

    def test_action_draft_card_text_message(self):
        """ActionDraft.card_text() returns formatted message display for draft_message."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(
            action_type=ActionType.draft_message,
            channel_id="C01GENERAL",
            thread_id="1234567890.000001",
            body="Hey team!",
        )
        text = draft.card_text()
        assert "C01GENERAL" in text
        assert "Hey team!" in text

    def test_action_draft_card_text_calendar(self):
        """ActionDraft.card_text() returns event display for schedule_event."""
        from daily.actions.base import ActionDraft, ActionType

        draft = ActionDraft(
            action_type=ActionType.schedule_event,
            event_title="Team Sync",
            start_dt=datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
            end_dt=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
            attendees=["alice@example.com"],
            body="Quarterly sync",
        )
        text = draft.card_text()
        assert "Team Sync" in text
        assert "alice@example.com" in text

    def test_action_draft_body_truncated_in_card_text(self):
        """card_text() shows at most 500 chars of body."""
        from daily.actions.base import ActionDraft, ActionType

        long_body = "x" * 1000
        draft = ActionDraft(
            action_type=ActionType.draft_email,
            recipient="alice@example.com",
            body=long_body,
        )
        text = draft.card_text()
        # Body section should not exceed 500 chars
        assert "x" * 501 not in text


class TestActionResultModel:
    """Tests for ActionResult Pydantic model."""

    def test_action_result_success_true(self):
        """ActionResult stores success bool."""
        from daily.actions.base import ActionResult

        result = ActionResult(success=True, external_id="msg-001")
        assert result.success is True
        assert result.external_id == "msg-001"
        assert result.error is None

    def test_action_result_success_false_with_error(self):
        """ActionResult stores failure with error message."""
        from daily.actions.base import ActionResult

        result = ActionResult(success=False, error="API error 500")
        assert result.success is False
        assert result.error == "API error 500"
        assert result.external_id is None

    def test_action_result_summary_success(self):
        """ActionResult.summary property returns sent message for success."""
        from daily.actions.base import ActionResult

        result = ActionResult(success=True, external_id="msg-abc")
        assert "msg-abc" in result.summary
        assert "Sent" in result.summary or "sent" in result.summary.lower()

    def test_action_result_summary_failure(self):
        """ActionResult.summary property returns failed message for failure."""
        from daily.actions.base import ActionResult

        result = ActionResult(success=False, error="Network timeout")
        assert "Failed" in result.summary or "failed" in result.summary.lower()
        assert "Network timeout" in result.summary


class TestActionExecutorABC:
    """Tests for ActionExecutor abstract base class."""

    def test_action_executor_cannot_be_instantiated(self):
        """ActionExecutor is abstract and cannot be instantiated directly."""
        from daily.actions.base import ActionExecutor

        with pytest.raises(TypeError):
            ActionExecutor()  # type: ignore

    def test_action_executor_subclass_must_implement_validate(self):
        """ActionExecutor subclass without validate() cannot be instantiated."""
        from daily.actions.base import ActionDraft, ActionExecutor, ActionResult

        class PartialExecutor(ActionExecutor):
            async def execute(self, draft: ActionDraft) -> ActionResult:
                return ActionResult(success=True)

        with pytest.raises(TypeError):
            PartialExecutor()

    def test_action_executor_subclass_must_implement_execute(self):
        """ActionExecutor subclass without execute() cannot be instantiated."""
        from daily.actions.base import ActionDraft, ActionExecutor

        class PartialExecutor(ActionExecutor):
            async def validate(self, draft: ActionDraft) -> None:
                pass

        with pytest.raises(TypeError):
            PartialExecutor()

    def test_action_executor_concrete_subclass_is_instantiable(self):
        """A fully implemented ActionExecutor subclass can be instantiated."""
        from daily.actions.base import ActionDraft, ActionExecutor, ActionResult

        class ConcreteExecutor(ActionExecutor):
            async def validate(self, draft: ActionDraft) -> None:
                pass

            async def execute(self, draft: ActionDraft) -> ActionResult:
                return ActionResult(success=True)

        executor = ConcreteExecutor()
        assert executor is not None


class TestActionLogORM:
    """Tests for ActionLog ORM model."""

    def test_action_log_tablename(self):
        """ActionLog has __tablename__ == 'action_log'."""
        from daily.actions.models import ActionLog

        assert ActionLog.__tablename__ == "action_log"

    def test_action_log_has_required_columns(self):
        """ActionLog ORM has all required columns."""
        from daily.actions.models import ActionLog

        cols = {c.key for c in ActionLog.__table__.columns}
        required = {
            "id",
            "user_id",
            "action_type",
            "target",
            "content_summary",
            "body_hash",
            "approval_status",
            "outcome",
            "created_at",
        }
        assert required.issubset(cols)

    def test_approval_status_enum_values(self):
        """ApprovalStatus enum has pending, approved, rejected."""
        from daily.actions.models import ApprovalStatus

        assert ApprovalStatus.pending == "pending"
        assert ApprovalStatus.approved == "approved"
        assert ApprovalStatus.rejected == "rejected"

    def test_action_log_no_raw_body_column(self):
        """ActionLog does NOT have a 'body' or 'raw_body' column (SEC-04)."""
        from daily.actions.models import ActionLog

        cols = {c.key for c in ActionLog.__table__.columns}
        assert "body" not in cols
        assert "raw_body" not in cols


class TestWhitelist:
    """Tests for check_recipient_whitelist()."""

    def test_whitelist_passes_known_address(self):
        """check_recipient_whitelist() returns None for known address."""
        from daily.actions.whitelist import check_recipient_whitelist

        known = {"alice@example.com", "bob@example.com"}
        # Should not raise
        result = check_recipient_whitelist("alice@example.com", known)
        assert result is None

    def test_whitelist_raises_for_unknown_address(self):
        """check_recipient_whitelist() raises ValueError for unknown address."""
        from daily.actions.whitelist import check_recipient_whitelist

        known = {"alice@example.com"}
        with pytest.raises(ValueError, match="not in known contacts"):
            check_recipient_whitelist("unknown@evil.com", known)

    def test_whitelist_case_insensitive(self):
        """check_recipient_whitelist() is case-insensitive."""
        from daily.actions.whitelist import check_recipient_whitelist

        known = {"Alice@Example.COM"}
        # Should not raise
        check_recipient_whitelist("alice@example.com", known)

    def test_whitelist_empty_set_always_rejects(self):
        """check_recipient_whitelist() with empty known_addresses always raises."""
        from daily.actions.whitelist import check_recipient_whitelist

        with pytest.raises(ValueError):
            check_recipient_whitelist("anyone@example.com", set())


class TestOrchestratorIntentExtension:
    """Tests for OrchestratorIntent Phase 4 action type extension."""

    def test_orchestrator_intent_accepts_draft_email(self):
        """OrchestratorIntent accepts 'draft_email' action."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="draft_email", narrative="Draft a reply")
        assert intent.action == "draft_email"

    def test_orchestrator_intent_accepts_draft_message(self):
        """OrchestratorIntent accepts 'draft_message' action."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="draft_message", narrative="Draft Slack message")
        assert intent.action == "draft_message"

    def test_orchestrator_intent_accepts_schedule_event(self):
        """OrchestratorIntent accepts 'schedule_event' action."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="schedule_event", narrative="Schedule a meeting")
        assert intent.action == "schedule_event"

    def test_orchestrator_intent_accepts_reschedule_event(self):
        """OrchestratorIntent accepts 'reschedule_event' action."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="reschedule_event", narrative="Move the meeting")
        assert intent.action == "reschedule_event"

    def test_orchestrator_intent_accepts_compose_email(self):
        """OrchestratorIntent accepts 'compose_email' action."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="compose_email", narrative="Write a new email")
        assert intent.action == "compose_email"

    def test_orchestrator_intent_rejects_execute(self):
        """OrchestratorIntent rejects 'execute' with ValidationError (SEC-05)."""
        from daily.orchestrator.models import OrchestratorIntent

        with pytest.raises(ValidationError):
            OrchestratorIntent(action="execute", narrative="Execute something")

    def test_orchestrator_intent_rejects_send(self):
        """OrchestratorIntent rejects 'send' with ValidationError."""
        from daily.orchestrator.models import OrchestratorIntent

        with pytest.raises(ValidationError):
            OrchestratorIntent(action="send", narrative="Send it")

    def test_orchestrator_intent_rejects_delete(self):
        """OrchestratorIntent rejects 'delete' with ValidationError."""
        from daily.orchestrator.models import OrchestratorIntent

        with pytest.raises(ValidationError):
            OrchestratorIntent(action="delete", narrative="Delete it")

    def test_orchestrator_intent_existing_actions_still_valid(self):
        """Existing Phase 3 actions still valid after extension."""
        from daily.orchestrator.models import OrchestratorIntent

        for action in ["answer", "summarise_thread", "skip", "clarify"]:
            intent = OrchestratorIntent(action=action, narrative="test")
            assert intent.action == action

    def test_orchestrator_intent_has_draft_instruction_field(self):
        """OrchestratorIntent has optional draft_instruction field."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(
            action="draft_email",
            narrative="OK",
            draft_instruction="Reply thanking them for their time",
        )
        assert intent.draft_instruction == "Reply thanking them for their time"

    def test_orchestrator_intent_draft_instruction_defaults_none(self):
        """OrchestratorIntent.draft_instruction defaults to None."""
        from daily.orchestrator.models import OrchestratorIntent

        intent = OrchestratorIntent(action="answer", narrative="Here you go")
        assert intent.draft_instruction is None


class TestSessionStateExtension:
    """Tests for SessionState Phase 4 extensions."""

    def test_session_state_has_pending_action_field(self):
        """SessionState has pending_action field defaulting to None."""
        from daily.orchestrator.state import SessionState

        state = SessionState()
        assert state.pending_action is None

    def test_session_state_pending_action_accepts_action_draft(self):
        """SessionState.pending_action accepts an ActionDraft."""
        from daily.actions.base import ActionDraft, ActionType
        from daily.orchestrator.state import SessionState

        draft = ActionDraft(
            action_type=ActionType.draft_email,
            recipient="alice@example.com",
            body="Hello",
        )
        state = SessionState(pending_action=draft)
        assert state.pending_action is not None
        assert state.pending_action.recipient == "alice@example.com"

    def test_session_state_has_approval_decision_field(self):
        """SessionState has approval_decision field defaulting to None."""
        from daily.orchestrator.state import SessionState

        state = SessionState()
        assert state.approval_decision is None

    def test_session_state_approval_decision_accepts_string(self):
        """SessionState.approval_decision accepts 'confirm' or 'reject'."""
        from daily.orchestrator.state import SessionState

        state = SessionState(approval_decision="confirm")
        assert state.approval_decision == "confirm"


class TestUserPreferencesExtension:
    """Tests for UserPreferences Phase 4 extension."""

    def test_user_preferences_has_rejection_behaviour(self):
        """UserPreferences has rejection_behaviour field."""
        from daily.profile.models import UserPreferences

        prefs = UserPreferences()
        assert hasattr(prefs, "rejection_behaviour")

    def test_user_preferences_rejection_behaviour_defaults_ask_why(self):
        """UserPreferences.rejection_behaviour defaults to 'ask_why'."""
        from daily.profile.models import UserPreferences

        prefs = UserPreferences()
        assert prefs.rejection_behaviour == "ask_why"

    def test_user_preferences_rejection_behaviour_accepts_discard(self):
        """UserPreferences.rejection_behaviour accepts 'discard'."""
        from daily.profile.models import UserPreferences

        prefs = UserPreferences(rejection_behaviour="discard")
        assert prefs.rejection_behaviour == "discard"

    def test_user_preferences_rejection_behaviour_rejects_invalid(self):
        """UserPreferences.rejection_behaviour rejects invalid values."""
        from daily.profile.models import UserPreferences

        with pytest.raises(ValidationError):
            UserPreferences(rejection_behaviour="ignore_always")


class TestRequiredScopes:
    """Tests for REQUIRED_SCOPES dict in base.py."""

    def test_required_scopes_exists(self):
        """REQUIRED_SCOPES dict exists and is non-empty."""
        from daily.actions.base import REQUIRED_SCOPES

        assert len(REQUIRED_SCOPES) > 0

    def test_draft_email_has_google_scope(self):
        """draft_email action has Google gmail.send scope."""
        from daily.actions.base import REQUIRED_SCOPES, ActionType

        scopes = REQUIRED_SCOPES.get(ActionType.draft_email, {})
        assert "google" in scopes
        assert any("gmail" in s for s in scopes["google"])

    def test_draft_message_has_slack_scope(self):
        """draft_message action has Slack chat:write scope."""
        from daily.actions.base import REQUIRED_SCOPES, ActionType

        scopes = REQUIRED_SCOPES.get(ActionType.draft_message, {})
        assert "slack" in scopes
        assert "chat:write" in scopes["slack"]
