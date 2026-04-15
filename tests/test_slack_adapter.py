"""Tests for Slack message adapter with mocked Slack API responses."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from daily.integrations.base import MessageAdapter
from daily.integrations.models import MessageMetadata, MessagePage


# ---------------------------------------------------------------------------
# Fixtures: realistic Slack API response mocks
# ---------------------------------------------------------------------------

SLACK_HISTORY_RESPONSE = {
    "ok": True,
    "messages": [
        {
            "ts": "1704067200.000100",
            "user": "U01234ABCD",
            "text": "Hello, world! <@U99999BOT>",
            "type": "message",
        },
        {
            "ts": "1704153600.000200",
            "user": "U05678EFGH",
            "text": "Another message here",
            "type": "message",
        },
    ],
    "has_more": True,
    "response_metadata": {
        "next_cursor": "bmV4dF90czoxNzA0MDY3MjAw",
    },
}

SLACK_HISTORY_RESPONSE_NO_CURSOR = {
    "ok": True,
    "messages": [
        {
            "ts": "1704067200.000100",
            "user": "U01234ABCD",
            "text": "Only message",
            "type": "message",
        },
    ],
    "has_more": False,
    "response_metadata": {
        "next_cursor": "",
    },
}

SLACK_HISTORY_RESPONSE_DM = {
    "ok": True,
    "messages": [
        {
            "ts": "1704240000.000300",
            "user": "U01234ABCD",
            "text": "Direct message",
            "type": "message",
        },
    ],
    "has_more": False,
    "response_metadata": {
        "next_cursor": "",
    },
}


def _make_mock_response(data: dict) -> MagicMock:
    """Wrap a dict in a MagicMock mirroring slack_sdk SlackResponse interface."""
    mock = MagicMock()
    mock.__getitem__ = lambda self, key: data[key]
    mock.get = lambda key, default=None: data.get(key, default)
    # Allow dict-style access for response_metadata
    mock.data = data
    return mock


def _make_slack_client(history_response: dict = None) -> MagicMock:
    """Build a mock slack_sdk WebClient.

    Uses side_effect so the pagination loop can terminate: if the response
    has a next_cursor, the second call returns an empty terminal page.
    """
    if history_response is None:
        history_response = SLACK_HISTORY_RESPONSE

    terminal = {"ok": True, "messages": [], "response_metadata": {"next_cursor": ""}}
    client = MagicMock()
    client.conversations_history.side_effect = [
        _make_mock_response(history_response),
        _make_mock_response(terminal),
    ]
    return client


# ---------------------------------------------------------------------------
# SlackAdapter interface tests
# ---------------------------------------------------------------------------

class TestSlackAdapterInterface:
    def test_slack_adapter_is_message_adapter(self):
        """SlackAdapter must implement MessageAdapter (isinstance check)."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")
        assert isinstance(adapter, MessageAdapter)


# ---------------------------------------------------------------------------
# SlackAdapter.list_messages tests
# ---------------------------------------------------------------------------

class TestSlackAdapterListMessages:
    @pytest.mark.asyncio
    async def test_list_messages_returns_message_page(self):
        """SlackAdapter.list_messages returns a MessagePage."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        assert isinstance(result, MessagePage)

    @pytest.mark.asyncio
    async def test_list_messages_returns_message_metadata_items(self):
        """SlackAdapter.list_messages returns MessageMetadata objects in the page."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        assert len(result.messages) == 2
        for msg in result.messages:
            assert isinstance(msg, MessageMetadata)

    @pytest.mark.asyncio
    async def test_list_messages_maps_fields_correctly(self):
        """SlackAdapter correctly maps Slack API fields to MessageMetadata."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        first = result.messages[0]
        assert first.message_id == "1704067200.000100"
        assert first.channel_id == "C01CHANNEL"
        assert first.sender_id == "U01234ABCD"
        assert isinstance(first.timestamp, datetime)
        assert isinstance(first.is_mention, bool)
        assert isinstance(first.is_dm, bool)

    @pytest.mark.asyncio
    async def test_list_messages_no_text_field(self):
        """MessageMetadata objects must not contain text or body fields (T-1-12)."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        for msg in result.messages:
            data = msg.model_dump()
            assert "text" not in data
            assert "body" not in data
            assert "content" not in data
            assert "raw_body" not in data

    @pytest.mark.asyncio
    async def test_list_messages_cursor_pagination(self):
        """SlackAdapter.list_messages always returns next_cursor=None (FIX-02: pagination is internal).

        The adapter paginates internally via _fetch_channel_messages.
        Callers always receive a complete in-window result — next_cursor is always None.
        """
        from daily.integrations.slack.adapter import SlackAdapter

        # SLACK_HISTORY_RESPONSE has next_cursor set, but after FIX-02 the adapter
        # consumes cursor internally — returned MessagePage always has next_cursor=None.
        # The response has no second page (side_effect would exhaust), so we need to
        # provide a terminal response when the adapter requests cursor "bmV4dF90czoxNzA0MDY3MjAw".
        page2 = {
            "ok": True,
            "messages": [],
            "response_metadata": {"next_cursor": ""},
        }
        client = MagicMock()
        client.conversations_history.side_effect = [
            _make_mock_response(SLACK_HISTORY_RESPONSE),
            _make_mock_response(page2),
        ]

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_messages_empty_cursor_becomes_none(self):
        """SlackAdapter returns next_cursor=None when Slack response has no more pages."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client(SLACK_HISTORY_RESPONSE_NO_CURSOR)
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_messages_empty_channel_list_returns_empty_page(self):
        """SlackAdapter.list_messages with empty channels returns empty MessagePage."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client()
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=[], since=since)

        assert isinstance(result, MessagePage)
        assert result.messages == []
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_messages_dm_channel_flagged_as_dm(self):
        """SlackAdapter marks channels starting with 'D' as DMs (is_dm=True)."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client(SLACK_HISTORY_RESPONSE_DM)
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # DM channels in Slack start with 'D'
        result = await adapter.list_messages(channels=["D01DMCHANNEL"], since=since)

        assert len(result.messages) == 1
        assert result.messages[0].is_dm is True

    @pytest.mark.asyncio
    async def test_list_messages_public_channel_not_dm(self):
        """SlackAdapter marks channels starting with 'C' as not DMs (is_dm=False)."""
        from daily.integrations.slack.adapter import SlackAdapter

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = _make_slack_client(SLACK_HISTORY_RESPONSE_NO_CURSOR)
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL"], since=since)

        assert len(result.messages) == 1
        assert result.messages[0].is_dm is False

    @pytest.mark.asyncio
    async def test_list_messages_multiple_channels_aggregated(self):
        """SlackAdapter aggregates messages from multiple channels into one list."""
        from daily.integrations.slack.adapter import SlackAdapter

        client = MagicMock()

        def _channel_history(**kwargs):
            channel = kwargs.get("channel", "")
            if channel == "C01CHANNEL":
                return _make_mock_response(SLACK_HISTORY_RESPONSE_NO_CURSOR)
            elif channel == "C02CHANNEL":
                return _make_mock_response(SLACK_HISTORY_RESPONSE_DM)
            return _make_mock_response({"ok": True, "messages": [], "has_more": False, "response_metadata": {"next_cursor": ""}})

        client.conversations_history.side_effect = _channel_history

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = await adapter.list_messages(channels=["C01CHANNEL", "C02CHANNEL"], since=since)

        # 1 from C01CHANNEL + 1 from C02CHANNEL
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# Pagination regression tests (FIX-02)
# epoch 1744934400.0 → 2025-04-18T04:40:00Z (UTC)
# IN_WINDOW timestamps: >= 1744934400.0
# OUT_OF_WINDOW timestamps: < 1744934400.0
# ---------------------------------------------------------------------------

SINCE_TS = datetime.fromtimestamp(1744934400.0, tz=timezone.utc)

# Timestamps for test messages
IN_1 = "1744934401.000000"  # 1 second after since
IN_2 = "1744934402.000000"  # 2 seconds after since
IN_3 = "1744934403.000000"  # 3 seconds after since
IN_4 = "1744934404.000000"  # 4 seconds after since
OUT_1 = "1744934399.000000"  # 1 second before since


def _make_mock_side_effect(*responses):
    """Build a side_effect list from dicts for conversations_history mock."""
    return [_make_mock_response(r) for r in responses]


class TestSlackAdapterPagination:
    @pytest.mark.asyncio
    async def test_pagination_single_page_no_cursor(self):
        """Single page with next_cursor='' — adapter makes exactly 1 call, returns all messages."""
        from daily.integrations.slack.adapter import SlackAdapter

        page1 = {
            "ok": True,
            "messages": [
                {"ts": IN_1, "user": "U1", "text": "hello"},
                {"ts": IN_2, "user": "U2", "text": "world"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        client = MagicMock()
        client.conversations_history.side_effect = _make_mock_side_effect(page1)

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        result = await adapter.list_messages(channels=["C01CHANNEL"], since=SINCE_TS)

        assert client.conversations_history.call_count == 1
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_pagination_follows_cursor_two_pages_all_in_window(self):
        """Two in-window pages — adapter follows cursor and returns all 4 messages."""
        from daily.integrations.slack.adapter import SlackAdapter

        page1 = {
            "ok": True,
            "messages": [
                {"ts": IN_2, "user": "U1", "text": "msg A"},
                {"ts": IN_1, "user": "U2", "text": "msg B"},
            ],
            "response_metadata": {"next_cursor": "c1"},
        }
        page2 = {
            "ok": True,
            "messages": [
                {"ts": IN_4, "user": "U3", "text": "msg C"},
                {"ts": IN_3, "user": "U4", "text": "msg D"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        client = MagicMock()
        client.conversations_history.side_effect = _make_mock_side_effect(page1, page2)

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        result = await adapter.list_messages(channels=["C01CHANNEL"], since=SINCE_TS)

        assert client.conversations_history.call_count == 2
        assert len(result.messages) == 4

        # Verify cursor was passed on the second call
        second_call_kwargs = client.conversations_history.call_args_list[1][1]
        assert second_call_kwargs.get("cursor") == "c1"

    @pytest.mark.asyncio
    async def test_pagination_stops_on_time_window(self):
        """Page 2 messages are all older than since — adapter stops and returns only in-window msgs."""
        from daily.integrations.slack.adapter import SlackAdapter

        page1 = {
            "ok": True,
            "messages": [
                {"ts": IN_2, "user": "U1", "text": "in-window 1"},
                {"ts": IN_1, "user": "U2", "text": "in-window 2"},
            ],
            "response_metadata": {"next_cursor": "c1"},
        }
        page2 = {
            "ok": True,
            "messages": [
                {"ts": OUT_1, "user": "U3", "text": "too old"},
            ],
            "response_metadata": {"next_cursor": "c2"},
        }

        client = MagicMock()
        client.conversations_history.side_effect = _make_mock_side_effect(page1, page2)

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        result = await adapter.list_messages(channels=["C01CHANNEL"], since=SINCE_TS)

        assert client.conversations_history.call_count == 2
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_pagination_empty_first_page(self):
        """Empty first page — adapter makes exactly 1 call and returns []."""
        from daily.integrations.slack.adapter import SlackAdapter

        page1 = {
            "ok": True,
            "messages": [],
            "response_metadata": {"next_cursor": ""},
        }

        client = MagicMock()
        client.conversations_history.side_effect = _make_mock_side_effect(page1)

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        result = await adapter.list_messages(channels=["C01CHANNEL"], since=SINCE_TS)

        assert client.conversations_history.call_count == 1
        assert result.messages == []

    @pytest.mark.asyncio
    async def test_pagination_mid_page_time_window_cutoff(self):
        """Single page: msgs[0], msgs[1] in-window; msgs[2] older than since — only first 2 returned."""
        from daily.integrations.slack.adapter import SlackAdapter

        page1 = {
            "ok": True,
            "messages": [
                {"ts": IN_3, "user": "U1", "text": "newest"},
                {"ts": IN_1, "user": "U2", "text": "second"},
                {"ts": OUT_1, "user": "U3", "text": "too old"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        client = MagicMock()
        client.conversations_history.side_effect = _make_mock_side_effect(page1)

        with patch("daily.integrations.slack.adapter.WebClient") as mock_wc:
            mock_wc.return_value = client
            adapter = SlackAdapter(bot_token="xoxb-test")

        result = await adapter.list_messages(channels=["C01CHANNEL"], since=SINCE_TS)

        assert len(result.messages) == 2
        ts_values = [m.message_id for m in result.messages]
        assert IN_3 in ts_values
        assert IN_1 in ts_values
        assert OUT_1 not in ts_values
