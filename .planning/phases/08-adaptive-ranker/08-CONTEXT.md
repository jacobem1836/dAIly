# Phase 8: Adaptive Ranker — Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the static heuristic ranking in the morning briefing with a signal-learned personal scoring layer. User interaction signals (expand, skip, re_request, follow_up, correction) already captured in `signal_log` are aggregated per sender to produce a multiplier that scales the existing heuristic score. When signal data is insufficient or unavailable, the ranker falls back to pure heuristics unchanged.

**In scope:**
- Per-sender multiplier computation from `signal_log` (new module: `adaptive_ranker.py`)
- Signal aggregation with decay and sigmoid normalisation
- Wiring multipliers into the existing `rank_emails()` call via `context_builder.py`
- Cold-start fallback (< 30 total signals → all multipliers = 1.0)
- Graceful degradation when DB session unavailable (pipeline runs, adaptive step skipped)
- Unit tests for multiplier computation, cold-start, decay, and blend

**Out of scope (v1.1):**
- Per-topic/keyword learning
- Cross-session memory (Phase 9)
- Dashboard or visibility into learned scores

</domain>

<decisions>
## Implementation Decisions

### 1. Blend Strategy — Sender Multiplier
Learned signals produce a per-sender float multiplier (range 0.5–2.0, sigmoid-normalised). The full `score_email()` result is multiplied by this float. A sender the user consistently engages with is scaled up; one consistently skipped is scaled down. Existing heuristics (recency, keywords, VIP, thread activity) all contribute before multiplication.

**Future milestone note:** Multiplier range and sigmoid parameters are candidates for user-configurable personalisation (e.g., "make suggestions more conservative" or "weight my attention patterns heavily"). Could expose as `ADAPTIVE_WEIGHT_MIN` / `ADAPTIVE_WEIGHT_MAX` preferences in `user_profile.preferences`.

### 2. Signal Weights
| Signal | Weight |
|--------|--------|
| re_request | +1.0 |
| expand | +0.5 |
| follow_up | +0.3 |
| correction | −0.3 |
| skip | −0.5 |

Raw net score per sender → sigmoid-normalised to 0.5–2.0 range.

**Future milestone note:** These weights are strong candidates for per-user personalisation. A power user who expands every email would benefit from higher skip weight; a passive user would benefit from heavier re_request weighting. Could be stored as a `signal_weights` dict in `user_profile.preferences`.

### 3. Signal Decay
14-day exponential half-life. Each signal's contribution is weighted by `exp(-ln(2) * days_old / 14)`. A signal from 14 days ago contributes half as much as today's.

**Future milestone note:** Half-life is a strong personalisation candidate. Users with stable attention patterns may want 30d; users in fast-changing roles may want 7d. Could store as `attention_halflife_days` in `user_profile.preferences`.

### 4. Scope — Per-Sender Only
v1.1 adaptive ranking operates at email-address granularity only. Topic/keyword-level learning is deferred.

**Future milestone note:** Per-topic/keyword learning requires a richer signal model (what subject keywords co-occurred with expand/skip). Defer to v2.0 after sufficient per-sender signal volume is validated.

### 5. Module Boundary
New file: `src/daily/profile/adaptive_ranker.py`

Exports:
- `get_sender_multipliers(user_id, session, min_signals=30) -> dict[str, float]`
  - Returns `{}` (empty = all multipliers 1.0) when total signal count < `min_signals`
  - Returns `{}` on any DB error (graceful degradation)

`context_builder.py` gains optional `db_session: AsyncSession | None = None`. When provided, calls `get_sender_multipliers()` and passes result to `rank_emails()`.

`rank_emails()` gains optional `sender_multipliers: dict[str, float] = {}`. When provided, multiplies each email's heuristic score by its sender's multiplier (default 1.0 for unknown senders).

`run_briefing_pipeline()` gains optional `db_session: AsyncSession | None = None`. Passes through to `context_builder`.

**Future milestone note:** `min_signals=30` is a global threshold. A per-sender minimum (e.g., 5 interactions before any multiplier is applied for that sender) could reduce noise at higher signal volumes. Defer to v2.0 when real signal data can inform the threshold.

### 6. Cold-Start Threshold
< 30 total signals in `signal_log` for the user → `get_sender_multipliers()` returns `{}` → all scores unchanged from v1.0 heuristics. No error, no log noise.

</decisions>

<code_context>
## Existing Code Insights

### Current Ranker (`src/daily/briefing/ranker.py`)
- `score_email()` is a pure function — no DB, no async. Safe to extend via optional `sender_multipliers` dict.
- `rank_emails()` is the entry point — orchestrates scoring and top-N selection.
- VIP override sets `sender_weight = WEIGHT_VIP` unconditionally. Adaptive multiplier applies to the full score AFTER VIP weight is included — VIP senders can still be scaled by attention signals.

### Signal Log (`src/daily/profile/signals.py`)
- `SignalLog` ORM model: `user_id`, `signal_type` (str), `target_id` (email_id or similar), `metadata_json` (JSONB), `created_at`.
- Sender email is NOT stored directly on `signal_log` — it lives in `metadata_json` or must be joined via the email record.
- **Implementation note:** The `append_signal()` call from the voice agent should include `{"sender": "<email>"}` in `metadata` when the signal refers to an email item. Check existing signal-capture callsites to confirm whether sender is already stored — if not, that callsite must be updated as part of this phase.

### Context Builder (`src/daily/briefing/context_builder.py`)
- `build_context()` at line ~127 calls `rank_emails(all_emails, vip_senders, user_email, top_n=top_n)`.
- This is the injection point for `sender_multipliers`.

### Pipeline (`src/daily/briefing/pipeline.py`)
- `run_briefing_pipeline()` has no `db_session` parameter today.
- Scheduler's `_build_pipeline_kwargs()` constructs all args — must be updated to pass a session factory or session to the pipeline when adaptive ranking is enabled.

</code_context>

<specifics>
## Specific Requirements

1. `get_sender_multipliers()` must never raise — all DB errors caught and logged, returns `{}` on failure.
2. Cold-start path must be tested: < 30 signals → multipliers are all 1.0 (i.e., heuristic output unchanged).
3. Decay must be applied per-signal before aggregation, not on the aggregate.
4. `rank_emails()` signature change must be backward-compatible — `sender_multipliers={}` default.
5. `build_context()` and `run_briefing_pipeline()` signature changes must be backward-compatible — `db_session=None` default.
6. All new code in `adaptive_ranker.py` must be unit-tested without a live DB (mock `AsyncSession`).

</specifics>

<deferred>
## Deferred Ideas

- Per-user configurable signal weights (`signal_weights` in `user_profile.preferences`) — v2.0
- Per-user configurable attention half-life (`attention_halflife_days`) — v2.0
- Per-user configurable multiplier range (`ADAPTIVE_WEIGHT_MIN` / `ADAPTIVE_WEIGHT_MAX`) — v2.0
- Per-sender minimum signal threshold before multiplier applied — v2.0
- Topic/keyword-level attention learning — v2.0
- Dashboard visibility into computed sender multipliers — v2.0 (DASH-01)

</deferred>
