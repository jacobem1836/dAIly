"""Profile ORM model and Pydantic preferences model."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, func
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
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# Audit M-4: canonical set of briefing sections. category_order was
# previously unvalidated free text that gets joined straight into the
# narrator LLM's system prompt (see briefing/narrator.py -
# build_narrator_system_prompt's "Section order: {order}" preamble) — any
# value outside this set must be rejected before it is persisted or used,
# rather than trusted as arbitrary prompt content. Matches the three actual
# briefing sections the narrator prompt structures its output around
# (emails / calendar / slack — see narrator.py's NARRATOR_SYSTEM_PROMPT).
VALID_CATEGORIES: frozenset[str] = frozenset({"emails", "calendar", "slack"})


class UserPreferences(BaseModel):
    """Typed view of the JSONB preferences blob stored in UserProfile.

    Values are validated on read via model_validate(). Invalid values are
    rejected at this layer (T-03-01: Literal types restrict allowed values).

    Phase 4 additions:
        rejection_behaviour: Controls what happens after a user rejects an action draft.
            'ask_why' — prompt the user for a reason and allow edit (default per D-03).
            'discard' — silently discard the draft without prompting.
    """

    tone: Literal["formal", "casual", "conversational"] = "conversational"
    briefing_length: Literal["concise", "standard", "detailed"] = "standard"
    category_order: list[str] = ["emails", "calendar", "slack"]
    rejection_behaviour: Literal["ask_why", "discard"] = "ask_why"
