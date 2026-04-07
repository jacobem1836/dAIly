"""
Outlook (Microsoft Graph) email and calendar read adapters.

Implements EmailAdapter and CalendarAdapter abstract base classes.
Uses msgraph-sdk (async) for all Graph API calls.

T-1-16: Graph API $select excludes body/uniqueBody — EmailMetadata has no body field.
         Only id, conversationId, subject, from, toRecipients, receivedDateTime,
         isRead, and categories are selected.

Note: msgraph-sdk is natively async — no asyncio.to_thread() wrapping needed.
"""

from datetime import datetime, timezone
from typing import Any

from kiota_abstractions.base_request_configuration import RequestConfiguration

from daily.integrations.base import CalendarAdapter, EmailAdapter
from daily.integrations.models import (
    CalendarEvent,
    EmailMetadata,
    EmailPage,
)


class _StaticTokenCredential:
    """Minimal azure-core TokenCredential wrapping a pre-obtained access token.

    Used to pass a decrypted MSAL access_token to the msgraph-sdk without
    triggering a full Azure Identity OAuth flow.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        from azure.core.credentials import AccessToken
        import time

        # Expiry is set 1 hour from now; actual expiry is managed by vault/refresh.py
        return AccessToken(self._token, int(time.time()) + 3600)


class OutlookAdapter(EmailAdapter, CalendarAdapter):
    """Read adapter for Microsoft Outlook (mail + calendar) via Microsoft Graph.

    Implements both EmailAdapter and CalendarAdapter since they share a single
    Microsoft Graph OAuth grant.

    T-1-16: $select excludes body/uniqueBody — metadata only.

    Args:
        access_token: Decrypted Microsoft Graph access token.
    """

    def __init__(self, access_token: str) -> None:
        from msgraph import GraphServiceClient

        credential = _StaticTokenCredential(access_token)
        self._client = GraphServiceClient(credentials=credential)

    async def list_emails(
        self, since: datetime, page_token: str | None = None
    ) -> EmailPage:
        """List Outlook emails since the given datetime, returning metadata only.

        T-1-16: $select explicitly excludes body/uniqueBody — only metadata fields
        are requested from the Graph API.

        Args:
            since: Only return emails received after this timestamp.
            page_token: OData skip token from a previous call, or None for first page.

        Returns:
            EmailPage with EmailMetadata objects and optional next_page_token.
        """
        from msgraph.generated.users.item.messages.messages_request_builder import (
            MessagesRequestBuilder,
        )

        # Format since datetime for OData $filter
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            # T-1-16: Only metadata fields — body/uniqueBody explicitly excluded
            select=[
                "id",
                "conversationId",
                "subject",
                "from",
                "toRecipients",
                "receivedDateTime",
                "isRead",
                "categories",
            ],
            filter=f"receivedDateTime ge {since_str}",
            top=50,
        )

        if page_token:
            # page_token is a $skiptoken value — use with_url to set it
            request_config = RequestConfiguration(query_parameters=query_params)
            # Build a URL with the skip token appended
            messages_response = await self._client.me.messages.with_url(
                f"https://graph.microsoft.com/v1.0/me/messages?$skiptoken={page_token}"
                f"&$select=id,conversationId,subject,from,toRecipients,receivedDateTime,isRead,categories"
                f"&$filter=receivedDateTime ge {since_str}&$top=50"
            ).get()
        else:
            request_config = RequestConfiguration(query_parameters=query_params)
            messages_response = await self._client.me.messages.get(
                request_configuration=request_config
            )

        emails: list[EmailMetadata] = []
        next_page_token: str | None = None

        if messages_response and messages_response.value:
            for msg in messages_response.value:
                # Map Graph Message to EmailMetadata
                sender_address = ""
                if msg.from_ and msg.from_.email_address:
                    sender_address = msg.from_.email_address.address or ""

                recipient_address = ""
                if msg.to_recipients:
                    first_recipient = msg.to_recipients[0]
                    if first_recipient.email_address:
                        recipient_address = first_recipient.email_address.address or ""

                timestamp = msg.received_date_time
                if timestamp and timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                elif timestamp is None:
                    timestamp = datetime.now(tz=timezone.utc)

                emails.append(
                    EmailMetadata(
                        message_id=msg.id or "",
                        thread_id=msg.conversation_id or "",
                        subject=msg.subject or "",
                        sender=sender_address,
                        recipient=recipient_address,
                        timestamp=timestamp,
                        is_unread=not (msg.is_read or False),
                        labels=list(msg.categories or []),
                    )
                )

            # Extract skip token from @odata.nextLink if present
            if messages_response.odata_next_link:
                # Parse the skip token from the next link URL
                next_link = messages_response.odata_next_link
                if "$skiptoken=" in next_link:
                    next_page_token = next_link.split("$skiptoken=")[1].split("&")[0]
                else:
                    next_page_token = next_link

        return EmailPage(emails=emails, next_page_token=next_page_token)

    async def list_events(
        self, since: datetime, until: datetime
    ) -> list[CalendarEvent]:
        """List Outlook calendar events in the given time range.

        Uses calendarView endpoint which expands recurring events within the range.

        Args:
            since: Start of the time window (inclusive).
            until: End of the time window (exclusive).

        Returns:
            List of CalendarEvent objects.
        """
        from msgraph.generated.users.item.calendar_view.calendar_view_request_builder import (
            CalendarViewRequestBuilder,
        )

        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        until_str = until.strftime("%Y-%m-%dT%H:%M:%SZ")

        query_params = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetQueryParameters(
            select=["id", "subject", "start", "end", "attendees", "location", "isAllDay"],
            start_date_time=since_str,
            end_date_time=until_str,
            top=100,
        )

        request_config = RequestConfiguration(query_parameters=query_params)
        events_response = await self._client.me.calendar_view.get(
            request_configuration=request_config
        )

        events: list[CalendarEvent] = []

        if events_response and events_response.value:
            for event in events_response.value:
                # Parse start datetime
                start_dt: datetime
                end_dt: datetime

                if event.start:
                    if event.start.date_time:
                        start_dt = datetime.fromisoformat(
                            event.start.date_time.replace("Z", "+00:00")
                        )
                    else:
                        start_dt = datetime.now(tz=timezone.utc)
                else:
                    start_dt = datetime.now(tz=timezone.utc)

                if event.end:
                    if event.end.date_time:
                        end_dt = datetime.fromisoformat(
                            event.end.date_time.replace("Z", "+00:00")
                        )
                    else:
                        end_dt = start_dt
                else:
                    end_dt = start_dt

                # Extract attendee emails
                attendees: list[str] = []
                if event.attendees:
                    for attendee in event.attendees:
                        if attendee.email_address and attendee.email_address.address:
                            attendees.append(attendee.email_address.address)

                location: str | None = None
                if event.location and event.location.display_name:
                    location = event.location.display_name

                events.append(
                    CalendarEvent(
                        event_id=event.id or "",
                        title=event.subject or "",
                        start=start_dt,
                        end=end_dt,
                        attendees=attendees,
                        location=location,
                        is_all_day=event.is_all_day or False,
                    )
                )

        return events

    async def get_email_body(self, message_id: str) -> str:
        """Fetch the plain-text body of a single Outlook message via Graph API.

        Calls GET /me/messages/{message_id} selecting body and bodyPreview.
        Returns body.content (plain text preferred) or bodyPreview as fallback.

        T-02-01: Returned body is stored in BriefingContext.raw_bodies only.
        Never persisted to DB or cache.

        Args:
            message_id: Microsoft Graph message ID.

        Returns:
            Plain-text body content as a string, or empty string if unavailable.
        """
        from msgraph.generated.users.item.messages.item.message_item_request_builder import (
            MessageItemRequestBuilder,
        )

        query_params = MessageItemRequestBuilder.MessageItemRequestBuilderGetQueryParameters(
            select=["body", "bodyPreview"],
        )
        from kiota_abstractions.base_request_configuration import RequestConfiguration

        request_config = RequestConfiguration(query_parameters=query_params)
        message = await self._client.me.messages.by_message_id(message_id).get(
            request_configuration=request_config
        )
        if message and message.body and message.body.content:
            return message.body.content
        if message and message.body_preview:
            return message.body_preview
        return ""
