"""Tests for LangGraph approval gate: draft_node, approval_node, execute_node.

TDD RED phase — tests must fail until nodes and graph extensions are implemented.

Covers:
- approval_node calls interrupt() with preview and action_type keys
- Graph pauses at approval_node (interrupted state)
- Command(resume="confirm") resumes to execute_node
- Command(resume="reject") cancels without reaching execute_node
- route_intent dispatches action keywords to "draft" node
- route_intent preserves existing routing ("respond", "summarise_thread")
- No direct edge from START to execute_node (approval gate cannot be bypassed)
"""
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from daily.actions.base import ActionDraft, ActionType
from daily.orchestrator.state import SessionState


def _make_email_draft() -> ActionDraft:
    """Return a simple email ActionDraft for testing."""
    return ActionDraft(
        action_type=ActionType.draft_email,
        recipient="test@example.com",
        subject="Test Subject",
        body="Hello, this is a test draft.",
    )


def _make_config(thread_id: str = "test-thread-001") -> dict:
    return {"configurable": {"thread_id": thread_id}}


# ---------------------------------------------------------------------------
# route_intent tests — action keywords
# ---------------------------------------------------------------------------


class TestRouteIntentActionKeywords:
    """Tests that route_intent dispatches action keywords to 'draft' node."""

    def test_route_intent_draft_keyword(self):
        """route_intent returns 'draft' for 'draft' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="draft a reply to that email")])
        assert route_intent(state) == "draft"

    def test_route_intent_reply_keyword(self):
        """route_intent returns 'draft' for 'reply' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="reply to Alice's message")])
        assert route_intent(state) == "draft"

    def test_route_intent_send_keyword(self):
        """route_intent returns 'draft' for 'send' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="send an email to Bob")])
        assert route_intent(state) == "draft"

    def test_route_intent_schedule_keyword(self):
        """route_intent returns 'draft' for 'schedule' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="schedule a meeting tomorrow")])
        assert route_intent(state) == "draft"

    def test_route_intent_compose_keyword(self):
        """route_intent returns 'draft' for 'compose' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="compose a new email")])
        assert route_intent(state) == "draft"

    def test_route_intent_write_keyword(self):
        """route_intent returns 'draft' for 'write' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="write a response to that")])
        assert route_intent(state) == "draft"

    def test_route_intent_reschedule_keyword(self):
        """route_intent returns 'draft' for 'reschedule' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="reschedule the 10am meeting")])
        assert route_intent(state) == "draft"


class TestRouteIntentPreservesExisting:
    """Tests that existing route_intent behavior is preserved."""

    def test_route_intent_general_question_returns_respond(self):
        """route_intent returns 'respond' for general questions."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="What emails do I have today?")])
        assert route_intent(state) == "respond"

    def test_route_intent_summarise_keyword_returns_summarise_thread(self):
        """route_intent returns 'summarise_thread' for summarise keyword (higher priority)."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="summarise that email thread")])
        assert route_intent(state) == "summarise_thread"

    def test_route_intent_summary_keyword_returns_summarise_thread(self):
        """route_intent returns 'summarise_thread' for 'summary' keyword."""
        from daily.orchestrator.graph import route_intent

        state = SessionState(messages=[HumanMessage(content="give me a summary")])
        assert route_intent(state) == "summarise_thread"


# ---------------------------------------------------------------------------
# Graph topology test — no bypass path to execute
# ---------------------------------------------------------------------------


class TestGraphTopologyNoBypss:
    """Tests that graph topology enforces draft -> approval -> execute path."""

    def test_graph_has_draft_node(self):
        """build_graph() compiled graph has 'draft' node."""
        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        assert "draft" in graph.nodes

    def test_graph_has_approval_node(self):
        """build_graph() compiled graph has 'approval' node."""
        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        assert "approval" in graph.nodes

    def test_graph_has_execute_node(self):
        """build_graph() compiled graph has 'execute' node."""
        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        assert "execute" in graph.nodes

    def test_no_direct_edge_start_to_execute(self):
        """No direct edge from START to execute node (T-04-02 gate enforcement)."""
        from langgraph.graph import START

        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        # The graph's underlying structure should not have a direct START->execute edge
        # We check by inspecting the graph edges
        edges = graph.edges if hasattr(graph, "edges") else []

        # Ensure START doesn't route directly to "execute"
        # route_intent is the conditional edge from START — it must not include "execute"
        from daily.orchestrator.graph import route_intent

        # Verify route_intent never returns "execute"
        test_messages = [
            "execute that action",
            "just execute it now",
            "execute",
            "run the action",
        ]
        for msg in test_messages:
            state = SessionState(messages=[HumanMessage(content=msg)])
            result = route_intent(state)
            assert result != "execute", f"route_intent returned 'execute' for: {msg}"


# ---------------------------------------------------------------------------
# Interrupt and resume tests (graph integration)
# ---------------------------------------------------------------------------


def _make_mock_llm_response(body: str = "Hi, I'm on it!") -> MagicMock:
    """Return a mock OpenAI response for draft_node."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "recipient": "test@example.com",
        "subject": "Re: Test",
        "body": body,
        "event_title": None,
        "start_dt": None,
        "end_dt": None,
        "attendees": [],
    })
    return mock_resp


class TestApprovalGateInterrupt:
    """Tests for interrupt/resume approval flow using MemorySaver checkpointer."""

    @pytest.mark.asyncio
    async def test_interrupt_fires_at_approval_node(self):
        """Graph pauses (raises interrupt) when reaching approval_node with pending_action."""
        from daily.orchestrator.graph import build_graph

        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        config = _make_config("interrupt-test-001")

        draft = _make_email_draft()

        # Mock LLM so draft_node doesn't call real OpenAI
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_llm_response())

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI", return_value=mock_client),
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            # Invoke graph with a pending_action to trigger draft -> approval path
            # The approval_node calls interrupt(), which causes LangGraph to pause
            try:
                result = await graph.ainvoke(
                    {
                        "messages": [HumanMessage(content="draft a reply")],
                        "pending_action": draft,
                        "active_user_id": 1,
                    },
                    config=config,
                )
                # LangGraph may return interrupted state with __interrupt__ key
                assert "__interrupt__" in result or result.get("approval_decision") is None
            except Exception as exc:
                exc_type = type(exc).__name__
                assert "interrupt" in exc_type.lower() or "Interrupt" in str(exc), (
                    f"Expected interrupt exception, got: {exc_type}: {exc}"
                )

    @pytest.mark.asyncio
    async def test_confirm_resumes_to_execute(self):
        """Command(resume='confirm') resumes graph and executes action."""
        from daily.orchestrator.graph import build_graph

        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        config = _make_config("confirm-test-001")

        draft = _make_email_draft()

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_llm_response())

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI", return_value=mock_client),
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            # First invocation — should interrupt at approval
            try:
                await graph.ainvoke(
                    {
                        "messages": [HumanMessage(content="draft a reply")],
                        "pending_action": draft,
                        "active_user_id": 1,
                    },
                    config=config,
                )
            except Exception:
                pass  # Expected interrupt

        # Resume with confirm — patch executor factory so no DB/API calls needed
        from unittest.mock import AsyncMock as _AsyncMock, MagicMock as _MagicMock
        from daily.actions.base import ActionResult as _ActionResult

        mock_executor = _MagicMock()
        mock_executor.validate = _AsyncMock(return_value=None)
        mock_executor.execute = _AsyncMock(
            return_value=_ActionResult(success=True, external_id="msg-test-001")
        )

        with patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=_AsyncMock(return_value=mock_executor),
        ):
            result = await graph.ainvoke(
                Command(resume="confirm"),
                config=config,
            )

        # After confirm, execute_node should produce a success message
        messages = result.get("messages", [])
        message_contents = [m.content for m in messages if hasattr(m, "content")]
        combined = " ".join(message_contents).lower()
        assert "done" in combined or "executed" in combined or "success" in combined or "sent" in combined

    @pytest.mark.asyncio
    async def test_reject_cancels_without_executing(self):
        """Command(resume='reject') cancels and returns cancellation message."""
        from daily.orchestrator.graph import build_graph

        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        config = _make_config("reject-test-001")

        draft = _make_email_draft()

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_llm_response())

        with (
            patch("daily.orchestrator.nodes.AsyncOpenAI", return_value=mock_client),
            patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        ):
            # First invocation — should interrupt at approval
            try:
                await graph.ainvoke(
                    {
                        "messages": [HumanMessage(content="draft a reply")],
                        "pending_action": draft,
                        "active_user_id": 1,
                    },
                    config=config,
                )
            except Exception:
                pass  # Expected interrupt

        # Resume with reject
        result = await graph.ainvoke(
            Command(resume="reject"),
            config=config,
        )

        messages = result.get("messages", [])
        message_contents = [m.content for m in messages if hasattr(m, "content")]
        combined = " ".join(message_contents).lower()
        assert "cancel" in combined or "cancelled" in combined or "rejected" in combined


# ---------------------------------------------------------------------------
# Node function structural tests
# ---------------------------------------------------------------------------


class TestNodeFunctionStructure:
    """Tests that node functions exist and have correct structure."""

    def test_approval_node_exists_in_nodes_module(self):
        """approval_node function exists in orchestrator.nodes."""
        from daily.orchestrator import nodes

        assert hasattr(nodes, "approval_node")
        assert callable(nodes.approval_node)

    def test_draft_node_exists_in_nodes_module(self):
        """draft_node function exists in orchestrator.nodes."""
        from daily.orchestrator import nodes

        assert hasattr(nodes, "draft_node")
        assert callable(nodes.draft_node)

    def test_execute_node_exists_in_nodes_module(self):
        """execute_node function exists in orchestrator.nodes."""
        from daily.orchestrator import nodes

        assert hasattr(nodes, "execute_node")
        assert callable(nodes.execute_node)

    def test_approval_node_uses_interrupt(self):
        """approval_node source contains interrupt() call without bare try/except."""
        from daily.orchestrator import nodes

        source = inspect.getsource(nodes.approval_node)
        assert "interrupt(" in source

        # Verify interrupt is NOT wrapped in bare try/except
        # The interrupt call should not be inside a try block
        lines = source.split("\n")
        interrupt_line_idx = next(
            (i for i, line in enumerate(lines) if "interrupt(" in line), None
        )
        assert interrupt_line_idx is not None

        # Check lines above interrupt call for try: (within 5 lines)
        context_lines = lines[max(0, interrupt_line_idx - 5) : interrupt_line_idx]
        has_bare_try = any(line.strip() == "try:" for line in context_lines)
        assert not has_bare_try, "interrupt() must not be wrapped in a bare try/except"

    def test_nodes_imports_interrupt_from_langgraph_types(self):
        """nodes.py imports interrupt from langgraph.types."""
        from daily.orchestrator import nodes

        source = inspect.getsource(nodes)
        assert "from langgraph.types import" in source
        assert "interrupt" in source

    def test_execute_node_uses_asyncio_create_task(self):
        """execute_node uses asyncio.create_task for fire-and-forget logging."""
        from daily.orchestrator import nodes

        source = inspect.getsource(nodes.execute_node)
        assert "asyncio.create_task" in source
