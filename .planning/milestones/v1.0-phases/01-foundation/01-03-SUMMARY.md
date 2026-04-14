---
phase: 01-foundation
plan: 03
subsystem: integrations/google
tags: [oauth, google, gmail, calendar, encryption, adapters, tdd]
dependency_graph:
  requires:
    - 01-01  # vault crypto, DB models, config
    - 01-02  # EmailAdapter/CalendarAdapter base classes, Pydantic models
  provides:
    - Google OAuth flow (run_google_oauth_flow)
    - Encrypted token storage (store_google_tokens)
    - GmailAdapter (EmailAdapter implementation)
    - GoogleCalendarAdapter (CalendarAdapter implementation)
  affects:
    - 01-04  # Slack plan can replicate OAuth-to-vault-to-adapter pattern
    - 01-05  # Microsoft plan can replicate same pattern
tech_stack:
  added:
    - uvicorn==0.43.0  # OAuth callback server (was missing from pyproject.toml)
    - google-auth-oauthlib>=1.3.0  # OAuth 2.0 flow
    - google-api-python-client>=2.100.0  # Gmail + Calendar API
  patterns:
    - OAuth callback server: FastAPI on localhost:8080 + threading.Event for shutdown
    - Token encryption: encrypt_token(plaintext, vault_key) before every DB write
    - Async adapter wrapping sync SDK: asyncio.to_thread() for google-api-python-client
    - TDD RED/GREEN cycle for adapter + OAuth tests
key_files:
  created:
    - src/daily/integrations/google/__init__.py
    - src/daily/integrations/google/auth.py
    - src/daily/integrations/google/adapter.py
    - tests/test_google_oauth.py
    - tests/test_google_adapter.py
  modified:
    - src/daily/cli.py  # gmail() and calendar() commands wired to OAuth flow
    - pyproject.toml    # uvicorn added as dependency
    - uv.lock
decisions:
  - "calendar connect command prints redirect message rather than running a duplicate OAuth flow (Gmail + Calendar share one Google OAuth grant per D-03)"
  - "asyncio.to_thread() wraps all google-api-python-client calls since the SDK is synchronous"
  - "uvicorn server shutdown via threading.Event + server.should_exit=True (avoids SIGKILL)"
metrics:
  duration_minutes: 20
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 5
  files_modified: 3
---

# Phase 01 Plan 03: Google OAuth and Read Adapters Summary

**One-liner:** Google OAuth 2.0 with localhost FastAPI callback, AES-256-GCM encrypted token storage, and Gmail/Calendar read adapters returning typed Pydantic models via mocked API tests.

## What Was Built

### Task 1: Google OAuth flow with localhost callback and encrypted token storage

Implemented `run_google_oauth_flow` in `src/daily/integrations/google/auth.py`:

- Uses `google_auth_oauthlib.flow.Flow.from_client_config` with `access_type="offline"` and `prompt="consent"` to ensure refresh_token is always issued
- Spins up a temporary FastAPI app on `127.0.0.1:8080` with a `/callback` endpoint
- OAuth callback captures auth code, exchanges for tokens, sets `threading.Event` to trigger server shutdown
- Server shutdown via `server.should_exit = True` (clean, avoids SIGKILL)
- `GOOGLE_READONLY_SCOPES` contains exactly `gmail.readonly` and `calendar.readonly` (SEC-03)

Implemented `store_google_tokens`:

- Encrypts both `access_token` and `refresh_token` via `encrypt_token` before any DB write (T-1-11)
- Creates a single `IntegrationToken` row with `provider="google"` (shared grant covers Gmail + Calendar, D-03)
- Scopes stored as space-separated string

Updated `src/daily/cli.py`:

- `gmail()` command: loads Settings, validates vault_key, calls `run_google_oauth_flow` + `store_google_tokens`
- `calendar()` command: prints redirect message to use `daily connect gmail` (shared OAuth grant)

### Task 2: Gmail and Google Calendar read adapters (TDD)

Implemented `GmailAdapter(EmailAdapter)` and `GoogleCalendarAdapter(CalendarAdapter)` in `src/daily/integrations/google/adapter.py`:

- `GmailAdapter.list_emails`: fetches message IDs via `messages.list()`, then per-message metadata via `messages.get(format="metadata")` — raw bodies never fetched (T-1-09)
- Maps Gmail API fields to `EmailMetadata`: subject/sender/recipient from headers, timestamp from `internalDate`, `is_unread` from `UNREAD` in `labelIds`
- `GoogleCalendarAdapter.list_events`: fetches via `events.list(singleEvents=True, orderBy="startTime")`
- Maps Calendar API fields to `CalendarEvent`: detects all-day events via `start.date` vs `start.dateTime`
- Both adapters wrap sync google-api-python-client calls with `asyncio.to_thread()`

19 tests written and passing:
- 8 OAuth tests: scope enforcement, readonly-only, token encryption, vault_key passed correctly, provider=google row
- 11 adapter tests: isinstance checks, field mapping, pagination, all-day detection, no-body assertion

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] uvicorn missing from pyproject.toml**
- **Found during:** Task 1 verification
- **Issue:** `import uvicorn` in `auth.py` raised `ModuleNotFoundError` — uvicorn was not listed as a dependency
- **Fix:** `uv add uvicorn` — added uvicorn==0.43.0 to pyproject.toml
- **Files modified:** pyproject.toml, uv.lock
- **Commit:** d610a49

## Known Stubs

None — both adapters are fully wired to the Google API (with mocked calls in tests). The CLI gmail command is fully wired to the OAuth flow (requires real GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET in .env to run end-to-end).

## Threat Surface

All threats from the plan's threat model were mitigated:

| Threat | Mitigation | Status |
|--------|-----------|--------|
| T-1-08: OAuth state spoofing | Flow object validates state on callback internally | Mitigated |
| T-1-09: Email body disclosure | `format="metadata"` enforced; no body field in EmailMetadata | Mitigated |
| T-1-10: Scope elevation | Only `gmail.readonly` + `calendar.readonly` in GOOGLE_READONLY_SCOPES; tested | Mitigated |
| T-1-11: Token plaintext in DB | `encrypt_token` called on both access_token and refresh_token before write | Mitigated |

No new threat surface introduced beyond what was planned.

## Self-Check: PASSED

Files exist:
- FOUND: src/daily/integrations/google/__init__.py
- FOUND: src/daily/integrations/google/auth.py
- FOUND: src/daily/integrations/google/adapter.py
- FOUND: tests/test_google_oauth.py
- FOUND: tests/test_google_adapter.py

Commits exist:
- d610a49: feat(01-03): Google OAuth flow with localhost callback and encrypted token storage
- a45fcb9: test(01-03): add failing tests for Gmail and Calendar adapters
- 50335e1: feat(01-03): Gmail and Google Calendar read adapters with mocked API tests
