"""Adaptive sender ranking based on interaction signal decay.

Computes per-sender multipliers from signal_log entries (skip, re_request, expand).
Called by context_builder.py at briefing generation time to bias email ranking
toward senders the user engages with and away from senders they skip.

Per D-05: exponential time-decay scoring with sigmoid clamping to [0.5, 2.0].
Per D-06: get_sender_multipliers(user_id, db_session) -> dict[str, float].
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import exp, tanh

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from daily.profile.signals import SignalLog, SignalType

logger = logging.getLogger(__name__)

# Tuning constants (D-05) — extracted for easy adjustment
SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.skip: -1.0,
    SignalType.re_request: 1.0,
    SignalType.expand: 0.5,
}
DECAY_BASE = 0.95
WINDOW_DAYS = 30
SIGMOID_SCALE = 3.0


async def get_sender_multipliers(
    user_id: int, db_session: AsyncSession
) -> dict[str, float]:
    """Return sender -> ranking multiplier map from recent interaction signals.

    Per D-06: Only senders with at least one signal in the 30-day window
    are included. Missing senders get 1.0 at the call site (context_builder.py).

    Args:
        user_id: User whose signals to query.
        db_session: Async SQLAlchemy session.

    Returns:
        Dict mapping normalised sender email (lowercase, stripped) to a
        float multiplier in the range [0.5, 2.0].
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=WINDOW_DAYS)
    result = await db_session.execute(
        select(SignalLog).where(
            SignalLog.user_id == user_id,
            SignalLog.created_at >= cutoff,
            SignalLog.signal_type.in_([t.value for t in SIGNAL_WEIGHTS]),
            SignalLog.target_id.isnot(None),
        )
    )
    rows = result.scalars().all()

    # Aggregate decay-weighted scores per sender
    scores: dict[str, float] = {}
    now = datetime.now(tz=timezone.utc)
    for row in rows:
        signal_type = SignalType(row.signal_type)
        weight = SIGNAL_WEIGHTS[signal_type]
        # Handle timezone-naive Postgres datetimes (Pitfall 3 from RESEARCH.md)
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        days_old = (now - created_at).days
        decayed = weight * (DECAY_BASE ** days_old)
        sender = (row.target_id or "").lower().strip()
        if not sender:
            continue
        scores[sender] = scores.get(sender, 0.0) + decayed

    # Map score -> multiplier range approximately [0.5, 2.0], centered at 1.0 (score=0).
    # Formula: 1.0 + tanh(score / SIGMOID_SCALE), clamped to [0.5, 2.0].
    # Per D-05: "neutral sender (no signals) → multiplier ≈ 1.0 (sigmoid midpoint at score=0)".
    # tanh(0) = 0 → neutral = 1.0. tanh saturates at ±1 → asymptotic range [0.0, 2.0].
    # Clamp ensures lower bound of 0.5 (per SIG-03 and test spec).
    multipliers: dict[str, float] = {}
    for sender, score in scores.items():
        raw = 1.0 + tanh(score / SIGMOID_SCALE)
        multipliers[sender] = max(0.5, min(2.0, raw))
    return multipliers
