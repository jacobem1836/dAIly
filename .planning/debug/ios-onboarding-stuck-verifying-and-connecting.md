---
status: awaiting_human_verify
trigger: "ios-onboarding-stuck-verifying-and-connecting"
created: 2026-05-04T00:00:00Z
updated: 2026-05-04T00:00:00Z
---

## Current Focus

hypothesis: Two independent state-reset bugs — confirmed by reading source code.
test: Applied fixes. Awaiting human verification in the simulator/device.
expecting: Bug 1 resolved — app advances to tab 2 after OTP verify. Bug 2 resolved — Connect button resets after OAuth session launches.
next_action: User to verify both flows in the iOS simulator or on device.

## Symptoms

expected:
  1. After OTP verify succeeds (backend 200 OK), app advances to Google IntegrationView (tab 2).
  2. After OAuth browser session closes without a deep link, Connect button resets so user can retry.
actual:
  1. PairingView stays on "Verifying..." indefinitely. Tab never advances.
  2. IntegrationView stays on "Connecting..." indefinitely after browser closes.
errors: No crashes. Backend logs clean (200 OK). Pure UI state management bugs.
reproduction:
  1. Enter valid 6-digit OTP → tap "Verify code" → backend 200 → stuck on "Verifying..."
  2. Tap "Connect Google" → ASWebAuthenticationSession opens → user completes/cancels → browser closes → stuck on "Connecting..."
started: Present from start of UAT testing. Never worked correctly.

## Eliminated

- hypothesis: Backend returning an error
  evidence: Backend logs show 200 OK for POST /auth/pair/complete. Error path in verifyCode() correctly resets isVerifying.
  timestamp: 2026-05-04T00:00:00Z

- hypothesis: OnboardingView .onChange not wired correctly
  evidence: .onChange on hasAccessToken IS wired. Problem is SwiftUI deduplicates same-value changes — if hasAccessToken was already true, the onChange never fires.
  timestamp: 2026-05-04T00:00:00Z

## Evidence

- timestamp: 2026-05-04T00:00:00Z
  checked: PairingView.swift verifyCode() lines 108-118
  found: isVerifying is set to true on entry (line 109). On the error path (line 115-116), isVerifying is reset. On the success path (line 113), appState.hasAccessToken is set to true but isVerifying is NEVER reset.
  implication: Button stays in "Verifying..." state forever on success. The UI is blocked.

- timestamp: 2026-05-04T00:00:00Z
  checked: OnboardingView.swift .onChange(of: appState.hasAccessToken) lines 110-114
  found: Fires when hasAccessToken changes. But if hasAccessToken was already true (prior session), SwiftUI won't fire onChange because the value didn't change from false to true.
  implication: Even fixing the isVerifying reset won't be enough when hasAccessToken is pre-existing. Need a direct advance callback from PairingView.

- timestamp: 2026-05-04T00:00:00Z
  checked: IntegrationView.swift connect() lines 110-124 and comment on line 117-120
  found: Comment explicitly says "Do NOT set isConnecting = false here — wait for the deep link". openOAuthSession() is not awaited in a way that suspends on session completion. isConnecting only resets via .onChange on connectedProviders (line 63-67). No timeout or cancellation handler.
  implication: When personal dev team has no Universal Links, deep link never arrives, isConnecting stays true forever.

- timestamp: 2026-05-04T00:00:00Z
  checked: IntegrationView.swift connect() line 115 — auth.openOAuthSession()
  found: Called as try auth.openOAuthSession(url: authURL) — not awaited with 'await'. This means the function starts the session but returns immediately without waiting for it to complete.
  implication: The OAuth session runs asynchronously. After openOAuthSession() returns, execution continues — but the code intentionally does NOT reset isConnecting at that point, expecting the deep link to do it. The fix is to reset isConnecting after the session launches (since we have no completion callback without deep links).

## Resolution

root_cause: |
  Bug 1: PairingView.verifyCode() sets isVerifying=true but never resets it on the success path (only on error). The UI is permanently stuck in "Verifying..." state. Additionally, OnboardingView relies on .onChange(of: hasAccessToken) to advance to tab 2, but SwiftUI deduplicates same-value changes — if the user already had a token from a prior session, .onChange never fires.

  Bug 2: IntegrationView.connect() intentionally avoids resetting isConnecting after openOAuthSession() returns, expecting a deep link (/oauth/success) to trigger the .onChange on connectedProviders. When running on personal dev team with no Universal Links, the deep link never arrives, so isConnecting stays true forever with no recovery path.

fix: |
  Bug 1: Add an `onComplete: () -> Void` callback parameter to PairingView. OnboardingView passes `{ advance() }` as the callback. verifyCode() calls onComplete() on the success path (after setting hasAccessToken=true) and also resets isVerifying=false. This removes dependence on .onChange for the advance, making the flow direct and reliable.

  Bug 2: In IntegrationView.connect(), after auth.openOAuthSession() returns (or after obtaining the URL — since openOAuthSession is synchronous/not awaited), reset isConnecting=false. The .onChange on connectedProviders still handles the connected state update when a deep link arrives. This way the button always resets after the OAuth session launches, and the user can retry or skip.

verification: "Pending human verification — user must test both flows on device/simulator."
files_changed:
  - ios/dAIly/views/PairingView.swift
  - ios/dAIly/onboarding/OnboardingView.swift
  - ios/dAIly/onboarding/IntegrationView.swift
