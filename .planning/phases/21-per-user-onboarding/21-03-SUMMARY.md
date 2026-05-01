---
phase: 21
plan: "03"
subsystem: integrations
tags: [oauth, google, microsoft, slack, redis, crypto, fastapi]
dependency_graph:
  requires: [21-01, 21-02]
  provides: [integrations-oauth-router]
  affects: [src/daily/main.py, src/daily/config.py]
tech_stack:
  added: [respx]
  patterns: [oauth-state-csrf-redis, aes256gcm-token-vault, delete-then-insert-upsert]
key_files:
  created:
    - src/daily/integrations/router.py
  modified:
    - src/daily/main.py
    - src/daily/config.py
    - tests/test_integrations_router.py
    - pyproject.toml
    - uv.lock
decisions:
  - "Microsoft stored as provider='outlook' to match existing CLI convention (D-05)"
  - "CSRF state deleted on first read in _consume_oauth_state (single-use)"
  - "_vault_key() falls back to UTF-8 bytes for test fixtures (e.g. 'y' * 32)"
  - "respx used for async httpx mocking in Slack tests"
metrics:
  duration: "~3 minutes"
  completed: "2026-05-01"
  tasks_completed: 3
  files_modified: 6
---

# Phase 21 Plan 03: Integrations OAuth Router Summary

**One-liner:** Mobile-mediated OAuth router with 6 endpoints (Google, Microsoft/outlook, Slack) using Redis CSRF state, AES-256-GCM token encryption, and Universal Link callbacks.

## What Was Built

`src/daily/integrations/router.py` — FastAPI `APIRouter(prefix="/integrations")` with:

- `GET /integrations/google/connect` — authenticated, generates CSRF state in Redis, returns Google auth URL
- `GET /integrations/google/callback` — validates state, exchanges code via `Flow.fetch_token`, encrypts and upserts `IntegrationToken(provider="google")`, redirects to Universal Link
- `GET /integrations/microsoft/connect` — same pattern, uses `msal.ConfidentialClientApplication`
- `GET /integrations/microsoft/callback` — exchanges code, stores `provider="outlook"` (matches CLI convention)
- `GET /integrations/slack/connect` — builds Slack OAuth V2 authorize URL
- `GET /integrations/slack/callback` — exchanges code via `httpx.AsyncClient` POST to `oauth.v2.access`, stores `provider="slack"`

All connect endpoints require Bearer JWT. All callbacks validate CSRF state from Redis (single-use, 600s TTL). All tokens encrypted via `encrypt_token` (AES-256-GCM) before DB write.

## Tasks

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | Google connect + callback endpoints | c8525eb | Done |
| 2 | Microsoft (outlook) connect + callback endpoints | c8525eb | Done |
| 3 | Slack connect + callback endpoints (async httpx) | c8525eb | Done |
| Tests | All 8 integration router tests | 86f89bf | Done |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Field] Added microsoft_client_secret to Settings**
- **Found during:** Task 2
- **Issue:** `src/daily/config.py` did not have `microsoft_client_secret` — `msal.ConfidentialClientApplication` requires it for confidential client flow
- **Fix:** Added `microsoft_client_secret: str = ""` to `Settings`
- **Files modified:** `src/daily/config.py`
- **Commit:** c8525eb

**2. [Rule 3 - Missing Dependency] Added respx for async httpx mocking**
- **Found during:** Task 3 test implementation
- **Issue:** No async httpx mock library was installed; `respx` is the standard solution for `httpx.AsyncClient` mocking
- **Fix:** `uv add --dev respx`
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** c8525eb

**3. [Rule 1 - Bug] _vault_key() fallback for test fixtures**
- **Found during:** Task 1 test debugging
- **Issue:** Test vault key `"y" * 32` is 32 ASCII bytes but not valid base64; `base64.b64decode` would fail
- **Fix:** `_vault_key()` tries base64 decode first, falls back to UTF-8 encode — matches test fixture pattern used in `test_auth_pairing.py`
- **Files modified:** `src/daily/integrations/router.py`
- **Commit:** c8525eb

## Security Surface

All threats from the plan's threat model are mitigated as designed:

| Threat | Mitigation |
|--------|-----------|
| T-21-03-01 CSRF | `secrets.token_urlsafe(32)` state, Redis TTL=600s, deleted on first read |
| T-21-03-02 Unauth connect | `Depends(get_current_user)` on all connect endpoints → 401 |
| T-21-03-04 Token disclosure | `encrypt_token(AES-256-GCM)` before any DB write |
| T-21-03-06 Replay | State key deleted in `_consume_oauth_state` — single-use |
| T-21-03-07 Open redirect | Redirect target from `settings.magic_link_base_url` (env-controlled) |
| T-21-03-08 Provider key | Hard-coded `provider="outlook"` in Microsoft callback |

## Known Stubs

None. All 6 endpoints are fully wired. Tokens encrypted and persisted. Tests cover the full request cycle with mocked providers.

## Self-Check: PASSED

- `src/daily/integrations/router.py` exists (404 lines, > 200 min): FOUND
- Commit c8525eb exists: FOUND
- Commit 86f89bf exists: FOUND
- All 8 tests pass: CONFIRMED (8 passed in 0.65s)
- `grep "GOOGLE_ACTION_SCOPES" src/daily/integrations/router.py`: FOUND (reused, not redefined)
- `grep "encrypt_token" src/daily/integrations/router.py`: FOUND
- `grep "oauth_state:" src/daily/integrations/router.py`: FOUND
- `grep 'provider="outlook"' src/daily/integrations/router.py`: FOUND
- `grep "ConfidentialClientApplication" src/daily/integrations/router.py`: FOUND
- `grep "httpx.AsyncClient" src/daily/integrations/router.py`: FOUND
