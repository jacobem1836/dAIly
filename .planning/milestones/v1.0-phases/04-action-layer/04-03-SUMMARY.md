---
phase: 04-action-layer
plan: "03"
subsystem: action-layer
tags: [executors, gmail, slack, outlook, calendar, dispatch, scope-validation]
dependency_graph:
  requires: ["04-01"]
  provides: ["concrete-executors", "execute-node-dispatch"]
  affects: ["orchestrator/nodes.py", "actions/google", "actions/slack", "actions/microsoft"]
tech_stack:
  added: []
  patterns:
    - ActionExecutor ABC with validate() + execute() protocol
    - TDD red-green cycle for all executor implementations
    - asyncio.to_thread() wrapping for sync Google/Slack API clients
    - msgraph-sdk natively async (no to_thread needed for Outlook)
    - fire-and-forget asyncio.create_task() for audit logging
key_files:
  created:
    - src/daily/actions/google/__init__.py
    - src/daily/actions/google/email.py
    - src/daily/actions/google/calendar.py
    - src/daily/actions/slack/__init__.py
    - src/daily/actions/slack/executor.py
    - src/daily/actions/microsoft/__init__.py
    - src/daily/actions/microsoft/executor.py
    - tests/test_action_executors.py
  modified:
    - src/daily/orchestrator/nodes.py
    - tests/test_action_approval.py
decisions:
  - "GmailExecutor uses asyncio.to_thread() to wrap sync google-api-python-client calls"
  - "OutlookExecutor uses msgraph-sdk natively async (no to_thread)"
  - "SlackExecutor casts thread_ts to str() before passing to chat_postMessage (Pitfall 2)"
  - "GoogleCalendarExecutor uses patch() never update() for reschedules (Pitfall 5)"
  - "execute_node prefers microsoft token when both google+microsoft tokens exist for user"
  - "_build_executor_for_type decrypts token in-memory only at call time (T-04-13)"
metrics:
  duration_minutes: 45
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_created: 8
  files_modified: 2
---

# Phase 4 Plan 3: Concrete ActionExecutors and execute_node Dispatch Summary

**One-liner:** Four concrete ActionExecutors (Gmail, Slack, Calendar, Outlook) wired to execute_node with OAuth scope validation, contact whitelist checks, and provider-based routing.

## What Was Built

### Task 1: GmailExecutor, SlackExecutor, OutlookExecutor

**GmailExecutor** (`src/daily/actions/google/email.py`)
- Builds RFC 2822-compliant MIME message with `In-Reply-To` and `References` headers for native Gmail threading
- base64url-encodes MIME via `base64.urlsafe_b64encode(msg.as_bytes())`
- Calls `users().messages().send(userId="me", body={"raw": encoded, "threadId": ...})` via `asyncio.to_thread`
- `validate()` checks `gmail.send` scope (D-11) then `check_recipient_whitelist` (ACT-06)

**SlackExecutor** (`src/daily/actions/slack/executor.py`)
- Calls `chat_postMessage` with `thread_ts=str(draft.thread_id)` — string cast is mandatory (Pitfall 2: float precision loss causes silent thread mismatch)
- `validate()` checks `chat:write` scope (D-11) then channel membership in known_channels

**OutlookExecutor** (`src/daily/actions/microsoft/executor.py`)
- Sends via `graph_client.me.send_mail.post(SendMailPostRequestBody(...))` — natively async
- Builds structured msgraph-sdk models (Message, ItemBody, Recipient, EmailAddress)
- `validate()` checks `Mail.Send` scope (D-11) then `check_recipient_whitelist` (ACT-06)

### Task 2: GoogleCalendarExecutor and execute_node Dispatch

**GoogleCalendarExecutor** (`src/daily/actions/google/calendar.py`)
- `schedule_event`: calls `events().insert(calendarId="primary", body=...)` — returns event ID
- `reschedule_event`: calls `events().patch(calendarId="primary", eventId=..., body=...)` — NEVER `events().update()` (Pitfall 5: update() overwrites all attendees; patch() merges)
- `validate()` checks `calendar.events` scope (D-11) and validates each attendee via `check_recipient_whitelist`

**execute_node dispatch** (`src/daily/orchestrator/nodes.py`)
- Added `_build_executor_for_type(action_type, user_id)` async factory:
  - `draft_email` / `compose_email`: queries `integration_tokens` ordered by `updated_at desc`; prefers `microsoft` token → `OutlookExecutor`, else `google` → `GmailExecutor`
  - `draft_message` → `SlackExecutor`
  - `schedule_event` / `reschedule_event` → `GoogleCalendarExecutor`
  - Decrypts token in-memory only at call time (T-04-13)
- Updated `execute_node` to: build executor → `await executor.validate()` → `await executor.execute()` → `asyncio.create_task(_log_action(...))` fire-and-forget
- `ValueError` from `validate()` returns "Cannot execute: {message}" without calling `execute()`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_action_approval.py broke when stub execute_node was replaced**
- **Found during:** Task 2 — full suite run
- **Issue:** `test_confirm_resumes_to_execute` expected the old stub message "Done. Action executed successfully." but the real execute_node tried to query the DB for tokens and failed with "Cannot execute: No email integration connected."
- **Fix:** Added `patch("daily.orchestrator.nodes._build_executor_for_type", ...)` in the test to mock the executor factory, returning a mock executor that succeeds. Updated assertion to also accept "sent" (from `ActionResult.summary`).
- **Files modified:** `tests/test_action_approval.py`
- **Commit:** 30d1ae3

**2. [Rule 3 - Blocking] Corrupted venv packages required reinstallation**
- **Found during:** Task 1 — running initial test suite
- **Issue:** Several packages (pytest, langchain-core, redis, pydantic, sqlalchemy, fastapi, google-auth, msgraph-sdk) were partially initialized or had broken imports due to version conflicts
- **Fix:** `uv pip install --reinstall` for each affected package
- **Impact:** No code changes needed; environment only

## Known Stubs

None — all executor implementations are wired to real API clients. The `known_channels` set for `SlackExecutor` in `_build_executor_for_type` is initialized as an empty set (all Slack channels pass whitelist in M1). This is intentional for M1 scope; contact list wiring for Slack is deferred to M2.

## Threat Flags

No new network endpoints, auth paths, or schema changes were introduced. All files operate within the trust boundary defined in the plan's threat model:

| Mitigated | File | Description |
|-----------|------|-------------|
| T-04-11 | google/email.py, microsoft/executor.py | check_recipient_whitelist in validate() before any API call |
| T-04-12 | slack/executor.py | channel validated + thread_ts cast to str |
| T-04-13 | orchestrator/nodes.py | token decrypted in-memory only at _build_executor_for_type call time |
| T-04-15 | google/calendar.py | events().patch() only — events().update() never called |
| T-04-17 | all executors | REQUIRED_SCOPES validated in validate() before execute() |

## Self-Check: PASSED

- FOUND: src/daily/actions/google/email.py
- FOUND: src/daily/actions/google/calendar.py
- FOUND: src/daily/actions/slack/executor.py
- FOUND: src/daily/actions/microsoft/executor.py
- FOUND: tests/test_action_executors.py
- FOUND commit: 6baf876 (GmailExecutor, SlackExecutor, OutlookExecutor)
- FOUND commit: 30d1ae3 (GoogleCalendarExecutor, execute_node dispatch)
- 43 tests pass in tests/test_action_executors.py
- 0 regressions introduced (pre-existing failures unchanged)
