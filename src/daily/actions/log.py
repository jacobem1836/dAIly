"""Action audit log service.

append_action_log() creates an append-only row in action_log for every action
(approved or rejected). Mirrors the append_signal pattern in profile/signals.py.

Security constraints:
  T-04-03 / D-09 / SEC-04:
    - content_summary is truncated to 200 chars (never the full body)
    - body_hash is SHA-256 of full_body (integrity check only)
    - full_body is NEVER persisted — only used transiently to compute the hash
"""
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from daily.actions.models import ActionLog


async def append_action_log(
    user_id: int,
    action_type: str,
    target: str,
    content_summary: str,
    full_body: str,
    approval_status: str,
    outcome: str | None,
    session: AsyncSession,
) -> None:
    """Append a single action audit row to action_log.

    Per D-08 fire-and-forget pattern: callers in nodes.py wrap this in
    asyncio.create_task() so it does not block the voice response path.

    Args:
        user_id: The user who initiated the action.
        action_type: String value of ActionType enum (e.g. 'draft_email').
        target: Recipient email, Slack channel, or calendar event ID.
        content_summary: Summary text — will be truncated to 200 chars.
        full_body: Full draft body — used ONLY to compute body_hash, never stored.
        approval_status: 'pending', 'approved', or 'rejected'.
        outcome: 'sent', 'failed', or None (None while pending/rejected).
        session: Async SQLAlchemy session (caller-owned).
    """
    body_hash = hashlib.sha256(full_body.encode()).hexdigest()

    row = ActionLog(
        user_id=user_id,
        action_type=action_type,
        target=target,
        content_summary=content_summary[:200],
        body_hash=body_hash,
        approval_status=approval_status,
        outcome=outcome,
    )
    session.add(row)
    await session.commit()
