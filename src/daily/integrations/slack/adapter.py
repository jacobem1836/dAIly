"""
Slack read adapter implementing the MessageAdapter interface.

Fetches message metadata from Slack channels using the slack-sdk WebClient.
Returns typed MessagePage with MessageMetadata objects — no message body stored.

T-1-12: MessageMetadata has no text/body field; message content is never stored.
SEC-04/D-06: Only metadata returned — raw content never passes to LLM layer.
FIX-02: Cursor-based pagination follows next_cursor until time window exhausted.
"""

import asyncio
from datetime import datetime, timezone

from slack_sdk import WebClient

from daily.integrations.base import MessageAdapter
from daily.integrations.models import MessageMetadata, MessagePage


class SlackAdapter(MessageAdapter):
    """Slack message read adapter using slack-sdk WebClient.

    Args:
        bot_token: Decrypted Slack bot token (xoxb-...).
    """

    def __init__(self, bot_token: str) -> None:
        self._client = WebClient(token=bot_token)

    async def _fetch_channel_messages(
        self, channel_id: str, since: datetime, is_dm: bool
    ) -> list[MessageMetadata]:
        """Fetch all in-window messages from a single channel with pagination.

        Follows next_cursor across multiple pages until either:
        - next_cursor is empty (no more pages), or
        - a message's timestamp is older than `since` (time window exhausted), or
        - a page returns no messages.

        FIX-02/D-04: No hard page cap — time window is the only stopping condition.

        Args:
            channel_id: Slack channel ID.
            since: Only include messages at or after this timestamp.
            is_dm: Whether the channel is a DM (starts with "D").

        Returns:
            List of MessageMetadata objects for all in-window messages.
        """
        messages: list[MessageMetadata] = []
        cursor: str | None = None
        oldest_ts = since.timestamp()

        while True:
            kwargs: dict = {"channel": channel_id, "oldest": oldest_ts, "limit": 100}
            if cursor:
                kwargs["cursor"] = cursor

            response = await asyncio.to_thread(
                self._client.conversations_history, **kwargs
            )

            messages_data = response.get("messages", [])
            if not messages_data:
                break

            for msg in messages_data:
                ts_str = msg.get("ts", "")
                timestamp = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
                if timestamp < since:
                    return messages
                text = msg.get("text", "")
                messages.append(
                    MessageMetadata(
                        message_id=ts_str,
                        channel_id=channel_id,
                        sender_id=msg.get("user", ""),
                        timestamp=timestamp,
                        is_mention="<@" in text,
                        is_dm=is_dm,
                    )
                )

            response_metadata = response.get("response_metadata") or {}
            raw_cursor = response_metadata.get("next_cursor", "")
            cursor = raw_cursor if raw_cursor else None
            if not cursor:
                break

        return messages

    async def list_messages(
        self, channels: list[str], since: datetime
    ) -> MessagePage:
        """Fetch message metadata from all channels since the given datetime.

        Delegates per-channel pagination to _fetch_channel_messages, aggregates
        results, and returns a MessagePage with next_cursor=None (pagination is
        fully internal — callers always receive a complete in-window result set).

        T-1-12: No text or body field stored — metadata only.
        FIX-02: Pagination handled internally; next_cursor on returned page is None.

        Args:
            channels: List of Slack channel IDs (e.g. ["C01CHANNEL", "D01DM"]).
            since: Only return messages after this timestamp.

        Returns:
            MessagePage with aggregated MessageMetadata. next_cursor is always None.
        """
        if not channels:
            return MessagePage(messages=[], next_cursor=None)

        all_messages: list[MessageMetadata] = []

        for channel_id in channels:
            is_dm = channel_id.startswith("D")
            msgs = await self._fetch_channel_messages(channel_id, since, is_dm)
            all_messages.extend(msgs)

        return MessagePage(messages=all_messages, next_cursor=None)

    async def get_message_text(self, message_id: str, channel_id: str) -> str:
        """Fetch the text of a single Slack message.

        Calls conversations_history with latest=message_id, inclusive=True,
        limit=1 to retrieve the specific message.

        T-02-01: Returned text is stored in BriefingContext.raw_bodies only.
        Never persisted to DB or cache.

        Args:
            message_id: Slack message timestamp (ts) used as message ID.
            channel_id: Channel the message belongs to.

        Returns:
            Message text as a string, or empty string if not found.
        """
        response = await asyncio.to_thread(
            self._client.conversations_history,
            channel=channel_id,
            latest=message_id,
            inclusive=True,
            limit=1,
        )
        messages = response.get("messages", [])
        if messages:
            return messages[0].get("text", "")
        return ""
