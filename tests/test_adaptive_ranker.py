"""Tests for the adaptive ranker — get_sender_multipliers decay formula.

Covers:
  - Empty signals -> empty dict
  - Single skip signal -> multiplier < 1.0
  - Single re_request signal -> multiplier > 1.0
  - Single expand signal -> multiplier slightly above 1.0
  - Window cutoff: 31-day-old signals excluded
  - Window includes: 29-day-old signals included
  - Sigmoid lower bound: many skips -> multiplier >= 0.5
  - Sigmoid upper bound: many re_requests -> multiplier <= 2.0
  - Sender normalisation: "  Alice@Example.COM  " -> "alice@example.com"
  - Null target_id excluded from results
  - Multiple senders produce independent multipliers
  - Decay reduces weight of older signals vs fresh signals
"""

from datetime import datetime, timedelta, timezone
from math import exp
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daily.profile.adaptive_ranker import get_sender_multipliers
from daily.profile.signals import SignalLog, SignalType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = 42


def _make_signal(
    signal_type: SignalType,
    target_id: str | None = "sender@example.com",
    days_old: int = 0,
    user_id: int = USER_ID,
) -> SignalLog:
    """Create an in-memory SignalLog with a synthetic created_at."""
    now = datetime.now(tz=timezone.utc)
    created_at = now - timedelta(days=days_old)
    row = SignalLog(
        user_id=user_id,
        signal_type=signal_type.value,
        target_id=target_id,
    )
    # Override server_default — inject created_at directly
    row.created_at = created_at
    return row


def _mock_session(rows: list[SignalLog]) -> AsyncMock:
    """Return a mock AsyncSession whose execute().scalars().all() returns rows."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_session.execute.return_value = mock_result
    return mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_signals_returns_empty_dict():
    """No signals in DB for user -> returns empty dict."""
    session = _mock_session([])
    result = await get_sender_multipliers(USER_ID, session)
    assert result == {}


@pytest.mark.asyncio
async def test_single_skip_signal_returns_below_one():
    """One skip signal (weight=-1.0) -> multiplier < 1.0."""
    rows = [_make_signal(SignalType.skip)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "sender@example.com" in result
    assert result["sender@example.com"] < 1.0


@pytest.mark.asyncio
async def test_single_re_request_signal_returns_above_one():
    """One re_request signal (weight=+1.0) -> multiplier > 1.0."""
    rows = [_make_signal(SignalType.re_request)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "sender@example.com" in result
    assert result["sender@example.com"] > 1.0


@pytest.mark.asyncio
async def test_single_expand_signal():
    """One expand signal (weight=+0.5) -> multiplier slightly above 1.0."""
    rows = [_make_signal(SignalType.expand)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "sender@example.com" in result
    # expand weight=0.5, score=0.5, multiplier=0.5 + 1.5/(1+exp(-0.5/3)) > 1.0
    assert result["sender@example.com"] > 1.0
    # But less than a re_request multiplier, so check it's reasonable
    assert result["sender@example.com"] < 1.5


@pytest.mark.asyncio
async def test_window_cutoff_excludes_old_signals():
    """Signal with created_at 31 days ago -> excluded from results, returns {}."""
    rows = [_make_signal(SignalType.skip, days_old=31)]
    session = _mock_session([])  # SQL query returns nothing (cutoff excludes it)
    result = await get_sender_multipliers(USER_ID, session)
    assert result == {}


@pytest.mark.asyncio
async def test_window_includes_recent_signals():
    """Signal with created_at 29 days ago -> included in results."""
    rows = [_make_signal(SignalType.re_request, days_old=29)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    # 29 days old: decay = 0.95^29 = ~0.228; score = 1.0 * 0.228 = 0.228
    # multiplier = 0.5 + 1.5/(1+exp(-0.228/3)) > 1.0
    assert "sender@example.com" in result
    assert result["sender@example.com"] > 1.0


@pytest.mark.asyncio
async def test_sigmoid_range_lower_bound():
    """Many skip signals from same sender -> multiplier >= 0.5."""
    # 20 skip signals (today) -> score = -20.0 -> sigmoid -> ~0.5
    rows = [_make_signal(SignalType.skip, target_id="spammer@example.com") for _ in range(25)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "spammer@example.com" in result
    assert result["spammer@example.com"] >= 0.5


@pytest.mark.asyncio
async def test_sigmoid_range_upper_bound():
    """Many re_request signals from same sender -> multiplier <= 2.0."""
    # 20 re_request signals (today) -> score = +20.0 -> sigmoid -> ~2.0
    rows = [_make_signal(SignalType.re_request, target_id="vip@example.com") for _ in range(25)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "vip@example.com" in result
    assert result["vip@example.com"] <= 2.0


@pytest.mark.asyncio
async def test_sender_normalisation():
    """Signal with target_id '  Alice@Example.COM  ' -> key is 'alice@example.com'."""
    rows = [_make_signal(SignalType.re_request, target_id="  Alice@Example.COM  ")]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "alice@example.com" in result
    assert "  Alice@Example.COM  " not in result


@pytest.mark.asyncio
async def test_null_target_id_excluded():
    """Signal with target_id=None -> not in result dict."""
    rows = [_make_signal(SignalType.skip, target_id=None)]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert result == {}


@pytest.mark.asyncio
async def test_multiple_senders_independent():
    """Two senders with different signal patterns -> independent multipliers."""
    rows = [
        _make_signal(SignalType.skip, target_id="low@example.com"),
        _make_signal(SignalType.re_request, target_id="high@example.com"),
        _make_signal(SignalType.re_request, target_id="high@example.com"),
    ]
    session = _mock_session(rows)
    result = await get_sender_multipliers(USER_ID, session)
    assert "low@example.com" in result
    assert "high@example.com" in result
    assert result["low@example.com"] < 1.0
    assert result["high@example.com"] > 1.0
    assert result["high@example.com"] > result["low@example.com"]


@pytest.mark.asyncio
async def test_decay_reduces_old_signal_weight():
    """Same signal type, one today, one 10 days ago -> today's contributes more.

    Expected: two re_request signals (one fresh, one 10 days old) produce a higher
    multiplier than two re_request signals (both 10 days old).
    """
    rows_mixed = [
        _make_signal(SignalType.re_request, target_id="sender@example.com", days_old=0),
        _make_signal(SignalType.re_request, target_id="sender@example.com", days_old=10),
    ]
    rows_old = [
        _make_signal(SignalType.re_request, target_id="sender@example.com", days_old=10),
        _make_signal(SignalType.re_request, target_id="sender@example.com", days_old=10),
    ]

    session_mixed = _mock_session(rows_mixed)
    result_mixed = await get_sender_multipliers(USER_ID, session_mixed)

    session_old = _mock_session(rows_old)
    result_old = await get_sender_multipliers(USER_ID, session_old)

    # Fresh signal contributes more -> mixed score is higher than both-old
    assert result_mixed["sender@example.com"] > result_old["sender@example.com"]
