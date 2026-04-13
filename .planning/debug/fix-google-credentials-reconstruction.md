# Fix: Google Credentials Reconstruction

## Problem
Two places build `google.oauth2.credentials.Credentials` with only the access token.
The Google API client needs full credentials (refresh_token, token_uri, client_id, client_secret) 
to refresh expired tokens and make API calls like listing emails.

This causes:
- `_fetch_style_examples` fails: can't list sent emails for style matching
- `_build_executor_for_type` fails: can't load known_addresses from email history
- Recipient resolves to "null" because LLM has no email context

## Root Cause
`Credentials(token=decrypted)` only sets the access token. Missing: refresh_token, token_uri, client_id, client_secret.

## Files to Fix

### 1. `src/daily/cli.py` — `_resolve_email_adapters()` (~line 620-634)

**Current (broken):**
```python
decrypted = decrypt_token(token.encrypted_access_token, vault_key)
if token.provider == "google":
    from google.oauth2.credentials import Credentials as GoogleCredentials
    creds = GoogleCredentials(token=decrypted)
    adapters.append(GmailAdapter(credentials=creds))
```

**Fix:** Decrypt both access_token and refresh_token, build full Credentials:
```python
decrypted = decrypt_token(token.encrypted_access_token, vault_key)
if token.provider == "google":
    from google.oauth2.credentials import Credentials as GoogleCredentials
    refresh_token = (
        decrypt_token(token.encrypted_refresh_token, vault_key)
        if token.encrypted_refresh_token else None
    )
    creds = GoogleCredentials(
        token=decrypted,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    adapters.append(GmailAdapter(credentials=creds))
```

Note: `settings` is already available — it's passed as a parameter to `_resolve_email_adapters`.

### 2. `src/daily/orchestrator/nodes.py` — `_build_executor_for_type()` (~line 555-600)

Same issue in the executor builder. Find where it creates GmailExecutor with the token.

**Current (broken):** Uses only `access_token = decrypt_token(token.encrypted_access_token, vault_key)` 
then passes raw token to executor.

**Fix:** Decrypt refresh_token too, build full Credentials, pass to GmailExecutor:
```python
access_token = decrypt_token(token.encrypted_access_token, vault_key)
refresh_token = (
    decrypt_token(token.encrypted_refresh_token, vault_key)
    if token.encrypted_refresh_token else None
)

# For Google provider, build full Credentials
from google.oauth2.credentials import Credentials as GoogleCredentials
creds = GoogleCredentials(
    token=access_token,
    refresh_token=refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
)
```

Then pass `creds` to GmailExecutor/GoogleCalendarExecutor instead of the raw token string.
Check what constructor args the executors expect and match accordingly.

### 3. Secondary issue: `_fetch_style_examples` in nodes.py

Grep for `label_filter` — the error `GmailAdapter.list_emails() got an unexpected keyword argument 'label_filter'` 
means `_fetch_style_examples` passes a kwarg the adapter doesn't support. 
Find the call and check `GmailAdapter.list_emails()` signature. Remove or rename the unsupported kwarg.

## Verification
After fix:
1. `PYTHONPATH=src uv run daily connect gmail` (re-auth with new scopes)
2. `PYTHONPATH=src uv run daily chat`
3. Verify "email adapter(s) connected" 
4. Type "draft a follow up email to brisbane north wreckers"
5. Should resolve the real email address (not "null")
6. Confirm → should send successfully
