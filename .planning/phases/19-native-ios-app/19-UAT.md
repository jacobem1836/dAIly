---
status: partial
phase: 19-native-ios-app
source: [19-01-SUMMARY.md, 19-02-SUMMARY.md, 19-03-SUMMARY.md, 19-04-SUMMARY.md, 19-05-SUMMARY.md]
started: 2026-04-30T02:30:00Z
updated: 2026-04-30T02:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Backend — Magic-Link Email Send
expected: POST /auth/pair/send-link with {"email": "your@email.com"} returns HTTP 204 (no body). A magic-link email arrives in your inbox with a link like https://<tunnel>/pair?code=XXXXXX. The same endpoint returns 204 even if the email doesn't exist (no enumeration leak).
result: pass
note: "204 confirmed via curl. RESEND_API_KEY not set in .env so email delivery untested — backend mechanics verified."

### 2. Backend — AASA Endpoint
expected: GET /.well-known/apple-app-site-association returns JSON (no redirect) containing "applinks" with an "apps" array and a "details" array that includes the bundle ID. Content-Type should be application/json.
result: pass
note: "JSON structure correct. appID shows .com.daily.ios with leading dot — APPLE_TEAM_ID not set in .env. Needs populating before TestFlight."

### 3. iOS App Launch — Pairing Screen
expected: Open the app on device/simulator. With no token stored, the PairingView appears showing a text field for email and a "Send magic link" button. The button is disabled until the email field contains "@".
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator to build and run"

### 4. iOS — Send Magic Link Flow
expected: Enter an email address in the PairingView field. Tap "Send magic link". The view transitions to the "sent" state showing an envelope icon and "Check your email" text. A "Use a different email" button is visible to reset back to the email entry state.
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator"

### 5. iOS — Universal Link Pairing Completes
expected: Tap the magic-link URL from the email on the same device. The app opens (or comes to foreground), the pairing completes, and the app transitions to the voice screen (VoiceView). The email/sent UI disappears. On subsequent app launches the voice screen shows directly (token persisted in Keychain).
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator + RESEND_API_KEY configured"

### 6. iOS — Voice Session States
expected: On the voice screen, tap "Start". The ConnectionIndicator transitions: grey "Tap to start" → yellow pulsing "Connecting" → green "Listening". When the AI responds, the indicator turns blue "Speaking". States are visible and clearly distinct.
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator + full backend running"

### 7. iOS — End Voice Session
expected: During an active session (Listening or Speaking state), tap "End". The session disconnects and the indicator returns to grey idle state ("Tap to start"). Tapping "Start" again reconnects cleanly.
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator"

### 8. iOS — Error State and Retry
expected: With the backend stopped (or agent unreachable), tap "Start". After ~8 seconds, the indicator turns red and shows an error message (e.g. "agent_unreachable") with a "Tap Retry" hint below. The full error message text appears above a Retry button. Tapping Retry re-attempts the connection.
result: blocked
blocked_by: physical-device
reason: "Requires Xcode + iPhone device or simulator"

## Summary

total: 8
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 6

## Gaps

[none yet]
