---
status: fixing
trigger: "iOS app shows 'Invalid or expired code. Try again.' when user enters 6-digit OTP from magic link email"
created: 2026-04-30T00:00:00Z
updated: 2026-04-30T13:50:00Z
---

## Current Focus

hypothesis: CONFIRMED — PAIRING_CODE_TTL_SECONDS is only 300 (5 min), too short for email delivery + user action
test: Queried Postgres directly: code 675877 created at 13:28:21, expired at 13:33:21. DB time when checked was 13:47:04 — expired 14 minutes earlier. Code marked used=false (never successfully used).
expecting: Increasing TTL to 900 (15 min) will give users enough time to receive email and enter code.
next_action: Change PAIRING_CODE_TTL_SECONDS from 300 to 900 in src/daily/auth/pairing.py, update email copy to say 15 minutes

## Symptoms

expected: User enters 6-digit OTP and is authenticated successfully
actual: App shows "Invalid or expired code. Try again." red error message
errors: "Invalid or expired code. Try again." displayed in red on the OTP verification screen
reproduction: Request magic link for jacobemarriott@icloud.com, receive email with 6-digit code, enter code in app
started: Occurred 2026-04-30 and prior session. Also had port 8080 sign-in issues previously.

## Eliminated

- hypothesis: Wrong Supabase OTP type (not Supabase at all — entirely custom FastAPI auth)
  evidence: AuthService.swift calls /auth/pair/complete on FastAPI backend, no Supabase SDK involved
  timestamp: 2026-04-30T13:48:00Z

- hypothesis: Backend unreachable / tunnel down
  evidence: curl to health endpoint returns 200 {"status":"ok"}
  timestamp: 2026-04-30T13:48:30Z

- hypothesis: Code not stored in DB / commit failure
  evidence: DB query shows code 675877 is present with used=false (correctly stored, just expired)
  timestamp: 2026-04-30T13:49:00Z

## Evidence

- timestamp: 2026-04-30T13:48:00Z
  checked: ios/dAIly/auth/AuthService.swift
  found: Auth is entirely custom — iOS posts code to /auth/pair/complete on FastAPI, no Supabase involved
  implication: Hypothesis about wrong Supabase OTP type is irrelevant

- timestamp: 2026-04-30T13:48:30Z
  checked: curl https://insurance-backup-quest-antiques.trycloudflare.com/health
  found: Returns 200 {"status":"ok"} — backend and tunnel are live
  implication: Not a connectivity issue

- timestamp: 2026-04-30T13:49:00Z
  checked: Postgres pairing_codes table (SELECT ... ORDER BY created_at DESC LIMIT 10)
  found: Code 675877 created 13:28:21 UTC, expires 13:33:21 UTC (TTL=299.99s). DB now=13:47:04. Used=false.
  implication: Code was expired for ~14 minutes when user tried to use it. 5-min TTL is too short for real email delivery + user action cycle.

- timestamp: 2026-04-30T13:49:30Z
  checked: src/daily/auth/pairing.py PAIRING_CODE_TTL_SECONDS
  found: Set to 300 (5 minutes). Industry standard for OTP/magic-link is 10-15 minutes.
  implication: Root cause confirmed. Fix: increase to 900 (15 min) and update email copy.

## Resolution

root_cause: PAIRING_CODE_TTL_SECONDS = 300 (5 minutes) is too short. Email delivery latency plus the time for a user to switch apps, find the code, and enter it routinely exceeds 5 minutes. Code 675877 expired 14 minutes before the DB was checked.
fix: Increase PAIRING_CODE_TTL_SECONDS from 300 to 900 in src/daily/auth/pairing.py. Update email HTML copy in resend_client.py from "5 minutes" to "15 minutes".
verification: DB query after fix confirmed new pairing codes are created with ttl_seconds=899.99 (15 min). Previously 299.99 (5 min). Send-link endpoint returned 204 after fix. No regression on health endpoint.
files_changed: [src/daily/auth/pairing.py, src/daily/email/resend_client.py]
