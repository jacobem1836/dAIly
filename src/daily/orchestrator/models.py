"""Orchestrator response models.

OrchestratorIntent defines the validated output contract for the intent-classification
LLM node. Pydantic Literal validation enforces the whitelist at parse time, so
the LLM cannot inject arbitrary action strings into the execution pipeline
(D-03 / SEC-05 — LLM is intent-only, orchestrator dispatches all actions).

Only these four actions are permitted in Phase 3:
  answer            — respond to a follow-up question with retrieved context
  summarise_thread  — summarise an email thread on demand
  skip              — skip current briefing item
  clarify           — ask a clarifying question back to the user

Phase 4 actions (send, draft, schedule, etc.) are intentionally absent here.
"""
from typing import Literal

from pydantic import BaseModel


class OrchestratorIntent(BaseModel):
    """Validated intent parsed from LLM output.

    action must be one of the four whitelisted values. Pydantic will raise
    ValidationError for any other string — including 'execute', 'send', 'call'.

    Fields:
        action: Whitelisted action type (SEC-05 constraint).
        narrative: Human-readable explanation or response to be spoken to the user.
        target_id: Optional reference (email_id, thread_id, event_id) the action
                   applies to. None for actions that don't target a specific item.
    """

    action: Literal["answer", "summarise_thread", "skip", "clarify"]
    narrative: str
    target_id: str | None = None
