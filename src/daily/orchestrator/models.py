"""Orchestrator response models.

OrchestratorIntent defines the validated output contract for the intent-classification
LLM node. Pydantic Literal validation enforces the whitelist at parse time, so
the LLM cannot inject arbitrary action strings into the execution pipeline
(D-03 / SEC-05 — LLM is intent-only, orchestrator dispatches all actions).

Phase 3 actions:
  answer            — respond to a follow-up question with retrieved context
  summarise_thread  — summarise an email thread on demand
  skip              — skip current briefing item
  clarify           — ask a clarifying question back to the user

Phase 4 actions (T-04-01: extended Literal whitelist enforces SEC-05):
  draft_email       — draft a reply or new email
  draft_message     — draft a Slack message
  compose_email     — compose a new email (alias for draft_email, explicit send intent)
  schedule_event    — schedule a new calendar event
  reschedule_event  — reschedule an existing calendar event
"""
from typing import Literal

from pydantic import BaseModel


class OrchestratorIntent(BaseModel):
    """Validated intent parsed from LLM output.

    action must be one of the whitelisted values. Pydantic will raise
    ValidationError for any other string — including 'execute', 'send', 'call'.

    Fields:
        action: Whitelisted action type (SEC-05 constraint).
        narrative: Human-readable explanation or response to be spoken to the user.
        target_id: Optional reference (email_id, thread_id, event_id) the action
                   applies to. None for actions that don't target a specific item.
        draft_instruction: User's natural language instruction for what to draft.
                           Only set for Phase 4 draft/schedule actions.
    """

    action: Literal[
        "answer",
        "summarise_thread",
        "skip",
        "clarify",
        "draft_email",
        "draft_message",
        "compose_email",
        "schedule_event",
        "reschedule_event",
    ]
    narrative: str
    target_id: str | None = None
    draft_instruction: str | None = None
