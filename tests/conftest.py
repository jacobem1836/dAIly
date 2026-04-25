"""Shared pytest fixtures for dAIly test suite."""
import os
from datetime import datetime, timezone

import pytest

from daily.integrations.models import CalendarEvent, EmailMetadata, MessageMetadata


@pytest.fixture
def vault_key() -> bytes:
    """Returns a fresh 32-byte key for AES-256 encryption tests."""
    return os.urandom(32)


@pytest.fixture
def sample_emails() -> list[EmailMetadata]:
    """Returns a diverse list of EmailMetadata for briefing pipeline tests."""
    base_time = datetime(2026, 4, 7, 8, 0, 0, tzinfo=timezone.utc)
    return [
        EmailMetadata(
            message_id="msg-vip-001",
            thread_id="thread-001",
            subject="Q2 Strategy Update",
            sender="vip@example.com",
            recipient="me@example.com",
            timestamp=base_time,
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        ),
        EmailMetadata(
            message_id="msg-urgent-002",
            thread_id="thread-002",
            subject="URGENT: Production incident",
            sender="oncall@example.com",
            recipient="me@example.com",
            timestamp=base_time,
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        ),
        EmailMetadata(
            message_id="msg-old-003",
            thread_id="thread-003",
            subject="Old newsletter",
            sender="newsletter@example.com",
            recipient="me@example.com",
            timestamp=datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc),
            is_unread=False,
            labels=["INBOX"],
        ),
        EmailMetadata(
            message_id="msg-cc-004",
            thread_id="thread-004",
            subject="FYI: Meeting notes",
            sender="colleague@example.com",
            recipient="team@example.com",
            timestamp=base_time,
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        ),
        EmailMetadata(
            message_id="msg-normal-005",
            thread_id="thread-005",
            subject="Weekly status",
            sender="manager@example.com",
            recipient="me@example.com",
            timestamp=base_time,
            is_unread=True,
            labels=["INBOX", "UNREAD"],
        ),
        EmailMetadata(
            message_id="msg-promo-006",
            thread_id="thread-006",
            subject="50% off sale this weekend!",
            sender="promo@shop.com",
            recipient="me@example.com",
            timestamp=base_time,
            is_unread=False,
            labels=["PROMOTIONS"],
        ),
    ]


@pytest.fixture
def sample_events() -> list[CalendarEvent]:
    """Returns calendar events including one overlap pair for conflict detection tests."""
    base_date = datetime(2026, 4, 7, tzinfo=timezone.utc)
    return [
        CalendarEvent(
            event_id="evt-standup",
            title="Daily Standup",
            start=datetime(2026, 4, 7, 9, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 7, 9, 15, 0, tzinfo=timezone.utc),
            attendees=["me@example.com", "teammate@example.com"],
            location=None,
            is_all_day=False,
        ),
        CalendarEvent(
            event_id="evt-strategy",
            title="Q2 Strategy Review",
            start=datetime(2026, 4, 7, 9, 0, 0, tzinfo=timezone.utc),  # overlaps standup
            end=datetime(2026, 4, 7, 10, 0, 0, tzinfo=timezone.utc),
            attendees=["me@example.com", "ceo@example.com"],
            location="Board Room",
            is_all_day=False,
        ),
        CalendarEvent(
            event_id="evt-lunch",
            title="Lunch with Ben",
            start=datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 7, 13, 0, 0, tzinfo=timezone.utc),
            attendees=["me@example.com", "ben@example.com"],
            location="Cafe",
            is_all_day=False,
        ),
        CalendarEvent(
            event_id="evt-allday",
            title="Company Offsite",
            start=datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc),
            attendees=["me@example.com"],
            location="Gold Coast",
            is_all_day=True,
        ),
    ]


@pytest.fixture
def sample_messages() -> list[MessageMetadata]:
    """Returns Slack messages including mentions and DMs for briefing pipeline tests."""
    base_time = datetime(2026, 4, 7, 8, 30, 0, tzinfo=timezone.utc)
    return [
        MessageMetadata(
            message_id="1712480400.000001",
            channel_id="C01GENERAL",
            sender_id="U01ALICE",
            timestamp=base_time,
            is_mention=True,
            is_dm=False,
        ),
        MessageMetadata(
            message_id="1712480401.000002",
            channel_id="D01DM123",
            sender_id="U01BOB",
            timestamp=base_time,
            is_mention=False,
            is_dm=True,
        ),
        MessageMetadata(
            message_id="1712480402.000003",
            channel_id="C01ENGINEERING",
            sender_id="U01CAROL",
            timestamp=base_time,
            is_mention=False,
            is_dm=False,
        ),
        MessageMetadata(
            message_id="1712480403.000004",
            channel_id="C01GENERAL",
            sender_id="U01DAVE",
            timestamp=base_time,
            is_mention=True,
            is_dm=False,
        ),
    ]


@pytest.fixture
def vip_senders() -> frozenset[str]:
    """Returns a set of VIP sender emails for priority scoring tests."""
    return frozenset({"vip@example.com"})
