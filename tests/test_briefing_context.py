"""Tests for the briefing context builder (Plan 02-02, Task 2).

TDD approach: tests written first, then implementation.
Tests cover: conflict detection, email pagination, body fetching,
Slack ingestion, partial failure handling, raw_bodies population,
and concurrent body fetches.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from daily.briefing.context_builder import build_context, find_conflicts
from daily.briefing.models import BriefingContext
from daily.integrations.base import CalendarAdapter, EmailAdapter, MessageAdapter
from daily.integrations.models import (
    CalendarEvent,
    EmailMetadata,
    EmailPage,
    MessageMetadata,
    MessagePage,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_event(
    event_id: str,
    start_hour: int,
    end_hour: int,
    is_all_day: bool = False,
    start_minute: int = 0,
    end_minute: int = 0,
) -> CalendarEvent:
    """Create a CalendarEvent for testing."""
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    return CalendarEvent(
        event_id=event_id,
        title=f"Event {event_id}",
        start=base.replace(hour=start_hour, minute=start_minute),
        end=base.replace(hour=end_hour, minute=end_minute),
        attendees=["me@example.com"],
        location=None,
        is_all_day=is_all_day,
    )


def make_email_meta(
    message_id: str,
    thread_id: str = "thread-001",
    sender: str = "sender@example.com",
    hours_ago: float = 1.0,
) -> EmailMetadata:
    """Create EmailMetadata for testing."""
    now = datetime.now(tz=timezone.utc)
    return EmailMetadata(
        message_id=message_id,
        thread_id=thread_id,
        subject="Test email",
        sender=sender,
        recipient="me@example.com",
        timestamp=now - timedelta(hours=hours_ago),
        is_unread=True,
        labels=["INBOX"],
    )


def make_message(message_id: str, is_mention: bool = True, is_dm: bool = False) -> MessageMetadata:
    """Create MessageMetadata for testing."""
    return MessageMetadata(
        message_id=message_id,
        channel_id="C01GENERAL",
        sender_id="U01ALICE",
        timestamp=datetime.now(tz=timezone.utc),
        is_mention=is_mention,
        is_dm=is_dm,
    )


class MockEmailAdapter(EmailAdapter):
    """Mock email adapter returning fixture pages."""

    def __init__(self, pages: list[tuple[list[EmailMetadata], str | None]]):
        """pages: list of (emails, next_page_token) tuples."""
        self._pages = pages
        self._page_index = 0
        self.get_email_body = AsyncMock(side_effect=lambda msg_id: f"body of {msg_id}")

    async def list_emails(self, since: datetime, page_token: str | None = None) -> EmailPage:
        idx = self._page_index
        if idx >= len(self._pages):
            return EmailPage(emails=[], next_page_token=None)
        emails, next_token = self._pages[idx]
        self._page_index += 1
        return EmailPage(emails=emails, next_page_token=next_token)


class MockCalendarAdapter(CalendarAdapter):
    """Mock calendar adapter returning fixture events."""

    def __init__(self, events: list[CalendarEvent]):
        self._events = events

    async def list_events(self, since: datetime, until: datetime) -> list[CalendarEvent]:
        return self._events


class MockMessageAdapter(MessageAdapter):
    """Mock message adapter returning fixture messages."""

    def __init__(self, pages: list[tuple[list[MessageMetadata], str | None]]):
        self._pages = pages
        self._page_index = 0
        self.get_message_text = AsyncMock(side_effect=lambda msg_id, ch_id: f"text of {msg_id}")

    async def list_messages(self, channels: list[str], since: datetime) -> MessagePage:
        idx = self._page_index
        if idx >= len(self._pages):
            return MessagePage(messages=[], next_cursor=None)
        msgs, next_cursor = self._pages[idx]
        self._page_index += 1
        return MessagePage(messages=msgs, next_cursor=next_cursor)


# ─── find_conflicts tests ──────────────────────────────────────────────────────


def test_find_conflicts():
    """Two overlapping events are detected; non-overlapping events are not."""
    # standup: 09:00-09:15, strategy: 09:00-10:00 (overlap), lunch: 12:00-13:00 (no overlap)
    standup = make_event("standup", 9, 9, start_minute=0, end_minute=15)
    strategy = make_event("strategy", 9, 10)
    lunch = make_event("lunch", 12, 13)

    conflicts = find_conflicts([standup, strategy, lunch])

    conflict_ids = {frozenset(pair) for pair in conflicts}
    assert frozenset({"standup", "strategy"}) in conflict_ids
    # lunch should not appear in any conflict
    assert all("lunch" not in pair for pair in conflicts)


def test_find_conflicts_no_overlap():
    """Adjacent events (end == start of next) are NOT conflicts."""
    a = make_event("a", 9, 10)  # 09:00-10:00
    b = make_event("b", 10, 11)  # 10:00-11:00 — starts exactly when a ends

    conflicts = find_conflicts([a, b])
    assert conflicts == [], f"Adjacent events should not conflict, got: {conflicts}"


def test_find_conflicts_long_overlap():
    """A long meeting overlapping two shorter ones produces two conflict pairs."""
    # long: 09:00-12:00, short1: 10:00-11:00, short2: 11:00-12:00 (adjacent to short1, but overlaps long)
    long_meeting = make_event("long", 9, 12)
    short1 = make_event("short1", 10, 11)
    short2 = make_event("short2", 11, 12)  # overlaps long, adjacent to short1

    conflicts = find_conflicts([long_meeting, short1, short2])

    conflict_ids = {frozenset(pair) for pair in conflicts}
    # long overlaps both short1 and short2
    assert frozenset({"long", "short1"}) in conflict_ids, f"long+short1 not in {conflict_ids}"
    assert frozenset({"long", "short2"}) in conflict_ids, f"long+short2 not in {conflict_ids}"
    # short1 and short2 are adjacent (not overlapping)
    assert frozenset({"short1", "short2"}) not in conflict_ids, (
        f"short1+short2 should not conflict (adjacent): {conflict_ids}"
    )


def test_find_conflicts_excludes_all_day():
    """All-day events are excluded from conflict detection."""
    all_day = make_event("all_day", 0, 23, is_all_day=True)
    timed = make_event("timed", 9, 10)

    conflicts = find_conflicts([all_day, timed])
    assert conflicts == [], f"All-day events should be excluded, got: {conflicts}"


# ─── build_context email tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_email_context():
    """build_context fetches bodies for top_n emails only (not all 6)."""
    emails = [make_email_meta(f"msg-{i:03d}") for i in range(6)]
    adapter = MockEmailAdapter(pages=[(emails, None)])

    ctx = await build_context(
        user_id=1,
        email_adapters=[adapter],
        calendar_adapters=[],
        message_adapters=[],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=3,
    )

    assert isinstance(ctx, BriefingContext)
    assert len(ctx.emails) == 3
    # get_email_body should be called exactly 3 times (top_n), not 6
    assert adapter.get_email_body.call_count == 3


@pytest.mark.asyncio
async def test_build_email_pagination():
    """All pages are consumed before ranking — adapter with 2 pages yields 5 total emails."""
    page1_emails = [make_email_meta(f"msg-p1-{i}") for i in range(3)]
    page2_emails = [make_email_meta(f"msg-p2-{i}") for i in range(2)]
    adapter = MockEmailAdapter(pages=[
        (page1_emails, "token-page-2"),
        (page2_emails, None),
    ])

    ctx = await build_context(
        user_id=1,
        email_adapters=[adapter],
        calendar_adapters=[],
        message_adapters=[],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=5,
    )

    # All 5 emails should be ranked and returned (top_n=5 and we have exactly 5)
    assert len(ctx.emails) == 5
    # Adapter list_emails was called twice (page 1 + page 2)
    assert adapter._page_index == 2


@pytest.mark.asyncio
async def test_build_calendar_context(sample_events):
    """Calendar with 2 overlapping events yields 1 conflict pair."""
    adapter = MockCalendarAdapter(events=sample_events)

    ctx = await build_context(
        user_id=1,
        email_adapters=[],
        calendar_adapters=[adapter],
        message_adapters=[],
        vip_senders=frozenset(),
        user_email="me@example.com",
    )

    assert len(ctx.calendar.conflicts) == 1
    conflict_pair = frozenset(ctx.calendar.conflicts[0])
    assert conflict_pair == frozenset({"evt-standup", "evt-strategy"})


@pytest.mark.asyncio
async def test_build_slack_context(sample_messages):
    """Slack context includes only mentions and DMs (filters out plain channel messages)."""
    adapter = MockMessageAdapter(pages=[(sample_messages, None)])

    ctx = await build_context(
        user_id=1,
        email_adapters=[],
        calendar_adapters=[],
        message_adapters=[adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
    )

    # sample_messages has 4 messages: 2 mentions, 1 DM, 1 plain channel (not mention, not DM)
    # Only mentions and DMs should be included (3 total)
    assert len(ctx.slack.messages) == 3
    for msg in ctx.slack.messages:
        assert msg.is_mention or msg.is_dm, f"Non-mention/DM in slack context: {msg}"


@pytest.mark.asyncio
async def test_partial_failure():
    """If one adapter raises, pipeline continues with other sources."""

    class FailingEmailAdapter(EmailAdapter):
        async def list_emails(self, since: datetime, page_token: str | None = None) -> EmailPage:
            raise RuntimeError("Token expired")

        async def get_email_body(self, message_id: str) -> str:
            raise RuntimeError("Token expired")

    events = [make_event("evt1", 9, 10)]
    cal_adapter = MockCalendarAdapter(events=events)

    ctx = await build_context(
        user_id=1,
        email_adapters=[FailingEmailAdapter()],
        calendar_adapters=[cal_adapter],
        message_adapters=[],
        vip_senders=frozenset(),
        user_email="me@example.com",
    )

    # Email failed — should have empty emails
    assert ctx.emails == []
    # Calendar succeeded — should have events
    assert len(ctx.calendar.events) == 1
    # Should be a valid BriefingContext (pipeline did not crash)
    assert isinstance(ctx, BriefingContext)


@pytest.mark.asyncio
async def test_raw_bodies_populated():
    """raw_bodies is populated with email bodies and Slack message texts."""
    emails = [make_email_meta("email-001"), make_email_meta("email-002")]
    email_adapter = MockEmailAdapter(pages=[(emails, None)])

    slack_msgs = [
        make_message("slack-001", is_mention=True),
        make_message("slack-002", is_dm=True),
    ]
    msg_adapter = MockMessageAdapter(pages=[(slack_msgs, None)])

    ctx = await build_context(
        user_id=1,
        email_adapters=[email_adapter],
        calendar_adapters=[],
        message_adapters=[msg_adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=2,
    )

    # Both top-N email bodies should be in raw_bodies
    assert "email-001" in ctx.raw_bodies
    assert "email-002" in ctx.raw_bodies
    assert ctx.raw_bodies["email-001"] == "body of email-001"
    assert ctx.raw_bodies["email-002"] == "body of email-002"

    # Slack message texts should be in raw_bodies
    assert "slack-001" in ctx.raw_bodies
    assert "slack-002" in ctx.raw_bodies
    assert ctx.raw_bodies["slack-001"] == "text of slack-001"
    assert ctx.raw_bodies["slack-002"] == "text of slack-002"


@pytest.mark.asyncio
async def test_concurrent_body_fetch():
    """Body fetches use asyncio.gather — total time should be less than sum of individual times."""
    DELAY = 0.05  # 50ms per fetch

    async def slow_get_body(msg_id: str) -> str:
        await asyncio.sleep(DELAY)
        return f"body of {msg_id}"

    emails = [make_email_meta(f"msg-{i}") for i in range(3)]
    adapter = MockEmailAdapter(pages=[(emails, None)])
    adapter.get_email_body = AsyncMock(side_effect=slow_get_body)

    start = time.monotonic()
    ctx = await build_context(
        user_id=1,
        email_adapters=[adapter],
        calendar_adapters=[],
        message_adapters=[],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=3,
    )
    elapsed = time.monotonic() - start

    # 3 sequential fetches at 50ms each = 150ms+. Concurrent should be ~50ms.
    # Allow generous upper bound (3x single fetch) to avoid flakiness.
    assert elapsed < DELAY * 3 * 0.9, (  # at least 10% faster than sequential
        f"Body fetches appear sequential: {elapsed:.3f}s >= {DELAY * 3 * 0.9:.3f}s"
    )
    assert len(ctx.emails) == 3
