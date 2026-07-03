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
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
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
        "slack_channels",
    }
    assert required_keys == set(result.keys()), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )
    assert "vip@example.com" in result["vip_senders"]
    # No BriefingConfig row -> falls back to global settings default (audit C1)
    assert result["top_n"] == 5
    assert result["slack_channels"] == []


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
async def test_setup_scheduler_for_user_defaults_to_utc():
    """setup_scheduler_for_user with no timezone arg builds a CronTrigger in UTC
    (backward compatible with existing UTC-only callers, e.g. the CLI)."""
    from daily.briefing.scheduler import scheduler, setup_scheduler_for_user

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_scheduler_for_user(hour=5, minute=0, user_id=1)

    trigger = mock_add_job.call_args[1]["trigger"]
    assert str(trigger.timezone) == "UTC"


@pytest.mark.asyncio
async def test_setup_scheduler_for_user_uses_configured_timezone():
    """setup_scheduler_for_user passes a non-UTC timezone straight to CronTrigger
    so hour/minute are interpreted as LOCAL wall-clock time (audit M1 DST fix).

    Fails without the fix (CronTrigger would always be built with timezone="UTC")
    and passes with it (CronTrigger.timezone reflects the passed IANA zone).
    """
    from daily.briefing.scheduler import scheduler, setup_scheduler_for_user

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_scheduler_for_user(
            hour=7, minute=0, user_id=1, timezone="Australia/Brisbane"
        )

    trigger = mock_add_job.call_args[1]["trigger"]
    assert str(trigger.timezone) == "Australia/Brisbane"
    hour_field_index = trigger.FIELD_NAMES.index("hour")
    assert str(trigger.fields[hour_field_index]) == "7"


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
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
    )

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
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
    )

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
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
    )

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


def _make_session_ctx(tokens: list, briefing_config=None) -> tuple:
    """Return (mock_ctx, mock_session) wired for VIP + token + BriefingConfig queries."""
    mock_session = AsyncMock()
    mock_result_vip = MagicMock()
    mock_result_vip.fetchall.return_value = []
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = tokens
    mock_result_config = MagicMock()
    mock_result_config.scalar_one_or_none.return_value = briefing_config
    mock_session.execute = AsyncMock(
        side_effect=[mock_result_vip, mock_result_tokens, mock_result_config]
    )
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


# ---------------------------------------------------------------------------
# BriefingConfig write-only fields now read by _build_pipeline_kwargs (audit C1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_reads_persisted_email_top_n():
    """A persisted BriefingConfig.email_top_n overrides the global settings default.

    Before the fix, _build_pipeline_kwargs always used settings.briefing_email_top_n
    and never looked at the per-user BriefingConfig row, so `daily config set
    briefing.email_top_n` had no effect on the actual pipeline run. This test
    fails without the fix (top_n would be 5, the global default) and passes
    with it (top_n reflects the persisted per-user value of 20).
    """
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_config = MagicMock()
    mock_config.email_top_n = 20
    mock_config.slack_channels = []
    mock_ctx, _ = _make_session_ctx([], briefing_config=mock_config)

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=5,  # global default — must NOT win
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["top_n"] == 20


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_falls_back_to_settings_top_n_when_no_config():
    """With no BriefingConfig row, top_n falls back to settings.briefing_email_top_n."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_ctx, _ = _make_session_ctx([], briefing_config=None)

    with (
        patch("daily.briefing.scheduler.async_session", return_value=mock_ctx),
        patch("daily.briefing.scheduler.load_profile", new=AsyncMock(return_value={})),
    ):
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            openai_api_key="test-key",
            briefing_email_top_n=7,
        )
        result = await _build_pipeline_kwargs(user_id=1, settings=settings)

    assert result["top_n"] == 7


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_reads_persisted_slack_channels():
    """A persisted BriefingConfig.slack_channels reaches the pipeline kwargs.

    Audit C1: BriefingConfig.slack_channels was persisted but context_builder
    hardcoded channels=[] regardless, so Slack briefing never respected the
    configured list. This test fails without the fix (slack_channels would be
    [], the hardcoded value) and passes with it.
    """
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_config = MagicMock()
    mock_config.email_top_n = 5
    mock_config.slack_channels = ["C01PRIORITY", "C02PRIORITY"]
    mock_ctx, _ = _make_session_ctx([], briefing_config=mock_config)

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

    assert result["slack_channels"] == ["C01PRIORITY", "C02PRIORITY"]


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_slack_channels_empty_when_no_config():
    """With no BriefingConfig row, slack_channels defaults to an empty list."""
    from daily.briefing.scheduler import _build_pipeline_kwargs
    from daily.config import Settings

    mock_ctx, _ = _make_session_ctx([], briefing_config=None)

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

    assert result["slack_channels"] == []


# ---------------------------------------------------------------------------
# Proactive OAuth token refresh job (audit C2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_token_refresh_job_registers_interval_job():
    """setup_token_refresh_job registers a periodic (interval) job on the scheduler.

    Fails without the fix (no such function/job exists) and passes with it.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    from daily.briefing.scheduler import (
        TOKEN_REFRESH_INTERVAL_MINUTES,
        _run_token_refresh_job,
        scheduler,
        setup_token_refresh_job,
    )

    with patch.object(scheduler, "add_job") as mock_add_job:
        setup_token_refresh_job()

    mock_add_job.assert_called_once()
    call_args, call_kwargs = mock_add_job.call_args
    assert call_args[0] is _run_token_refresh_job
    assert call_kwargs["id"] == "token_refresh"
    assert call_kwargs["replace_existing"] is True
    trigger = call_kwargs["trigger"]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval.total_seconds() == TOKEN_REFRESH_INTERVAL_MINUTES * 60


@pytest.mark.asyncio
async def test_run_token_refresh_job_calls_refresh_expiring_tokens():
    """_run_token_refresh_job loads the vault key and calls refresh_expiring_tokens.

    This proves the previously-dead refresh_expiring_tokens function is now
    actually invoked by the scheduler's job wrapper.
    """
    from daily.briefing.scheduler import _run_token_refresh_job

    fake_results = [{"provider": "google", "user_id": 1, "success": True, "error": None}]

    with (
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32) as mock_load_key,
        patch(
            "daily.vault.refresh.refresh_expiring_tokens",
            new=AsyncMock(return_value=fake_results),
        ) as mock_refresh,
    ):
        await _run_token_refresh_job()

    mock_load_key.assert_called_once()
    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_token_refresh_job_survives_vault_key_failure():
    """_run_token_refresh_job does not raise if load_vault_key fails."""
    from daily.briefing.scheduler import _run_token_refresh_job

    with (
        patch(
            "daily.vault.crypto.load_vault_key",
            side_effect=ValueError("bad key"),
        ),
        patch(
            "daily.vault.refresh.refresh_expiring_tokens", new=AsyncMock()
        ) as mock_refresh,
    ):
        # Must not raise
        await _run_token_refresh_job()

    mock_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_token_refresh_job_survives_refresh_exception():
    """_run_token_refresh_job does not raise if refresh_expiring_tokens itself raises."""
    from daily.briefing.scheduler import _run_token_refresh_job

    with (
        patch("daily.vault.crypto.load_vault_key", return_value=b"k" * 32),
        patch(
            "daily.vault.refresh.refresh_expiring_tokens",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        # Must not raise
        await _run_token_refresh_job()
