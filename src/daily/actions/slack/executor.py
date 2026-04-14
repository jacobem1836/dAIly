"""Slack ActionExecutor: posts messages to Slack channels via slack_sdk WebClient.

Security boundaries:
  ACT-06 / T-04-12: validate() checks channel is in known_channels before any API call.
  D-11 / T-04-17: validate() checks chat:write scope is granted before any API call.

Threading (Pitfall 2):
  thread_ts MUST be passed as str(), never as a float. Slack treats "1234567890.000001"
  and 1234567890.000001 differently — the float form may silently lose precision,
  causing the reply to land in the wrong thread.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from daily.actions.base import ActionDraft, ActionExecutor, ActionResult

logger = logging.getLogger(__name__)

SLACK_CHAT_WRITE_SCOPE = "chat:write"


class SlackExecutor(ActionExecutor):
    """Posts messages to Slack channels via slack_sdk WebClient.

    Args:
        client: slack_sdk.WebClient instance.
        known_channels: Set of known channel IDs for whitelist validation.
        granted_scopes: Set of OAuth scopes granted by the Slack workspace.
    """

    def __init__(
        self,
        client: Any,
        known_channels: set[str],
        granted_scopes: set[str],
    ) -> None:
        self._client = client
        self._known_channels = known_channels
        self._granted_scopes = granted_scopes

    async def validate(self, draft: ActionDraft) -> None:
        """Pre-execution validation for Slack message.

        Checks:
          1. chat:write scope is granted (D-11 / T-04-17).
          2. channel_id is in known_channels whitelist (ACT-06 / T-04-12).

        Args:
            draft: The ActionDraft to validate.

        Raises:
            ValueError: If scope is missing or channel is unknown.
        """
        if SLACK_CHAT_WRITE_SCOPE not in self._granted_scopes:
            raise ValueError(
                "Slack chat:write scope not granted. "
                "Reconnect your Slack workspace with write permissions."
            )
        if draft.channel_id and draft.channel_id not in self._known_channels:
            raise ValueError(
                f"Channel '{draft.channel_id}' is not in known channels. "
                "Add it to your workspace channels or cancel."
            )

    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Post a message to a Slack channel via WebClient.chat_postMessage.

        CRITICAL: thread_ts is cast to str() — never passed as a float
        (Pitfall 2 from RESEARCH.md: float precision can lose the fractional ts).

        Args:
            draft: The approved ActionDraft to execute.

        Returns:
            ActionResult with success from response["ok"] and ts as external_id.
        """
        try:
            response = await asyncio.to_thread(
                self._client.chat_postMessage,
                channel=draft.channel_id,
                text=draft.body,
                thread_ts=str(draft.thread_id) if draft.thread_id else None,
            )
            return ActionResult(
                success=response["ok"],
                external_id=response.get("ts"),
            )
        except Exception as exc:
            logger.warning("SlackExecutor.execute: failed: %s", exc)
            return ActionResult(success=False, error=str(exc))
