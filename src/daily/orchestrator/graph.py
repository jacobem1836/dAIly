"""LangGraph StateGraph definition for the orchestrator.

Defines the graph topology: two nodes (respond, summarise_thread) with a
conditional entry edge that dispatches based on user message content.

Model routing (per D-02):
  respond           -> GPT-4.1 mini (quick follow-ups, low latency)
  summarise_thread  -> GPT-4.1 (reasoning-heavy, richer context window)

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
    Dispatches to 'summarise_thread' or 'respond'.

    Args:
        state: Current SessionState, checked for the last message.

    Returns:
        Node name to route to: 'summarise_thread' or 'respond'.
    """
    last_msg = state.messages[-1].content.lower() if state.messages else ""
    summarise_keywords = ["summarise", "summarize", "summary", "thread", "email chain"]
    if any(kw in last_msg for kw in summarise_keywords):
        return "summarise_thread"
    return "respond"


def build_graph(checkpointer=None):
    """Build and compile the orchestrator StateGraph.

    Creates a graph with:
    - START -> conditional edge using route_intent
    - respond node -> END
    - summarise_thread node -> END

    Args:
        checkpointer: LangGraph checkpointer instance. Use MemorySaver for
                     tests, AsyncPostgresSaver for production.

    Returns:
        CompiledStateGraph ready for ainvoke/astream calls.
    """
    from daily.orchestrator.nodes import respond_node, summarise_thread_node

    builder = StateGraph(SessionState)
    builder.add_node("respond", respond_node)
    builder.add_node("summarise_thread", summarise_thread_node)
    builder.add_conditional_edges(
        START,
        route_intent,
        {
            "respond": "respond",
            "summarise_thread": "summarise_thread",
        },
    )
    builder.add_edge("respond", END)
    builder.add_edge("summarise_thread", END)
    return builder.compile(checkpointer=checkpointer)
