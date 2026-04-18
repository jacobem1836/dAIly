"""Tests for Phase 11: Trusted Actions — autonomy levels and approval gate bypass.

Covers all four success criteria:
  1. Auto-execution bypass for trusted action types
  2. Blocked types (compose_email) never auto-execute
  3. Approve level (default) behaves identically to v1.0
  4. Config command validation and persistence
"""
from unittest.mock import patch

import pytest

from daily.actions.base import (
    BLOCKED_ACTION_TYPES,
    CONFIGURABLE_ACTION_TYPES,
    ActionDraft,
    ActionType,
)
from daily.orchestrator.state import SessionState
from daily.profile.models import UserPreferences


# ---------------------------------------------------------------------------
# Autonomy constants tests
# ---------------------------------------------------------------------------


class TestAutonomyConstants:
    def test_blocked_types_contains_compose_email(self):
        assert ActionType.compose_email in BLOCKED_ACTION_TYPES

    def test_blocked_types_is_frozenset(self):
        assert isinstance(BLOCKED_ACTION_TYPES, frozenset)

    def test_configurable_types_has_four_entries(self):
        expected = {
            ActionType.draft_email,
            ActionType.draft_message,
            ActionType.schedule_event,
            ActionType.reschedule_event,
        }
        assert CONFIGURABLE_ACTION_TYPES == expected

    def test_no_overlap_blocked_and_configurable(self):
        assert BLOCKED_ACTION_TYPES.isdisjoint(CONFIGURABLE_ACTION_TYPES)


# ---------------------------------------------------------------------------
# UserPreferences tests
# ---------------------------------------------------------------------------


class TestUserPreferencesAutonomy:
    def test_defaults_to_empty_dict(self):
        prefs = UserPreferences()
        assert prefs.autonomy_levels == {}

    def test_accepts_valid_autonomy_levels(self):
        prefs = UserPreferences.model_validate(
            {"autonomy_levels": {"draft_email": "auto", "schedule_event": "approve"}}
        )
        assert prefs.autonomy_levels["draft_email"] == "auto"
        assert prefs.autonomy_levels["schedule_event"] == "approve"


# ---------------------------------------------------------------------------
# approval_node bypass tests
# ---------------------------------------------------------------------------


class TestApprovalNodeAutonomy:
    def _make_state(
        self, action_type: ActionType, autonomy_levels: dict | None = None
    ) -> SessionState:
        draft = ActionDraft(
            action_type=action_type,
            body="Test body",
            recipient="test@example.com" if "email" in action_type.value else None,
            subject="Test" if "email" in action_type.value else None,
        )
        prefs = {"autonomy_levels": autonomy_levels} if autonomy_levels else {}
        return SessionState(
            pending_action=draft,
            preferences=prefs,
            active_user_id=1,
        )

    @pytest.mark.asyncio
    async def test_auto_bypasses_interrupt_for_draft_email(self):
        """SC-1: autonomy=auto for draft_email skips interrupt."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.draft_email, {"draft_email": "auto"})
        result = await approval_node(state)
        assert result["approval_decision"] == "confirm"
        assert result["auto_executed"] is True

    @pytest.mark.asyncio
    async def test_auto_bypasses_interrupt_for_schedule_event(self):
        """SC-1: autonomy=auto for schedule_event skips interrupt."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.schedule_event, {"schedule_event": "auto"})
        result = await approval_node(state)
        assert result["approval_decision"] == "confirm"
        assert result["auto_executed"] is True

    @pytest.mark.asyncio
    async def test_blocked_type_always_interrupts_even_with_auto(self):
        """SC-2: compose_email ALWAYS interrupts regardless of autonomy."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.compose_email, {"compose_email": "auto"})
        with patch(
            "daily.orchestrator.nodes.interrupt", side_effect=Exception("interrupted")
        ) as mock_interrupt:
            with pytest.raises(Exception, match="interrupted"):
                await approval_node(state)
            mock_interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_level_calls_interrupt(self):
        """SC-3: approve level triggers interrupt (identical to v1.0)."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.draft_email, {"draft_email": "approve"})
        with patch(
            "daily.orchestrator.nodes.interrupt", return_value="confirm"
        ) as mock_interrupt:
            result = await approval_node(state)
            mock_interrupt.assert_called_once()
            assert result["approval_decision"] == "confirm"

    @pytest.mark.asyncio
    async def test_missing_autonomy_calls_interrupt(self):
        """SC-3: missing autonomy_levels (default) triggers interrupt."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.draft_email)
        with patch(
            "daily.orchestrator.nodes.interrupt", return_value="confirm"
        ) as mock_interrupt:
            await approval_node(state)
            mock_interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_suggest_level_calls_interrupt(self):
        """D-09: suggest treated as approve in Phase 11."""
        from daily.orchestrator.nodes import approval_node

        state = self._make_state(ActionType.draft_email, {"draft_email": "suggest"})
        with patch(
            "daily.orchestrator.nodes.interrupt", return_value="confirm"
        ) as mock_interrupt:
            result = await approval_node(state)
            mock_interrupt.assert_called_once()


# ---------------------------------------------------------------------------
# CLI validation tests (unit-level, no DB)
# ---------------------------------------------------------------------------


class TestCliAutonomyValidation:
    @pytest.mark.asyncio
    async def test_rejects_blocked_action_type(self):
        """Blocked action types (compose_email) cannot be set to any autonomy level."""
        from daily.cli import _upsert_autonomy

        # Validation occurs before DB — no session mock needed
        result = await _upsert_autonomy(
            user_id=1, action_type="compose_email", level="auto"
        )
        assert "always requires approval" in result

    @pytest.mark.asyncio
    async def test_rejects_invalid_level(self):
        """Invalid autonomy level strings are rejected with clear error."""
        from daily.cli import _upsert_autonomy

        result = await _upsert_autonomy(
            user_id=1, action_type="draft_email", level="yolo"
        )
        assert "Invalid autonomy level" in result
        assert "yolo" in result

    @pytest.mark.asyncio
    async def test_rejects_unknown_action_type(self):
        """Unrecognised action type strings are rejected with clear error."""
        from daily.cli import _upsert_autonomy

        result = await _upsert_autonomy(
            user_id=1, action_type="fly_plane", level="auto"
        )
        assert "Unknown action type" in result
        assert "fly_plane" in result
