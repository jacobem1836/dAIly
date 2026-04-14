"""ActionLog ORM model and ApprovalStatus enum.

Append-only audit log for all actions (approved and rejected).

Security constraints:
  T-04-03 / D-09 / SEC-04: No raw body column — body_hash (SHA-256) and
  content_summary[:200] only. Full body is never persisted.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from daily.db.models import Base


class ApprovalStatus(str, Enum):
    """Approval lifecycle states for an action.

    Using str mixin so values compare directly with string DB values.
    """

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ActionLog(Base):
    """Append-only audit log for all actions, approved or rejected.

    Per T-04-03 / D-09 / SEC-04: raw body content is NEVER stored.
    Only content_summary[:200] and body_hash (SHA-256 hex) are persisted.

    Columns:
        id: Auto-incrementing primary key.
        user_id: Foreign key to users.id — which user initiated the action.
        action_type: String value of ActionType enum.
        target: Recipient email, Slack channel, or calendar event ID.
        content_summary: First 200 characters of draft body (not the full body).
        body_hash: SHA-256 hex digest of the full draft body for integrity checking.
        approval_status: 'pending', 'approved', or 'rejected'.
        outcome: 'sent', 'failed', or None (None while pending).
        created_at: Row insertion timestamp (server-generated).
    """

    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action_type: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(String(500))
    content_summary: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 hex = 64 chars
    approval_status: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
