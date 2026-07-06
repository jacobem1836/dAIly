"""Profile service: load and upsert user preferences."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from daily.db.models import User
from daily.profile.models import VALID_CATEGORIES, UserPreferences, UserProfile


async def _ensure_default_user(user_id: int, session: AsyncSession) -> None:
    """Insert a default user row if none exists for this user_id.

    PoC workaround for Phase 3 single-user CLI (user_id=1 stub, T-03-11).
    Real authentication and user creation come in Phase 4.
    Uses INSERT ... ON CONFLICT DO NOTHING so it is safe to call on every
    upsert — no extra SELECT round-trip needed when the row already exists.
    """
    stmt = (
        pg_insert(User)
        .values(id=user_id)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)


async def load_profile(user_id: int, session: AsyncSession) -> UserPreferences:
    """Load user preferences from DB, returning defaults if no row exists."""
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalars().first()
    if profile is None:
        return UserPreferences()
    return UserPreferences.model_validate(profile.preferences)


async def upsert_preference(
    user_id: int, key: str, value: str, session: AsyncSession
) -> UserPreferences:
    """Set a single preference key for a user and persist it.

    Ensures a default user row exists before upserting the profile (PoC
    workaround for Phase 3 hardcoded user_id=1 stub — real auth in Phase 4).
    For 'category_order', value is parsed as a comma-separated list and each
    item is validated against VALID_CATEGORIES (audit M-4) — category_order
    is joined straight into the narrator LLM's system prompt
    (briefing/narrator.py), so it must not accept arbitrary free text.
    Returns the updated UserPreferences.

    Raises:
        ValueError: If key == "category_order" and any item is not a
            recognised category. daily.cli._upsert_profile already checks
            this before calling upsert_preference (so CLI users get a clean
            error message), but this is the actual persistence boundary and
            must not trust any other caller to have validated first.
    """
    await _ensure_default_user(user_id, session)

    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalars().first()

    if profile is None:
        profile = UserProfile(user_id=user_id, preferences={})
        session.add(profile)

    # Parse category_order as comma-separated list
    parsed_value: str | list[str]
    if key == "category_order":
        items = [item.strip() for item in value.split(",")]
        invalid = [item for item in items if item not in VALID_CATEGORIES]
        if invalid:
            raise ValueError(
                f"Invalid category_order value(s): {', '.join(invalid)}. "
                f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            )
        parsed_value = items
    else:
        parsed_value = value

    # Update the specific key — create new dict to avoid in-place mutation issues
    updated_prefs = dict(profile.preferences)
    updated_prefs[key] = parsed_value
    profile.preferences = updated_prefs

    await session.commit()
    return UserPreferences.model_validate(profile.preferences)
