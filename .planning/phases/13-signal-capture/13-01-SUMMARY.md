---
phase: 13-signal-capture
plan: "01"
subsystem: adaptive-ranker
tags: [tdd, signals, ranking, decay, sigmoid]
dependency_graph:
  requires:
    - src/daily/profile/signals.py (SignalLog, SignalType)
    - src/daily/briefing/context_builder.py (call site at line 181)
  provides:
    - src/daily/profile/adaptive_ranker.py (get_sender_multipliers)
  affects:
    - src/daily/briefing/context_builder.py (import now resolves)
    - src/daily/briefing/ranker.py (multipliers applied at line 173)
tech_stack:
  added: []
  patterns:
    - TDD (RED -> GREEN with mock async sessions)
    - Exponential time-decay scoring (0.95^days_old)
    - tanh-centered sigmoid with clamp to [0.5, 2.0]
    - AsyncSession mock pattern for unit tests without DB
key_files:
  created:
    - src/daily/profile/adaptive_ranker.py
    - tests/test_adaptive_ranker.py
  modified: []
decisions:
  - id: D-A
    summary: "Used tanh formula (1.0 + tanh(score/scale)) instead of plan's exp formula (0.5 + 1.5/(1+exp(-score/scale))) because the exp formula places neutral at 1.25 not 1.0, contradicting the behavior spec in tests"
requirements:
  - SIG-03
metrics:
  duration_minutes: 12
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
---

# Phase 13 Plan 01: Adaptive Ranker — Summary

**One-liner:** Decay-weighted per-sender multiplier module using tanh sigmoid clamped to [0.5, 2.0], wiring the pre-existing context_builder.py import at line 181.

## What Was Built

`src/daily/profile/adaptive_ranker.py` implements `get_sender_multipliers(user_id, db_session) -> dict[str, float]`. The function:

1. Queries `signal_log` for signals within 30 days for the given user
2. Applies exponential time-decay: `weight * (0.95 ** days_old)` per signal
3. Aggregates decay-weighted scores per normalised sender (lowercase, stripped)
4. Maps each score to a multiplier via `max(0.5, min(2.0, 1.0 + tanh(score / 3.0)))`
5. Returns only senders with at least one signal — callers default absent senders to 1.0

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write failing tests (RED) | 169a9b0 | tests/test_adaptive_ranker.py |
| 2 | Implement get_sender_multipliers (GREEN) | 7ecaf50 | src/daily/profile/adaptive_ranker.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Formula deviation: tanh instead of plan's exp-based sigmoid**
- **Found during:** Task 2 (GREEN phase — test_single_skip_signal_returns_below_one failed)
- **Issue:** The plan specified `0.5 + 1.5 / (1 + exp(-score / SIGMOID_SCALE))`. At score=0 this evaluates to 1.25 (not 1.0). A single skip signal (score=-1.0) gives 1.126 — above 1.0, contradicting the behavior spec "skip signal -> multiplier < 1.0".
- **Fix:** Used `1.0 + tanh(score / SIGMOID_SCALE)` clamped to [0.5, 2.0]. This correctly centers neutral at 1.0 (score=0), skip signals < 1.0, re_request signals > 1.0.
- **Files modified:** src/daily/profile/adaptive_ranker.py
- **Commit:** 7ecaf50

## Verification

- `python -m pytest tests/test_adaptive_ranker.py -q` — 12 passed
- `from daily.profile.adaptive_ranker import get_sender_multipliers` — resolves (PYTHONPATH=src)
- `grep -n "get_sender_multipliers" src/daily/briefing/context_builder.py` — confirms line 181 import now resolves to real module

## Known Stubs

None.

## Threat Flags

None. The `user_id` filter on all signal_log queries prevents cross-user data leakage (T-13-01 mitigated). Multiplier values are internal ranking weights only (T-13-02 accepted).

## Self-Check: PASSED

- [x] `src/daily/profile/adaptive_ranker.py` exists
- [x] `tests/test_adaptive_ranker.py` exists
- [x] Commit 169a9b0 exists (test RED phase)
- [x] Commit 7ecaf50 exists (implementation GREEN phase)
- [x] All 12 tests pass
