---
phase: "08"
plan: "03"
subsystem: briefing
tags: [adaptive-ranking, sender-multipliers, ranker, context-builder, graceful-degradation]
dependency_graph:
  requires: [adaptive_ranker.get_sender_multipliers]
  provides: [rank_emails.sender_multipliers, build_context.db_session]
  affects: [briefing/ranker.py, briefing/context_builder.py]
tech_stack:
  added: []
  patterns: [type-checking-import, lazy-import, graceful-degradation, tolerance-comparison]
key_files:
  created: []
  modified:
    - src/daily/briefing/ranker.py
    - src/daily/briefing/context_builder.py
    - tests/test_briefing_ranker.py
    - tests/test_briefing_context.py
decisions:
  - "TYPE_CHECKING guard used for AsyncSession import to avoid runtime SQLAlchemy dependency in briefing layer"
  - "Lazy import of get_sender_multipliers inside function body isolates the profile module — context_builder has no module-level profile dependency"
  - "Recency drift between two rank_emails calls requires tolerance-based score comparison in tests (< 0.1) not exact equality"
metrics:
  duration_minutes: 12
  completed_at: "2026-04-16T00:13:43Z"
  tasks_completed: 1
  files_changed: 4
---

# Phase 8 Plan 3: Wire Multipliers into Ranker and Context Builder Summary

## One-liner

Threaded adaptive sender multipliers from build_context through rank_emails with graceful degradation — adaptive failure falls back to pure heuristics without interrupting the briefing.

## What Was Built

`src/daily/briefing/ranker.py` — extended `rank_emails()`:
- New optional parameter `sender_multipliers: dict[str, float] | None = None`
- After computing heuristic score, looks up `email.sender.lower().strip()` in multipliers dict
- Unknown senders default to 1.0 (no-op); parameter defaults to None (backward compatible)
- `score_email()` unchanged — multiplier is applied in `rank_emails()` after scoring

`src/daily/briefing/context_builder.py` — extended `build_context()`:
- New optional parameter `db_session: "AsyncSession | None" = None`
- `AsyncSession` imported under `TYPE_CHECKING` guard — no runtime SQLAlchemy dependency
- When `db_session` is not None: lazy-imports and calls `get_sender_multipliers(user_id, db_session)`
- Failure wrapped in try/except with `logger.warning` — falls back to empty multipliers dict
- Passes `sender_multipliers` to `rank_emails()` call

`tests/test_briefing_ranker.py` — 5 new tests:
- `test_rank_emails_no_multipliers_unchanged` — None and {} produce same ordering
- `test_rank_emails_unknown_sender_defaults_to_one` — unknown sender score is unchanged
- `test_rank_emails_multiplier_scales_score` — 2.0 multiplier doubles heuristic score
- `test_rank_emails_multiplier_reorders` — higher multiplier promotes lower-scored sender
- `test_rank_emails_sender_normalisation` — "Alice@Example.com " matches key "alice@example.com"

`tests/test_briefing_context.py` — 3 new tests:
- `test_build_context_no_db_session` — db_session=None works without error
- `test_build_context_with_db_session_calls_adaptive_ranker` — patches source module, asserts called once with correct (user_id, session) args
- `test_build_context_adaptive_ranker_failure_falls_back` — raises from patch, asserts valid BriefingContext returned

## Decisions Made

1. **Lazy import strategy**: `from daily.profile.adaptive_ranker import get_sender_multipliers` is inside the function body, not at module level. This means patching must target the source module (`daily.profile.adaptive_ranker.get_sender_multipliers`) rather than the callsite module. Tests document this clearly.

2. **Score comparison tolerance**: `rank_emails()` recomputes `datetime.now()` internally on each call. Two sequential calls in tests produce slightly different recency scores (~0.001 drift). Tests use `abs(a - b) < 0.1` tolerance instead of exact equality for score comparisons across two calls.

3. **T-08-10 compliance**: Warning log uses `%s` on the exception only — `sender_multipliers` dict content is never logged. Sender strings are not in the warning path.

## Deviations from Plan

**1. [Rule 1 - Bug] Score comparison tests use tolerance, not equality**
- **Found during:** Writing `test_rank_emails_no_multipliers_unchanged` and `test_rank_emails_unknown_sender_defaults_to_one`
- **Issue:** `rank_emails()` calls `datetime.now()` internally — two separate calls in a test produce subtly different recency scores (~0.001 difference), causing exact equality assertions to fail
- **Fix:** Changed to `abs(a - b) < 0.1` tolerance comparisons. The 0.1 tolerance is >> the observed drift (~0.001) and << the multiplier effect being tested (2x scores differ by ~24 units)
- **Files modified:** `tests/test_briefing_ranker.py`
- **Commit:** d64ec3b

## Known Stubs

None.

## Threat Flags

None beyond what the plan's threat model already covers.

## Self-Check: PASSED

- `src/daily/briefing/ranker.py` — FOUND, `sender_multipliers` parameter present
- `src/daily/briefing/context_builder.py` — FOUND, `db_session` parameter present
- `tests/test_briefing_ranker.py` — FOUND, 5 new tests present
- `tests/test_briefing_context.py` — FOUND, 3 new tests present
- Commit `d64ec3b` — confirmed in git log
- `pytest tests/test_briefing_ranker.py tests/test_briefing_context.py` — 25 passed
- Full suite: 541 passed, 4 pre-existing failures in test_action_draft.py and test_briefing_scheduler.py (unchanged)
