"""
Abstract adapter base classes defining the interface contract for integration adapters.

These classes define the exact contract that Phase 2 (briefing pipeline) consumes.
All concrete adapters (Gmail, Google Calendar, Slack, Outlook) must implement
these interfaces (D-08).
"""

from abc import ABC, abstractmethod
from datetime import datetime

from daily.integrations.models import CalendarEvent, EmailPage, MessagePage


class EmailAdapter(ABC):
    @abstractmethod
    async def list_emails(
        self, since: datetime, page_token: str | None = None
    ) -> EmailPage:
        """
        List emails since the given datetime.

        Args:
            since: Only return emails after this timestamp.
            page_token: Pagination token from a previous call, or None for first page.

        Returns:
            EmailPage containing metadata-only EmailMetadata objects and
            an optional next_page_token for pagination.
        """
        ...

    @abstractmethod
    async def get_email_body(self, message_id: str) -> str:
        """
        Fetch the plain-text body of a single email (per D-01).

        The returned body is stored in BriefingContext.raw_bodies (exclude=True)
        and consumed by the redactor before any LLM call. Raw content is never
        persisted to DB or cache (SEC-02/T-02-01).

        Args:
            message_id: Provider-specific message identifier.

        Returns:
            Plain-text body of the email as a string.
        """
        ...


class CalendarAdapter(ABC):
    @abstractmethod
    async def list_events(
        self, since: datetime, until: datetime
    ) -> list[CalendarEvent]:
        """
        List calendar events in the given time range.

        Args:
            since: Start of the time window (inclusive).
            until: End of the time window (exclusive).

        Returns:
            List of CalendarEvent objects.
        """
        ...


class MessageAdapter(ABC):
    @abstractmethod
    async def list_messages(
        self, channels: list[str], since: datetime
    ) -> MessagePage:
        """
        List messages from the given channels since the given datetime.

        Args:
            channels: Channel IDs to fetch messages from.
            since: Only return messages after this timestamp.

        Returns:
            MessagePage containing metadata-only MessageMetadata objects and
            an optional next_cursor for pagination.
        """
        ...

    @abstractmethod
    async def get_message_text(self, message_id: str, channel_id: str) -> str:
        """
        Fetch the plain text of a single message (per D-01).

        The returned text is stored in BriefingContext.raw_bodies (exclude=True)
        and consumed by the redactor before any LLM call. Raw content is never
        persisted to DB or cache (SEC-02/T-02-01).

        Args:
            message_id: Provider-specific message identifier.
            channel_id: Channel the message belongs to.

        Returns:
            Plain text of the message as a string.
        """
        ...
