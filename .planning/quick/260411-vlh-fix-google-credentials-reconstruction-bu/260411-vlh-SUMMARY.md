# Quick Task 260411-vlh: Fix Google credentials reconstruction — Summary

**Completed:** 2026-04-11

## Changes

### 1. `src/daily/cli.py` — `_resolve_email_adapters()` (line ~622-634)
- Built full `GoogleCredentials` with `refresh_token`, `token_uri`, `client_id`, `client_secret` from settings
- Previously only passed the access token, causing API calls to fail on token refresh

### 2. `src/daily/orchestrator/nodes.py` — `_build_executor_for_type()` email path (line ~600-610)
- Same fix: full credentials for GmailExecutor construction
- Decrypts `encrypted_refresh_token` from the integration token

### 3. `src/daily/orchestrator/nodes.py` — `_build_executor_for_type()` calendar path (line ~653-665)
- Same fix: full credentials for GoogleCalendarExecutor construction

### 4. `src/daily/orchestrator/nodes.py` — `_fetch_style_examples()` (line ~314)
- Removed unsupported `label_filter="SENT"` kwarg from `list_emails()` call
- `GmailAdapter.list_emails()` only accepts `since` and `page_token`

## Impact
- Email drafting should now resolve real addresses (not "null")
- Style example fetching should no longer throw TypeError
- Calendar actions should work with refreshable credentials
