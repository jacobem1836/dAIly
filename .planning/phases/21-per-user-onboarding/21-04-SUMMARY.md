---
phase: 21
plan: 04
subsystem: users-api
tags: [fastapi, users, preferences, integrations, zoneinfo, pydantic]
dependency_graph:
  requires: [21-01, 21-02]
  provides: [GET /users/me/integrations, PUT /users/me/preferences]
  affects: [main.py, iOS onboarding flow]
tech_stack:
  added: []
  patterns:
    - FastAPI APIRouter with async SQLAlchemy dependency injection
    - stdlib zoneinfo for UTC conversion (ZoneInfo, ZoneInfoNotFoundError)
    - Pydantic v2 field_validator for time string validation
    - SQLAlchemy select + scalar_one_or_none upsert pattern
key_files:
  created:
    - src/daily/users/__init__.py
    - src/daily/users/router.py
  modified:
    - src/daily/main.py
    - tests/test_users_router.py
    - pyproject.toml (dev deps: aiosqlite, pydantic[email])
decisions:
  - "outlook provider string maps to microsoft: true in API response"
  - "Local-to-UTC conversion uses stdlib zoneinfo only (no third-party library)"
  - "422 (not 500) returned for unknown IANA timezone strings via ZoneInfoNotFoundError"
  - "BriefingConfig upsert via select then insert/update pattern (no ON CONFLICT)"
  - "SQLite in-memory test DB handles ARRAY column incompatibility via event listener + raw DDL"
metrics:
  duration: ~20min
  completed: "2026-05-01"
  tasks_completed: 2
  files_changed: 5
requirements_satisfied:
  - USR-01
  - USR-02
  - USR-03
---

# Phase 21 Plan 04: users_router (integrations + preferences) Summary

**One-liner:** FastAPI users router with JWT-guarded integration status and timezone-aware preference upsert using stdlib zoneinfo.

## What Was Built

Two endpoints in `src/daily/users/router.py` serving the iOS onboarding UI:

### GET /users/me/integrations
- Returns `{google: bool, microsoft: bool, slack: bool}` for the authenticated user
- Queries `IntegrationToken` rows scoped to `current_user.id`
- Critical mapping: DB `provider="outlook"` → response `microsoft: true` (matches existing vault/token-refresh conventions)
- 401 if no valid Bearer JWT

### PUT /users/me/preferences
- Accepts `{briefing_time: "HH:MM", timezone: "<IANA>"}` body
- Validates `briefing_time` via Pydantic `field_validator` (range check, format)
- Converts local time + IANA timezone to UTC `(schedule_hour, schedule_minute)` using `zoneinfo.ZoneInfo`
- `ZoneInfoNotFoundError` → HTTP 422 (not 500)
- Upserts `BriefingConfig` row (select + insert/update pattern, no duplicate rows)
- Stores IANA string verbatim in `BriefingConfig.timezone` for display + DST correctness
- Returns 204 No Content on success; 401 without JWT; 422 for unknown timezone

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1+2 | 5458f3d | feat(21-04): implement GET /users/me/integrations endpoint (includes PUT endpoint) |

## Test Results

All 5 tests in `tests/test_users_router.py` pass:
- `test_integration_status` — USR-01: correct boolean map, outlook→microsoft mapping
- `test_integration_status_no_auth` — 401 without Bearer
- `test_update_preferences` — USR-02: upsert BriefingConfig with UTC conversion + DST-correct assertion
- `test_update_preferences_no_auth` — 401 without Bearer
- `test_invalid_timezone` — USR-03: 422 for `Not/A_Zone`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] SQLite ARRAY incompatibility in test DB**
- **Found during:** Task 1 test setup
- **Issue:** `BriefingConfig.slack_channels` uses PostgreSQL `ARRAY(String)` type; SQLite in-memory test DB cannot handle ARRAY type or Python list parameters
- **Fix:** Created `briefing_config` table via raw DDL (TEXT for slack_channels) and registered a SQLAlchemy event listener to serialize Python lists to JSON strings before SQLite execution
- **Files modified:** `tests/test_users_router.py`
- **Commit:** 5458f3d

**2. [Rule 3 - Blocking] Missing dev dependencies**
- **Found during:** Task 1 test run
- **Issue:** `aiosqlite` not installed (needed for SQLite async driver in tests); `email-validator` not installed (needed for Pydantic EmailStr used in auth router)
- **Fix:** `uv add aiosqlite --dev` and `uv add "pydantic[email]" --dev`
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** 5458f3d

## Known Stubs

None — both endpoints are fully wired to real DB queries.

## Threat Surface Scan

No new threat surface beyond what is documented in the plan's threat model. All endpoints are behind `Depends(get_current_user)` JWT validation. All queries are scoped to `current_user.id`. 422 error messages contain only the submitted timezone string, no PII or DB internals.

## Self-Check: PASSED

Files exist:
- src/daily/users/__init__.py: FOUND
- src/daily/users/router.py: FOUND

Commit exists:
- 5458f3d: FOUND
