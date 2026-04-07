"""
Briefing context builder — assembles BriefingContext from all three data sources.

Orchestrates the data-gathering phase of the briefing pipeline:
  1. Email: fetch all pages -> rank -> fetch top-N bodies concurrently
  2. Calendar: fetch events -> detect conflicts
  3. Slack: fetch all pages -> filter to mentions/DMs -> fetch message texts concurrently

raw_bodies is populated here and travels in-memory to the redactor via pipeline.py (Plan 04).
BriefingContext.raw_bodies uses Field(exclude=True) so raw content never serialises
to cache/DB (SEC-02 contract, T-02-03).

Design decisions:
- Partial failure handling: each phase is try/except isolated. If one source fails,
  the pipeline continues with defaults for that source (BRIEF always delivers — D-01).
- Concurrent body fetches: asyncio.gather for email bodies and Slack message texts.
- Pagination: all pages consumed before ranking (email) or processing (Slack).
- Calendar conflicts: O(n^2) sweep — correct and simple for M1 scale (few events).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from daily.briefing.models import (
    BriefingContext,
    CalendarContext,
    RankedEmail,
    SlackContext,
)
from daily.briefing.ranker import rank_emails
from daily.integrations.base import CalendarAdapter, EmailAdapter, MessageAdapter
from daily.integrations.models import CalendarEvent, EmailMetadata, MessageMetadata

logger = logging.getLogger(__name__)


def find_conflicts(events: list[CalendarEvent]) -> list[tuple[str, str]]:
    """Detect overlapping calendar events (exclude all-day events).

    Uses a sorted sweep: for each event A, check all subsequent events B.
    Since events are sorted by start time, once B.start >= A.end, all
    subsequent events also start >= A.end (sorted invariant), so we break.
    This correctly handles the long-meeting case: a 3-hour meeting A checked
    against short1 (overlap -> add), short2 (if short2.start < A.end -> add).

    Args:
        events: List of CalendarEvent objects to check for overlaps.

    Returns:
        List of (event_id, event_id) pairs that overlap in time.
    """
    # Filter out all-day events
    timed = [e for e in events if not e.is_all_day]

    # Sort by start time
    timed.sort(key=lambda e: e.start)

    conflicts: list[tuple[str, str]] = []
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if b.start < a.end:
                conflicts.append((a.event_id, b.event_id))
            else:
                # Since events are sorted by start, all subsequent events also
                # start >= a.end — no more overlaps possible for this 'a'.
                break

    return conflicts


async def _fetch_all_emails(
    adapters: list[EmailAdapter], since: datetime
) -> list[EmailMetadata]:
    """Fetch all email metadata from all adapters, handling pagination.

    Loops through pages until next_page_token is None for each adapter.

    Args:
        adapters: List of email adapter instances to query.
        since: Only fetch emails after this datetime.

    Returns:
        Combined list of EmailMetadata from all adapters and all pages.
    """
    all_emails: list[EmailMetadata] = []
    for adapter in adapters:
        page_token: str | None = None
        while True:
            page = await adapter.list_emails(since=since, page_token=page_token)
            all_emails.extend(page.emails)
            page_token = page.next_page_token
            if page_token is None:
                break
    return all_emails


async def _fetch_all_messages(
    adapters: list[MessageAdapter], since: datetime
) -> list[MessageMetadata]:
    """Fetch all message metadata from all adapters, handling pagination.

    Loops through pages until next_cursor is None for each adapter.

    Args:
        adapters: List of message adapter instances to query.
        since: Only fetch messages after this datetime.

    Returns:
        Combined list of MessageMetadata from all adapters and all pages.
    """
    all_messages: list[MessageMetadata] = []
    for adapter in adapters:
        cursor: str | None = None
        while True:
            page = await adapter.list_messages(channels=[], since=since)
            all_messages.extend(page.messages)
            cursor = page.next_cursor
            if cursor is None:
                break
    return all_messages


async def build_context(
    user_id: int,
    email_adapters: list[EmailAdapter],
    calendar_adapters: list[CalendarAdapter],
    message_adapters: list[MessageAdapter],
    vip_senders: frozenset[str],
    user_email: str,
    top_n: int = 5,
) -> BriefingContext:
    """Assemble a BriefingContext from email, calendar, and Slack data sources.

    Each data source is isolated in try/except — partial failure means that
    source returns empty defaults while others continue (briefing always delivers).

    SEC-02 contract: raw_bodies is populated here with fetched email bodies and
    Slack message texts. Because BriefingContext.raw_bodies has Field(exclude=True),
    it is never serialised to cache or DB. It travels in-memory to the redactor
    in pipeline.py (Plan 04).

    Args:
        user_id: ID of the user for whom the briefing is being built.
        email_adapters: List of email adapter instances (Gmail, Outlook, etc).
        calendar_adapters: List of calendar adapter instances.
        message_adapters: List of message adapter instances (Slack, Teams, etc).
        vip_senders: Set of VIP sender email addresses for priority override.
        user_email: User's email address for recipient comparison in ranker.
        top_n: Number of top-ranked emails to include in the briefing.

    Returns:
        BriefingContext with emails, calendar, slack, and raw_bodies populated.
    """
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=24)
    until = now + timedelta(hours=48)

    # Accumulate all fetched raw bodies (email + slack) for SEC-02 redactor handoff
    raw_bodies: dict[str, str] = {}

    # ── Email phase ────────────────────────────────────────────────────────────
    ranked_emails: list[RankedEmail] = []
    try:
        all_emails = await _fetch_all_emails(email_adapters, since)
        ranked_emails = rank_emails(all_emails, vip_senders, user_email, top_n=top_n)

        # Fetch bodies for top-N emails concurrently (asyncio.gather)
        async def _fetch_email_body(
            adapter: EmailAdapter, message_id: str
        ) -> tuple[str, str]:
            body = await adapter.get_email_body(message_id)
            return message_id, body

        # For M1 single-adapter, fetch all from first adapter.
        # In multi-adapter scenario, we use the first adapter for all bodies
        # (adapter routing by email domain is a M2 concern).
        body_tasks = []
        if email_adapters:
            adapter = email_adapters[0]
            body_tasks = [
                _fetch_email_body(adapter, ranked.metadata.message_id)
                for ranked in ranked_emails
            ]

        results = await asyncio.gather(*body_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Email body fetch failed: %s", result)
                continue
            msg_id, body = result
            raw_bodies[msg_id] = body

    except Exception as exc:
        logger.error("Email phase failed, continuing with empty emails: %s", exc)
        ranked_emails = []

    # ── Calendar phase ─────────────────────────────────────────────────────────
    cal_ctx = CalendarContext(events=[], conflicts=[])
    try:
        all_events: list[CalendarEvent] = []
        for adapter in calendar_adapters:
            events = await adapter.list_events(since=now, until=until)
            all_events.extend(events)

        conflicts = find_conflicts(all_events)
        cal_ctx = CalendarContext(events=all_events, conflicts=conflicts)

    except Exception as exc:
        logger.error("Calendar phase failed, continuing with empty calendar: %s", exc)

    # ── Slack phase ────────────────────────────────────────────────────────────
    slack_ctx = SlackContext(messages=[])
    try:
        all_messages = await _fetch_all_messages(message_adapters, since)

        # Filter to mentions and DMs only (BRIEF-05)
        filtered = [m for m in all_messages if m.is_mention or m.is_dm]

        # Fetch message texts concurrently (asyncio.gather)
        async def _fetch_message_text(
            adapter: MessageAdapter, msg: MessageMetadata
        ) -> tuple[str, str]:
            text = await adapter.get_message_text(msg.message_id, msg.channel_id)
            return msg.message_id, text

        text_tasks = []
        if message_adapters and filtered:
            adapter = message_adapters[0]
            text_tasks = [
                _fetch_message_text(adapter, msg)
                for msg in filtered
            ]

        text_results = await asyncio.gather(*text_tasks, return_exceptions=True)
        for result in text_results:
            if isinstance(result, Exception):
                logger.warning("Slack message text fetch failed: %s", result)
                continue
            msg_id, text = result
            raw_bodies[msg_id] = text

        slack_ctx = SlackContext(messages=filtered)

    except Exception as exc:
        logger.error("Slack phase failed, continuing with empty slack: %s", exc)

    return BriefingContext(
        user_id=user_id,
        generated_at=now,
        emails=ranked_emails,
        calendar=cal_ctx,
        slack=slack_ctx,
        raw_bodies=raw_bodies,
    )
