"""LangGraph session state for the orchestrator graph.

SessionState holds the shared mutable state passed between graph nodes.
Per D-09: state is persisted by the LangGraph checkpointer (AsyncPostgresSaver).
Only summaries and metadata are stored — never raw email/message bodies (SEC-04).

The `messages` field uses add_messages from langgraph.graph.message so that
LangGraph merges message lists correctly during state updates (append semantics).

Phase 4 additions:
  pending_action: Holds an ActionDraft awaiting user approval.
  approval_decision: Holds the user's decision string ('confirm', 'reject', 'edit:*').
"""
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class SessionState(BaseModel):
    """Shared state for the orchestrator LangGraph.

    Fields:
        messages: Conversation messages with append-merge semantics via add_messages.
        briefing_narrative: The precomputed briefing text delivered at session start.
        active_user_id: The user whose session is active (0 = no active user).
        preferences: User preference snapshot loaded at session start.
        active_section: Pointer to the current section being discussed.
        pending_action: ActionDraft awaiting user approval (Phase 4). Typed as Any
                        to avoid circular imports — always an ActionDraft instance
                        or None at runtime.
        approval_decision: User's approval decision string (Phase 4).
                           Expected values: 'confirm', 'reject', 'edit:*'.
    """

    messages: Annotated[list, add_messages] = Field(default_factory=list)
    briefing_narrative: str = ""
    active_user_id: int = 0
    preferences: dict = Field(default_factory=dict)
    active_section: str = ""  # current briefing section pointer
    pending_action: Any = None  # ActionDraft | None at runtime
    approval_decision: str | None = None
