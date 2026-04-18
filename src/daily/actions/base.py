"""Action layer base types: ActionType enum, ActionDraft, ActionResult, ActionExecutor ABC.

Defines the structural skeleton for all action executors in Phase 4.

Security boundaries:
  ACT-06: ActionExecutor.validate() enforces pre-execution checks (whitelist, scope).
  D-11: REQUIRED_SCOPES documents OAuth scope requirements per action type and provider.
  T-04-04: validate() must be called before execute() — enforced by graph topology.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Whitelisted action types for Phase 4.

    Using str mixin so values compare directly with string DB values
    (e.g. ActionType.draft_email == "draft_email" is True).
    """

    draft_email = "draft_email"
    draft_message = "draft_message"
    compose_email = "compose_email"
    schedule_event = "schedule_event"
    reschedule_event = "reschedule_event"


# Required OAuth scopes per action type and provider (per D-11).
# Used for pre-execution scope validation in ActionExecutor.validate().
REQUIRED_SCOPES: dict[ActionType, dict[str, list[str]]] = {
    ActionType.draft_email: {
        "google": ["https://www.googleapis.com/auth/gmail.send"],
        "microsoft": ["Mail.Send"],
    },
    ActionType.compose_email: {
        "google": ["https://www.googleapis.com/auth/gmail.send"],
        "microsoft": ["Mail.Send"],
    },
    ActionType.draft_message: {
        "slack": ["chat:write"],
    },
    ActionType.schedule_event: {
        "google": ["https://www.googleapis.com/auth/calendar.events"],
    },
    ActionType.reschedule_event: {
        "google": ["https://www.googleapis.com/auth/calendar.events"],
    },
}


# Action types that are NEVER auto-executed regardless of user config (per D-01).
# These always interrupt for approval in approval_node.
BLOCKED_ACTION_TYPES: frozenset[ActionType] = frozenset({
    ActionType.compose_email,
    # create_external_calendar_invite will be added here when the ActionType exists
})

# Action types the user may configure to "auto" (per D-02).
# All default to "approve" when not explicitly set.
CONFIGURABLE_ACTION_TYPES: frozenset[ActionType] = frozenset({
    ActionType.draft_email,
    ActionType.draft_message,
    ActionType.schedule_event,
    ActionType.reschedule_event,
})


class ActionDraft(BaseModel):
    """Represents a pending action awaiting user approval.

    Contains all information needed to display a preview (card_text) and
    execute the action after approval. PII-sensitive fields (body, recipient)
    are never stored raw — only hashed and summarised in the audit log (T-04-03).

    Fields:
        action_type: Whitelisted type from ActionType enum.
        recipient: Email address or Slack user ID for the message.
        subject: Email subject line (emails only).
        body: Draft content — the text to be sent.
        thread_id: Email thread_id or Slack thread_ts for replies.
        thread_message_id: RFC 2822 Message-ID for email reply threading.
        channel_id: Slack channel ID (Slack messages only).
        event_id: Calendar event ID (reschedule only).
        event_title: Human-readable event title (calendar actions).
        start_dt: Event start datetime (calendar actions).
        end_dt: Event end datetime (calendar actions).
        attendees: List of attendee email addresses (calendar actions).
    """

    action_type: ActionType
    recipient: str | None = None
    subject: str | None = None
    body: str
    thread_id: str | None = None
    thread_message_id: str | None = None
    channel_id: str | None = None
    event_id: str | None = None
    event_title: str | None = None
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    attendees: list[str] = Field(default_factory=list)

    def card_text(self) -> str:
        """Return a structured key-value string for CLI preview display (per D-04).

        Formats the draft as a human-readable card appropriate for the action type.
        Body is truncated to 500 characters to keep the preview scannable.
        """
        body_preview = self.body[:500]

        if self.action_type in (ActionType.draft_email, ActionType.compose_email):
            return (
                f"To: {self.recipient}\n"
                f"Subject: {self.subject}\n"
                f"Body:\n{body_preview}"
            )

        if self.action_type == ActionType.draft_message:
            return (
                f"Channel: {self.channel_id}\n"
                f"Thread: {self.thread_id}\n"
                f"Message:\n{body_preview}"
            )

        if self.action_type in (ActionType.schedule_event, ActionType.reschedule_event):
            attendees_str = ", ".join(self.attendees) if self.attendees else "(none)"
            return (
                f"Event: {self.event_title}\n"
                f"Time: {self.start_dt} - {self.end_dt}\n"
                f"Attendees: {attendees_str}"
            )

        # Fallback for any future action types
        return f"Action: {self.action_type.value}\nBody:\n{body_preview}"


class ActionResult(BaseModel):
    """Result of executing an action.

    Fields:
        success: Whether the action completed successfully.
        external_id: Provider-assigned ID (message ID, event ID). None on failure.
        error: Error description when success is False. None on success.
    """

    success: bool
    external_id: str | None = None
    error: str | None = None

    @property
    def summary(self) -> str:
        """Human-readable one-line result for CLI feedback."""
        if self.success:
            return f"Sent (ID: {self.external_id})"
        return f"Failed: {self.error}"


class ActionExecutor(ABC):
    """Abstract base class for all action executors.

    Concrete subclasses handle a specific action type (e.g. GmailSendExecutor,
    SlackMessageExecutor). Each executor must validate the draft before executing
    to enforce whitelist and scope constraints (ACT-06, T-04-04).

    Methods:
        validate: Raises ValueError if the draft fails any pre-execution check.
        execute: Performs the external API call and returns an ActionResult.
    """

    @abstractmethod
    async def validate(self, draft: ActionDraft) -> None:
        """Pre-execution validation.

        Must be called before execute(). Raises ValueError if the draft fails
        any constraint (e.g. unknown recipient, missing OAuth scope).

        Args:
            draft: The ActionDraft to validate.

        Raises:
            ValueError: If validation fails. Message must be user-displayable.
        """

    @abstractmethod
    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Execute the action via external API.

        Called only after validate() passes AND user approves (T-04-02).
        Must never be called directly without going through the approval gate.

        Args:
            draft: The approved ActionDraft to execute.

        Returns:
            ActionResult with success/failure status and provider-assigned ID.
        """
