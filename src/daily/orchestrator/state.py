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
from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from daily.actions.base import ActionDraft


class SessionState(BaseModel):
    """Shared state for the orchestrator LangGraph.

    Fields:
        messages: Conversation messages with append-merge semantics via add_messages.
        briefing_narrative: The precomputed briefing text delivered at session start.
        active_user_id: The user whose session is active (0 = no active user).
        preferences: User preference snapshot loaded at session start.
        active_section: Pointer to the current section being discussed.
        pending_action: ActionDraft awaiting user approval (Phase 4).
        approval_decision: User's approval decision string (Phase 4).
                           Expected values: 'confirm', 'reject', 'edit:*'.
        email_context: Recent email metadata (sender, subject, thread_id, message_id,
                       recipient, timestamp) loaded at session init. Used by draft_node
                       to match user intent to a specific email thread. Stored as plain
                       dicts (not EmailMetadata) for clean LangGraph state serialisation.
                       Only metadata is stored — never raw bodies (SEC-04).
    """

    messages: Annotated[list, add_messages] = Field(default_factory=list)
    briefing_narrative: str = ""
    active_user_id: int = 0
    preferences: dict = Field(default_factory=dict)
    active_section: str = ""  # current briefing section pointer
    pending_action: ActionDraft | None = None
    approval_decision: str | None = None
    email_context: list[dict] = Field(default_factory=list)
