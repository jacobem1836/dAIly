"""
Pydantic data models for the briefing pipeline.

These models define the data contracts between pipeline stages:
  context_builder -> redactor -> narrator -> cache

SEC-02: BriefingContext.raw_bodies uses Field(exclude=True) so raw bodies
travel in-memory from context_builder to redactor but never serialise
to cache, DB, or logs.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from daily.integrations.models import CalendarEvent, EmailMetadata, MessageMetadata


class RankedEmail(BaseModel):
    """Email metadata with computed priority score."""

    metadata: EmailMetadata
    score: float
    summary: str = ""  # populated after redaction step


class CalendarContext(BaseModel):
    """Calendar events with conflict info."""

    events: list[CalendarEvent]
    conflicts: list[tuple[str, str]]  # pairs of event_ids that overlap


class SlackContext(BaseModel):
    """Slack messages selected for briefing."""

    messages: list[MessageMetadata]
    summaries: dict[str, str] = {}  # message_id -> redacted summary


class BriefingContext(BaseModel):
    """Assembled context passed to narrator LLM. In-memory only, never persisted (SEC-04)."""

    user_id: int
    generated_at: datetime
    emails: list[RankedEmail]
    calendar: CalendarContext
    slack: SlackContext
    raw_bodies: dict[str, str] = Field(default_factory=dict, exclude=True)
    # raw_bodies maps message_id -> raw body text. Excluded from serialisation
    # so raw content never leaks to cache/DB. Populated by context_builder,
    # consumed by redactor in pipeline.py. Key contract for SEC-02.

    def to_prompt_string(self) -> str:
        """Format context for the narrator LLM prompt.

        Addresses review concern: to_prompt_string() must be fully implemented,
        not a stub. This plan owns the implementation because the model defines
        the data shape.
        """
        sections = []

        # Email section
        if self.emails:
            email_lines = []
            for ranked in self.emails:
                meta = ranked.metadata
                summary_text = ranked.summary or f"Subject: {meta.subject}"
                email_lines.append(
                    f"From: {meta.sender} | Score: {ranked.score:.0f} | {summary_text}"
                )
            sections.append("EMAILS (ranked by priority):\n" + "\n".join(email_lines))
        else:
            sections.append("EMAILS: Nothing notable today.")

        # Calendar section
        if self.calendar.events:
            event_lines = []
            for evt in self.calendar.events:
                time_str = (
                    "All day"
                    if evt.is_all_day
                    else f"{evt.start.strftime('%H:%M')}-{evt.end.strftime('%H:%M')}"
                )
                event_lines.append(f"{time_str}: {evt.title}")
            conflict_note = ""
            if self.calendar.conflicts:
                pairs = [f"{a} & {b}" for a, b in self.calendar.conflicts]
                conflict_note = f"\nConflicts detected: {'; '.join(pairs)}"
            sections.append(
                "CALENDAR (next 48h):\n" + "\n".join(event_lines) + conflict_note
            )
        else:
            sections.append("CALENDAR: Nothing scheduled in the next 48 hours.")

        # Slack section
        if self.slack.messages:
            slack_lines = []
            for msg in self.slack.messages:
                summary_text = self.slack.summaries.get(msg.message_id, "")
                tag = "[mention]" if msg.is_mention else "[DM]"
                slack_lines.append(f"{tag} {msg.sender_id}: {summary_text}")
            sections.append("SLACK:\n" + "\n".join(slack_lines))
        else:
            sections.append("SLACK: Nothing notable today.")

        return "\n\n".join(sections)


class BriefingOutput(BaseModel):
    """Final output cached in Redis (per D-14)."""

    narrative: str
    generated_at: datetime
    version: int = 1


class RedactedItem(BaseModel):
    """Single item after summarise+redact step (per D-09/D-10)."""

    source_id: str
    source_type: str  # "email" or "slack"
    summary: str  # GPT-4.1 mini summary with credentials stripped
