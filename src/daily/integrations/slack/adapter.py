"""
Slack read adapter implementing the MessageAdapter interface.

Fetches message metadata from Slack channels using the slack-sdk WebClient.
Returns typed MessagePage with MessageMetadata objects — no message body stored.

T-1-12: MessageMetadata has no text/body field; message content is never stored.
SEC-04/D-06: Only metadata returned — raw content never passes to LLM layer.
"""

import asyncio
import logging
from datetime import datetime, timezone

from slack_sdk import WebClient

from daily.integrations.base import MessageAdapter
from daily.integrations.models import MessageMetadata, MessagePage

logger = logging.getLogger(__name__)

_MAX_PAGES_PER_CHANNEL = 10


class SlackAdapter(MessageAdapter):
    """Slack message read adapter using slack-sdk WebClient.

    Args:
        bot_token: Decrypted Slack bot token (xoxb-...).
    """

    def __init__(self, bot_token: str) -> None:
        self._client = WebClient(token=bot_token)

    async def list_messages(
        self, channels: list[str], since: datetime
    ) -> MessagePage:
        """Fetch message metadata from Slack channels since the given datetime.

        Calls conversations_history for each channel, maps each message to
        MessageMetadata, aggregates across channels, and returns a MessagePage.

        T-1-12: No text or body field stored — metadata only.
        The next_cursor is taken from the last channel's response_metadata.

        Args:
            channels: List of Slack channel IDs (e.g. ["C01CHANNEL", "D01DM"]).
            since: Only return messages after this timestamp.

        Returns:
            MessagePage with aggregated MessageMetadata and optional next_cursor.
        """
        if not channels:
            return MessagePage(messages=[], next_cursor=None)

        all_messages: list[MessageMetadata] = []

        for channel_id in channels:
            is_dm = channel_id.startswith("D")
            oldest_ts = since.timestamp()
            cursor: str | None = None
            page_count = 0

            while page_count < _MAX_PAGES_PER_CHANNEL:
                kwargs: dict = {
                    "channel": channel_id,
                    "oldest": oldest_ts,
                    "limit": 100,
                }
                if cursor:
                    kwargs["cursor"] = cursor

                response = await asyncio.to_thread(
                    self._client.conversations_history,
                    **kwargs,
                )

                messages_data = response.get("messages", [])

                for msg in messages_data:
                    ts = msg.get("ts", "")
                    timestamp = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    text = msg.get("text", "")
                    is_mention = "<@" in text

                    metadata = MessageMetadata(
                        message_id=ts,
                        channel_id=channel_id,
                        sender_id=msg.get("user", ""),
                        timestamp=timestamp,
                        is_mention=is_mention,
                        is_dm=is_dm,
                    )
                    all_messages.append(metadata)

                page_count += 1

                # Check for more pages
                response_metadata = response.get("response_metadata", {})
                raw_cursor = response_metadata.get("next_cursor", "") if response_metadata else ""
                cursor = raw_cursor if raw_cursor else None

                if not cursor:
                    break

            if page_count >= _MAX_PAGES_PER_CHANNEL and cursor:
                logger.warning(
                    "Slack pagination cap (%d pages) hit for channel %s — %d messages fetched",
                    _MAX_PAGES_PER_CHANNEL,
                    channel_id,
                    len([m for m in all_messages if m.channel_id == channel_id]),
                )

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
