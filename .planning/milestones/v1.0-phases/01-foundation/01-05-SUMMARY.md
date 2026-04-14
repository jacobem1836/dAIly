---
phase: 01-foundation
plan: "05"
subsystem: integrations/microsoft, vault/refresh
tags: [microsoft-graph, oauth, msal, outlook, token-refresh, encryption]
dependency_graph:
  requires: ["01-01", "01-02", "01-03"]
  provides: ["microsoft-oauth", "outlook-adapter", "token-refresh"]
  affects: ["phase-02-briefing-pipeline"]
tech_stack:
  added: [msal, msgraph-sdk]
  patterns: ["MSAL auth code flow", "in-process FastAPI callback server", "async msgraph-sdk", "per-token error isolation"]
key_files:
  created:
    - src/daily/integrations/microsoft/__init__.py
    - src/daily/integrations/microsoft/auth.py
    - src/daily/integrations/microsoft/adapter.py
    - src/daily/vault/refresh.py
    - tests/test_microsoft_oauth.py
    - tests/test_microsoft_adapter.py
    - tests/test_token_refresh.py
  modified:
    - src/daily/cli.py
decisions:
  - "OutlookAdapter inherits both EmailAdapter and CalendarAdapter — single Graph OAuth grant covers mail and calendar"
  - "msgraph-sdk is natively async — no asyncio.to_thread() wrapping needed (unlike google-api-python-client)"
  - "_StaticTokenCredential wraps a pre-obtained access token as an azure-core TokenCredential for msgraph-sdk injection"
  - "Token refresh logic lives in vault/refresh.py (not integrations/) to co-locate with encryption and be callable by APScheduler in Phase 2"
  - "refresh_expiring_tokens uses SQLAlchemy select() query — works with the session passed in, no direct DB connection needed in tests"
metrics:
  duration_minutes: 40
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 7
  files_modified: 1
  tests_added: 30
  tests_total: 104
---

# Phase 1 Plan 5: Microsoft Graph OAuth, Outlook Adapters, and Token Refresh Summary

**One-liner:** MSAL auth code flow for Microsoft Graph with Outlook email/calendar adapters and cross-provider proactive token refresh using AES-256-GCM re-encryption.

## What Was Built

### Task 1: Microsoft Graph OAuth and Outlook Adapters

**src/daily/integrations/microsoft/auth.py**
- `run_microsoft_oauth_flow`: MSAL `PublicClientApplication` auth code flow with temporary FastAPI server on `127.0.0.1:8080` (same localhost callback pattern as Google OAuth in Plan 03)
- `store_microsoft_tokens`: Encrypts access_token and refresh_token via `encrypt_token` before DB write; calculates `token_expiry` from `expires_in`
- `MICROSOFT_READONLY_SCOPES`: `[Mail.Read, Calendars.Read, User.Read, offline_access]` — no write scopes (SEC-03/T-1-17)

**src/daily/integrations/microsoft/adapter.py**
- `OutlookAdapter(EmailAdapter, CalendarAdapter)`: Dual-inheritance adapter for mail + calendar via single Graph grant
- `list_emails`: Uses `$select` with `[id, conversationId, subject, from, toRecipients, receivedDateTime, isRead, categories]` — body/uniqueBody explicitly excluded (T-1-16)
- `list_events`: Uses `calendarView` endpoint for automatic recurring event expansion; maps to `CalendarEvent` typed Pydantic model
- `_StaticTokenCredential`: Minimal azure-core `TokenCredential` wrapping a pre-obtained access token for injection into `GraphServiceClient`

**src/daily/cli.py**
- `outlook()` command updated to call `run_microsoft_oauth_flow` and `store_microsoft_tokens`

### Task 2: Cross-Provider Token Refresh (TDD)

**src/daily/vault/refresh.py**
- `refresh_expiring_tokens(session_factory, vault_key, buffer_minutes=15)`: Queries tokens with `token_expiry IS NOT NULL AND token_expiry <= now + buffer_minutes`; dispatches to provider-specific helpers
- `_refresh_google_token`: Uses `google.oauth2.credentials.Credentials` with stored refresh token to call Google's token endpoint
- `_refresh_microsoft_token`: Uses `msal.PublicClientApplication.acquire_token_by_refresh_token` to call Microsoft's token endpoint
- Per-token exception handling (T-1-21): one failure is logged and reported but processing continues
- Returns `list[dict]` with `{provider, user_id, success, error}` for Phase 2 monitoring/logging

## Test Results

- Task 1: 21 tests — Microsoft OAuth scope validation, token storage encryption, adapter field mapping, pagination
- Task 2 (TDD): 9 tests — near-expiry detection, Slack skip, Google/Microsoft refresh, re-encryption, error isolation
- Full suite: 104/104 tests pass

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Implementation Notes (not deviations)

**1. msgraph-sdk natively async**
The plan noted "If not, wrap in asyncio.to_thread()". msgraph-sdk is fully async-native — no wrapping was needed. `OutlookAdapter.list_emails` and `list_events` are direct `async` calls.

**2. _StaticTokenCredential for msgraph-sdk injection**
The plan specified `OutlookAdapter` accepts `access_token: str`. The msgraph-sdk's `GraphServiceClient` requires an `azure.core.credentials.TokenCredential`. A minimal `_StaticTokenCredential` class was added to wrap the pre-obtained token — this keeps the adapter's public interface identical to the plan spec.

**3. Deprecation warnings from msgraph-sdk inner query parameter classes**
The nested `MessagesRequestBuilderGetQueryParameters` and `CalendarViewRequestBuilderGetQueryParameters` classes within msgraph-sdk emit deprecation warnings. These are internal library deprecations (library instructs users to use the generic `RequestConfiguration[QueryParameters]` pattern). The warnings are benign and do not affect functionality; the recommended alternative requires raw URL construction which reduces readability. Deferred to a future refactor when msgraph-sdk provides a cleaner public API.

## Known Stubs

None — all adapter methods are fully implemented.

## Threat Flags

No new security surface beyond the plan's threat model. All T-1-16 through T-1-21 mitigations implemented as specified.

## Self-Check

### Files Exist
- src/daily/integrations/microsoft/__init__.py: FOUND
- src/daily/integrations/microsoft/auth.py: FOUND
- src/daily/integrations/microsoft/adapter.py: FOUND
- src/daily/vault/refresh.py: FOUND
- tests/test_microsoft_oauth.py: FOUND
- tests/test_microsoft_adapter.py: FOUND
- tests/test_token_refresh.py: FOUND

### Commits Exist
- 271bcff: feat(01-05): implement Microsoft Graph OAuth flow and Outlook adapters
- 0e0be77: test(01-05): add failing tests for cross-provider token refresh logic
- 0e9fea3: feat(01-05): implement cross-provider token refresh logic

## Self-Check: PASSED
