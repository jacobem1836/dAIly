"""
Gmail and Google Calendar read adapters.

Both adapters implement the abstract base classes from daily.integrations.base
and return typed Pydantic models from daily.integrations.models.

T-1-09: Gmail API is called with format="metadata" — raw bodies are never
fetched. No body field appears in any returned object (SEC-04/D-06).

Note: google-api-python-client uses synchronous HTTP calls. Both adapters
wrap API calls in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build

from daily.integrations.base import CalendarAdapter, EmailAdapter
from daily.integrations.models import (
    CalendarEvent,
    EmailMetadata,
    EmailPage,
)


class GmailAdapter(EmailAdapter):
    """Read adapter for Gmail using google-api-python-client.

    T-1-09: Uses format="metadata" — raw message bodies are never fetched.
    """

    def __init__(self, credentials: Any) -> None:
        """Initialise the Gmail service from a Google credentials object.

        Args:
            credentials: google.oauth2.credentials.Credentials (already decrypted).
        """
        self._credentials = credentials
        self._service = build("gmail", "v1", credentials=credentials)

    async def list_emails(
        self, since: datetime, page_token: str | None = None
    ) -> EmailPage:
        """List emails since the given datetime, returning metadata only.

        Args:
            since: Only return emails after this timestamp.
            page_token: Pagination token from a previous call, or None for first page.

        Returns:
            EmailPage with EmailMetadata objects and optional next_page_token.
        """
        since_epoch = int(since.timestamp())

        def _fetch() -> EmailPage:
            # Fetch message IDs
            list_kwargs: dict[str, Any] = {
                "userId": "me",
                "q": f"after:{since_epoch}",
            }
            if page_token:
                list_kwargs["pageToken"] = page_token

            list_response = (
                self._service.users()
                .messages()
                .list(**list_kwargs)
                .execute()
            )

            messages = list_response.get("messages", [])
            next_token = list_response.get("nextPageToken")

            email_items: list[EmailMetadata] = []
            for msg_ref in messages:
                msg_id = msg_ref["id"]
                # T-1-09: format="metadata" ensures no body is returned from API
                msg = (
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "To"],
                    )
                    .execute()
                )

                headers = msg.get("payload", {}).get("headers", [])
                header_map = {h["name"]: h["value"] for h in headers}

                label_ids: list[str] = msg.get("labelIds", [])
                internal_date_ms = int(msg.get("internalDate", "0"))
                timestamp = datetime.fromtimestamp(
                    internal_date_ms / 1000, tz=timezone.utc
                )

                email_items.append(
                    EmailMetadata(
                        message_id=msg["id"],
                        thread_id=msg["threadId"],
                        subject=header_map.get("Subject", ""),
                        sender=header_map.get("From", ""),
                        recipient=header_map.get("To", ""),
                        timestamp=timestamp,
                        is_unread="UNREAD" in label_ids,
                        labels=label_ids,
                    )
                )

            return EmailPage(emails=email_items, next_page_token=next_token)

        return await asyncio.to_thread(_fetch)

    async def get_email_body(self, message_id: str) -> str:
        """Fetch the plain-text body of a single Gmail message.

        Calls Gmail API messages.get with format='full' and extracts the
        plain-text part from the payload. Returns empty string if no text/plain
        part is found.

        T-02-01: Returned body is stored in BriefingContext.raw_bodies only.
        Never persisted to DB or cache.

        Args:
            message_id: Gmail message ID.

        Returns:
            Decoded plain-text body, or empty string if unavailable.
        """
        import base64

        def _fetch() -> str:
            # Build a fresh service per thread to avoid httplib2 shared-connection races
            svc = build("gmail", "v1", credentials=self._credentials)
            msg = (
                svc.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            def _extract_text(payload: dict) -> str:
                mime_type = payload.get("mimeType", "")
                if mime_type == "text/plain":
                    data = payload.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data + "==").decode(
                            "utf-8", errors="replace"
                        )
                for part in payload.get("parts", []):
                    result = _extract_text(part)
                    if result:
                        return result
                return ""

            return _extract_text(msg.get("payload", {}))

        return await asyncio.to_thread(_fetch)


class GoogleCalendarAdapter(CalendarAdapter):
    """Read adapter for Google Calendar using google-api-python-client."""

    def __init__(self, credentials: Any) -> None:
        """Initialise the Calendar service from a Google credentials object.

        Args:
            credentials: google.oauth2.credentials.Credentials (already decrypted).
        """
        self._service = build("calendar", "v3", credentials=credentials)

    async def list_events(
        self, since: datetime, until: datetime
    ) -> list[CalendarEvent]:
        """List calendar events in the given time range.

        Args:
            since: Start of the time window (inclusive).
            until: End of the time window (exclusive).

        Returns:
            List of CalendarEvent objects.
        """

        def _fetch() -> list[CalendarEvent]:
            response = (
                self._service.events()
                .list(
                    calendarId="primary",
                    timeMin=since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    timeMax=until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events: list[CalendarEvent] = []
            for item in response.get("items", []):
                start_info = item.get("start", {})
                end_info = item.get("end", {})

                is_all_day = "date" in start_info and "dateTime" not in start_info

                if is_all_day:
                    # All-day events use date strings — represent as midnight UTC
                    start_str = start_info["date"]
                    end_str = end_info["date"]
                    start_dt = datetime.fromisoformat(start_str).replace(
                        tzinfo=timezone.utc
                    )
                    end_dt = datetime.fromisoformat(end_str).replace(
                        tzinfo=timezone.utc
                    )
                else:
                    start_str = start_info.get("dateTime", "")
                    end_str = end_info.get("dateTime", "")
                    start_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    )
                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

                attendees = [
                    a["email"] for a in item.get("attendees", []) if "email" in a
                ]

                events.append(
                    CalendarEvent(
                        event_id=item["id"],
                        title=item.get("summary", ""),
                        start=start_dt,
                        end=end_dt,
                        attendees=attendees,
                        location=item.get("location"),
                        is_all_day=is_all_day,
                    )
                )

            return events

        return await asyncio.to_thread(_fetch)
