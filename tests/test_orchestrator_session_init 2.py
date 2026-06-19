"""Tests for orchestrator/session.py initialize_session_state and helpers.

Covers:
- initialize_session_state returns correct structure
- Briefing narrative populated from cache hit
- Empty string on cache miss
- Email context populated from adapter
- Email adapter exception handled gracefully
- _extract_email helper
- get_email_adapters / set_email_adapters registry
"""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _extract_email helper
# ---------------------------------------------------------------------------


def test_extract_email_bare_address():
    """_extract_email returns address unchanged when no display name."""
    from daily.orchestrator.session import _extract_email

    assert _extract_email("alice@example.com") == "alice@example.com"


def test_extract_email_with_display_name():
    """_extract_email strips display name from 'Name <email>' format."""
    from daily.orchestrator.session import _extract_email

    result = _extract_email("Alice Smith <alice@example.com>")
    assert result == "alice@example.com"


def test_extract_email_empty_string():
    """_extract_email returns empty string for empty input."""
    from daily.orchestrator.session import _extract_email

    assert _extract_email("") == ""


def test_extract_email_no_angle_brackets():
    """_extract_email returns full string when no angle brackets present."""
    from daily.orchestrator.session import _extract_email

    result = _extract_email("alice@example.com")
    assert result == "alice@example.com"


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


def test_get_email_adapters_returns_empty_by_default():
    """get_email_adapters returns empty list before any adapters are set."""
    from daily.orchestrator import session

    session.set_email_adapters([])
    result = session.get_email_adapters()
    assert result == []


def test_set_get_email_adapters_round_trip():
    """set_email_adapters stores adapters retrievable via get_email_adapters."""
    from daily.orchestrator import session

    fake_adapter = MagicMock()
    session.set_email_adapters([fake_adapter])

    result = session.get_email_adapters()
    assert result == [fake_adapter]

    # Cleanup
    session.set_email_adapters([])


# ---------------------------------------------------------------------------
# initialize_session_state
# ---------------------------------------------------------------------------


def _make_briefing(narrative: str = "Here is your briefing."):
    b = MagicMock()
    b.narrative = narrative
    return b


def _make_preferences():
    prefs = MagicMock()
    prefs.model_dump.return_value = {"tone": "conversational", "briefing_length": "standard"}
    return prefs


@pytest.mark.asyncio
async def test_initialize_returns_correct_keys():
    """initialize_session_state returns dict with required keys."""
    from daily.orchestrator.session import initialize_session_state

    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=_make_briefing())),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[]),
    ):
        result = await initialize_session_state(
            user_id=1, redis=redis, db_session=db_session
        )

    assert "briefing_narrative" in result
    assert "active_user_id" in result
    assert "preferences" in result
    assert "email_context" in result


@pytest.mark.asyncio
async def test_initialize_narrative_from_cache():
    """briefing_narrative is populated from cached briefing."""
    from daily.orchestrator.session import initialize_session_state

    briefing = _make_briefing("You have 3 emails and 1 meeting today.")
    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=briefing)),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[]),
    ):
        result = await initialize_session_state(user_id=1, redis=redis, db_session=db_session)

    assert result["briefing_narrative"] == "You have 3 emails and 1 meeting today."


@pytest.mark.asyncio
async def test_initialize_empty_narrative_on_cache_miss():
    """briefing_narrative is empty string when no cached briefing exists."""
    from daily.orchestrator.session import initialize_session_state

    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=None)),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[]),
    ):
        result = await initialize_session_state(user_id=1, redis=redis, db_session=db_session)

    assert result["briefing_narrative"] == ""


@pytest.mark.asyncio
async def test_initialize_active_user_id_set():
    """active_user_id matches the user_id argument."""
    from daily.orchestrator.session import initialize_session_state

    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=None)),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[]),
    ):
        result = await initialize_session_state(user_id=42, redis=redis, db_session=db_session)

    assert result["active_user_id"] == 42


@pytest.mark.asyncio
async def test_initialize_email_context_populated():
    """email_context is populated from the adapter when emails are available."""
    from daily.orchestrator.session import initialize_session_state
    from daily.integrations.models import EmailMetadata, EmailPage

    email = EmailMetadata(
        message_id="m001",
        thread_id="t001",
        subject="Test subject",
        sender="Alice <alice@example.com>",
        recipient="bob@example.com",
        timestamp=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
        is_unread=True,
        labels=["INBOX"],
    )
    page = EmailPage(emails=[email], next_page_token=None)
    adapter = AsyncMock()
    adapter.list_emails = AsyncMock(return_value=page)

    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=None)),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[adapter]),
    ):
        result = await initialize_session_state(user_id=1, redis=redis, db_session=db_session)

    assert len(result["email_context"]) == 1
    ctx = result["email_context"][0]
    assert ctx["message_id"] == "m001"
    assert ctx["subject"] == "Test subject"
    assert ctx["sender"] == "alice@example.com"


@pytest.mark.asyncio
async def test_initialize_email_adapter_error_handled_gracefully():
    """Exception from adapter is caught; email_context is empty, no crash."""
    from daily.orchestrator.session import initialize_session_state

    adapter = AsyncMock()
    adapter.list_emails = AsyncMock(side_effect=RuntimeError("connection failed"))

    redis = MagicMock()
    db_session = MagicMock()

    with (
        patch("daily.orchestrator.session.get_briefing", new=AsyncMock(return_value=None)),
        patch("daily.orchestrator.session.load_profile", new=AsyncMock(return_value=_make_preferences())),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[adapter]),
    ):
        result = await initialize_session_state(user_id=1, redis=redis, db_session=db_session)

    assert result["email_context"] == []
