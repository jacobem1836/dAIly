"""Tests for adaptive_ranker.py — get_sender_multipliers and helpers.

Covers:
- Cold-start (< 30 total signals → {})
- DB error graceful degradation → {}
- NULL metadata_json rows excluded without error
- Sigmoid: raw score 0 → multiplier 1.0 exactly
- Decay: 14-day-old signal → weight ≈ 0.5
- Engaged sender (repeat expand) → multiplier > 1.8
- Disengaged sender (repeat skip) → multiplier < 0.25
- Unknown signal types silently ignored
- Sender key normalisation (lowercase + strip)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from daily.profile.adaptive_ranker import (
    _compute_multipliers,
    _decay_weight,
    _sigmoid_neutral_at_one,
    get_sender_multipliers,
)


# ---------------------------------------------------------------------------
# Helper: build a mock result set whose scalar_one() returns a count value
# ---------------------------------------------------------------------------


def _mock_count_result(count: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = count
    return result


def _mock_rows_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


# ---------------------------------------------------------------------------
# Test 1: cold-start returns empty dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cold_start_returns_empty():
    """Count query returns 5 (< 30) — expect {} without error."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = _mock_count_result(5)

    result = await get_sender_multipliers(user_id=1, session=mock_session)

    assert result == {}
    # Only one execute call (the count) should have been made
    assert mock_session.execute.call_count == 1


# ---------------------------------------------------------------------------
# Test 2: DB error returns empty dict and logs a warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_error_returns_empty():
    """session.execute raises OperationalError — expect {} and a warning logged."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = OperationalError(
        "connection refused", None, None
    )

    with patch("daily.profile.adaptive_ranker.logger") as mock_logger:
        result = await get_sender_multipliers(user_id=1, session=mock_session)

    assert result == {}
    mock_logger.warning.assert_called_once()
    # Warning message must not contain metadata values — only a generic message
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "DB error" in warning_msg or "skipping" in warning_msg


# ---------------------------------------------------------------------------
# Test 3: NULL metadata rows — no error, returns {} when no qualifying rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_metadata_excluded():
    """Count ≥ 30 but detail query returns empty rows — returns {} without error."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = [
        _mock_count_result(50),
        _mock_rows_result([]),  # no rows with sender in metadata
    ]

    result = await get_sender_multipliers(user_id=1, session=mock_session)

    assert result == {}


# ---------------------------------------------------------------------------
# Test 4: Sigmoid at zero score → exactly 1.0
# ---------------------------------------------------------------------------


def test_sigmoid_zero_score():
    """_sigmoid_neutral_at_one(0.0) must return exactly 1.0."""
    assert _sigmoid_neutral_at_one(0.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 5: Decay at 14-day half-life → ≈ 0.5
# ---------------------------------------------------------------------------


def test_decay_half_life():
    """Signal from exactly 14 days ago should have decay weight ≈ 0.5."""
    now = datetime.now(tz=timezone.utc)
    fourteen_days_ago = now - timedelta(days=14)
    weight = _decay_weight(fourteen_days_ago)
    assert weight == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Test 6: Engaged sender (5 expand, recent) → high multiplier; skipped → low
# ---------------------------------------------------------------------------


def test_compute_multipliers_engaged_sender():
    """Alice with 5 recent expand → multiplier > 1.8; Bob with 5 skip → < 0.25."""
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(hours=1)  # decay ≈ 1.0

    # 5 expand signals at weight 0.5 each → raw ≈ 2.5
    alice_rows = [("alice@example.com", "expand", recent)] * 5
    # 5 skip signals at weight -0.5 each → raw ≈ -2.5
    bob_rows = [("bob@example.com", "skip", recent)] * 5

    result = _compute_multipliers(alice_rows + bob_rows)

    assert "alice@example.com" in result
    assert "bob@example.com" in result
    assert result["alice@example.com"] > 1.8
    assert result["bob@example.com"] < 0.25


# ---------------------------------------------------------------------------
# Test 7: Unknown signal type is silently ignored (no KeyError)
# ---------------------------------------------------------------------------


def test_unknown_signal_type_ignored():
    """Rows with signal_type not in SIGNAL_WEIGHTS contribute nothing and don't error."""
    now = datetime.now(tz=timezone.utc)
    rows = [
        ("alice@example.com", "unknown_signal", now),
        ("alice@example.com", "expand", now),  # raw contribution = 0.5
    ]
    result = _compute_multipliers(rows)

    # Only 'expand' contributed → raw = 0.5 → sigmoid(0.5) = 2 * (1/(1+exp(-0.5)))
    import math
    expected = 2.0 * (1.0 / (1.0 + math.exp(-0.5)))
    assert "alice@example.com" in result
    assert result["alice@example.com"] == pytest.approx(expected, abs=0.001)


# ---------------------------------------------------------------------------
# Test 8: Sender key normalisation — uppercase and padded sender → lowercase stripped key
# ---------------------------------------------------------------------------


def test_sender_key_normalisation():
    """Sender '  ALICE@EXAMPLE.COM  ' in rows → key 'alice@example.com' in result."""
    now = datetime.now(tz=timezone.utc)
    rows = [("  ALICE@EXAMPLE.COM  ", "expand", now)]
    result = _compute_multipliers(rows)

    assert "alice@example.com" in result
    assert "  ALICE@EXAMPLE.COM  " not in result
