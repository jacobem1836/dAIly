"""Tests for briefing pipeline Pydantic models."""
from datetime import datetime, timezone

import pytest

from daily.briefing.models import (
    BriefingContext,
    BriefingOutput,
    CalendarContext,
    RankedEmail,
    RedactedItem,
    SlackContext,
)
from daily.integrations.models import EmailMetadata


def _make_briefing_context(
    emails=None,
    calendar_events=None,
    slack_messages=None,
    raw_bodies=None,
) -> BriefingContext:
    """Helper to build a minimal BriefingContext for tests."""
    return BriefingContext(
        user_id=1,
        generated_at=datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc),
        emails=emails or [],
        calendar=CalendarContext(events=calendar_events or [], conflicts=[]),
        slack=SlackContext(messages=slack_messages or []),
        raw_bodies=raw_bodies or {},
    )


def test_briefing_context_instantiation(sample_emails, sample_events, sample_messages):
    """BriefingContext can be instantiated with all required fields."""
    ranked = [RankedEmail(metadata=e, score=float(i)) for i, e in enumerate(sample_emails)]
    ctx = BriefingContext(
        user_id=42,
        generated_at=datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc),
        emails=ranked,
        calendar=CalendarContext(events=sample_events, conflicts=[("evt-standup", "evt-strategy")]),
        slack=SlackContext(messages=sample_messages),
    )
    assert ctx.user_id == 42
    assert len(ctx.emails) == len(sample_emails)
    assert len(ctx.calendar.events) == len(sample_events)
    assert len(ctx.slack.messages) == len(sample_messages)


def test_briefing_output_serialises_to_redis_schema():
    """BriefingOutput serialises to dict matching Redis cache schema."""
    now = datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc)
    output = BriefingOutput(narrative="Good morning! Here is your briefing.", generated_at=now)
    data = output.model_dump()
    assert "narrative" in data
    assert "generated_at" in data
    assert "version" in data
    assert data["narrative"] == "Good morning! Here is your briefing."
    assert data["version"] == 1


def test_ranked_email_accepts_email_metadata():
    """RankedEmail accepts an EmailMetadata in its metadata field."""
    meta = EmailMetadata(
        message_id="msg-001",
        thread_id="thread-001",
        subject="Test Subject",
        sender="sender@example.com",
        recipient="me@example.com",
        timestamp=datetime(2026, 4, 7, 8, 0, 0, tzinfo=timezone.utc),
        is_unread=True,
        labels=["INBOX"],
    )
    ranked = RankedEmail(metadata=meta, score=85.0)
    assert ranked.metadata.message_id == "msg-001"
    assert ranked.score == 85.0
    assert ranked.summary == ""


def test_to_prompt_string_contains_all_three_sections(sample_emails, sample_events, sample_messages):
    """to_prompt_string() returns a string containing all three section headers."""
    ranked = [RankedEmail(metadata=e, score=float(i * 10)) for i, e in enumerate(sample_emails)]
    ctx = BriefingContext(
        user_id=1,
        generated_at=datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc),
        emails=ranked,
        calendar=CalendarContext(events=sample_events, conflicts=[]),
        slack=SlackContext(messages=sample_messages),
    )
    prompt = ctx.to_prompt_string()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "EMAILS" in prompt
    assert "CALENDAR" in prompt
    assert "SLACK" in prompt


def test_to_prompt_string_empty_sources():
    """to_prompt_string() returns 'Nothing notable' for empty sources (per D-08)."""
    ctx = _make_briefing_context()
    prompt = ctx.to_prompt_string()
    assert "Nothing notable today" in prompt or "Nothing scheduled" in prompt
    assert "EMAILS" in prompt
    assert "CALENDAR" in prompt
    assert "SLACK" in prompt


def test_model_dump_excludes_raw_bodies():
    """BriefingContext.model_dump() does NOT include raw_bodies."""
    ctx = _make_briefing_context(raw_bodies={"msg-001": "Sensitive email body text"})
    # Verify raw_bodies is accessible in-memory
    assert ctx.raw_bodies == {"msg-001": "Sensitive email body text"}
    # Verify it is excluded from serialisation
    dumped = ctx.model_dump()
    assert "raw_bodies" not in dumped


def test_model_dump_json_excludes_raw_bodies():
    """BriefingContext.model_dump_json() does NOT contain 'raw_bodies' (SEC-02)."""
    ctx = _make_briefing_context(raw_bodies={"msg-001": "Sensitive email body text"})
    json_str = ctx.model_dump_json()
    assert "raw_bodies" not in json_str
    assert "Sensitive email body text" not in json_str


def test_briefing_context_raw_bodies_accessible_in_memory():
    """BriefingContext can be instantiated with raw_bodies and the field is readable in-memory."""
    ctx = _make_briefing_context(raw_bodies={"id1": "body text", "id2": "another body"})
    assert ctx.raw_bodies["id1"] == "body text"
    assert ctx.raw_bodies["id2"] == "another body"


def test_redacted_item_fields():
    """RedactedItem has correct source_id, source_type, and summary fields."""
    item = RedactedItem(source_id="msg-001", source_type="email", summary="Project update confirmed.")
    assert item.source_id == "msg-001"
    assert item.source_type == "email"
    assert item.summary == "Project update confirmed."
