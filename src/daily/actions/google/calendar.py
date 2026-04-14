"""Google Calendar ActionExecutor: creates and reschedules calendar events.

Security boundaries:
  ACT-06 / T-04-11: validate() calls check_recipient_whitelist for each attendee.
  D-11 / T-04-17: validate() checks calendar.events scope is granted before any API call.
  T-04-15: Uses events().patch() for reschedules — never events().update().
           (Pitfall 5 from RESEARCH.md: update() overwrites attendees; patch() merges.)

Calendar API patterns:
  schedule_event  -> events().insert(calendarId="primary", body=...).execute()
  reschedule_event -> events().patch(calendarId="primary", eventId=..., body=...).execute()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from daily.actions.base import ActionDraft, ActionExecutor, ActionResult, ActionType
from daily.actions.whitelist import check_recipient_whitelist

logger = logging.getLogger(__name__)

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GoogleCalendarExecutor(ActionExecutor):
    """Creates and reschedules Google Calendar events via the Calendar API.

    Args:
        service: Google Calendar API service object (from googleapiclient.discovery.build).
        known_addresses: Set of known contact email addresses for attendee whitelist.
        granted_scopes: Set of OAuth scopes granted by the user.
    """

    def __init__(
        self,
        service: Any,
        known_addresses: set[str],
        granted_scopes: set[str],
    ) -> None:
        self._service = service
        self._known_addresses = known_addresses
        self._granted_scopes = granted_scopes

    async def validate(self, draft: ActionDraft) -> None:
        """Pre-execution validation for calendar events.

        Checks:
          1. calendar.events scope is granted (D-11 / T-04-17).
          2. Each attendee email is in known_addresses whitelist (ACT-06).

        Args:
            draft: The ActionDraft to validate.

        Raises:
            ValueError: If scope is missing or any attendee is unknown.
        """
        if CALENDAR_EVENTS_SCOPE not in self._granted_scopes:
            raise ValueError(
                "Google Calendar events scope not granted. "
                "Reconnect your Google account with write permissions."
            )
        for attendee in draft.attendees:
            check_recipient_whitelist(attendee, self._known_addresses)

    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Create or reschedule a Google Calendar event.

        For schedule_event: calls events().insert(calendarId="primary", body=...).
        For reschedule_event: calls events().patch(calendarId="primary", eventId=..., body=...).

        CRITICAL: reschedule ALWAYS uses patch(), never update().
        events().update() replaces the full event (including removing attendees);
        events().patch() merges only the changed fields (Pitfall 5 prevention).

        Args:
            draft: The approved ActionDraft to execute.

        Returns:
            ActionResult with success status and event ID.
        """
        try:
            if draft.action_type == ActionType.schedule_event:
                event_body = {
                    "summary": draft.event_title,
                    "start": {
                        "dateTime": draft.start_dt.isoformat(),
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": draft.end_dt.isoformat(),
                        "timeZone": "UTC",
                    },
                    "attendees": [{"email": a} for a in draft.attendees],
                }
                result = await asyncio.to_thread(
                    self._service.events()
                    .insert(calendarId="primary", body=event_body)
                    .execute
                )
                return ActionResult(success=True, external_id=result["id"])

            elif draft.action_type == ActionType.reschedule_event:
                # CRITICAL: Use patch() not update() (Pitfall 5 prevention)
                patch_body = {
                    "start": {
                        "dateTime": draft.start_dt.isoformat(),
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": draft.end_dt.isoformat(),
                        "timeZone": "UTC",
                    },
                }
                await asyncio.to_thread(
                    self._service.events()
                    .patch(
                        calendarId="primary",
                        eventId=draft.event_id,
                        body=patch_body,
                    )
                    .execute
                )
                return ActionResult(success=True, external_id=draft.event_id)

            else:
                return ActionResult(
                    success=False,
                    error=f"Unsupported action_type for calendar: {draft.action_type}",
                )

        except Exception as exc:
            logger.warning("GoogleCalendarExecutor.execute: failed: %s", exc)
            return ActionResult(success=False, error=str(exc))
