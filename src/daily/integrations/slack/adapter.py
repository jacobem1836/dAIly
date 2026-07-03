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

    async def _resolve_default_channels(self) -> list[str]:
        """Resolve a default channel set when the caller has configured none.

        Audit finding C1: BriefingConfig.slack_channels defaults to an empty
        list, and prior code treated "empty" as "fetch nothing", which meant
        Slack briefings were silently dead for every user who never set an
        explicit channel list. Per BRIEF-05's original M1 intent ("empty list
        = all accessible channels"), empty now means "every channel this bot
        is a member of" instead of "no channels" — so Slack briefing works
        out of the box, and setting slack_channels only narrows the scope.

        Returns:
            List of channel IDs the bot is currently a member of (public and
            private conversations only — excludes archived channels).
        """
        response = await asyncio.to_thread(
            self._client.conversations_list,
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
        )
        channels_data = response.get("channels", []) or []
        return [c["id"] for c in channels_data if c.get("is_member")]

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
                Empty list resolves to the bot's default channel membership
                (see _resolve_default_channels) rather than fetching nothing —
                see audit finding C1.
            since: Only return messages after this timestamp.

        Returns:
            MessagePage with aggregated MessageMetadata and optional next_cursor.
        """
        if not channels:
            channels = await self._resolve_default_channels()

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
