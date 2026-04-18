"""Tests for Phase 13 orchestrator node functions: skip_node and re_request_node.

Covers:
- skip_node returns correct acknowledgement message (SIG-01)
- re_request_node returns correct repeat acknowledgement (SIG-02)
"""


class TestSkipNode:
    """Tests for skip_node (Phase 13 SIG-01)."""

    async def test_skip_node_returns_ack_message(self):
        """skip_node returns 'Skipping to the next item.' acknowledgement."""
        from daily.orchestrator.nodes import skip_node
        from daily.orchestrator.state import SessionState

        # active_user_id=0 is falsy — _capture_signal is never called, no mock needed
        state = SessionState(
            messages=[],
            active_user_id=0,
            briefing_items=[],
            current_item_index=0,
        )

        result = await skip_node(state)

        assert result["messages"][0].content == "Skipping to the next item."


class TestReRequestNode:
    """Tests for re_request_node (Phase 13 SIG-02)."""

    async def test_re_request_node_returns_repeat_content(self):
        """re_request_node returns message starting with 'Sure, let me repeat that.'"""
        from daily.orchestrator.nodes import re_request_node
        from daily.orchestrator.state import SessionState

        # active_user_id=0 is falsy — _capture_signal is never called, no mock needed
        # Empty briefing_items and no narrative — falls back to bare acknowledgement
        state = SessionState(
            messages=[],
            active_user_id=0,
            briefing_items=[],
            current_item_index=0,
        )

        result = await re_request_node(state)

        assert result["messages"][0].content.startswith("Sure, let me repeat that.")
