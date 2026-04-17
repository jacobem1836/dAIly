"""Profile ORM model and Pydantic preferences model."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from daily.db.models import Base


class UserProfile(Base):
    """Stores per-user preferences as a JSONB blob.

    Using JSONB allows schema evolution (adding new preference fields) without
    requiring database migrations. Validation is enforced at the Pydantic layer
    on read, not at the DB schema level (per D-04).
    """

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UserPreferences(BaseModel):
    """Typed view of the JSONB preferences blob stored in UserProfile.

    Values are validated on read via model_validate(). Invalid values are
    rejected at this layer (T-03-01: Literal types restrict allowed values).

    Phase 4 additions:
        rejection_behaviour: Controls what happens after a user rejects an action draft.
            'ask_why' — prompt the user for a reason and allow edit (default per D-03).
            'discard' — silently discard the draft without prompting.

    Phase 9 additions:
        memory_enabled: Gates both extraction and injection of cross-session memory facts.
            True (default) — facts extracted at session end; relevant facts injected
              into briefing narrator and live session context.
            False — no extraction, no injection. Hard gate (no partial opt-out). Per D-05.
    """

    tone: Literal["formal", "casual", "conversational"] = "conversational"
    briefing_length: Literal["concise", "standard", "detailed"] = "standard"
    category_order: list[str] = ["emails", "calendar", "slack"]
    rejection_behaviour: Literal["ask_why", "discard"] = "ask_why"
    memory_enabled: bool = True
