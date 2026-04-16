"""Adaptive per-sender ranking multiplier computation.

Implements INTEL-01: queries signal_log, applies 14-day exponential decay per
signal, aggregates weighted contributions per sender, and sigmoid-normalises to
a (0.0, 2.0) range where raw score 0 maps exactly to multiplier 1.0 (neutral).

Design decisions from 08-CONTEXT.md:
- Sigmoid formula: 2.0 * sigmoid(raw_score) — neutral sender (raw=0) → 1.0 exactly.
- Cold-start: < 30 total signals for user → return {} (heuristics unchanged).
- Graceful degradation: any DB exception → log warning, return {}.
- Decay: exp(-ln(2) * days_old / 14) per signal before aggregation.
- Sender key: normalised lowercase stripped email address.

"Never raises" contract: get_sender_multipliers() catches all exceptions and
returns {} so the briefing pipeline (BRIEF-01) always delivers.

References: INTEL-01, 08-CONTEXT.md (decisions 2, 3, 5, 6, 7).
"""

import logging
import math
from datetime import datetime, timezone

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from daily.profile.signals import SignalLog

logger = logging.getLogger(__name__)

HALF_LIFE_DAYS: float = 14.0
MIN_MULT: float = 0.0
MAX_MULT: float = 2.0
DEFAULT_MIN_SIGNALS: int = 30

SIGNAL_WEIGHTS: dict[str, float] = {
    "re_request": 1.0,
    "expand": 0.5,
    "follow_up": 0.3,
    "correction": -0.3,
    "skip": -0.5,
}


def _decay_weight(created_at: datetime) -> float:
    """Return exponential decay weight for a signal based on its age.

    Formula: exp(-ln(2) * days_old / HALF_LIFE_DAYS)
    A signal from 14 days ago contributes half the weight of a signal from today.

    Defensively coerces timezone-naive created_at to UTC (Pitfall 2 in RESEARCH).

    Args:
        created_at: The timestamp the signal was created.

    Returns:
        Float in (0.0, 1.0] — 1.0 for brand-new signals, approaching 0 with age.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    days_old = (now - created_at).total_seconds() / 86400.0
    return math.exp(-math.log(2) * days_old / HALF_LIFE_DAYS)


def _sigmoid_neutral_at_one(raw_score: float) -> float:
    """Map raw_score (−∞, +∞) to (0.0, 2.0) with neutral=1.0 at raw_score=0.

    Formula: 2.0 * (1 / (1 + exp(-raw_score)))
    sigmoid(0) = 0.5, so 2.0 * 0.5 = 1.0 exactly — neutral sender.

    Args:
        raw_score: Aggregated decayed signal score for a sender.

    Returns:
        Float in (0.0, 2.0) — 1.0 for raw score of zero.
    """
    return 2.0 * (1.0 / (1.0 + math.exp(-raw_score)))


def _compute_multipliers(
    rows: list[tuple[str, str, datetime]],
) -> dict[str, float]:
    """Aggregate per-sender decayed signal scores and sigmoid-normalise.

    Args:
        rows: Iterable of (sender, signal_type, created_at) tuples.
              signal_type values not in SIGNAL_WEIGHTS are silently skipped.

    Returns:
        Dict mapping normalised sender email to sigmoid-normalised multiplier.
        Keys are lowercased and stripped.
    """
    raw_scores: dict[str, float] = {}

    for sender, signal_type, created_at in rows:
        weight = SIGNAL_WEIGHTS.get(signal_type)
        if weight is None:
            continue
        normalised_sender = sender.lower().strip()
        decay = _decay_weight(created_at)
        raw_scores[normalised_sender] = (
            raw_scores.get(normalised_sender, 0.0) + decay * weight
        )

    return {
        sender: _sigmoid_neutral_at_one(score)
        for sender, score in raw_scores.items()
    }


async def get_sender_multipliers(
    user_id: int,
    session: AsyncSession,
    min_signals: int = DEFAULT_MIN_SIGNALS,
) -> dict[str, float]:
    """Compute per-sender ranking multipliers from signal_log.

    Returns a dict mapping normalised sender email addresses to float multipliers
    in (0.0, 2.0). Callers should use .get(sender, 1.0) — unknown senders default
    to 1.0 (no adjustment).

    Cold-start: if total signal count for user < min_signals, returns {} immediately.
    Graceful degradation: any DB error returns {} and logs a warning — never raises.

    Args:
        user_id: The user whose signals to aggregate.
        session: Async SQLAlchemy session (caller-owned).
        min_signals: Minimum total signals required before adaptive ranking is
                     applied. Defaults to 30.

    Returns:
        Dict[str, float] mapping sender email to multiplier, or {} on cold-start
        or DB error.
    """
    try:
        # Step 1: Cold-start check — count ALL signals for user across all types
        count_stmt = (
            select(func.count())
            .select_from(SignalLog)
            .where(SignalLog.user_id == user_id)
        )
        total = (await session.execute(count_stmt)).scalar_one()
        if total < min_signals:
            return {}

        # Step 2: Fetch signals with sender in metadata_json (NULL guard applied)
        detail_stmt = (
            select(
                cast(SignalLog.metadata_json["sender"].astext, String).label("sender"),
                SignalLog.signal_type,
                SignalLog.created_at,
            )
            .where(SignalLog.user_id == user_id)
            .where(SignalLog.metadata_json.isnot(None))
            .where(SignalLog.metadata_json["sender"].astext.isnot(None))
        )
        result = await session.execute(detail_stmt)
        rows = result.fetchall()

        # Step 3: Aggregate with decay and sigmoid-normalise per sender
        return _compute_multipliers(rows)

    except Exception:
        logger.warning(
            "get_sender_multipliers: DB error, skipping adaptive ranking"
        )
        return {}
