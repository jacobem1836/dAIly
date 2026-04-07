"""Tests for the profile service — UserProfile ORM, UserPreferences model, load/upsert."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# UserPreferences model tests (pure Pydantic — no DB needed)
# ---------------------------------------------------------------------------


def test_user_preferences_defaults():
    from daily.profile.models import UserPreferences

    prefs = UserPreferences()
    assert prefs.tone == "conversational"
    assert prefs.briefing_length == "standard"
    assert prefs.category_order == ["emails", "calendar", "slack"]


def test_user_preferences_tone_validation_accepts_valid():
    from daily.profile.models import UserPreferences

    for tone in ("formal", "casual", "conversational"):
        prefs = UserPreferences(tone=tone)
        assert prefs.tone == tone


def test_user_preferences_tone_validation_rejects_invalid():
    from daily.profile.models import UserPreferences

    with pytest.raises(ValidationError):
        UserPreferences(tone="aggressive")


def test_user_preferences_briefing_length_accepts_valid():
    from daily.profile.models import UserPreferences

    for length in ("concise", "standard", "detailed"):
        prefs = UserPreferences(briefing_length=length)
        assert prefs.briefing_length == length


def test_user_preferences_briefing_length_rejects_invalid():
    from daily.profile.models import UserPreferences

    with pytest.raises(ValidationError):
        UserPreferences(briefing_length="verbose")


def test_user_preferences_category_order_default():
    from daily.profile.models import UserPreferences

    prefs = UserPreferences()
    assert prefs.category_order == ["emails", "calendar", "slack"]


# ---------------------------------------------------------------------------
# UserProfile ORM model presence tests (structural, no DB)
# ---------------------------------------------------------------------------


def test_user_profile_orm_has_correct_tablename():
    from daily.profile.models import UserProfile

    assert UserProfile.__tablename__ == "user_profile"


def test_user_profile_orm_has_required_columns():
    from daily.profile.models import UserProfile

    columns = {c.name for c in UserProfile.__table__.columns}
    assert "id" in columns
    assert "user_id" in columns
    assert "preferences" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


# ---------------------------------------------------------------------------
# load_profile service tests (mocked session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_profile_returns_defaults_when_no_row():
    """load_profile returns UserPreferences defaults when no DB row exists."""
    from daily.profile.models import UserPreferences
    from daily.profile.service import load_profile

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    prefs = await load_profile(user_id=1, session=mock_session)

    assert isinstance(prefs, UserPreferences)
    assert prefs.tone == "conversational"
    assert prefs.briefing_length == "standard"
    assert prefs.category_order == ["emails", "calendar", "slack"]


@pytest.mark.asyncio
async def test_load_profile_returns_stored_preferences():
    """load_profile returns UserPreferences built from stored JSONB dict."""
    from daily.profile.models import UserPreferences
    from daily.profile.service import load_profile

    stored = {"tone": "casual", "briefing_length": "concise", "category_order": ["emails", "slack", "calendar"]}
    mock_profile_row = MagicMock()
    mock_profile_row.preferences = stored

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_profile_row
    mock_session.execute.return_value = mock_result

    prefs = await load_profile(user_id=1, session=mock_session)

    assert prefs.tone == "casual"
    assert prefs.briefing_length == "concise"
    assert prefs.category_order == ["emails", "slack", "calendar"]


# ---------------------------------------------------------------------------
# upsert_preference service tests (mocked session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_preference_creates_row_when_none_exists():
    """upsert_preference creates a new row and returns updated preferences."""
    from daily.profile.models import UserPreferences
    from daily.profile.service import upsert_preference

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    prefs = await upsert_preference(user_id=1, key="tone", value="casual", session=mock_session)

    assert isinstance(prefs, UserPreferences)
    assert prefs.tone == "casual"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_preference_updates_existing_row():
    """upsert_preference updates an existing row's preferences dict."""
    from daily.profile.models import UserPreferences
    from daily.profile.service import upsert_preference

    existing_prefs = {"tone": "formal", "briefing_length": "standard", "category_order": ["emails", "calendar", "slack"]}
    mock_profile_row = MagicMock()
    mock_profile_row.preferences = dict(existing_prefs)  # mutable copy

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_profile_row
    mock_session.execute.return_value = mock_result

    prefs = await upsert_preference(user_id=1, key="tone", value="casual", session=mock_session)

    assert prefs.tone == "casual"
    # Verify no duplicate add
    mock_session.add.assert_not_called()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_preference_does_not_create_duplicate_row():
    """upsert_preference on existing row does not call session.add."""
    from daily.profile.service import upsert_preference

    existing_prefs = {"tone": "formal", "briefing_length": "detailed", "category_order": ["emails", "calendar", "slack"]}
    mock_profile_row = MagicMock()
    mock_profile_row.preferences = dict(existing_prefs)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_profile_row
    mock_session.execute.return_value = mock_result

    await upsert_preference(user_id=1, key="briefing_length", value="concise", session=mock_session)

    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_preference_category_order_parses_csv():
    """upsert_preference parses comma-separated value for category_order."""
    from daily.profile.service import upsert_preference

    existing_prefs = {"tone": "formal", "briefing_length": "standard", "category_order": ["emails", "calendar", "slack"]}
    mock_profile_row = MagicMock()
    mock_profile_row.preferences = dict(existing_prefs)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_profile_row
    mock_session.execute.return_value = mock_result

    prefs = await upsert_preference(user_id=1, key="category_order", value="slack,emails,calendar", session=mock_session)

    assert prefs.category_order == ["slack", "emails", "calendar"]
