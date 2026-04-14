---
phase: 01-foundation
plan: 04
subsystem: integrations/slack
tags: [slack, oauth, adapter, messaging, encryption]
dependency_graph:
  requires:
    - 01-01 (vault crypto — encrypt_token, IntegrationToken model, DB engine)
    - 01-02 (adapter interface — MessageAdapter, MessagePage, MessageMetadata)
  provides:
    - Slack OAuth V2 flow with localhost callback
    - Encrypted bot token storage (provider="slack")
    - SlackAdapter implementing MessageAdapter interface
  affects:
    - 01-05 (Microsoft adapter — same pattern to follow)
    - Phase 2 briefing pipeline (consumes SlackAdapter.list_messages)
tech_stack:
  added:
    - slack-sdk WebClient (conversations_history, sync wrapped in asyncio.to_thread)
    - httpx (POST to oauth.v2.access in callback server)
  patterns:
    - Localhost FastAPI callback server (same as google/auth.py)
    - Async wrapper for sync SDK via asyncio.to_thread
    - DM detection via channel ID prefix ("D" = DM)
    - Empty cursor string normalized to None
key_files:
  created:
    - src/daily/integrations/slack/__init__.py
    - src/daily/integrations/slack/auth.py
    - src/daily/integrations/slack/adapter.py
    - tests/test_slack_oauth.py
    - tests/test_slack_adapter.py
  modified:
    - src/daily/cli.py (slack() command wired to run_slack_oauth_flow + store_slack_token)
decisions:
  - "Slack bot tokens do not expire — store token_expiry=None and encrypted_refresh_token=None"
  - "DM detection uses channel ID prefix ('D') rather than conversations_info API call to avoid extra API round-trip"
  - "is_mention detected from '<@' pattern in text — text itself is never stored (T-1-12)"
  - "asyncio.to_thread wraps synchronous WebClient calls to maintain async interface"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 5
  files_modified: 1
---

# Phase 1 Plan 4: Slack Integration Summary

**One-liner:** Slack OAuth V2 with localhost callback, encrypted bot token storage, and SlackAdapter returning typed MessagePage via sync SDK wrapped in asyncio.to_thread.

## What Was Built

### Task 1: Slack OAuth flow
- `src/daily/integrations/slack/auth.py` — `run_slack_oauth_flow` opens browser, spins temporary FastAPI server on `127.0.0.1:8080`, captures `code` param, POSTs to `https://slack.com/api/oauth.v2.access`, extracts `access_token`
- `store_slack_token` encrypts bot token via `encrypt_token` before DB write, stores `provider="slack"`, `token_expiry=None`, `encrypted_refresh_token=None` (Slack bot tokens do not expire)
- `src/daily/cli.py` `slack()` command fully wired: checks env vars, decodes vault key, calls flow and storage functions

### Task 2: Slack adapter with TDD
- `src/daily/integrations/slack/adapter.py` — `SlackAdapter(MessageAdapter)` with `list_messages(channels, since) -> MessagePage`
- Uses `slack_sdk.WebClient.conversations_history`, wrapped in `asyncio.to_thread` (SDK is synchronous)
- Maps: `ts` → `message_id`, `user` → `sender_id`, channel prefix "D" → `is_dm`, `<@` in text → `is_mention`
- Empty `next_cursor` string normalized to `None`
- 24 tests: 13 OAuth tests, 11 adapter tests — all pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AsyncMock session.add coroutine warning in OAuth tests**
- **Found during:** Task 2 GREEN phase — RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
- **Issue:** Tests using `AsyncMock()` for the session object inherited async behavior on `add()`, creating an unawaited coroutine when `session.add(token_row)` was called
- **Fix:** Added `mock_session.add = MagicMock()` in the two tests that didn't already override it (`test_store_slack_token_encrypts_bot_token`, `test_store_slack_token_uses_vault_key`)
- **Files modified:** `tests/test_slack_oauth.py`
- **Commit:** 711fd6a

**2. [Rule 3 - Blocking] Files created in main project instead of worktree**
- **Found during:** Task 1 commit — git rejected files outside repository
- **Issue:** Initial file writes used the main project path (`/Users/jacobmarriott/Documents/Personal/dAIly/src/...`) instead of the worktree path
- **Fix:** Recreated all files at correct worktree path; cleaned up accidental main-project writes (those files remain in main project but are not committed to this branch)
- **Files affected:** All Task 1 files

## Known Stubs

None. All integration points are wired:
- `daily connect slack` CLI command is fully implemented
- `SlackAdapter.list_messages` returns real `MessagePage` from Slack API
- Token storage writes to DB via session factory

## Threat Flags

No new threat surface beyond what was declared in the plan's threat model. All T-1-12, T-1-13, T-1-14 mitigations implemented as specified.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/daily/integrations/slack/__init__.py | FOUND |
| src/daily/integrations/slack/auth.py | FOUND |
| src/daily/integrations/slack/adapter.py | FOUND |
| tests/test_slack_oauth.py | FOUND |
| tests/test_slack_adapter.py | FOUND |
| Commit 50dad41 (Task 1) | FOUND |
| Commit 51abe6b (RED tests) | FOUND |
| Commit 711fd6a (GREEN adapter) | FOUND |
| 24 tests passing | PASSED |
