---
phase: 19-native-ios-app
plan: "01"
subsystem: auth
tags: [auth, email, ios, magic-link, universal-links, resend]
dependency_graph:
  requires:
    - "18-02: pair code generation (generate_pairing_code, code_expiry)"
    - "18-01: LiveKit settings pattern (Settings extension)"
  provides:
    - "POST /auth/pair/send-link — email-based pair code delivery via Resend"
    - "GET /.well-known/apple-app-site-association — Universal Links AASA JSON"
    - "send_magic_link() — Resend HTTP API client with ResendError"
  affects:
    - "19-02: iOS Xcode project authenticates via send-link + pair/complete"
    - "src/daily/db/models.py — PairingCode.user_id now nullable, email field added"
tech_stack:
  added:
    - "httpx (already dep): used for Resend API calls"
    - "pydantic[email] / email-validator: EmailStr validation on send-link endpoint"
    - "Resend REST API: magic-link email delivery"
  patterns:
    - "TDD (RED → GREEN) for all three tasks"
    - "Security: 204 always returned on send-link, ResendError swallowed server-side"
    - "AASA served as direct JSONResponse with no redirects"
key_files:
  created:
    - "src/daily/email/__init__.py"
    - "src/daily/email/resend_client.py"
    - "tests/test_resend_client.py"
    - "tests/test_auth_send_link.py"
    - "tests/test_aasa.py"
  modified:
    - "src/daily/config.py — 5 new settings fields"
    - "src/daily/auth/router.py — pair_send_link endpoint + SendLinkRequest model"
    - "src/daily/db/models.py — PairingCode.user_id nullable, email field added"
    - "src/daily/main.py — AASA route"
    - ".env.example — 5 new env vars documented"
    - "pyproject.toml / uv.lock — email-validator added"
decisions:
  - "PairingCode.user_id made nullable: magic-link flow issues a code before knowing which user will redeem it; user resolved at pair/complete time"
  - "PairingCode.email field added: stores submitter email for traceability at redemption"
  - "email-validator installed: Pydantic EmailStr requires it for proper RFC 5322 validation"
  - "ResendError swallowed at endpoint boundary: 204 always returned to prevent email enumeration (T-19-01)"
metrics:
  duration_minutes: 30
  completed_date: "2026-04-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 5
  files_modified: 6
---

# Phase 19 Plan 01: Magic-Link Email Delivery + Apple App Site Association Summary

**One-liner:** Resend-powered magic-link email endpoint (always 204, no enumeration) and AASA JSON endpoint enabling Universal Links for iOS pairing.

## What Was Built

### Task 1: Resend email client + config
- `src/daily/email/resend_client.py`: async `send_magic_link(email, code, *, settings)` POSTing to `https://api.resend.com/emails` with Bearer auth; raises `ResendError` on non-200
- `src/daily/config.py`: five new Settings fields — `resend_api_key`, `resend_from_email`, `magic_link_base_url`, `apple_team_id`, `apple_bundle_id`
- `.env.example`: matching placeholder vars documented

### Task 2: POST /auth/pair/send-link
- New endpoint at `/auth/pair/send-link` accepting `{email: EmailStr}` body
- Generates a 6-digit pair code, inserts `PairingCode` row (user_id=None, email stored), calls Resend, returns 204 always
- Schema change: `PairingCode.user_id` made nullable; `PairingCode.email` column added
- `email-validator` added as dependency for `EmailStr` validation

### Task 3: GET /.well-known/apple-app-site-association
- New route on FastAPI app returning AASA JSON with `appID: "{apple_team_id}.{apple_bundle_id}"` and `paths: ["/pair", "/pair/*"]`
- Direct `JSONResponse` — no redirects (Apple CDN requirement)
- `include_in_schema=False` to suppress from OpenAPI docs

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] PairingCode.user_id made nullable + email field added**
- **Found during:** Task 2 implementation
- **Issue:** Plan specified `POST /auth/pair/send-link` accepts email with no user context, but `PairingCode.user_id` was non-nullable with no email column on either `User` or `PairingCode`. The endpoint cannot create a `PairingCode` row without a user record, and there is no mechanism to look up or create a `User` by email (User model has no email field).
- **Fix:** Made `PairingCode.user_id` nullable (the pair/complete endpoint already handles user resolution from the code); added `PairingCode.email` (nullable String(255)) so redemption can trace back to the original email submission.
- **Files modified:** `src/daily/db/models.py`
- **Commits:** 15593ef

**2. [Rule 3 - Blocking Issue] email-validator dependency missing**
- **Found during:** Task 2 test run
- **Issue:** Pydantic's `EmailStr` requires the `email-validator` package which was not in pyproject.toml
- **Fix:** `uv add "pydantic[email]"` — installs `email-validator==2.3.0` and `dnspython==2.8.0`
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commits:** 15593ef

**3. [Rule 3 - Blocking Issue] Corrupted venv (pygments/iniconfig missing)**
- **Found during:** Task 1 test run
- **Issue:** .venv had partial/corrupted packages after a prior forced reinstall
- **Fix:** Deleted `.venv` and ran `uv sync` — restored clean environment
- **Impact:** No code changes; environment-level fix only

## Commits

| Hash | Task | Description |
|------|------|-------------|
| d7e678f | Task 1 | Resend email client + config (5 files, 4 tests) |
| 15593ef | Task 2 | POST /auth/pair/send-link + nullable PairingCode (5 tests) |
| a14b0b5 | Task 3 | GET /.well-known/apple-app-site-association (3 tests) |

## Test Coverage

| Test file | Tests | Status |
|-----------|-------|--------|
| tests/test_resend_client.py | 4 | Passing |
| tests/test_auth_send_link.py | 5 | Passing |
| tests/test_aasa.py | 3 | Passing |
| tests/test_auth_pairing.py | 6 | Still passing (no regression) |
| tests/test_auth_jwt.py | 8 | Still passing (no regression) |
| tests/test_token_refresh.py | 9 | Still passing (no regression) |

## Known Stubs

None. All endpoints are fully wired:
- `send_magic_link` calls real Resend API (mocked in tests)
- AASA reads live `Settings()` — populated from env at runtime
- `PairingCode.email` is populated by the endpoint

## Threat Surface Scan

All surfaces are covered in the plan's threat model:
- `POST /auth/pair/send-link` → T-19-01 (email enumeration mitigated: always 204)
- Resend API key → T-19-03 (env-only, never logged/returned)
- AASA endpoint → T-19-04 (no user input, HTTPS-only, no redirects)

No new threat surfaces introduced beyond what the plan registered.

## Self-Check

Files exist:
- `src/daily/email/__init__.py` — FOUND
- `src/daily/email/resend_client.py` — FOUND
- `tests/test_resend_client.py` — FOUND
- `tests/test_auth_send_link.py` — FOUND
- `tests/test_aasa.py` — FOUND

Commits exist:
- d7e678f — FOUND
- 15593ef — FOUND
- a14b0b5 — FOUND

## Self-Check: PASSED
