"""Tests for Gmail and Google Calendar adapters with mocked Google API responses."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from daily.integrations.base import CalendarAdapter, EmailAdapter
from daily.integrations.models import CalendarEvent, EmailMetadata, EmailPage


# ---------------------------------------------------------------------------
# Fixtures: realistic Gmail API response mocks
# ---------------------------------------------------------------------------

GMAIL_LIST_RESPONSE = {
    "messages": [
        {"id": "msg001", "threadId": "thread001"},
        {"id": "msg002", "threadId": "thread002"},
    ],
    "nextPageToken": "token_page2",
}

GMAIL_GET_RESPONSE_MSG001 = {
    "id": "msg001",
    "threadId": "thread001",
    "labelIds": ["INBOX", "UNREAD"],
    "internalDate": "1704067200000",  # 2024-01-01 00:00:00 UTC in ms
    "payload": {
        "headers": [
            {"name": "Subject", "value": "Test Email"},
            {"name": "From", "value": "sender@example.com"},
            {"name": "To", "value": "me@example.com"},
        ]
    },
}

GMAIL_GET_RESPONSE_MSG002 = {
    "id": "msg002",
    "threadId": "thread002",
    "labelIds": ["INBOX"],
    "internalDate": "1704153600000",  # 2024-01-02 00:00:00 UTC in ms
    "payload": {
        "headers": [
            {"name": "Subject", "value": "Another Email"},
            {"name": "From", "value": "other@example.com"},
            {"name": "To", "value": "me@example.com"},
        ]
    },
}

CALENDAR_LIST_RESPONSE = {
    "items": [
        {
            "id": "event001",
            "summary": "Team Standup",
            "start": {"dateTime": "2024-01-01T09:00:00Z"},
            "end": {"dateTime": "2024-01-01T09:30:00Z"},
            "attendees": [
                {"email": "alice@example.com"},
                {"email": "bob@example.com"},
            ],
            "location": "Conference Room A",
        },
        {
            "id": "event002",
            "summary": "All Day Event",
            "start": {"date": "2024-01-02"},
            "end": {"date": "2024-01-03"},
            "attendees": [],
        },
    ]
}


def _make_gmail_service():
    """Build a mock Gmail service matching the google-api-python-client interface."""
    svc = MagicMock()
    users = svc.users.return_value
    messages = users.messages.return_value

    # messages().list().execute()
    list_req = MagicMock()
    list_req.execute.return_value = GMAIL_LIST_RESPONSE
    messages.list.return_value = list_req

    # messages().get().execute() — different response per id
    def _get_msg(userId, id, format, metadataHeaders):
        req = MagicMock()
        req.execute.return_value = (
            GMAIL_GET_RESPONSE_MSG001 if id == "msg001" else GMAIL_GET_RESPONSE_MSG002
        )
        return req

    messages.get.side_effect = _get_msg
    return svc


def _make_calendar_service():
    """Build a mock Calendar service matching the google-api-python-client interface."""
    svc = MagicMock()
    events = svc.events.return_value

    list_req = MagicMock()
    list_req.execute.return_value = CALENDAR_LIST_RESPONSE
    events.list.return_value = list_req
    return svc


# ---------------------------------------------------------------------------
# GmailAdapter tests
# ---------------------------------------------------------------------------

class TestGmailAdapterInterface:
    def test_gmail_adapter_is_email_adapter(self):
        """GmailAdapter must implement EmailAdapter (isinstance check)."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())
        assert isinstance(adapter, EmailAdapter)


class TestGmailAdapterListEmails:
    @pytest.mark.asyncio
    async def test_list_emails_returns_email_page(self):
        """GmailAdapter.list_emails returns an EmailPage."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert isinstance(result, EmailPage)

    @pytest.mark.asyncio
    async def test_list_emails_returns_email_metadata_items(self):
        """GmailAdapter.list_emails returns EmailMetadata objects in the page."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert len(result.emails) == 2
        for email in result.emails:
            assert isinstance(email, EmailMetadata)

    @pytest.mark.asyncio
    async def test_list_emails_maps_fields_correctly(self):
        """GmailAdapter correctly maps Gmail API fields to EmailMetadata."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        first = result.emails[0]
        assert first.message_id == "msg001"
        assert first.thread_id == "thread001"
        assert first.subject == "Test Email"
        assert first.sender == "sender@example.com"
        assert first.is_unread is True
        assert "UNREAD" in first.labels

    @pytest.mark.asyncio
    async def test_list_emails_handles_pagination(self):
        """GmailAdapter passes next_page_token through in EmailPage."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert result.next_page_token == "token_page2"

    @pytest.mark.asyncio
    async def test_list_emails_no_body_field(self):
        """EmailMetadata objects must not contain body-related fields."""
        from daily.integrations.google.adapter import GmailAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_gmail_service()
            adapter = GmailAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        for email in result.emails:
            data = email.model_dump()
            assert "body" not in data
            assert "raw_body" not in data
            assert "content" not in data


# ---------------------------------------------------------------------------
# GoogleCalendarAdapter tests
# ---------------------------------------------------------------------------

class TestGoogleCalendarAdapterInterface:
    def test_calendar_adapter_is_calendar_adapter(self):
        """GoogleCalendarAdapter must implement CalendarAdapter."""
        from daily.integrations.google.adapter import GoogleCalendarAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_calendar_service()
            adapter = GoogleCalendarAdapter(credentials=MagicMock())
        assert isinstance(adapter, CalendarAdapter)


class TestGoogleCalendarAdapterListEvents:
    @pytest.mark.asyncio
    async def test_list_events_returns_list_of_calendar_events(self):
        """GoogleCalendarAdapter.list_events returns list[CalendarEvent]."""
        from daily.integrations.google.adapter import GoogleCalendarAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_calendar_service()
            adapter = GoogleCalendarAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 1, 31, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        assert isinstance(result, list)
        assert len(result) == 2
        for event in result:
            assert isinstance(event, CalendarEvent)

    @pytest.mark.asyncio
    async def test_list_events_maps_fields_correctly(self):
        """GoogleCalendarAdapter correctly maps Calendar API fields to CalendarEvent."""
        from daily.integrations.google.adapter import GoogleCalendarAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_calendar_service()
            adapter = GoogleCalendarAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 1, 31, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        first = result[0]
        assert first.event_id == "event001"
        assert first.title == "Team Standup"
        assert first.location == "Conference Room A"
        assert first.is_all_day is False
        assert "alice@example.com" in first.attendees
        assert "bob@example.com" in first.attendees

    @pytest.mark.asyncio
    async def test_list_events_detects_all_day_event(self):
        """GoogleCalendarAdapter marks events with 'date' key as all-day."""
        from daily.integrations.google.adapter import GoogleCalendarAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_calendar_service()
            adapter = GoogleCalendarAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 1, 31, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        all_day = result[1]
        assert all_day.event_id == "event002"
        assert all_day.is_all_day is True

    @pytest.mark.asyncio
    async def test_list_events_empty_attendees(self):
        """GoogleCalendarAdapter handles events with no attendees."""
        from daily.integrations.google.adapter import GoogleCalendarAdapter

        with patch("daily.integrations.google.adapter.build") as mock_build:
            mock_build.return_value = _make_calendar_service()
            adapter = GoogleCalendarAdapter(credentials=MagicMock())

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 1, 31, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        all_day = result[1]
        assert all_day.attendees == []
