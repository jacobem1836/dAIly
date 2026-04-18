---
phase: "08"
plan: "01"
subsystem: profile
tags: [adaptive-ranking, signal-decay, sigmoid, cold-start, graceful-degradation]
dependency_graph:
  requires: []
  provides: [adaptive_ranker.get_sender_multipliers]
  affects: [briefing/ranker.py, briefing/context_builder.py]
tech_stack:
  added: []
  patterns: [exponential-decay, sigmoid-normalisation, async-sqlalchemy-mock]
key_files:
  created:
    - src/daily/profile/adaptive_ranker.py
    - tests/test_adaptive_ranker.py
  modified: []
decisions:
  - "Sigmoid formula 2.0*sigmoid(raw) chosen so raw=0 maps to exactly 1.0 (neutral) — differs from RESEARCH.md Pattern 3 (1.25 midpoint) per critical_decisions in prompt"
  - "Cold-start counts ALL signals for user across all types (not per-sender) then returns {} if < 30"
  - "Sender key: normalised lowercase stripped email address"
  - "DB error logs warning without metadata values to satisfy T-08-03 (no information disclosure)"
metrics:
  duration_minutes: 15
  completed_at: "2026-04-16T00:02:54Z"
  tasks_completed: 1
  files_changed: 2
---

# Phase 8 Plan 1: Adaptive Ranker Core Module Summary

## One-liner

Per-sender ranking multiplier from signal_log with 14-day exponential decay, 2.0*sigmoid normalisation (neutral=1.0), cold-start guard, and never-raises contract.

## What Was Built

`src/daily/profile/adaptive_ranker.py` — new module exporting:

- `get_sender_multipliers(user_id, session, min_signals=30) -> dict[str, float]`
- `_decay_weight(created_at) -> float`
- `_sigmoid_neutral_at_one(raw_score) -> float`
- `_compute_multipliers(rows) -> dict[str, float]`

Constants: `HALF_LIFE_DAYS=14.0`, `SIGNAL_WEIGHTS` (5 signal types), `DEFAULT_MIN_SIGNALS=30`.

`tests/test_adaptive_ranker.py` — 8 tests covering all success criteria.

## Decisions Made

1. **Sigmoid formula**: `2.0 * sigmoid(raw_score)` so that raw score 0 gives multiplier 1.0 exactly. The RESEARCH.md Pattern 3 proposed a [0.5, 2.0] remap giving 1.25 at neutral — overridden by the plan's `<critical_decisions>` block which locked the formula and the 1.0 neutral requirement.

2. **Cold-start counting**: Count query uses `select(func.count()).select_from(SignalLog).where(...)` — counts all signal types for the user, not just those with sender in metadata.

3. **JSONB extraction idiom**: Used `.astext` accessor on `metadata_json["sender"]` per plan spec, combined with `isnot(None)` NULL guards on both `metadata_json` and the sender field.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — the module is complete and functional. Wiring into `rank_emails()` and `context_builder.py` is deferred to Plan 08-02.

## Threat Flags

None beyond what the plan's threat model already covers.

## Self-Check: PASSED

- `src/daily/profile/adaptive_ranker.py` — FOUND
- `tests/test_adaptive_ranker.py` — FOUND
- Commit `f6d6d68` — present in git log
- `pytest tests/test_adaptive_ranker.py` — 8 passed
- Pre-existing failure in `test_action_draft.py` confirmed pre-existing (unchanged before/after)
