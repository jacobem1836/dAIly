---
phase: quick
task_id: 260503-gdw
description: Update magic link email to also include OTP code as plain text
status: complete
completed_date: "2026-05-03"
duration_minutes: 5
tasks_completed: 2
files_modified: 2
commits:
  - hash: 79971fb
    message: "feat(260503-gdw): add plain-text OTP code fallback to magic link email"
  - hash: c381b03
    message: "test(260503-gdw): verify OTP code fallback appears in magic link email body"
key_decisions:
  - Added code as plain paragraph after expiry notice, matching plan's exact HTML structure
---

# Quick Task 260503-gdw: Update Magic Link Email to Include OTP Code

**One-liner:** Added `<p>Or enter code manually: {code}</p>` to magic link email HTML, with new test verifying the fallback renders correctly.

## What Was Done

### Task 1: Updated `send_magic_link()` in `resend_client.py`

Added a third paragraph to `html_body` that renders the plain-text OTP code:

```python
f'<p>Or enter code manually: {code}</p>'
```

This gives users who receive the email on a different device from their app (e.g., email on desktop, app on mobile) a manual entry path.

### Task 2: Added test in `test_resend_client.py`

Added `test_send_magic_link_body_contains_code_fallback` — a new async test that monkeypatches the HTTP client, calls `send_magic_link` with code `654321`, and asserts `"Or enter code manually: 654321"` appears in the HTML body.

## Verification

```
5 passed in 0.08s
- test_send_magic_link_posts_to_resend_with_auth       PASSED
- test_send_magic_link_body_contains_pair_url          PASSED
- test_send_magic_link_raises_on_non_200               PASSED
- test_settings_exposes_resend_and_apple_fields        PASSED
- test_send_magic_link_body_contains_code_fallback     PASSED
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints or auth paths introduced. OTP code was already present as a parameter; this change only adds it to the email body.

## Self-Check: PASSED

- [x] `src/daily/email/resend_client.py` exists and contains `Or enter code manually: {code}`
- [x] `tests/test_resend_client.py` exists and contains `test_send_magic_link_body_contains_code_fallback`
- [x] Commit `79971fb` exists
- [x] Commit `c381b03` exists
- [x] All 5 tests pass
