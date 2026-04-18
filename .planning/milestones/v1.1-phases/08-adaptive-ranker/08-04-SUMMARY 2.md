---
phase: "08"
plan: "04"
subsystem: briefing
tags: [adaptive-ranking, db-session, pipeline-wiring, scheduler, graceful-degradation, session-lifecycle]
dependency_graph:
  requires: [adaptive_ranker.get_sender_multipliers, build_context.db_session]
  provides: [run_briefing_pipeline.db_session, scheduler.session-per-run]
  affects: [briefing/pipeline.py, briefing/scheduler.py]
tech_stack:
  added: []
  patterns: [type-checking-import, async-with-session, none-default-backward-compat, session-scoped-to-run]
key_files:
  created: []
  modified:
    - src/daily/briefing/pipeline.py
    - src/daily/briefing/scheduler.py
    - tests/test_briefing_pipeline.py
    - tests/test_briefing_scheduler.py
decisions:
  - "db_session added at end of run_briefing_pipeline signature with None default — zero breaking changes to callers"
  - "Session opened in _scheduled_pipeline_run via async with, not in _build_pipeline_kwargs — lifetime visibly scoped at call site"
  - "get_or_generate_briefing not modified — on-demand path runs in pure-heuristic mode (backward compatible)"
  - "TYPE_CHECKING guard for AsyncSession import keeps runtime SQLAlchemy dependency out of pipeline module"
metrics:
  duration_minutes: 10
  completed_at: "2026-04-16T00:35:00Z"
  tasks_completed: 1
  files_changed: 4
---

# Phase 8 Plan 4: Wire db_session Through Pipeline and Scheduler Summary

## One-liner

Wired db_session from scheduler cron run through run_briefing_pipeline to build_context, activating adaptive ranking end-to-end for scheduled briefings while preserving backward compatibility.

## What Was Built

`src/daily/briefing/pipeline.py` — extended `run_briefing_pipeline()`:
- New optional parameter `db_session: "AsyncSession | None" = None` at end of signature
- Passes `db_session` through to `build_context()` call
- `AsyncSession` imported under `TYPE_CHECKING` guard — no runtime SQLAlchemy dependency
- Docstring updated to describe graceful-degradation contract: None → no adaptive ranking, briefing always delivers

`src/daily/briefing/scheduler.py` — extended `_scheduled_pipeline_run()`:
- Opens `async with async_session() as session:` scoped to the pipeline run
- Passes `db_session=session` to `run_briefing_pipeline()`
- Session lifetime is visibly bounded: opened after `_build_pipeline_kwargs` resolves, closed when pipeline returns (or raises)
- `async with` guarantees `__aexit__` on both success and exception paths (T-08-11)
- `_build_pipeline_kwargs` unchanged — session is NOT in the returned dict (separation of concerns)
- `get_or_generate_briefing` unchanged — on-demand path stays `db_session=None` (backward compatible)

`tests/test_briefing_pipeline.py` — 3 new tests:
- `test_run_briefing_pipeline_no_db_session` — db_session=None passed through to build_context as None
- `test_run_briefing_pipeline_passes_db_session` — mock session passed through unchanged
- `test_pipeline_end_to_end_with_adaptive_ranker` — full wiring integration: multipliers from get_sender_multipliers reach rank_emails via db_session

`tests/test_briefing_scheduler.py` — 2 new tests:
- `test_scheduled_pipeline_run_opens_session` — async_session() called and mock session passed as db_session
- `test_scheduled_pipeline_run_closes_session_on_error` — session __aexit__ and redis.aclose() both called when pipeline raises

## Decisions Made

1. **Session not in _build_pipeline_kwargs**: The plan spec is explicit — session lifetime must be visible at the call site in `_scheduled_pipeline_run`. Putting it in the returned dict would obscure when it's opened and closed, violating T-08-13 (session reuse risk).

2. **Backward-compatible None defaults throughout**: All three signature changes (pipeline, context_builder from 08-03, scheduler) use `None` as default. Existing callers — including `get_or_generate_briefing` and all existing tests — require zero changes.

3. **Integration test patches source module**: `get_sender_multipliers` is lazy-imported inside `build_context` (documented in 08-03 summary). The integration test patches `daily.profile.adaptive_ranker.get_sender_multipliers` (the source module) rather than the callsite, which is the correct approach for lazy imports.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None beyond what the plan's threat model already covers.

## Self-Check: PASSED

- `src/daily/briefing/pipeline.py` — FOUND, `db_session` parameter present, passed to build_context
- `src/daily/briefing/scheduler.py` — FOUND, `async with async_session() as session:` block present
- `tests/test_briefing_pipeline.py` — FOUND, 3 new tests present
- `tests/test_briefing_scheduler.py` — FOUND, 2 new tests present
- Commit `e004d10` — confirmed in git log
- New tests: 5 passed (546 total vs 541 before)
- Pre-existing failures: 4 (test_action_draft x3, test_briefing_scheduler::test_build_pipeline_kwargs_returns_required_keys) — unchanged from before this plan
