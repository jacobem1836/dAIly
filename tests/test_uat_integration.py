"""
Integration tests replacing manual UAT tests 6-10 for Phase 02 (Briefing Pipeline).

These test the FastAPI app (health endpoint, lifespan) and CLI commands (config, VIP)
with mocked DB sessions — verifying real application wiring without requiring a live
Postgres instance.

UAT mapping:
  Test 6: FastAPI health endpoint returns 200
  Test 7: CLI config set/get persists BriefingConfig
  Test 8: CLI VIP add/list/remove manages VipSender rows
  Test 9: Schedule persistence — CLI sets config, lifespan reads it
  Test 10: Graceful DB fallback — app starts even when DB is unreachable
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers: reusable mock builders
# ---------------------------------------------------------------------------


def _mock_db_session(execute_return=None, side_effect=None):
    """Build a mock async_session context manager.

    Args:
        execute_return: Value returned by session.execute().
        side_effect: If set, session.__aenter__ raises this.
    """
    mock_session = AsyncMock()
    # session.add() is synchronous in SQLAlchemy — use MagicMock to avoid
    # "coroutine never awaited" warnings when CLI helpers call session.add().
    mock_session.add = MagicMock()
    if execute_return is not None:
        mock_session.execute = AsyncMock(return_value=execute_return)
    mock_ctx = AsyncMock()
    if side_effect:
        mock_ctx.__aenter__ = AsyncMock(side_effect=side_effect)
    else:
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _mock_scheduler():
    """Build a mock APScheduler that does nothing."""
    s = MagicMock()
    s.start = MagicMock()
    s.shutdown = MagicMock()
    return s


# ---------------------------------------------------------------------------
# UAT 6: FastAPI health endpoint returns 200
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """UAT 6: Server starts and /health returns 200 with scheduler started."""

    def test_health_returns_ok(self):
        """GET /health returns 200 and {"status": "ok"}."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler"),
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from daily.main import app

            client = TestClient(app)
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_scheduler_starts_during_lifespan(self):
        """Scheduler.start() is called when app starts."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler"),
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from daily.main import app

            with TestClient(app):
                mock_sched.start.assert_called_once()


# ---------------------------------------------------------------------------
# UAT 7: CLI config set persists BriefingConfig
# ---------------------------------------------------------------------------


class TestCLIConfig:
    """UAT 7: `daily config set briefing.schedule_time HH:MM` persists to DB."""

    def test_config_set_schedule_time(self):
        """config set briefing.schedule_time 07:30 → prints confirmation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no existing row

        mock_ctx, mock_session = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["config", "set", "briefing.schedule_time", "07:30"])

        assert result.exit_code == 0
        assert "Set briefing.schedule_time = 07:30" in result.stdout
        mock_session.commit.assert_called_once()

    def test_config_set_email_top_n(self):
        """config set briefing.email_top_n 10 → prints confirmation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_ctx, mock_session = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["config", "set", "briefing.email_top_n", "10"])

        assert result.exit_code == 0
        assert "Set briefing.email_top_n = 10" in result.stdout

    def test_config_set_invalid_key(self):
        """config set unknown.key value → prints error message."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["config", "set", "unknown.key", "foo"])

        assert result.exit_code == 0
        assert "Unknown config key" in result.stdout

    def test_config_set_invalid_time_format(self):
        """config set briefing.schedule_time badformat → prints error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["config", "set", "briefing.schedule_time", "badformat"])

        assert result.exit_code == 0
        assert "Invalid format" in result.stdout


# ---------------------------------------------------------------------------
# UAT 8: CLI VIP add/list/remove
# ---------------------------------------------------------------------------


class TestCLIVip:
    """UAT 8: `daily vip add/list/remove` manages VipSender rows."""

    def test_vip_add(self):
        """vip add boss@company.com → prints confirmation."""
        mock_ctx, mock_session = _mock_db_session()

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["vip", "add", "boss@company.com"])

        assert result.exit_code == 0
        assert "Added VIP: boss@company.com" in result.stdout
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_vip_remove(self):
        """vip remove boss@company.com → prints confirmation."""
        mock_ctx, mock_session = _mock_db_session()

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["vip", "remove", "boss@company.com"])

        assert result.exit_code == 0
        assert "Removed VIP: boss@company.com" in result.stdout
        mock_session.commit.assert_called_once()

    def test_vip_list_with_entries(self):
        """vip list → prints each VIP email."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("alice@co.com",), ("bob@co.com",)]

        mock_ctx, mock_session = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["vip", "list"])

        assert result.exit_code == 0
        assert "alice@co.com" in result.stdout
        assert "bob@co.com" in result.stdout

    def test_vip_list_empty(self):
        """vip list with no VIPs → prints 'No VIP senders configured.'."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["vip", "list"])

        assert result.exit_code == 0
        assert "No VIP senders configured" in result.stdout

    def test_vip_add_normalises_email(self):
        """vip add BOSS@Company.COM → stores lowercase, stripped."""
        mock_ctx, mock_session = _mock_db_session()

        with patch("daily.db.engine.async_session", return_value=mock_ctx):
            from daily.cli import app

            result = runner.invoke(app, ["vip", "add", "  BOSS@Company.COM  "])

        assert result.exit_code == 0
        # Verify the VipSender was created with lowered email
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.email == "boss@company.com"


# ---------------------------------------------------------------------------
# UAT 9: Schedule persistence — CLI → lifespan reads from DB
# ---------------------------------------------------------------------------


class TestSchedulePersistence:
    """UAT 9: Config set via CLI is picked up by lifespan on restart."""

    @pytest.mark.asyncio
    async def test_lifespan_reads_db_schedule(self):
        """Lifespan uses DB-stored 07:30 instead of env default 05:00."""
        mock_config = MagicMock()
        mock_config.schedule_hour = 7
        mock_config.schedule_minute = 30

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler") as mock_setup,
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from fastapi import FastAPI
            from daily.main import lifespan

            test_app = FastAPI()
            async with lifespan(test_app):
                pass

        mock_setup.assert_called_once_with(hour=7, minute=30, user_id=1)

    @pytest.mark.asyncio
    async def test_lifespan_logs_db_schedule(self, caplog):
        """Lifespan logs 'Briefing schedule loaded from database: 07:30 UTC'."""
        mock_config = MagicMock()
        mock_config.schedule_hour = 7
        mock_config.schedule_minute = 30

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config

        mock_ctx, _ = _mock_db_session(execute_return=mock_result)
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler"),
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
            caplog.at_level(logging.INFO, logger="daily.main"),
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from fastapi import FastAPI
            from daily.main import lifespan

            test_app = FastAPI()
            async with lifespan(test_app):
                pass

        assert "Briefing schedule loaded from database: 07:30 UTC" in caplog.text


# ---------------------------------------------------------------------------
# UAT 10: Graceful DB fallback — app starts even when DB is unreachable
# ---------------------------------------------------------------------------


class TestGracefulDBFallback:
    """UAT 10: App starts and serves /health even when DB is down."""

    def test_health_works_without_db(self):
        """GET /health returns 200 even when DB raises on startup."""
        mock_ctx, _ = _mock_db_session(side_effect=Exception("Connection refused"))
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler"),
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from daily.main import app

            client = TestClient(app)
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_falls_back_to_env_schedule_on_db_failure(self):
        """When DB is down, setup_scheduler uses env default (05:00)."""
        mock_ctx, _ = _mock_db_session(side_effect=Exception("Connection refused"))
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler") as mock_setup,
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from daily.main import app

            with TestClient(app):
                pass

        mock_setup.assert_called_once_with(hour=5, minute=0, user_id=1)

    @pytest.mark.asyncio
    async def test_logs_db_fallback_warning(self, caplog):
        """Lifespan logs warning when DB config read fails."""
        mock_ctx, _ = _mock_db_session(side_effect=Exception("DB unavailable"))
        mock_sched = _mock_scheduler()

        with (
            patch("daily.main.async_session", return_value=mock_ctx),
            patch("daily.main.setup_scheduler"),
            patch("daily.main.scheduler", mock_sched),
            patch("daily.main.Settings") as mock_settings_cls,
            caplog.at_level(logging.WARNING, logger="daily.main"),
        ):
            mock_settings_cls.return_value.briefing_schedule_time = "05:00"
            from fastapi import FastAPI
            from daily.main import lifespan

            test_app = FastAPI()
            async with lifespan(test_app):
                pass

        assert "Failed to read BriefingConfig from database" in caplog.text
