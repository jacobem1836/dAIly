"""
Tests for profile CLI commands (Task 1 TDD).

Tests cover:
- `daily config set profile.tone casual` calls upsert_preference with key="tone", value="casual"
- `daily config set profile.tone invalid_value` prints error about valid values
- `daily config set profile.briefing_length detailed` calls upsert_preference
- `daily config set profile.category_order calendar,emails,slack` calls upsert_preference
- `daily config set profile.unknown_key value` prints error about unknown key
- `daily config get profile` prints current preferences as formatted output
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from daily.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_prefs(tone="conversational", briefing_length="standard", category_order=None):
    """Return a mock UserPreferences-like object."""
    mock = MagicMock()
    mock.tone = tone
    mock.briefing_length = briefing_length
    mock.category_order = category_order or ["emails", "calendar", "slack"]
    return mock


# ---------------------------------------------------------------------------
# config set profile.tone
# ---------------------------------------------------------------------------


class TestConfigSetProfileTone:
    def test_set_tone_casual_calls_upsert_preference(self):
        """daily config set profile.tone casual calls upsert_preference(key='tone', value='casual')."""
        mock_prefs = _make_mock_prefs(tone="casual")

        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Set profile.tone = casual"
            result = runner.invoke(app, ["config", "set", "profile.tone", "casual"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "casual" in result.output
        mock_upsert.assert_called_once_with(user_id=1, key="tone", value="casual")

    def test_set_tone_formal_succeeds(self):
        """daily config set profile.tone formal is valid and echoes result."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Set profile.tone = formal"
            result = runner.invoke(app, ["config", "set", "profile.tone", "formal"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        mock_upsert.assert_called_once_with(user_id=1, key="tone", value="formal")

    def test_set_tone_invalid_prints_error(self):
        """daily config set profile.tone invalid prints error about valid values."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Invalid tone: invalid. Must be: formal, casual, conversational"
            result = runner.invoke(app, ["config", "set", "profile.tone", "invalid"])

        assert result.exit_code == 0
        output = result.output
        assert "Invalid" in output or "invalid" in output or "formal" in output or "casual" in output


# ---------------------------------------------------------------------------
# config set profile.briefing_length
# ---------------------------------------------------------------------------


class TestConfigSetProfileBriefingLength:
    def test_set_briefing_length_detailed(self):
        """daily config set profile.briefing_length detailed calls upsert_preference."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Set profile.briefing_length = detailed"
            result = runner.invoke(app, ["config", "set", "profile.briefing_length", "detailed"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        mock_upsert.assert_called_once_with(user_id=1, key="briefing_length", value="detailed")

    def test_set_briefing_length_concise(self):
        """daily config set profile.briefing_length concise is valid."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Set profile.briefing_length = concise"
            result = runner.invoke(app, ["config", "set", "profile.briefing_length", "concise"])

        assert result.exit_code == 0
        mock_upsert.assert_called_once_with(user_id=1, key="briefing_length", value="concise")

    def test_set_briefing_length_invalid_prints_error(self):
        """daily config set profile.briefing_length invalid_val prints error."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Invalid briefing_length: invalid_val. Must be: concise, standard, detailed"
            result = runner.invoke(app, ["config", "set", "profile.briefing_length", "invalid_val"])

        assert result.exit_code == 0
        output = result.output
        assert "invalid" in output.lower() or "concise" in output or "detailed" in output


# ---------------------------------------------------------------------------
# config set profile.category_order
# ---------------------------------------------------------------------------


class TestConfigSetProfileCategoryOrder:
    def test_set_category_order(self):
        """daily config set profile.category_order calendar,emails,slack calls upsert_preference."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Set profile.category_order = calendar,emails,slack"
            result = runner.invoke(
                app, ["config", "set", "profile.category_order", "calendar,emails,slack"]
            )

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        mock_upsert.assert_called_once_with(
            user_id=1, key="category_order", value="calendar,emails,slack"
        )


# ---------------------------------------------------------------------------
# config set unknown profile key
# ---------------------------------------------------------------------------


class TestConfigSetProfileUnknownKey:
    def test_unknown_profile_key_prints_error(self):
        """daily config set profile.unknown_key value prints error about unknown key."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = "Unknown profile key: unknown_key. Valid keys: briefing_length, category_order, tone"
            result = runner.invoke(app, ["config", "set", "profile.unknown_key", "val"])

        assert result.exit_code == 0
        output = result.output
        assert "unknown" in output.lower() or "Unknown" in output or "Valid" in output


# ---------------------------------------------------------------------------
# config get profile
# ---------------------------------------------------------------------------


class TestConfigGetProfile:
    def test_get_profile_prints_preferences(self):
        """daily config get profile prints current tone, briefing_length, category_order."""
        with patch("daily.cli._get_profile", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (
                "tone: conversational\n"
                "briefing_length: standard\n"
                "category_order: emails, calendar, slack"
            )
            result = runner.invoke(app, ["config", "get", "profile"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "tone" in result.output
        assert "briefing_length" in result.output
        assert "category_order" in result.output
        mock_get.assert_called_once_with(user_id=1)

    def test_get_unknown_key_prints_error(self):
        """daily config get unknown_key prints error about supported keys."""
        result = runner.invoke(app, ["config", "get", "unknown_key"])

        assert result.exit_code == 0
        assert "unknown_key" in result.output or "Unknown" in result.output or "Supported" in result.output


# ---------------------------------------------------------------------------
# Profile routing in config_set
# ---------------------------------------------------------------------------


class TestProfileRouting:
    def test_profile_key_routes_to_upsert_profile_not_upsert_config(self):
        """profile.* keys must route to _upsert_profile, not _upsert_config."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_profile, \
             patch("daily.cli._upsert_config", new_callable=AsyncMock) as mock_config:
            mock_profile.return_value = "Set profile.tone = casual"
            result = runner.invoke(app, ["config", "set", "profile.tone", "casual"])

        assert result.exit_code == 0
        mock_profile.assert_called_once()
        mock_config.assert_not_called()

    def test_briefing_key_routes_to_upsert_config_not_upsert_profile(self):
        """briefing.* keys must still route to _upsert_config (backward compatible)."""
        with patch("daily.cli._upsert_profile", new_callable=AsyncMock) as mock_profile, \
             patch("daily.cli._upsert_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = "Set briefing.schedule_time = 06:00"
            result = runner.invoke(app, ["config", "set", "briefing.schedule_time", "06:00"])

        assert result.exit_code == 0
        mock_config.assert_called_once()
        mock_profile.assert_not_called()
