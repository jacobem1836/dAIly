---
phase: 21
plan: 02
subsystem: tests
tags: [testing, wave-0, scaffold, tdd]
dependency_graph:
  requires: []
  provides:
    - tests/test_integrations_router.py (INT-01..08 stubs)
    - tests/test_users_router.py (USR-01..03 stubs)
    - tests/test_aasa.py (test_aasa_includes_oauth_success_path stub)
    - tests/conftest.py (mock_redis, auth_headers fixtures)
  affects:
    - Plan 03 (integrations router — unskip INT-01..08)
    - Plan 04 (users router — unskip USR-01..03)
    - Plan 05 (AASA update — unskip test_aasa_includes_oauth_success_path)
tech_stack:
  added: [fakeredis.aioredis]
  patterns:
    - Import-inside-test-body for not-yet-implemented modules (collection-safe)
    - pytest.mark.skip with forward-reference to plan number
key_files:
  created:
    - tests/test_integrations_router.py
    - tests/test_users_router.py
  modified:
    - tests/test_aasa.py
    - tests/conftest.py
decisions:
  - Import-inside-test-body pattern chosen over module-level import to allow pytest collection before Plan 03/04 land
  - auth_headers fixture uses Settings constructor with literal jwt_secret rather than monkeypatch to avoid async fixture dependency
  - mock_redis uses aclose() (not close()) for async cleanup compatibility with fakeredis.aioredis
metrics:
  duration_minutes: 30
  tasks_completed: 4
  tasks_total: 4
  files_created: 2
  files_modified: 2
  completed_date: "2026-05-02"
---

# Phase 21 Plan 02: Wave 0 Test Scaffold Summary

**One-liner:** 11 skip-marked pytest stubs (8 integration router + 3 user router + 1 AASA) plus `mock_redis` and `auth_headers` fixtures wired into conftest.py, enabling downstream Plans 03-05 to unskip tests as implementations land.

## What Was Built

### tests/test_integrations_router.py (Task 1)

8 stub tests covering the full integration OAuth flow:

| Test | Coverage |
|------|---------|
| `test_google_connect` | INT-01: GET /integrations/google/connect returns 200 + auth_url |
| `test_google_callback` | INT-02: callback stores encrypted token, redirects to /oauth/success |
| `test_microsoft_connect` | INT-03: GET /integrations/microsoft/connect returns 200 + auth_url |
| `test_microsoft_callback` | INT-04: callback stores provider="outlook" (not "microsoft") |
| `test_slack_connect` | INT-05: GET /integrations/slack/connect returns 200 + auth_url |
| `test_slack_callback` | INT-06: callback POSTs to oauth.v2.access, stores provider="slack" |
| `test_invalid_state` | INT-07: state not in Redis → HTTP 400 |
| `test_connect_requires_auth` | Unauthenticated request → HTTP 401 |

All tests: `@pytest.mark.skip(reason="MISSING — implemented in Plan 03")`.

### tests/test_users_router.py (Task 2)

3 stub tests for the user preferences / status endpoints:

| Test | Coverage |
|------|---------|
| `test_integration_status` | USR-01: GET /users/me/integrations → {google, microsoft, slack} booleans |
| `test_update_preferences` | USR-02: PUT /users/me/preferences → upserts BriefingConfig with UTC schedule |
| `test_invalid_timezone` | USR-03: timezone="Not/A_Zone" → HTTP 422 |

All tests: `@pytest.mark.skip(reason="MISSING — implemented in Plan 04")`.

### tests/test_aasa.py (Task 3)

Added `test_aasa_includes_oauth_success_path` — asserts `/oauth/success` appears in AASA paths list. Marked skip referencing Plan 05. Existing 3 tests unchanged.

### tests/conftest.py (Task 4)

Two new fixtures appended at the end of conftest.py:

- **`mock_redis`** — async fixture using `fakeredis.aioredis.FakeRedis`, fully compatible with `redis.asyncio` interface. Used by Plan 03 tests for OAuth state CSRF validation.
- **`auth_headers`** — synchronous fixture returning `{"Authorization": "Bearer <token>"}` with JWT for user_id=100. Uses `Settings(jwt_secret="x"*32)` directly to avoid monkeypatch dependency.

## Verification Results

```
pytest tests/test_integrations_router.py -q  → 8 skipped, 0 failed, 0 errors
pytest tests/test_users_router.py -q          → 3 skipped, 0 failed, 0 errors
pytest tests/test_aasa.py --collect-only -q   → 4 collected (3 existing + 1 new)
pytest tests/ --collect-only -q               → 604 tests collected, 0 errors
```

## Deviations from Plan

### Pre-existing environment issue (out of scope)

`tests/test_aasa.py`'s 3 existing tests error at fixture setup (`email-validator` not in pyproject.toml dev dependencies). These failures pre-date Plan 02 and existed at commit 922af2c before any changes were made. The task's acceptance criterion "existing tests still pass" cannot be satisfied in this environment because the tests were already failing. The new test (`test_aasa_includes_oauth_success_path`) collects and skips correctly — no new failures were introduced. Deferred fix: add `"pydantic[email]"` or `"email-validator"` to `[project.optional-dependencies] dev` in pyproject.toml.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 2975dde | test(21-02): add Wave 0 stub tests for integrations router (INT-01..08) |
| 2 | b8744dd | test(21-02): add Wave 0 stub tests for users router (USR-01..03) |
| 3 | 24c3fea | test(21-02): add test_aasa_includes_oauth_success_path stub to test_aasa.py |
| 4 | f621e09 | test(21-02): add mock_redis and auth_headers fixtures to conftest.py |

## Self-Check: PASSED

- [x] `tests/test_integrations_router.py` exists
- [x] `tests/test_users_router.py` exists
- [x] `tests/test_aasa.py` contains `test_aasa_includes_oauth_success_path`
- [x] `tests/conftest.py` contains both `mock_redis` and `auth_headers`
- [x] All 4 commits exist in git log
- [x] `pytest tests/ --collect-only -q` exits 0 with 604 tests
