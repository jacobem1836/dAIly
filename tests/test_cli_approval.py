"""Tests for CLI approval flow: card display, confirm/reject/edit interaction.

TDD RED phase — tests describe the expected behavior of the CLI approval flow
in `daily chat`. These tests should fail until the CLI is extended.

Covers:
- Card display renders structured format with DRAFT header
- confirm/yes/y/send/ok all map to decision="confirm"
- reject/no/n/cancel all map to decision="reject"
- Arbitrary text maps to decision="edit:{input}"
- Edit re-entry loop sends edit instruction as new user message
- Rejection with ask_why preference shows "Action cancelled" + allows re-entry
- Rejection with discard preference shows silent cancellation
"""

import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.actions.base import ActionDraft, ActionType


def _make_email_draft(
    recipient: str = "alice@example.com",
    subject: str = "Re: Project Update",
    body: str = "Hi Alice, I'm on it!",
) -> ActionDraft:
    return ActionDraft(
        action_type=ActionType.draft_email,
        recipient=recipient,
        subject=subject,
        body=body,
    )


def _make_schedule_draft() -> ActionDraft:
    return ActionDraft(
        action_type=ActionType.schedule_event,
        body="Meeting invitation",
        event_title="Team Sync",
    )


# ---------------------------------------------------------------------------
# Input parsing helpers (extracted from CLI logic)
# ---------------------------------------------------------------------------


def _parse_decision(user_input: str) -> str:
    """Parse user input into a decision string.

    This mirrors the parsing logic expected in cli.py.

    Returns:
        'confirm', 'reject', or 'edit:{input}'.
    """
    lowered = user_input.strip().lower()
    if lowered in ("confirm", "yes", "y", "send", "ok"):
        return "confirm"
    if lowered in ("reject", "no", "n", "cancel"):
        return "reject"
    return f"edit:{user_input.strip()}"


class TestDecisionParsing:
    """Tests that user input maps to correct decision strings."""

    def test_confirm_maps_to_confirm(self):
        assert _parse_decision("confirm") == "confirm"

    def test_yes_maps_to_confirm(self):
        assert _parse_decision("yes") == "confirm"

    def test_y_maps_to_confirm(self):
        assert _parse_decision("y") == "confirm"

    def test_send_maps_to_confirm(self):
        assert _parse_decision("send") == "confirm"

    def test_ok_maps_to_confirm(self):
        assert _parse_decision("ok") == "confirm"

    def test_confirm_case_insensitive(self):
        assert _parse_decision("CONFIRM") == "confirm"
        assert _parse_decision("Yes") == "confirm"
        assert _parse_decision("Y") == "confirm"

    def test_reject_maps_to_reject(self):
        assert _parse_decision("reject") == "reject"

    def test_no_maps_to_reject(self):
        assert _parse_decision("no") == "reject"

    def test_n_maps_to_reject(self):
        assert _parse_decision("n") == "reject"

    def test_cancel_maps_to_reject(self):
        assert _parse_decision("cancel") == "reject"

    def test_reject_case_insensitive(self):
        assert _parse_decision("REJECT") == "reject"
        assert _parse_decision("NO") == "reject"
        assert _parse_decision("Cancel") == "reject"

    def test_arbitrary_text_maps_to_edit(self):
        assert _parse_decision("make it shorter") == "edit:make it shorter"

    def test_another_edit_instruction(self):
        assert _parse_decision("use more formal language") == "edit:use more formal language"

    def test_edit_preserves_original_text(self):
        instruction = "change the tone to be less aggressive"
        result = _parse_decision(instruction)
        assert result == f"edit:{instruction}"

    def test_edit_strips_leading_whitespace(self):
        result = _parse_decision("  make it shorter  ")
        assert result == "edit:make it shorter"


# ---------------------------------------------------------------------------
# Card display format tests
# ---------------------------------------------------------------------------


class TestCardDisplayFormat:
    """Tests that the draft card renders in the expected structured format."""

    def test_card_display_contains_draft_header(self, capsys):
        """Draft card output must contain 'DRAFT:' header."""
        draft = _make_email_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "DRAFT:" in captured.out

    def test_card_display_contains_action_type(self, capsys):
        """Draft card output contains the action type."""
        draft = _make_email_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "draft_email" in captured.out

    def test_card_display_contains_card_text(self, capsys):
        """Draft card output contains the card_text() content (To:, Subject:, Body:)."""
        draft = _make_email_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "alice@example.com" in captured.out
        assert "Re: Project Update" in captured.out

    def test_card_display_contains_separator_lines(self, capsys):
        """Draft card output contains separator lines."""
        draft = _make_email_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "---" in captured.out or "===" in captured.out or "----" in captured.out

    def test_card_display_contains_confirmation_prompt(self, capsys):
        """Draft card output contains instruction on how to confirm/reject/edit."""
        draft = _make_email_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "Confirm, reject, or describe changes" in captured.out

    def test_card_display_schedule_event(self, capsys):
        """Draft card shows event details for schedule_event type."""
        draft = _make_schedule_draft()
        _display_draft_card(draft)
        captured = capsys.readouterr()
        assert "schedule_event" in captured.out


def _display_draft_card(draft: ActionDraft) -> None:
    """Helper that mirrors the expected CLI card display logic.

    This function should match what the CLI does when displaying a draft.
    It will fail until the CLI exports or makes available this display logic.
    """
    from daily.cli import _display_draft_card as cli_display
    cli_display(draft)


# ---------------------------------------------------------------------------
# CLI approval flow integration tests
# ---------------------------------------------------------------------------


class TestCliApprovalFlowStructural:
    """Structural tests that verify CLI contains required approval flow code."""

    def test_cli_imports_command_from_langgraph(self):
        """cli.py imports Command from langgraph.types."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        assert "from langgraph.types import" in source
        assert "Command" in source

    def test_cli_contains_command_resume_call(self):
        """cli.py contains Command(resume= call for approval flow."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        assert "Command(resume=" in source

    def test_cli_contains_interrupted_state_check(self):
        """cli.py checks for interrupted graph state."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        # The CLI should check state.next or equivalent
        assert "state.next" in source or "interrupted" in source or "__interrupt__" in source

    def test_cli_contains_draft_header_string(self):
        """cli.py contains 'DRAFT:' string for card display."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        assert "DRAFT:" in source

    def test_cli_contains_edit_prefix_string(self):
        """cli.py contains 'edit:' prefix string for edit flow parsing."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        assert '"edit:"' in source or "'edit:'" in source

    def test_cli_contains_confirm_reject_prompt(self):
        """cli.py contains the confirmation/rejection prompt."""
        import inspect
        import daily.cli as cli_module
        source = inspect.getsource(cli_module)
        assert "Confirm, reject, or describe changes" in source

    def test_cli_has_display_draft_card_function(self):
        """cli.py exports _display_draft_card function."""
        import daily.cli as cli_module
        assert hasattr(cli_module, "_display_draft_card"), (
            "cli.py must have _display_draft_card function for card display"
        )
        assert callable(cli_module._display_draft_card)

    def test_cli_has_parse_approval_decision_function(self):
        """cli.py exports _parse_approval_decision function."""
        import daily.cli as cli_module
        assert hasattr(cli_module, "_parse_approval_decision"), (
            "cli.py must have _parse_approval_decision function"
        )
        assert callable(cli_module._parse_approval_decision)


# ---------------------------------------------------------------------------
# _parse_approval_decision from cli.py
# ---------------------------------------------------------------------------


class TestCliParseApprovalDecision:
    """Tests for the _parse_approval_decision function in cli.py."""

    def test_cli_confirm_parsing(self):
        """_parse_approval_decision maps confirm synonyms to 'confirm'."""
        from daily.cli import _parse_approval_decision
        for word in ("confirm", "yes", "y", "send", "ok"):
            assert _parse_approval_decision(word) == "confirm", (
                f"Expected 'confirm' for input '{word}'"
            )

    def test_cli_reject_parsing(self):
        """_parse_approval_decision maps reject synonyms to 'reject'."""
        from daily.cli import _parse_approval_decision
        for word in ("reject", "no", "n", "cancel"):
            assert _parse_approval_decision(word) == "reject", (
                f"Expected 'reject' for input '{word}'"
            )

    def test_cli_edit_parsing(self):
        """_parse_approval_decision maps arbitrary text to 'edit:{text}'."""
        from daily.cli import _parse_approval_decision
        result = _parse_approval_decision("make it shorter")
        assert result == "edit:make it shorter"

    def test_cli_edit_parsing_formal(self):
        """_parse_approval_decision correctly prefixes edit instructions."""
        from daily.cli import _parse_approval_decision
        result = _parse_approval_decision("use more formal language")
        assert result == "edit:use more formal language"

    def test_cli_confirm_case_insensitive(self):
        """_parse_approval_decision is case-insensitive for confirm synonyms."""
        from daily.cli import _parse_approval_decision
        assert _parse_approval_decision("YES") == "confirm"
        assert _parse_approval_decision("CONFIRM") == "confirm"
        assert _parse_approval_decision("OK") == "confirm"

    def test_cli_reject_case_insensitive(self):
        """_parse_approval_decision is case-insensitive for reject synonyms."""
        from daily.cli import _parse_approval_decision
        assert _parse_approval_decision("NO") == "reject"
        assert _parse_approval_decision("CANCEL") == "reject"


# ---------------------------------------------------------------------------
# Edit re-entry loop behaviour
# ---------------------------------------------------------------------------


class TestEditReentryLoop:
    """Tests that edit decisions re-enter the draft flow."""

    def test_edit_decision_prefix_is_edit_colon(self):
        """Edit instruction is prefixed with 'edit:' to re-enter draft flow."""
        from daily.cli import _parse_approval_decision
        result = _parse_approval_decision("shorter please")
        assert result.startswith("edit:"), (
            f"Edit decision must start with 'edit:', got: {result}"
        )

    def test_edit_instruction_preserved_after_prefix(self):
        """Full edit instruction is preserved after 'edit:' prefix."""
        from daily.cli import _parse_approval_decision
        instruction = "make the tone warmer and more personal"
        result = _parse_approval_decision(instruction)
        assert result == f"edit:{instruction}"


# ---------------------------------------------------------------------------
# Rejection behaviour tests
# ---------------------------------------------------------------------------


class TestRejectionBehaviour:
    """Tests for ask_why vs discard rejection behaviours."""

    def test_ask_why_rejection_shows_action_cancelled(self, capsys):
        """Rejection with ask_why preference shows 'Action cancelled' message."""
        # execute_node returns "Action cancelled." — this tests the CLI displays it
        # The ask_why re-entry happens naturally: user sees "Action cancelled"
        # and can continue chatting to re-enter the draft flow
        from daily.cli import _display_cancellation_message
        _display_cancellation_message(rejection_behaviour="ask_why")
        captured = capsys.readouterr()
        assert "cancelled" in captured.out.lower() or "cancel" in captured.out.lower()

    def test_discard_rejection_shows_cancellation(self, capsys):
        """Rejection with discard preference also shows cancellation message."""
        from daily.cli import _display_cancellation_message
        _display_cancellation_message(rejection_behaviour="discard")
        captured = capsys.readouterr()
        assert "cancelled" in captured.out.lower() or "cancel" in captured.out.lower()


# ---------------------------------------------------------------------------
# Full approval flow integration test (mocked graph)
# ---------------------------------------------------------------------------


class TestCliApprovalFlowIntegration:
    """Integration tests for the CLI approval flow using a mocked graph."""

    @pytest.mark.asyncio
    async def test_approval_flow_confirm_resumes_graph(self):
        """When user confirms, CLI resumes graph with Command(resume='confirm')."""
        from langgraph.types import Command

        # Mock the graph and state
        mock_graph = AsyncMock()
        mock_state = MagicMock()

        draft = _make_email_draft()

        # First graph.aget_state call returns interrupted state
        mock_interrupted_state = MagicMock()
        mock_interrupted_state.next = ["approval"]  # has pending nodes
        mock_task = MagicMock()
        mock_task.interrupts = [MagicMock(value={
            "preview": draft.card_text(),
            "action_type": draft.action_type.value,
        })]
        mock_interrupted_state.tasks = [mock_task]

        # After resume, state is complete
        mock_completed_state = MagicMock()
        mock_completed_state.next = []
        mock_completed_state.tasks = []

        mock_graph.aget_state = AsyncMock(
            side_effect=[mock_interrupted_state, mock_completed_state]
        )
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Done. Action executed successfully.")]
        })

        # Simulate user input: "confirm"
        from daily.cli import _handle_approval_flow

        with patch("builtins.input", return_value="confirm"):
            result = await _handle_approval_flow(
                graph=mock_graph,
                state=mock_interrupted_state,
                config={"configurable": {"thread_id": "test-thread"}},
            )

        # Verify Command(resume="confirm") was used
        call_args = mock_graph.ainvoke.call_args
        resume_cmd = call_args.args[0] if call_args.args else call_args.kwargs.get("input")
        assert isinstance(resume_cmd, Command)
        assert resume_cmd.resume == "confirm"

    @pytest.mark.asyncio
    async def test_approval_flow_reject_resumes_with_reject(self):
        """When user rejects, CLI resumes graph with Command(resume='reject')."""
        from langgraph.types import Command

        mock_graph = AsyncMock()
        draft = _make_email_draft()

        mock_interrupted_state = MagicMock()
        mock_interrupted_state.next = ["approval"]
        mock_task = MagicMock()
        mock_task.interrupts = [MagicMock(value={
            "preview": draft.card_text(),
            "action_type": draft.action_type.value,
        })]
        mock_interrupted_state.tasks = [mock_task]

        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="Action cancelled.")]
        })

        from daily.cli import _handle_approval_flow

        with patch("builtins.input", return_value="no"):
            await _handle_approval_flow(
                graph=mock_graph,
                state=mock_interrupted_state,
                config={"configurable": {"thread_id": "test-thread"}},
            )

        call_args = mock_graph.ainvoke.call_args
        resume_cmd = call_args.args[0] if call_args.args else call_args.kwargs.get("input")
        assert isinstance(resume_cmd, Command)
        assert resume_cmd.resume == "reject"
