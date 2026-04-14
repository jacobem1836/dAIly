---
phase: 03-orchestrator
plan: 01
subsystem: database
tags: [langgraph, psycopg, pydantic, sqlalchemy, user-profile, jsonb]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Base ORM class, async_session, Settings, db engine infrastructure
  - phase: 02-briefing-pipeline
    provides: BriefingConfig ORM, existing db/models.py patterns
provides:
  - UserProfile ORM model with JSONB preferences column
  - UserPreferences Pydantic model with Literal validation
  - load_profile() service function
  - upsert_preference() service function
  - LangGraph ecosystem dependencies (langgraph, langgraph-checkpoint-postgres, psycopg, psycopg-pool, langchain-openai)
  - Settings.database_url_psycopg field for AsyncPostgresSaver
affects: [03-02, 03-03, orchestrator, profile]

# Tech tracking
tech-stack:
  added:
    - langgraph==1.1.6
    - langgraph-checkpoint-postgres==3.0.5
    - langgraph-checkpoint==4.0.1
    - langchain-core==1.2.26
    - langchain-openai==1.1.12
    - psycopg==3.3.3 (psycopg[binary])
    - psycopg-pool==3.3.0
  patterns:
    - JSONB preferences pattern: schema evolution without migrations, validated at Pydantic layer on read
    - UserPreferences as typed view of JSONB blob (not ORM model)
    - Service functions accept explicit session parameter (no module-level session dependency)

key-files:
  created:
    - src/daily/profile/__init__.py
    - src/daily/profile/models.py
    - src/daily/profile/service.py
    - tests/test_profile_service.py
  modified:
    - pyproject.toml (new dependencies)
    - uv.lock (resolved dependency tree)
    - src/daily/config.py (database_url_psycopg field)

key-decisions:
  - "JSONB for preferences allows schema evolution without migrations — UserPreferences validates on read, not enforced at DB level"
  - "langchain-openai resolved without conflict with openai>=2.0.0 pin — included rather than deferred"
  - "Service functions take explicit AsyncSession parameter rather than using module-level async_session"

patterns-established:
  - "JSONB preferences: store as dict, validate with Pydantic model_validate() on read"
  - "Profile service: pass session explicitly, no module-level imports of async_session"

requirements-completed: [PERS-01]

# Metrics
duration: 20min
completed: 2026-04-07
---

# Phase 03 Plan 01: Dependencies and Profile Data Layer Summary

**LangGraph ecosystem installed and UserProfile JSONB data layer created with Pydantic-validated preferences and async CRUD service**

## Performance

- **Duration:** 20 min
- **Started:** 2026-04-07T13:00:00Z
- **Completed:** 2026-04-07T13:20:42Z
- **Tasks:** 2 (Task 1: deps + Settings; Task 2: profile package TDD)
- **Files modified:** 7

## Accomplishments
- LangGraph 1.1.6, langgraph-checkpoint-postgres 3.0.5, psycopg 3.3.3, psycopg-pool 3.3.0, and langchain-openai 1.1.12 installed and importable
- `Settings.database_url_psycopg` field added — provides plain `postgresql://` connection string for `AsyncPostgresSaver.from_conn_string()`
- `UserProfile` ORM model with JSONB preferences column for schema-evolution-friendly user settings
- `UserPreferences` Pydantic model enforcing Literal validation on tone (3 values) and briefing_length (3 values) at read time
- `load_profile()` and `upsert_preference()` service functions fully tested (14 tests, all passing)

## Task Commits

1. **Task 1: Install dependencies and extend Settings** - `ad0aa73` (feat)
2. **Task 2 RED: Failing tests for profile service** - `7cdfd73` (test)
3. **Task 2 GREEN: Profile package implementation** - `59f6c1b` (feat)

## Files Created/Modified
- `src/daily/profile/__init__.py` - Package init (empty)
- `src/daily/profile/models.py` - UserProfile ORM and UserPreferences Pydantic model
- `src/daily/profile/service.py` - load_profile() and upsert_preference() async service functions
- `tests/test_profile_service.py` - 14 tests covering defaults, validation, CRUD, CSV parsing
- `src/daily/config.py` - Added database_url_psycopg field
- `pyproject.toml` - Added LangGraph ecosystem dependencies
- `uv.lock` - Updated lock file

## Decisions Made
- Used JSONB for preferences rather than discrete columns — allows adding new preference fields without migrations (D-04 pattern)
- langchain-openai included (no conflict with openai>=2.0.0 pin) — avoids fallback noted in plan
- Service functions accept explicit `session: AsyncSession` parameter — avoids module-level session coupling, consistent with testability pattern

## Deviations from Plan

None - plan executed exactly as written. langchain-openai resolved without conflict so the fallback (use AsyncOpenAI directly) was not needed.

## Issues Encountered
- `uv run pytest` failed due to corrupted pytest installation (missing RECORD files from prior venv state). Fixed by running `uv pip install --force-reinstall pytest pytest-asyncio fakeredis`. All 14 profile tests passed after fix.
- `.pth` file for the `daily` package was not being processed by Python's site module. Tests run successfully with `PYTHONPATH=/path/to/src` (used by `uv run` when invoked directly).

## User Setup Required
None - no external service configuration required for this plan.

## Next Phase Readiness
- Plan 02 (orchestrator graph) can consume `UserPreferences` from `daily.profile.models` and service functions from `daily.profile.service`
- Plan 03 (CLI) can wire `upsert_preference()` to user-facing commands
- `AsyncPostgresSaver` is importable — graph checkpointing infrastructure is ready to use
- All LangGraph ecosystem packages available: `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver` works

---
*Phase: 03-orchestrator*
*Completed: 2026-04-07*

## Self-Check: PASSED

- FOUND: src/daily/profile/__init__.py
- FOUND: src/daily/profile/models.py
- FOUND: src/daily/profile/service.py
- FOUND: tests/test_profile_service.py
- FOUND: .planning/phases/03-orchestrator/03-01-SUMMARY.md
- FOUND commit ad0aa73 (Task 1: deps + Settings)
- FOUND commit 7cdfd73 (Task 2 RED: failing tests)
- FOUND commit 59f6c1b (Task 2 GREEN: profile implementation)
