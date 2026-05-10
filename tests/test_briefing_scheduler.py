"""Tests for APScheduler briefing scheduler (scheduler.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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

    # Mock DB queries
    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = [("vip@example.com",)]
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens]
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
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


@pytest.mark.asyncio
async def test_setup_scheduler_for_user_adds_per_user_job():
    """setup_scheduler_for_user adds a job with id briefing_user_{user_id}."""
    from daily.briefing.scheduler import scheduler, setup_scheduler_for_user, _scheduled_pipeline_run

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_scheduler_for_user(hour=5, minute=0, user_id=1)
        mock_add_job.assert_called_once()
        call_kwargs = mock_add_job.call_args[1]
        assert call_kwargs["id"] == "briefing_user_1"
        assert call_kwargs["replace_existing"] is True
        assert call_kwargs["kwargs"] == {"user_id": 1}
        assert mock_add_job.call_args[0][0] is _scheduled_pipeline_run


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_with_google_token():
    """_build_pipeline_kwargs with a google token populates email and calendar adapters."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_token = MagicMock()
    mock_token.encrypted_access_token = "enc_access"
    mock_token.encrypted_refresh_token = "enc_refresh"
    mock_token.provider = "google"
    mock_token.scopes = "https://www.googleapis.com/auth/gmail.readonly"

    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = [mock_token]

    mock_session.execute = AsyncMock(side_effect=[mock_result_vip, mock_result_tokens])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_gmail = MagicMock()
    mock_cal = MagicMock()
    mock_creds = MagicMock()

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", side_effect=lambda enc, key: f"decrypted:{enc}"),
        patch("daily.integrations.google.adapter.GmailAdapter", return_value=mock_gmail),
        patch("daily.integrations.google.adapter.GoogleCalendarAdapter", return_value=mock_cal),
        patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
    ):
        settings = Settings(redis_url="redis://localhost:6379/0", openai_api_key="key", briefing_email_top_n=5)
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert mock_gmail in result["email_adapters"]
    assert mock_cal in result["calendar_adapters"]
    assert result["message_adapters"] == []


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_with_outlook_token():
    """_build_pipeline_kwargs with an outlook token populates email_adapters."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_token = MagicMock()
    mock_token.encrypted_access_token = "enc_access"
    mock_token.encrypted_refresh_token = None
    mock_token.provider = "outlook"
    mock_token.scopes = "Mail.Read"

    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = [mock_token]

    mock_session.execute = AsyncMock(side_effect=[mock_result_vip, mock_result_tokens])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_outlook = MagicMock()

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", side_effect=lambda enc, key: f"decrypted:{enc}"),
        patch("daily.integrations.microsoft.adapter.OutlookAdapter", return_value=mock_outlook),
    ):
        settings = Settings(redis_url="redis://localhost:6379/0", openai_api_key="key", briefing_email_top_n=5)
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert mock_outlook in result["email_adapters"]
    assert result["calendar_adapters"] == []
    assert result["message_adapters"] == []


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_with_slack_token():
    """_build_pipeline_kwargs with a slack token populates message_adapters."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_token = MagicMock()
    mock_token.encrypted_access_token = "enc_slack"
    mock_token.encrypted_refresh_token = None
    mock_token.provider = "slack"
    mock_token.scopes = "channels:read"

    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = [mock_token]

    mock_session.execute = AsyncMock(side_effect=[mock_result_vip, mock_result_tokens])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_slack = MagicMock()

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", side_effect=lambda enc, key: f"decrypted:{enc}"),
        patch("daily.integrations.slack.adapter.SlackAdapter", return_value=mock_slack),
    ):
        settings = Settings(redis_url="redis://localhost:6379/0", openai_api_key="key", briefing_email_top_n=5)
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["email_adapters"] == []
    assert result["calendar_adapters"] == []
    assert mock_slack in result["message_adapters"]


@pytest.mark.asyncio
async def test_per_user_cron_two_users():
    """Two calls to setup_scheduler_for_user produce two distinct job ids."""
    from daily.briefing.scheduler import scheduler, setup_scheduler_for_user

    added = {}

    def fake_add_job(fn, trigger=None, kwargs=None, id=None, replace_existing=False):
        added[id] = {"kwargs": kwargs, "trigger": trigger}

    with patch.object(scheduler, "add_job", side_effect=fake_add_job):
        setup_scheduler_for_user(hour=5, minute=0, user_id=1)
        setup_scheduler_for_user(hour=14, minute=30, user_id=2)

    assert "briefing_user_1" in added
    assert "briefing_user_2" in added
    assert added["briefing_user_1"]["kwargs"] == {"user_id": 1}
    assert added["briefing_user_2"]["kwargs"] == {"user_id": 2}


# ---------------------------------------------------------------------------
# Token provider branches (lines 90-117)
# ---------------------------------------------------------------------------


def _make_token(provider: str, scopes: str = "") -> MagicMock:
    t = MagicMock()
    t.provider = provider
    t.encrypted_access_token = "enc_access"
    t.encrypted_refresh_token = "enc_refresh" if provider != "slack" else None
    t.scopes = scopes
    return t


def _make_session_ctx(tokens: list) -> tuple:
    """Return (mock_ctx, mock_session) wired for VIP + token queries."""
    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = tokens
    mock_session.execute = AsyncMock(side_effect=[mock_result_vip, mock_result_tokens])
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_google_token_creates_adapters():
    """_build_pipeline_kwargs instantiates GmailAdapter + GoogleCalendarAdapter for google tokens."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    google_token = _make_token(
        "google", "https://www.googleapis.com/auth/gmail.readonly"
    )
    mock_ctx, _ = _make_session_ctx([google_token])

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", return_value="plain_token"),
        patch("google.oauth2.credentials.Credentials"),
        patch("daily.integrations.google.adapter.GmailAdapter") as mock_gmail,
        patch("daily.integrations.google.adapter.GoogleCalendarAdapter") as mock_cal,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert len(result["email_adapters"]) == 1
    assert len(result["calendar_adapters"]) == 1
    mock_gmail.assert_called_once()
    mock_cal.assert_called_once()


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_outlook_token_creates_adapter():
    """_build_pipeline_kwargs instantiates OutlookAdapter for outlook/microsoft tokens."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    outlook_token = _make_token("outlook")
    mock_ctx, _ = _make_session_ctx([outlook_token])

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", return_value="plain_token"),
        patch("daily.integrations.microsoft.adapter.OutlookAdapter") as mock_outlook,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert len(result["email_adapters"]) == 1
    mock_outlook.assert_called_once()


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_slack_token_creates_adapter():
    """_build_pipeline_kwargs instantiates SlackAdapter for slack tokens."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    slack_token = _make_token("slack")
    mock_ctx, _ = _make_session_ctx([slack_token])

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
        patch("daily.vault.crypto.decrypt_token", return_value="plain_token"),
        patch("daily.integrations.slack.adapter.SlackAdapter") as mock_slack,
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert len(result["message_adapters"]) == 1
    mock_slack.assert_called_once()
