---
phase: 21
plan: "01"
subsystem: database
tags: [alembic, sqlalchemy, schema, timezone, briefing-config]
dependency_graph:
  requires: []
  provides: [briefing_config.timezone]
  affects: [orchestrator/session.py, scheduler]
tech_stack:
  added: []
  patterns: [SQLAlchemy Mapped[str] column with server_default]
key_files:
  created:
    - alembic/versions/007_briefing_config_timezone.py
  modified:
    - src/daily/db/models.py
decisions:
  - "Used down_revision='006' not '004' — alembic heads revealed 006 was actual DB head (005/006 pairing migrations existed on main)"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-01"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
---

# Phase 21 Plan 01: Add BriefingConfig Timezone Column Summary

**One-liner:** Added `timezone: Mapped[str]` column (String 64, server_default UTC) to `BriefingConfig` ORM model and applied Alembic migration `007_briefing_config_timezone` against the running Postgres instance.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add timezone column to BriefingConfig model | 11a8f3c | src/daily/db/models.py |
| 2 | Create Alembic migration 007 for timezone column | 78382e9 | alembic/versions/007_briefing_config_timezone.py |
| 3 | Apply Alembic migration (BLOCKING) | 4f2c54c | alembic/versions/005, 006 restored; 007 down_revision fixed |

## Verification Results

- `alembic current` → `007_briefing_config_timezone (head)` ✓
- `\d briefing_config` in psql → `timezone | character varying(64) | not null | 'UTC'::character varying` ✓
- `BriefingConfig.__table__.c.timezone` → `briefing_config.timezone` ✓
- `pytest tests/test_briefing_scheduler.py` → 2 passed, 1 pre-existing failure (unrelated to this plan)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect down_revision in migration 007**
- **Found during:** Task 3 (applying migration)
- **Issue:** Plan specified `down_revision = "56a7489e1608"` (plan context) and then said to use `alembic heads` result. Running `alembic heads` in the worktree returned `004` (pairing migrations 005/006 were deleted by the worktree reset). The DB was at `006`. Migration chain was branched.
- **Fix:** Restored migration files `005` and `006` from main repo; updated `down_revision` from `004` to `006` in migration 007.
- **Files modified:** alembic/versions/007_briefing_config_timezone.py, alembic/versions/005_add_pairing_codes_device_tokens.py (restored), alembic/versions/006_pairing_codes_add_email_nullable_user.py (restored)
- **Commit:** 4f2c54c

**2. [Rule 3 - Blocking] Restored deleted alembic migration files 005 and 006**
- **Found during:** Task 3 (alembic current showed '006' not found)
- **Issue:** The worktree soft-reset from an older commit base deleted 005 and 006 migration files that existed in main repo.
- **Fix:** Copied 005 and 006 from main repo to worktree alembic/versions/.
- **Files modified:** alembic/versions/005_add_pairing_codes_device_tokens.py, alembic/versions/006_pairing_codes_add_email_nullable_user.py

### Pre-existing Test Failure (Out of Scope)

`tests/test_briefing_scheduler.py::test_build_pipeline_kwargs_returns_required_keys` fails with `StopAsyncIteration` — confirmed pre-existing before our changes. Not introduced by this plan. Logged as deferred.

## Decisions Made

- Used `down_revision = "006"` (the actual DB-applied head) rather than the plan's suggested `56a7489e1608` value, which was outdated context.
- Timezone column placed between `schedule_minute` and `email_top_n` to keep schedule-related fields grouped.

## Known Stubs

None.

## Threat Flags

None — `timezone` column stores IANA timezone strings only (not PII), as documented in the plan's threat model.

## Self-Check: PASSED

- [x] `src/daily/db/models.py` exists with `timezone: Mapped[str]` at line 47
- [x] `alembic/versions/007_briefing_config_timezone.py` exists with `op.add_column`
- [x] Commits 11a8f3c, 78382e9, 4f2c54c all exist in git log
- [x] `alembic current` returns `007_briefing_config_timezone (head)`
- [x] `briefing_config` table has `timezone` column with `NOT NULL DEFAULT 'UTC'`
