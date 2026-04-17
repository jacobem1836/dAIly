"""LangGraph StateGraph definition for the orchestrator.

Defines the graph topology: nodes with conditional entry edge that dispatches
based on user message content.

Phase 3 nodes:
  respond           -> GPT-4.1 mini (quick follow-ups, low latency)
  summarise_thread  -> GPT-4.1 (reasoning-heavy, richer context window)

Phase 4 nodes (action layer, T-04-02 gate enforcement):
  draft             -> Stub in Plan 01; full drafting in Plan 02
  approval          -> Human-in-the-loop interrupt() gate (MUST fire before execute)
  execute           -> Executes or cancels based on approval_decision

Phase 10 nodes (memory transparency, MEM-01/MEM-02/MEM-03):
  memory            -> Query, delete, bulk-clear, or disable stored memory facts

Route priority (most specific first):
  1. memory_keywords    -> 'memory'          (Phase 10)
  2. summarise_keywords -> 'summarise_thread'
  3. draft_keywords     -> 'draft'
  4. default            -> 'respond'

Model selection happens inside the node functions (nodes.py), not here.

Checkpointer note:
  build_graph() accepts any LangGraph checkpointer. Pass MemorySaver for
  tests, AsyncPostgresSaver for production. Phase 3 CLI uses MemorySaver.
"""

from langgraph.graph import END, START, StateGraph

from daily.orchestrator.state import SessionState


def route_intent(state: SessionState) -> str:
    """Route based on last user message content.

    Keyword matching only — no user-controlled code execution (T-03-04).
    Priority: memory_keywords > summarise_keywords > draft_keywords > respond (default).

    Memory check must come FIRST (most specific per D-01, Phase 10).
    Summarise check must come BEFORE draft check — "summarise that thread" should
    go to summarise_thread, not draft, even though 'thread' could be ambiguous.

    Args:
        state: Current SessionState, checked for the last message.

    Returns:
        Node name: 'memory', 'summarise_thread', 'draft', or 'respond'.
    """
    last_msg = state.messages[-1].content.lower() if state.messages else ""

    # Memory keywords — checked FIRST (most specific; per D-01 Phase 10)
    memory_query_keywords = ["what do you know", "what do you remember",
                             "tell me what you know", "what have you learned"]
    memory_clear_keywords = ["forget everything", "clear my memory", "reset my memory"]
    memory_delete_keywords = ["forget that", "delete that", "remove that fact"]
    memory_disable_keywords = ["disable memory", "stop learning",
                               "turn off memory", "don't remember"]

    all_memory_keywords = (memory_query_keywords + memory_clear_keywords
                           + memory_delete_keywords + memory_disable_keywords)
    if any(kw in last_msg for kw in all_memory_keywords):
        return "memory"

    # Summarise keywords — checked FIRST among non-memory (more specific than draft keywords)
    summarise_keywords = ["summarise", "summarize", "summary", "thread", "email chain"]
    if any(kw in last_msg for kw in summarise_keywords):
        return "summarise_thread"

    # Draft/action keywords — Phase 4
    draft_keywords = [
        "draft",
        "reply",
        "send",
        "compose",
        "write",
        "schedule",
        "reschedule",
        "book",
        "move",
        "create event",
        "cancel meeting",
    ]
    if any(kw in last_msg for kw in draft_keywords):
        return "draft"

    return "respond"


def route_after_approval(state: SessionState) -> str:
    """Route after approval_node based on the user's decision.

    Decision routing:
      - 'confirm' or 'reject' -> 'execute' (execute handles both)
      - 'edit:*' -> 'draft' (re-enter draft with edit instruction)

    Args:
        state: Current SessionState with approval_decision set.

    Returns:
        Node name: 'execute' or 'draft'.
    """
    decision = state.approval_decision or ""
    if decision.startswith("edit:"):
        return "draft"
    return "execute"


def build_graph(checkpointer=None):
    """Build and compile the orchestrator StateGraph.

    Creates a graph with:
    - START -> conditional edge using route_intent
    - respond node -> END
    - summarise_thread node -> END
    - draft -> approval -> conditional(execute | draft) -> END  (Phase 4, T-04-02)

    The draft -> approval chain enforces the approval gate.
    Edit decisions loop back to draft for unlimited re-drafting (D-01).
    There is NO direct edge from START to execute — approval cannot be bypassed.

    Args:
        checkpointer: LangGraph checkpointer instance. Use MemorySaver for
                     tests, AsyncPostgresSaver for production.

    Returns:
        CompiledStateGraph ready for ainvoke/astream calls.
    """
    from daily.orchestrator.nodes import (
        approval_node,
        draft_node,
        execute_node,
        memory_node,
        respond_node,
        summarise_thread_node,
    )

    builder = StateGraph(SessionState)

    # Phase 3 nodes
    builder.add_node("respond", respond_node)
    builder.add_node("summarise_thread", summarise_thread_node)

    # Phase 4 nodes (action layer)
    builder.add_node("draft", draft_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)

    # Phase 10 nodes (memory transparency)
    builder.add_node("memory", memory_node)

    # Conditional entry from START
    builder.add_conditional_edges(
        START,
        route_intent,
        {
            "memory": "memory",
            "respond": "respond",
            "summarise_thread": "summarise_thread",
            "draft": "draft",
        },
    )

    # Phase 3 terminal edges
    builder.add_edge("respond", END)
    builder.add_edge("summarise_thread", END)

    # Phase 10 terminal edge
    builder.add_edge("memory", END)

    # Phase 4 action chain: draft -> approval -> conditional -> END
    # approval_node uses interrupt() which pauses the graph — no bypass possible
    # After approval, route_after_approval sends edit decisions back to draft
    # for unlimited re-drafting (D-01), or forward to execute for confirm/reject.
    builder.add_edge("draft", "approval")
    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {
            "execute": "execute",
            "draft": "draft",
        },
    )
    builder.add_edge("execute", END)

    return builder.compile(checkpointer=checkpointer)
