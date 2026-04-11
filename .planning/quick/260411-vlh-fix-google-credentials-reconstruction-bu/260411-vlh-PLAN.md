# Quick Task 260411-vlh: Fix Google credentials reconstruction

**Created:** 2026-04-11
**Status:** Ready

## Goal

Build full `google.oauth2.credentials.Credentials` objects (with refresh_token, token_uri, client_id, client_secret) instead of access-token-only credentials. Also fix unsupported `label_filter` kwarg in `_fetch_style_examples`.

## Tasks

### Task 1: Fix `_resolve_email_adapters` in cli.py (~line 620-628)

**files:** `src/daily/cli.py`
**action:** Replace `GoogleCredentials(token=decrypted)` with full credentials construction that decrypts refresh_token and includes token_uri, client_id, client_secret from settings.
**verify:** No syntax errors; `settings` is already available as a parameter.
**done:** `_resolve_email_adapters` builds full Google credentials.

### Task 2: Fix `_build_executor_for_type` in nodes.py — email executor (~line 600-604)

**files:** `src/daily/orchestrator/nodes.py`
**action:** Replace `Credentials(token=access_token)` at line 603 with full credentials construction. Decrypt refresh_token from token.encrypted_refresh_token. Include token_uri, client_id, client_secret from settings.
**verify:** GmailExecutor receives credentials that can refresh tokens.
**done:** Email executor path builds full Google credentials.

### Task 3: Fix `_build_executor_for_type` in nodes.py — calendar executor (~line 655-658)

**files:** `src/daily/orchestrator/nodes.py`
**action:** Replace `Credentials(token=access_token)` at line 658 with full credentials construction, same pattern as Task 2.
**verify:** GoogleCalendarExecutor receives credentials that can refresh tokens.
**done:** Calendar executor path builds full Google credentials.

### Task 4: Fix `label_filter` kwarg in `_fetch_style_examples` (~line 314-316)

**files:** `src/daily/orchestrator/nodes.py`
**action:** Remove `label_filter="SENT"` from the `list_emails()` call at line 316. The `GmailAdapter.list_emails()` signature only accepts `since` and `page_token`. To filter sent emails, add `q` parameter support or filter in the Gmail query string within the adapter, OR simply remove the filter (fetch all recent emails for style).
**verify:** `_fetch_style_examples` calls `list_emails` with only supported kwargs.
**done:** No `TypeError` on `list_emails()` call.
