"""Outlook ActionExecutor: sends emails via Microsoft Graph API.

Security boundaries:
  ACT-06 / T-04-11: validate() calls check_recipient_whitelist before any API call.
  D-11 / T-04-17: validate() checks Mail.Send scope is granted before any API call.
  T-04-13: graph_client holds decrypted token in-memory only at call time.

Graph API:
  Uses the msgraph-sdk natively async client (no asyncio.to_thread wrapping needed).
  Sends via POST /me/sendMail with a structured message body.
"""

from __future__ import annotations

import logging
from typing import Any

from daily.actions.base import ActionDraft, ActionExecutor, ActionResult
from daily.actions.whitelist import check_recipient_whitelist

logger = logging.getLogger(__name__)

OUTLOOK_MAIL_SEND_SCOPE = "Mail.Send"


class OutlookExecutor(ActionExecutor):
    """Sends emails via Microsoft Graph API sendMail endpoint.

    Args:
        graph_client: msgraph-sdk GraphServiceClient instance.
        known_addresses: Set of known contact addresses for whitelist validation.
        granted_scopes: Set of OAuth scopes granted by the user.
    """

    def __init__(
        self,
        graph_client: Any,
        known_addresses: set[str],
        granted_scopes: set[str],
    ) -> None:
        self._graph_client = graph_client
        self._known_addresses = known_addresses
        self._granted_scopes = granted_scopes

    async def validate(self, draft: ActionDraft) -> None:
        """Pre-execution validation for Outlook send.

        Checks:
          1. Mail.Send scope is granted (D-11 / T-04-17).
          2. Recipient is in known_addresses whitelist (ACT-06 / T-04-11).

        Args:
            draft: The ActionDraft to validate.

        Raises:
            ValueError: If scope is missing or recipient is unknown.
        """
        if OUTLOOK_MAIL_SEND_SCOPE not in self._granted_scopes:
            raise ValueError(
                "Outlook Mail.Send scope not granted. "
                "Reconnect your Microsoft account with write permissions."
            )
        if draft.recipient:
            check_recipient_whitelist(draft.recipient, self._known_addresses)

    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Send an email via Microsoft Graph API sendMail.

        Builds the sendMail request body and posts to /me/sendMail.
        msgraph-sdk is natively async — no asyncio.to_thread wrapping needed.

        Args:
            draft: The approved ActionDraft to execute.

        Returns:
            ActionResult(success=True, external_id="sent") on success.
        """
        try:
            from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
                SendMailPostRequestBody,
            )
            from msgraph.generated.models.message import Message
            from msgraph.generated.models.item_body import ItemBody
            from msgraph.generated.models.body_type import BodyType
            from msgraph.generated.models.recipient import Recipient
            from msgraph.generated.models.email_address import EmailAddress

            subject = f"Re: {draft.subject}" if draft.subject else "(no subject)"

            message = Message()
            message.subject = subject

            body = ItemBody()
            body.content_type = BodyType.Text
            body.content = draft.body
            message.body = body

            recipient = Recipient()
            email_addr = EmailAddress()
            email_addr.address = draft.recipient
            recipient.email_address = email_addr
            message.to_recipients = [recipient]

            if draft.thread_id:
                message.conversation_id = draft.thread_id

            request_body = SendMailPostRequestBody()
            request_body.message = message

            await self._graph_client.me.send_mail.post(request_body)
            return ActionResult(success=True, external_id="sent")

        except Exception as exc:
            logger.warning("OutlookExecutor.execute: failed: %s", exc)
            return ActionResult(success=False, error=str(exc))
