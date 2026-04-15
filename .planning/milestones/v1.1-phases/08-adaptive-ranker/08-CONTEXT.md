# Phase 8: Adaptive Ranker - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace static email heuristics with signal-learned personal scoring so briefing email order reflects the user's observed attention patterns. Scope: modify the ranker to incorporate a per-sender learned score derived from signal_log data, blended with existing heuristics. Memory extraction, transparency UI, and autonomy settings are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Scoring model
- **D-01:** Use a blended alpha model: `final_score = (alpha × learned_sender_score) + ((1 - alpha) × heuristic_sender_weight)`. This replaces only the sender_weight term in the existing formula — keyword, recency, and thread weights remain as heuristics.
- **D-02:** Alpha starts at 0.2 at cold start (fewer than 30 signals total for the user). It scales linearly: `alpha = min(0.8, signal_count / 30 × 0.8)`. Heuristics always retain at least 20% weight as a safety floor — alpha is capped at 0.8.
- **D-03:** Cold-start threshold is 30 signals (total across all senders for the user). Below 30 signals, alpha is derived from the formula above (will be low). The ranker must not error — it runs the same blend code path at all signal counts.

### Signal weighting
- **D-04:** Per-signal weights for computing learned_sender_score: `expand=+2`, `re_request=+2`, `follow_up=+1`, `skip=-2`, `correction=0` (neutral — correction is about content, not priority signal).
- **D-05:** The learned score for each sender is computed from the last 30 signals for that sender (rolling window, most recent 30 rows by created_at). If a sender has fewer than 30 signals, use all available signals for that sender.
- **D-06:** Raw sum of weighted signals is normalised to a [0, 40] range (matching WEIGHT_VIP ceiling) to produce learned_sender_score. VIP override (WEIGHT_VIP=40) continues to take precedence — if sender is in vip_senders, bypass the blend and use WEIGHT_VIP directly.

### What gets learned
- **D-07:** Only the sender_weight term is replaced by the blended learned score. The keyword_weight, recency_weight, and thread_activity_weight terms remain unchanged. Formula stays: `sender_weight_blended + keyword_weight + recency_weight + thread_activity_weight`.
- **D-08:** Learned scoring is per-sender (keyed by sender email address), not per-email. A sender's learned score is fetched once per briefing run (batch), not recalculated per email.

### Graceful degradation
- **D-09:** If signal retrieval from the DB fails or times out, set alpha=0 and proceed with full heuristic scoring. Log a structured warning (`logger.warning("signal_retrieval_failed", ...)`) but do not surface the error to the user — briefing delivers on schedule.
- **D-10:** Signal retrieval timeout: 2 seconds. If not resolved in 2s, fallback to heuristics immediately.

### Claude's Discretion
- Exact SQL query for fetching last-30 signals per sender (aggregate or ORM-level)
- How learned_sender_score is normalised from raw sum to [0, 40] (e.g., clip + scale vs sigmoid)
- Whether to cache the per-sender learned scores in Redis for the briefing window or query fresh each run
- Where the adaptive ranker logic lives: extend `ranker.py` or a new `adaptive_ranker.py` wrapper

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing ranker
- `src/daily/briefing/ranker.py` — Current heuristic scoring formula, constants, and rank_emails() signature to extend
- `src/daily/briefing/models.py` — RankedEmail and EmailMetadata shapes

### Signal data
- `src/daily/profile/signals.py` — SignalLog ORM model, SignalType enum, signal_log table schema
- `src/daily/db/models.py` — Base ORM class (check for async session patterns)

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — INTEL-01 acceptance criteria
- `.planning/ROADMAP.md` §Phase 8 — goal and success criteria (cold-start, graceful degradation, ordering correctness)

### Prior phase context
- `.planning/milestones/v1.1-phases/07-tech-debt-fixes/07-CONTEXT.md` — D-08 (backfill was done before this phase; signal data is clean)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ranker.py:score_email()` — The sender_weight computation (lines 85–95 approx) is the exact injection point for the blended alpha. The rest of the function stays unchanged.
- `ranker.py:rank_emails()` — Orchestrates scoring; will need to accept a `learned_scores: dict[str, float]` param populated from signal_log before the email loop.
- `signals.py:SignalLog` — ORM model is ready; a read query over this table is all that's needed to build the per-sender learned scores dict.

### Established Patterns
- Async-first: all DB access uses `async with AsyncSession` — signal retrieval must be async
- Pydantic models for cross-module data shapes — if a new LearnedScores type is needed, follow this pattern
- VIP override in ranker takes precedence unconditionally — preserve this, skip blend for VIP senders

### Integration Points
- `rank_emails()` is called from the briefing pipeline (`pipeline.py`) — the call site is where learned_scores will be pre-fetched and passed in
- Signal log is written by the voice orchestrator (`nodes.py`) after user interactions — read-only for this phase

</code_context>

<specifics>
## Specific Ideas

- The 30-signal cold-start threshold is from the STATE.md pending confirmation — now confirmed.
- VIP senders bypass the blend entirely (D-06) — this preserves the existing guarantee that VIP emails always surface regardless of learned patterns.
- The 2s timeout on signal retrieval (D-10) is tight enough to protect briefing delivery latency.

</specifics>

<deferred>
## Deferred Ideas

- Keyword weight learning (e.g., if user always expands emails with "action required", boost that keyword weight) — future intelligence phase.
- Recency decay personalisation (user may prefer older important emails over newer noise) — deferred.
- Per-sender score explanation ("ranked higher because you expanded 5 recent emails from this sender") — Memory Transparency phase (Phase 10).

</deferred>

---

*Phase: 08-adaptive-ranker*
*Context gathered: 2026-04-15*
