---
phase: 21
plan: "05"
subsystem: app-wiring
tags: [fastapi, apscheduler, aasa, universal-links, multi-user, scheduler]
dependency_graph:
  requires: [21-03, 21-04]
  provides: [multi-user-scheduler, aasa-oauth-success, router-mounts]
  affects: [src/daily/main.py, src/daily/briefing/scheduler.py]
tech_stack:
  added: []
  patterns:
    - Per-user APScheduler cron job registration from BriefingConfig rows
    - Idempotent job_id pattern briefing_user_{user_id}
    - DB error fallback to zero jobs (T-21-05-02 mitigation)
key_files:
  created: []
  modified:
    - src/daily/main.py
    - src/daily/briefing/scheduler.py
    - tests/test_aasa.py
    - tests/test_briefing_scheduler.py
    - tests/test_main_lifespan.py
    - tests/test_uat_integration.py
decisions:
  - "setup_scheduler_for_user added alongside old setup_scheduler for backward compatibility"
  - "Lifespan now iterates all BriefingConfig rows — no env-var fallback needed in the new path"
  - "UAT lifespan tests migrated to new multi-user contract rather than deleted"
metrics:
  duration: ~15min
  completed: "2026-05-02"
  tasks_completed: 3
  files_modified: 6
---

# Phase 21 Plan 05: App Wiring + Multi-User Scheduler Summary

**One-liner:** Mounted integrations and users routers, added /oauth/success to AASA paths, and refactored FastAPI lifespan to register one APScheduler cron job per BriefingConfig row.

## What Was Built

### Router Mounts (already present from Phase 21-03/04)

Both `integrations_router` and `users_router` were confirmed already imported and mounted in `main.py` — no changes needed.

### AASA Paths Update

`src/daily/main.py` — `apple_app_site_association` handler paths list updated from `["/pair", "/pair/*"]` to `["/pair", "/pair/*", "/oauth/success"]`. This allows iOS to intercept the post-OAuth redirect via ASWebAuthenticationSession Universal Link (D-03).

### Multi-User Scheduler Refactor

`src/daily/briefing/scheduler.py` — New function `setup_scheduler_for_user(hour, minute, user_id)` added:
- Uses per-user job_id `briefing_user_{user_id}`
- `replace_existing=True` (idempotent)
- Passes `user_id` via `kwargs` (not positional `args`)

`src/daily/main.py` lifespan refactored:
- Fetches all `BriefingConfig` rows via `select(BriefingConfig).all()`
- Registers one cron job per row via `setup_scheduler_for_user`
- DB failure logs error and starts scheduler with zero jobs (does not crash)
- Old env-var schedule parsing removed from lifespan

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 869834d | feat(21-05): add /oauth/success to AASA paths and unskip test |
| Task 2 | d65f5e6 | feat(21-05): refactor lifespan to register one cron job per BriefingConfig row |
| Task 3 | 8eb2022 | fix(21-05): migrate UAT lifespan tests to multi-user contract |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test_build_pipeline_kwargs mock missing load_profile patch**
- **Found during:** Task 2 test run
- **Issue:** `_build_pipeline_kwargs` calls `async_session` 3 times but test only mocked 2 side effects; also `required_keys` set was missing `preferences` key
- **Fix:** Added `patch("daily.briefing.scheduler.load_profile", new=AsyncMock(...))` to test; added `preferences` to required_keys set
- **Files modified:** `tests/test_briefing_scheduler.py`
- **Commit:** d65f5e6

**2. [Rule 1 - Bug] UAT integration tests patched old single-user lifespan contract**
- **Found during:** Task 3 full suite run
- **Issue:** `tests/test_uat_integration.py` TestSchedulePersistence and TestGracefulDBFallback classes patched `setup_scheduler` and asserted single-user behavior, which the refactored lifespan no longer exercises
- **Fix:** Migrated all 4 tests to new multi-user contract (setup_scheduler_for_user, scalars().all() mock pattern, updated log message assertions)
- **Files modified:** `tests/test_uat_integration.py`
- **Commit:** 8eb2022

## Test Results

Phase 21 test targets — all pass:

| Test File | Tests | Result |
|-----------|-------|--------|
| test_integrations_router.py | 8 | Pass |
| test_users_router.py | 5 | Pass |
| test_aasa.py | 4 (incl. new oauth_success) | Pass |
| test_briefing_scheduler.py | 5 (incl. 2 new per-user) | Pass |
| test_main_lifespan.py | 3 (rewritten multi-user) | Pass |
| **Total** | **25** | **25 passed** |

Full suite: 590 passed, 18 failed (all pre-existing failures unrelated to Phase 21).

## Known Stubs

None — all wiring is complete. Routers mounted, AASA updated, scheduler multi-user.

## Threat Surface Scan

No new threat surface beyond plan's threat model. AASA path is a string literal (T-21-05-01). DB error falls back gracefully (T-21-05-02). Per-user job_ids do not contain PII (T-21-05-04).

## Self-Check: PASSED

- `src/daily/main.py` contains `integrations_router`, `users_router`, `/oauth/success`, `select(BriefingConfig)`, `for row in rows`: CONFIRMED
- `src/daily/briefing/scheduler.py` contains `setup_scheduler_for_user`, `briefing_user_`: CONFIRMED
- Commit 869834d exists: CONFIRMED
- Commit d65f5e6 exists: CONFIRMED
- Commit 8eb2022 exists: CONFIRMED
- 25 Phase 21 tests pass: CONFIRMED
