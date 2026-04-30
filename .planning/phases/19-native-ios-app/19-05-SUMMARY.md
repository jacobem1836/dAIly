---
phase: 19-native-ios-app
plan: "05"
subsystem: ios-client
tags: [swift, ios, config, livekit, voice, swiftui, validation, ux]
dependency_graph:
  requires:
    - "19-01: POST /auth/pair/send-link + AASA endpoints"
    - "19-03: AuthService + magic-link pairing"
    - "19-04: LiveKit VoiceSession + VoiceView"
  provides:
    - "ios/dAIly/Config.swift — static let backendBaseURL: URL — single source of truth"
    - ".planning/phases/19-native-ios-app/19-VALIDATION.md — filled validation matrix, nyquist_compliant: true"
  affects:
    - "All iOS files that previously had app.example.com literals — now read Config.backendBaseURL"
tech_stack:
  added: []
  patterns:
    - "Config enum as namespace for compile-time constants (single URL source of truth)"
    - "30s reconnect timeout Task — fires .error('reconnect_timeout') if recovery stalls (T-19-28)"
    - "roomDidDisconnectWithError delegate — unexpected disconnect surfaces user-visible error"
    - "VoiceView error message text — truncated msg prefix(60) above Retry button"
key_files:
  created:
    - "ios/dAIly/Config.swift"
  modified:
    - "ios/dAIly/dAIlyApp.swift — Config.backendBaseURL replaces two hardcoded URL literals"
    - "ios/dAIly/livekit/VoiceSession.swift — disconnect delegate + 30s reconnect timeout + handleDisconnect"
    - "ios/dAIly/views/VoiceView.swift — error message text above Retry button"
    - "ios/README.md — Local Dev with ngrok/Cloudflare Tunnel section"
    - ".planning/phases/19-native-ios-app/19-VALIDATION.md — fully populated"
decisions:
  - "Config enum (not struct/class) chosen — no instantiation possible; purely a namespace for constants"
  - "30s reconnect timeout in handleConnectionState — fires from reconnecting state, not from connect() — keeps timeout scoped to reconnect recovery only"
  - "roomDidDisconnectWithError delegates only error disconnects (guard error != nil) — clean disconnects already handled by didUpdateConnectionState(.disconnected)"
  - "VoiceView shows error text AND Retry button in .error branch — the ConnectionIndicator already shows red circle + truncated msg; VoiceView adds full msg text for readability"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-29"
  tasks_completed: 2
  tasks_total: 3
  files_created: 1
  files_modified: 5
---

# Phase 19 Plan 05: Config Centralisation + Validation + Device Test Summary

**One-liner:** Backend URL centralised to Config.swift, disconnect/reconnect UX hardened with 30s timeout and error delegate, VALIDATION.md fully populated with 13-row verification map — awaiting manual device-test checkpoint.

## What Was Built

### Task 1: Config.swift + Reconnect/Disconnect UX

**`ios/dAIly/Config.swift`** (new file):
- `public enum Config` — namespace with single `public static let backendBaseURL: URL`
- Inline comment explains tunnel workflow (ngrok / Cloudflare) for local dev
- Single place to edit before TestFlight; no duplicate URL literals in codebase

**`ios/dAIly/dAIlyApp.swift`** updated:
- Both `AuthService(baseURL:)` and `LiveKitTokenSource(baseURL:)` now use `Config.backendBaseURL`
- Removed hardcoded `"https://app.example.com"` literals (T-19-25 acceptance criteria)

**`ios/dAIly/livekit/VoiceSession.swift`** updated:
- `handleDisconnect(error:)` — called from `roomDidDisconnectWithError` delegate; sets `.error("disconnected: <msg>")` on non-nil error
- `handleConnectionState(.reconnecting)` now starts a `Task.sleep(30s)` timeout → `.error("reconnect_timeout")` if still reconnecting (T-19-28)
- `handleConnectionState(.connected)` cancels the reconnect timeout Task
- `disconnect()` cancels both `listeningTimeoutTask` and `reconnectTimeoutTask`
- `SessionRoomDelegate.room(_:didDisconnectWithError:)` added — guards on non-nil error, dispatches to `handleDisconnect`
- `_testHandleDisconnect(error:)` DEBUG hook added for unit testing

**`ios/dAIly/views/VoiceView.swift`** updated:
- `.error(let msg)` branch extracts and displays `String(msg.prefix(60))` in a red caption above the Retry button
- `errorMessage(_:)` helper renders the truncated text at `maxWidth: 280`

**`ios/README.md`** updated:
- "Local Dev with ngrok / Cloudflare Tunnel" section added with step-by-step tunnel setup
- "Backend URL Configuration" section updated to reference Config.swift (not dAIlyApp.swift)

### Task 2: VALIDATION.md Finalised

- Frontmatter: `nyquist_compliant: true`, `wave_0_complete: true`, `approved: 2026-04-29`
- Test Infrastructure table: both iOS (xcodebuild) and backend (pytest) quick-run commands
- 13-row Per-Task Verification Map covering every task in plans 01–05
- Wave 0 checklist: all 8 test files ticked
- 4 Manual-Only Verifications: Hardware AEC, Universal Link cold/warm, briefing audio, <3s launch
- Validation Sign-Off: all boxes ticked

## Deviations from Plan

None — plan executed exactly as written for Tasks 1 and 2.

## Awaiting Manual Checkpoint

**Task 3 (checkpoint:human-verify)** is a blocking gate requiring physical iPhone testing. The 7 device tests are documented in the plan. No code modifications are made by Task 3.

Required pre-conditions:
1. Backend running: `uv run uvicorn daily.main:app --reload --port 8000`
2. LiveKit dev server running (Phase 18 setup)
3. Tunnel: `cloudflared tunnel --url http://localhost:8000`
4. `Config.swift` `backendBaseURL` set to tunnel URL
5. `dAIly.entitlements` `applinks:` updated to tunnel host
6. Apple Team ID + bundle ID set in Xcode Signing & Capabilities
7. `.env` with `RESEND_API_KEY`, `APPLE_TEAM_ID`, `APPLE_BUNDLE_ID`, `MAGIC_LINK_BASE_URL`

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `backendBaseURL = URL(string: "https://app.example.com")!` | `ios/dAIly/Config.swift` | Placeholder; developer replaces with tunnel URL for testing and production URL before TestFlight |
| `appState.isAuthenticated` | `ios/dAIly/AppState.swift` | Legacy Plan 02 stub; both `isAuthenticated` and `hasAccessToken` exist; consolidation deferred post-device-test |

## Threat Surface Scan

No new threat surfaces beyond those in the plan's threat register. All T-19-25 through T-19-29 dispositions implemented as planned.

| Threat | File | Mitigation Applied |
|--------|------|--------------------|
| T-19-25: URL tampering via duplicate literals | Config.swift + dAIlyApp.swift | Single URL literal in Config.swift; acceptance criteria verified no duplicates |
| T-19-28: Reconnect DoS storm | VoiceSession.swift | 30s timeout → .error("reconnect_timeout") → user-initiated retry only |
| T-19-29: Audio captured outside session | VoiceSession.swift | handleDisconnect clears room reference; manual test #6 verifies mic indicator clears |

## Self-Check

**Files exist:**
- `ios/dAIly/Config.swift` — FOUND
- `ios/dAIly/dAIlyApp.swift` — FOUND (modified)
- `ios/dAIly/livekit/VoiceSession.swift` — FOUND (modified)
- `ios/dAIly/views/VoiceView.swift` — FOUND (modified)
- `ios/README.md` — FOUND (modified)
- `.planning/phases/19-native-ios-app/19-VALIDATION.md` — FOUND (modified)

**Commits exist:**
- c50c40c — FOUND
- e4a1925 — FOUND

## Self-Check: PASSED
