"""Profile service: load and upsert user preferences."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from daily.profile.models import UserPreferences, UserProfile


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

    For 'category_order', value is parsed as a comma-separated list.
    Returns the updated UserPreferences.
    """
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
        parsed_value = [item.strip() for item in value.split(",")]
    else:
        parsed_value = value

    # Update the specific key — create new dict to avoid in-place mutation issues
    updated_prefs = dict(profile.preferences)
    updated_prefs[key] = parsed_value
    profile.preferences = updated_prefs

    await session.commit()
    return UserPreferences.model_validate(profile.preferences)
