"""Tests for APScheduler briefing scheduler (scheduler.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_session_ctx(side_effects):
    """Return a mock async context manager whose session.execute returns side_effects."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=side_effects)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


def _make_session_factory(sessions):
    """Return a callable that yields each session context manager in order."""
    call_count = [0]

    def factory():
        idx = call_count[0]
        call_count[0] += 1
        return sessions[idx % len(sessions)]

    return factory


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_user_email_from_profile():
    """_build_pipeline_kwargs returns user_email from UserProfile.email when profile exists."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    # VIP query result
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []

    # Token query result (no tokens)
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    # UserProfile email query result — email is "user@example.com"
    mock_result_email = MagicMock()
    mock_result_email.scalar_one_or_none.return_value = "user@example.com"

    # Preferences query result (load_profile) — None profile returns defaults
    mock_result_prefs = MagicMock()
    mock_result_prefs.scalars.return_value.first.return_value = None

    # Four async_session() calls: vip, tokens, user_email, preferences
    sessions = [
        _make_mock_session_ctx([mock_result_vip]),
        _make_mock_session_ctx([mock_result_tokens]),
        _make_mock_session_ctx([mock_result_email]),
        _make_mock_session_ctx([mock_result_prefs]),
    ]

    with (
        patch("daily.briefing.scheduler.async_session", side_effect=sessions),
        patch("daily.briefing.scheduler.load_profile", return_value=None),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["user_email"] == "user@example.com"


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_user_email_empty_when_no_profile():
    """_build_pipeline_kwargs returns empty string user_email when no profile exists."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []

    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    # No UserProfile row for this user
    mock_result_email = MagicMock()
    mock_result_email.scalar_one_or_none.return_value = None

    mock_result_prefs = MagicMock()
    mock_result_prefs.scalars.return_value.first.return_value = None

    sessions = [
        _make_mock_session_ctx([mock_result_vip]),
        _make_mock_session_ctx([mock_result_tokens]),
        _make_mock_session_ctx([mock_result_email]),
        _make_mock_session_ctx([mock_result_prefs]),
    ]

    with (
        patch("daily.briefing.scheduler.async_session", side_effect=sessions),
        patch("daily.briefing.scheduler.load_profile", return_value=None),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["user_email"] == ""


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_user_email_empty_when_profile_email_none():
    """_build_pipeline_kwargs returns empty string when UserProfile.email is None."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []

    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    # UserProfile exists but email field is NULL
    mock_result_email = MagicMock()
    mock_result_email.scalar_one_or_none.return_value = None

    mock_result_prefs = MagicMock()
    mock_result_prefs.scalars.return_value.first.return_value = None

    sessions = [
        _make_mock_session_ctx([mock_result_vip]),
        _make_mock_session_ctx([mock_result_tokens]),
        _make_mock_session_ctx([mock_result_email]),
        _make_mock_session_ctx([mock_result_prefs]),
    ]

    with (
        patch("daily.briefing.scheduler.async_session", side_effect=sessions),
        patch("daily.briefing.scheduler.load_profile", return_value=None),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["user_email"] == ""


@pytest.mark.asyncio
async def test_scheduler_reschedule():
    """update_schedule calls scheduler.reschedule_job with CronTrigger params."""
    from apscheduler.triggers.cron import CronTrigger

    from daily.briefing.scheduler import scheduler, update_schedule

    with patch.object(scheduler, "reschedule_job") as mock_reschedule:
        update_schedule(10, 30)
        mock_reschedule.assert_called_once()
        call_kwargs = mock_reschedule.call_args
        assert call_kwargs[0][0] == "briefing_precompute"
        trigger = call_kwargs[1]["trigger"]
        assert isinstance(trigger, CronTrigger)


@pytest.mark.asyncio
async def test_setup_scheduler_adds_job():
    """setup_scheduler adds a job with _scheduled_pipeline_run as the callable."""
    from daily.briefing.scheduler import scheduler, setup_scheduler, _scheduled_pipeline_run

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_scheduler(hour=5, minute=30, user_id=1)
        mock_add_job.assert_called_once()
        call_args = mock_add_job.call_args
        # First positional arg should be _scheduled_pipeline_run
        assert call_args[0][0] is _scheduled_pipeline_run
        # Should have replace_existing=True
        assert call_args[1].get("replace_existing") is True


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_returns_required_keys():
    """_build_pipeline_kwargs returns dict with all pipeline dependency keys."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    # Mock DB queries — four separate async_session() calls:
    # 1. VIP senders, 2. integration tokens, 3. user_email, 4. preferences
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = [("vip@example.com",)]

    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    mock_result_email = MagicMock()
    mock_result_email.scalar_one_or_none.return_value = "vip@example.com"

    # 4th call: preferences session (load_profile is patched but async_session() still called)
    mock_result_prefs = MagicMock()
    mock_result_prefs.scalars.return_value.first.return_value = None

    sessions = [
        _make_mock_session_ctx([mock_result_vip]),
        _make_mock_session_ctx([mock_result_tokens]),
        _make_mock_session_ctx([mock_result_email]),
        _make_mock_session_ctx([mock_result_prefs]),
    ]

    with (
        patch("daily.briefing.scheduler.async_session", side_effect=sessions),
        patch("daily.briefing.scheduler.load_profile", return_value=None),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    required_keys = {
        "email_adapters",
        "calendar_adapters",
        "message_adapters",
        "vip_senders",
        "user_email",
        "top_n",
        "redis",
        "openai_client",
        "preferences",
    }
    assert required_keys == set(result.keys()), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )
    assert "vip@example.com" in result["vip_senders"]
    assert result["top_n"] == 5
