"""
Slack read adapter implementing the MessageAdapter interface.

Fetches message metadata from Slack channels using the slack-sdk WebClient.
Returns typed MessagePage with MessageMetadata objects — no message body stored.

T-1-12: MessageMetadata has no text/body field; message content is never stored.
SEC-04/D-06: Only metadata returned — raw content never passes to LLM layer.
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
        last_cursor: str | None = None

        for channel_id in channels:
            is_dm = channel_id.startswith("D")
            oldest_ts = since.timestamp()

            response = await asyncio.to_thread(
                self._client.conversations_history,
                channel=channel_id,
                oldest=oldest_ts,
                limit=100,
            )

            messages_data = response.get("messages", [])
            response_metadata = response.get("response_metadata", {})
            raw_cursor = response_metadata.get("next_cursor", "") if response_metadata else ""
            cursor = raw_cursor if raw_cursor else None

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

            last_cursor = cursor

        return MessagePage(messages=all_messages, next_cursor=last_cursor)
