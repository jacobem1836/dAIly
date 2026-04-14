"""
Tests for OutlookAdapter (Microsoft Graph email + calendar read adapter).

All tests mock msgraph-sdk API responses — no live Graph API calls.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.integrations.microsoft.adapter import OutlookAdapter
from daily.integrations.models import CalendarEvent, EmailMetadata, EmailPage


def _make_graph_message(
    *,
    id: str = "msg-001",
    conversation_id: str = "conv-001",
    subject: str = "Test Subject",
    sender_address: str = "sender@example.com",
    recipient_address: str = "recipient@example.com",
    received_dt: datetime | None = None,
    is_read: bool = False,
    categories: list[str] | None = None,
) -> MagicMock:
    """Build a mock Graph Message object."""
    if received_dt is None:
        received_dt = datetime(2026, 4, 5, 9, 0, 0, tzinfo=timezone.utc)
    if categories is None:
        categories = []

    msg = MagicMock()
    msg.id = id
    msg.conversation_id = conversation_id
    msg.subject = subject
    msg.received_date_time = received_dt
    msg.is_read = is_read
    msg.categories = categories

    # from_ and to_recipients mock hierarchy
    from_ea = MagicMock()
    from_ea.address = sender_address
    from_obj = MagicMock()
    from_obj.email_address = from_ea
    msg.from_ = from_obj

    recipient_ea = MagicMock()
    recipient_ea.address = recipient_address
    recipient_obj = MagicMock()
    recipient_obj.email_address = recipient_ea
    msg.to_recipients = [recipient_obj]

    return msg


def _make_graph_event(
    *,
    id: str = "evt-001",
    subject: str = "Team Meeting",
    start_dt: str = "2026-04-05T09:00:00Z",
    end_dt: str = "2026-04-05T10:00:00Z",
    attendee_emails: list[str] | None = None,
    location_name: str | None = "Conference Room A",
    is_all_day: bool = False,
) -> MagicMock:
    """Build a mock Graph Event object."""
    if attendee_emails is None:
        attendee_emails = ["alice@example.com", "bob@example.com"]

    event = MagicMock()
    event.id = id
    event.subject = subject
    event.is_all_day = is_all_day

    start = MagicMock()
    start.date_time = start_dt
    event.start = start

    end = MagicMock()
    end.date_time = end_dt
    event.end = end

    attendees = []
    for email in attendee_emails:
        ea = MagicMock()
        ea.address = email
        att = MagicMock()
        att.email_address = ea
        attendees.append(att)
    event.attendees = attendees

    if location_name:
        loc = MagicMock()
        loc.display_name = location_name
        event.location = loc
    else:
        event.location = None

    return event


@pytest.fixture
def mock_graph_client():
    """Patch GraphServiceClient to avoid live network calls.

    GraphServiceClient is imported inside OutlookAdapter.__init__ to avoid
    top-level import side effects. Patch the canonical location in msgraph.
    """
    with patch("msgraph.GraphServiceClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def adapter(mock_graph_client):
    return OutlookAdapter(access_token="fake_access_token")


class TestOutlookAdapterListEmails:
    @pytest.mark.asyncio
    async def test_returns_email_page_type(self, adapter, mock_graph_client):
        """list_emails must return an EmailPage."""
        response = MagicMock()
        response.value = [_make_graph_message()]
        response.odata_next_link = None
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert isinstance(result, EmailPage)

    @pytest.mark.asyncio
    async def test_maps_fields_correctly(self, adapter, mock_graph_client):
        """EmailMetadata fields must map correctly from Graph API message."""
        received = datetime(2026, 4, 5, 8, 30, 0, tzinfo=timezone.utc)
        msg = _make_graph_message(
            id="msg-xyz",
            conversation_id="conv-xyz",
            subject="Important Update",
            sender_address="alice@example.com",
            recipient_address="bob@example.com",
            received_dt=received,
            is_read=False,
            categories=["Important"],
        )

        response = MagicMock()
        response.value = [msg]
        response.odata_next_link = None
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert len(result.emails) == 1
        email = result.emails[0]
        assert isinstance(email, EmailMetadata)
        assert email.message_id == "msg-xyz"
        assert email.thread_id == "conv-xyz"
        assert email.subject == "Important Update"
        assert email.sender == "alice@example.com"
        assert email.recipient == "bob@example.com"
        assert email.timestamp == received
        assert email.is_unread is True  # is_read=False → is_unread=True
        assert "Important" in email.labels

    @pytest.mark.asyncio
    async def test_no_body_in_select(self, adapter, mock_graph_client):
        """Graph API request must not include body or uniqueBody in $select.

        T-1-16: Metadata only — body fields must be excluded.
        """
        response = MagicMock()
        response.value = []
        response.odata_next_link = None
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        from kiota_abstractions.base_request_configuration import RequestConfiguration
        from msgraph.generated.users.item.messages.messages_request_builder import (
            MessagesRequestBuilder,
        )

        captured_configs = []

        async def capture_get(request_configuration=None):
            captured_configs.append(request_configuration)
            return response

        mock_graph_client.me.messages.get = capture_get

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        await adapter.list_emails(since=since)

        assert len(captured_configs) == 1
        config = captured_configs[0]
        assert config is not None
        select_fields = config.query_parameters.select
        assert "body" not in select_fields
        assert "uniqueBody" not in select_fields
        # Required metadata fields must be present
        assert "id" in select_fields
        assert "conversationId" in select_fields
        assert "subject" in select_fields

    @pytest.mark.asyncio
    async def test_pagination_next_page_token(self, adapter, mock_graph_client):
        """next_page_token must be set when odata_next_link is present."""
        response = MagicMock()
        response.value = [_make_graph_message()]
        response.odata_next_link = (
            "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=abc123"
        )
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert result.next_page_token == "abc123"

    @pytest.mark.asyncio
    async def test_no_pagination_when_no_next_link(self, adapter, mock_graph_client):
        """next_page_token must be None when odata_next_link is absent."""
        response = MagicMock()
        response.value = [_make_graph_message()]
        response.odata_next_link = None
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert result.next_page_token is None

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_page(self, adapter, mock_graph_client):
        """Empty value list returns EmailPage with no emails."""
        response = MagicMock()
        response.value = []
        response.odata_next_link = None
        mock_graph_client.me.messages.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_emails(since=since)

        assert isinstance(result, EmailPage)
        assert result.emails == []
        assert result.next_page_token is None


class TestOutlookAdapterListEvents:
    @pytest.mark.asyncio
    async def test_returns_list_of_calendar_events(self, adapter, mock_graph_client):
        """list_events must return list[CalendarEvent]."""
        response = MagicMock()
        response.value = [_make_graph_event()]
        mock_graph_client.me.calendar_view.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], CalendarEvent)

    @pytest.mark.asyncio
    async def test_maps_event_fields_correctly(self, adapter, mock_graph_client):
        """CalendarEvent fields must map correctly from Graph API event."""
        event = _make_graph_event(
            id="evt-xyz",
            subject="Quarterly Review",
            start_dt="2026-04-05T14:00:00Z",
            end_dt="2026-04-05T15:00:00Z",
            attendee_emails=["carol@example.com", "dave@example.com"],
            location_name="Boardroom",
            is_all_day=False,
        )

        response = MagicMock()
        response.value = [event]
        mock_graph_client.me.calendar_view.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        ev = result[0]
        assert ev.event_id == "evt-xyz"
        assert ev.title == "Quarterly Review"
        assert ev.start == datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        assert ev.end == datetime(2026, 4, 5, 15, 0, 0, tzinfo=timezone.utc)
        assert "carol@example.com" in ev.attendees
        assert "dave@example.com" in ev.attendees
        assert ev.location == "Boardroom"
        assert ev.is_all_day is False

    @pytest.mark.asyncio
    async def test_all_day_event(self, adapter, mock_graph_client):
        """is_all_day flag must be correctly mapped."""
        event = _make_graph_event(
            is_all_day=True,
            start_dt="2026-04-05T00:00:00",
            end_dt="2026-04-05T00:00:00",
        )

        response = MagicMock()
        response.value = [event]
        mock_graph_client.me.calendar_view.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        assert result[0].is_all_day is True

    @pytest.mark.asyncio
    async def test_no_location_returns_none(self, adapter, mock_graph_client):
        """Location must be None when event has no location."""
        event = _make_graph_event(location_name=None)

        response = MagicMock()
        response.value = [event]
        mock_graph_client.me.calendar_view.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        assert result[0].location is None

    @pytest.mark.asyncio
    async def test_empty_event_list(self, adapter, mock_graph_client):
        """Empty response value returns empty list."""
        response = MagicMock()
        response.value = []
        mock_graph_client.me.calendar_view.get = AsyncMock(return_value=response)

        since = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        result = await adapter.list_events(since=since, until=until)

        assert result == []
