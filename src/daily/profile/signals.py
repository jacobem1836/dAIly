"""Signal log ORM model, SignalType enum, and append_signal service.

Captures interaction signals from the briefing session per D-07 (signal taxonomy)
and D-08 (fire-and-forget pattern — callers wrap append_signal in asyncio.create_task()).

Requirement: PERS-02
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from daily.db.models import Base


class SignalType(str, Enum):
    """Interaction signal taxonomy per D-07.

    Using str mixin so values compare directly with string DB values
    (e.g. SignalType.skip == "skip" is True).
    """

    skip = "skip"
    correction = "correction"
    re_request = "re_request"
    follow_up = "follow_up"
    expand = "expand"


class SignalLog(Base):
    """Append-only log of user interaction signals.

    Per D-08: rows are never updated or deleted — only inserted.
    signal_type stores the string value of SignalType enum.
    target_id identifies the email, event, or message the signal refers to.
    metadata_json holds optional flexible extra context (system-generated only — T-03-02).
    """

    __tablename__ = "signal_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    signal_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


async def append_signal(
    user_id: int,
    signal_type: SignalType,
    session: AsyncSession,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append a single interaction signal row to signal_log.

    Per D-08: fire-and-forget — callers should wrap this in asyncio.create_task()
    so it does not block the voice response path.

    Args:
        user_id: The user this signal belongs to.
        signal_type: One of the SignalType enum values.
        session: Async SQLAlchemy session (caller-owned).
        target_id: Optional reference to an email_id, event_id, or message_id.
        metadata: Optional dict of extra context (system-generated only).
    """
    row = SignalLog(
        user_id=user_id,
        signal_type=signal_type.value,
        target_id=target_id,
        metadata_json=metadata,
    )
    session.add(row)
    await session.commit()
