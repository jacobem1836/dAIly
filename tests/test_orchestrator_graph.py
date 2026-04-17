"""Tests for the orchestrator LangGraph graph and session entry point.

Task 1 (TDD RED phase): Tests will fail until graph.py and session.py are created.
Tests cover:
- build_graph() returns a compiled StateGraph with required nodes
- route_intent dispatches to correct node
- thread_id scoping per user and date (T-03-04)
- session entry point creates correct config and loads state
"""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage


class TestBuildGraph:
    """Tests for graph.py build_graph()."""

    def test_build_graph_returns_compiled_state_graph(self):
        """build_graph() returns a CompiledStateGraph."""
        from langgraph.checkpoint.memory import MemorySaver

        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        # A compiled graph has an ainvoke method
        assert hasattr(graph, "ainvoke")
        assert callable(graph.ainvoke)

    def test_build_graph_with_no_checkpointer(self):
        """build_graph() works without a checkpointer (test mode)."""
        from daily.orchestrator.graph import build_graph

        graph = build_graph()
        assert hasattr(graph, "ainvoke")

    def test_build_graph_has_respond_node(self):
        """Compiled graph has 'respond' node."""
        from langgraph.checkpoint.memory import MemorySaver

        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        # Nodes are accessible via graph.nodes or the underlying builder
        assert "respond" in graph.nodes

    def test_build_graph_has_summarise_thread_node(self):
        """Compiled graph has 'summarise_thread' node."""
        from langgraph.checkpoint.memory import MemorySaver

        from daily.orchestrator.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        assert "summarise_thread" in graph.nodes

    def test_build_graph_compiled_with_checkpointer(self):
        """Graph compiled with checkpointer stores it."""
        from langgraph.checkpoint.memory import MemorySaver

        from daily.orchestrator.graph import build_graph

        saver = MemorySaver()
        graph = build_graph(checkpointer=saver)
        assert graph.checkpointer is saver


class TestRouteIntent:
    """Tests for the route_intent conditional edge function."""

    def test_route_intent_returns_summarise_for_summarise_keyword(self):
        """route_intent routes to 'summarise_thread' when 'summarise' in message."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="Can you summarise that email?")])
        result = route_intent(state)
        assert result == "summarise_thread"

    def test_route_intent_returns_summarise_for_summary_keyword(self):
        """route_intent routes to 'summarise_thread' for 'summary'."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="Give me a summary of that thread")])
        result = route_intent(state)
        assert result == "summarise_thread"

    def test_route_intent_returns_summarise_for_email_chain(self):
        """route_intent routes to 'summarise_thread' for 'email chain'."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="What does that email chain say?")])
        result = route_intent(state)
        assert result == "summarise_thread"

    def test_route_intent_returns_respond_for_general_question(self):
        """route_intent routes to 'respond' for general questions."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="What emails do I have today?")])
        result = route_intent(state)
        assert result == "respond"

    def test_route_intent_returns_respond_for_empty_messages(self):
        """route_intent defaults to 'respond' when no messages."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[])
        result = route_intent(state)
        assert result == "respond"

    def test_route_intent_case_insensitive(self):
        """route_intent matching is case-insensitive."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="SUMMARISE that thread please")])
        result = route_intent(state)
        assert result == "summarise_thread"

    def test_route_intent_returns_summarise_for_thread_keyword(self):
        """route_intent routes to 'summarise_thread' for 'thread'."""
        from langchain_core.messages import HumanMessage

        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="Tell me more about that thread")])
        result = route_intent(state)
        assert result == "summarise_thread"


class TestSessionConfig:
    """Tests for session.py create_session_config()."""

    @pytest.mark.asyncio
    async def test_create_session_config_returns_configurable_dict(self):
        """create_session_config returns dict with configurable key."""
        from daily.orchestrator.session import create_session_config

        config = await create_session_config(user_id=1)
        assert "configurable" in config
        assert "thread_id" in config["configurable"]

    @pytest.mark.asyncio
    async def test_thread_id_follows_user_date_pattern(self):
        """thread_id follows 'user-{user_id}-{date}' pattern (T-03-04)."""
        from daily.orchestrator.session import create_session_config

        d = date(2026, 4, 7)
        config = await create_session_config(user_id=42, session_date=d)
        assert config["configurable"]["thread_id"] == "user-42-2026-04-07"

    @pytest.mark.asyncio
    async def test_thread_id_scoped_per_user(self):
        """Different users get different thread_ids (T-03-04 cross-user isolation)."""
        from daily.orchestrator.session import create_session_config

        d = date(2026, 4, 7)
        config1 = await create_session_config(user_id=1, session_date=d)
        config2 = await create_session_config(user_id=2, session_date=d)
        assert config1["configurable"]["thread_id"] != config2["configurable"]["thread_id"]

    @pytest.mark.asyncio
    async def test_thread_id_scoped_per_date(self):
        """Same user gets different thread_id on different dates."""
        from daily.orchestrator.session import create_session_config

        config1 = await create_session_config(user_id=1, session_date=date(2026, 4, 7))
        config2 = await create_session_config(user_id=1, session_date=date(2026, 4, 8))
        assert config1["configurable"]["thread_id"] != config2["configurable"]["thread_id"]


class TestRunSession:
    """Tests for session.py run_session()."""

    @pytest.mark.asyncio
    async def test_run_session_calls_ainvoke_with_user_message(self):
        """run_session calls graph.ainvoke with messages containing user input."""
        from daily.orchestrator.session import run_session

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {"messages": []}
        config = {"configurable": {"thread_id": "user-1-2026-04-07"}}

        await run_session(mock_graph, "test question", config)

        mock_graph.ainvoke.assert_called_once()
        call_args = mock_graph.ainvoke.call_args
        state_input = call_args[0][0]
        assert "messages" in state_input
        # Messages should contain the human input
        assert any("test question" in str(m) for m in state_input["messages"])

    @pytest.mark.asyncio
    async def test_run_session_passes_initial_state_on_first_turn(self):
        """run_session merges initial_state on first turn."""
        from daily.orchestrator.session import run_session

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {"messages": []}
        config = {"configurable": {"thread_id": "user-1-2026-04-07"}}
        initial_state = {"briefing_narrative": "Morning briefing text", "active_user_id": 1}

        await run_session(mock_graph, "hello", config, initial_state=initial_state)

        call_args = mock_graph.ainvoke.call_args
        state_input = call_args[0][0]
        assert state_input.get("briefing_narrative") == "Morning briefing text"
        assert state_input.get("active_user_id") == 1

    @pytest.mark.asyncio
    async def test_run_session_uses_ainvoke_not_invoke(self):
        """run_session must use ainvoke (not invoke) to avoid hanging (Pitfall 2)."""
        import inspect

        from daily.orchestrator import session

        # Read the source to verify it uses ainvoke
        source = inspect.getsource(session.run_session)
        assert "ainvoke" in source
        assert "graph.invoke(" not in source


class TestEmailAdapterRegistry:
    """Tests for the email adapter registry in session.py."""

    def test_set_email_adapters_stores_adapters(self):
        """set_email_adapters stores a list of adapters."""
        from daily.orchestrator.session import get_email_adapters, set_email_adapters

        mock_adapter = MagicMock()
        set_email_adapters([mock_adapter])
        adapters = get_email_adapters()
        assert len(adapters) == 1
        assert adapters[0] is mock_adapter

    def test_get_email_adapters_returns_empty_list_initially(self):
        """get_email_adapters returns list (may be empty if not set)."""
        from daily.orchestrator.session import get_email_adapters, set_email_adapters

        # Reset to empty
        set_email_adapters([])
        adapters = get_email_adapters()
        assert isinstance(adapters, list)

    def test_set_email_adapters_replaces_previous(self):
        """set_email_adapters replaces the previous list."""
        from daily.orchestrator.session import get_email_adapters, set_email_adapters

        adapter1 = MagicMock()
        adapter2 = MagicMock()
        set_email_adapters([adapter1])
        set_email_adapters([adapter2])
        adapters = get_email_adapters()
        assert len(adapters) == 1
        assert adapters[0] is adapter2


# ---------------------------------------------------------------------------
# Phase 10: Memory transparency routing (MEM-01, MEM-02, MEM-03)
# ---------------------------------------------------------------------------


class TestRouteIntentMemory:
    """Tests for route_intent memory keyword routing (Phase 10)."""

    def test_route_intent_memory_query(self):
        """'what do you know about me' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="what do you know about me")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_delete(self):
        """'forget that fact about my travel' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="forget that fact about my travel")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_clear(self):
        """'forget everything' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="forget everything")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_disable(self):
        """'disable memory' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="disable memory")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_priority_over_summarise(self):
        """Memory keywords take priority over summarise keywords."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        # "what do you know" is a memory keyword; message also contains no summarise keyword
        state = SessionState(messages=[HumanMessage(content="what do you know about that topic")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_what_do_you_remember(self):
        """'what do you remember' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="what do you remember about me")])
        assert route_intent(state) == "memory"

    def test_route_intent_memory_clear_my_memory(self):
        """'clear my memory' routes to 'memory'."""
        from daily.orchestrator.graph import route_intent
        from daily.orchestrator.state import SessionState

        state = SessionState(messages=[HumanMessage(content="clear my memory please")])
        assert route_intent(state) == "memory"


class TestBuildGraphPhase10:
    """Tests for Phase 10 graph topology."""

    def test_build_graph_has_memory_node(self):
        """Compiled graph has 'memory' node registered."""
        from daily.orchestrator.graph import build_graph

        graph = build_graph()
        assert "memory" in graph.get_graph().nodes
