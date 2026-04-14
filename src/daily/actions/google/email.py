"""Gmail ActionExecutor: sends emails and replies via the Gmail API.

Security boundaries:
  ACT-06 / T-04-11: validate() calls check_recipient_whitelist before any API call.
  D-11 / T-04-17: validate() checks gmail.send scope is granted before any API call.
  T-04-13: Service object holds decrypted credentials in-memory only at call time.

Threading (RFC 2822):
  execute() sets In-Reply-To and References headers to enable native Gmail threading.

Encoding:
  MIME messages are base64url-encoded per Gmail API requirement.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from email.message import EmailMessage
from typing import Any

from daily.actions.base import ActionDraft, ActionExecutor, ActionResult
from daily.actions.whitelist import check_recipient_whitelist

logger = logging.getLogger(__name__)

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class GmailExecutor(ActionExecutor):
    """Sends emails (new or reply) via the Gmail API.

    Args:
        service: Gmail API service object (from googleapiclient.discovery.build).
        known_addresses: Set of known contact addresses for whitelist validation.
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
        """Pre-execution validation for Gmail send.

        Checks:
          1. gmail.send scope is granted (D-11 / T-04-17).
          2. Recipient is in known_addresses whitelist (ACT-06 / T-04-11).

        Args:
            draft: The ActionDraft to validate.

        Raises:
            ValueError: If scope is missing or recipient is unknown.
        """
        if GMAIL_SEND_SCOPE not in self._granted_scopes:
            raise ValueError(
                "Gmail send scope not granted. "
                "Reconnect your Google account with write permissions."
            )
        if draft.recipient:
            check_recipient_whitelist(draft.recipient, self._known_addresses)

    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Send an email via Gmail API.

        Builds a MIME message with In-Reply-To and References headers for
        native Gmail threading, base64url-encodes it, and calls
        users().messages().send(userId="me", body=...).

        Args:
            draft: The approved ActionDraft to execute.

        Returns:
            ActionResult with success status and Gmail message ID on success.
        """
        try:
            msg = EmailMessage()
            msg.set_content(draft.body)
            msg["To"] = draft.recipient or ""
            msg["Subject"] = f"Re: {draft.subject}" if draft.subject else "(no subject)"

            if draft.thread_message_id:
                msg["In-Reply-To"] = draft.thread_message_id
                msg["References"] = draft.thread_message_id

            encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            send_body: dict[str, str] = {"raw": encoded}
            if draft.thread_id:
                send_body["threadId"] = draft.thread_id

            result = await asyncio.to_thread(
                self._service.users()
                .messages()
                .send(userId="me", body=send_body)
                .execute
            )
            return ActionResult(success=True, external_id=result["id"])

        except Exception as exc:
            logger.warning("GmailExecutor.execute: failed: %s", exc)
            return ActionResult(success=False, error=str(exc))
