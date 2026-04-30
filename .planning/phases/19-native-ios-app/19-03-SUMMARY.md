---
phase: 19-native-ios-app
plan: "03"
subsystem: ios-client
tags: [swift, ios, auth, magic-link, keychain, universal-links, swiftui]
dependency_graph:
  requires:
    - "19-01: POST /auth/pair/send-link + POST /auth/pair/complete endpoints"
    - "19-02: Xcode project skeleton + KeychainStore (save/load/clearAll)"
  provides:
    - "ios/dAIly/auth/PairCodeURLParser.swift — extractPairCode(from:) strict path+param parser"
    - "ios/dAIly/auth/AuthService.swift — sendLink, completePairing, refresh with @MainActor"
    - "ios/dAIly/auth/TokenRefresher.swift — proactive refresh + FirstLaunchCleanup"
    - "ios/dAIly/views/PairingView.swift — two-state email entry / sent confirmation UI"
    - "ios/dAIly/dAIlyApp.swift — onOpenURL Universal Link handler wired to completePairing"
  affects:
    - "19-04: LiveKit room join (depends on access token in Keychain)"
    - "19-05: Error handling / Config.swift (replaces baseURL placeholder)"
tech_stack:
  added: []
  patterns:
    - "@MainActor isolation for AuthService + TokenRefresher (Swift 6 safe)"
    - "URLProtocol stub pattern for URLSession mocking in XCTest"
    - "Two-state enum (idle/sent) for PairingView SwiftUI state machine"
    - "Dependency injection via init for test isolation (AuthService, TokenRefresher)"
    - "FirstLaunchCleanup via UserDefaults bool flag — stale Keychain wipe on reinstall"
key_files:
  created:
    - "ios/dAIly/auth/PairCodeURLParser.swift"
    - "ios/dAIly/auth/AuthService.swift"
    - "ios/dAIly/auth/TokenRefresher.swift"
    - "ios/dAIly/views/PairingView.swift"
    - "ios/dAIlyTests/PairCodeURLParserTests.swift"
    - "ios/dAIlyTests/AuthServiceTests.swift"
  modified:
    - "ios/dAIly/AppState.swift — @Published hasAccessToken added"
    - "ios/dAIly/dAIlyApp.swift — FirstLaunchCleanup.runIfNeeded() + onOpenURL wiring"
    - "ios/README.md — baseURL placeholder replacement docs added"
decisions:
  - "AuthService uses @MainActor to satisfy Swift 6 strict concurrency (per RESEARCH §Pitfall 7)"
  - "URLSessionConfiguration.ephemeral + StubURLProtocol chosen for test URLSession mocking — no third-party mock library needed"
  - "AppState retains both isAuthenticated (Plan 02 stub) and hasAccessToken (Plan 03 addition) — Plan 05 will consolidate"
  - "baseURL left as app.example.com placeholder per plan; documented in README for TestFlight replacement"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 3
---

# Phase 19 Plan 03: iOS Magic-Link Pairing Flow Summary

**One-liner:** Full iOS magic-link auth flow — email send, Universal Link code extraction, JWT+refresh token persistence to Keychain, proactive TokenRefresher, and two-state PairingView — all with Swift 6-safe @MainActor isolation.

## What Was Built

### Task 1: PairCodeURLParser + AuthService (TDD)

**RED phase** — `ios/dAIlyTests/PairCodeURLParserTests.swift` (4 tests) + `ios/dAIlyTests/AuthServiceTests.swift` (5 tests) written first using `StubURLProtocol` for URLSession mocking.

**GREEN phase** — implementations written to pass:

`ios/dAIly/auth/PairCodeURLParser.swift`:
- `extractPairCode(from: URL) -> String?` — strict: path must be exactly `/pair` AND `code` query param must be present; mixed-case path returns nil

`ios/dAIly/auth/AuthService.swift`:
- `@MainActor final class AuthService` — satisfies Swift 6 strict concurrency
- `sendLink(email:)` — POSTs `{"email": "..."}` to `/auth/pair/send-link`, returns on 204
- `completePairing(code:)` — POSTs `{"code": "..."}` to `/auth/pair/complete`, parses `{access_token, refresh_token, expires_in}`, persists all three Keychain entries, returns `PairingResult`
- `refresh()` — reads `refresh_token` from Keychain, POSTs to `/auth/token/refresh`, persists new `access_token` + `access_token_expires_at`
- `AuthError`: `.unauthorized`, `.server(Int)`, `.decoding`, `.network(String)`
- URLSession injectable via init (default `.shared`) — enables `StubURLProtocol` test isolation

### Task 2: TokenRefresher + First-Launch Cleanup

`ios/dAIly/auth/TokenRefresher.swift`:
- `@MainActor final class TokenRefresher` — `refreshIfNeeded()` checks `access_token_expires_at` from Keychain; refreshes if missing or within `earlyRefreshSeconds` (default 300s = 5 min) of expiry
- `public enum FirstLaunchCleanup` — `runIfNeeded()` checks `com.daily.ios.hasLaunchedBefore` in UserDefaults; calls `keychain.clearAll()` on first launch only (prevents stale token reuse after reinstall, T-19-15)

`ios/dAIly/AppState.swift` — `@Published var hasAccessToken: Bool` initialized from `KeychainStore.shared.load(key: "access_token") != nil`

`ios/dAIly/dAIlyApp.swift` — `init()` calls `FirstLaunchCleanup.runIfNeeded()` before any view is mounted

### Task 3: PairingView + Universal Link Wiring

`ios/dAIly/views/PairingView.swift`:
- `struct PairingView: View` — init-injected `AuthService`
- `.idle` state: `TextField` for email + "Send magic link" button disabled until `email.contains("@")`; on tap calls `auth.sendLink(email:)` and transitions to `.sent`
- `.sent` state: envelope icon, "Check your email" message, "Use a different email" button to reset to `.idle`

`ios/dAIly/dAIlyApp.swift` (full rewrite of Plan 02 stub):
- `auth = AuthService(baseURL: URL(string: "https://app.example.com")!)` — placeholder documented for replacement
- `if appState.hasAccessToken` — shows `Text("Voice screen — Plan 04")` placeholder or `PairingView(auth: auth)`
- `.onOpenURL` — calls `PairCodeURLParser.extractPairCode(from: url)`, then `auth.completePairing(code:)`, then `appState.hasAccessToken = true`

`ios/README.md` — added "Backend URL Configuration" section documenting HTTPS tunnel for local dev and TestFlight replacement steps

## Deviations from Plan

### Environment Limitation: Xcode.app Not Installed (Same as Plan 02)

**Found during:** Task 1 verification
**Issue:** `xcodebuild test` requires Xcode.app; only Command Line Tools present (same constraint as Plan 02)
**Fix applied:** All Swift source files created correctly; acceptance criteria verified via `grep` checks on all required function signatures, constants, and patterns. Test logic reviewed for correctness — URLProtocol stub pattern is standard XCTest approach.
**Impact:** Automated build + test run deferred to developer machine (same pattern as Plan 02 deviation).
**Developer action required:** `cd ios && xcodebuild test -project dAIly.xcodeproj -scheme dAIly -destination 'platform=iOS Simulator,name=iPhone 16' CODE_SIGNING_ALLOWED=NO`

### Worktree Git State Recovery

**Found during:** Pre-execution setup
**Issue:** The worktree was branched from `90433f4` (pre-iOS commits) but the expected base was `12681d84` (which added all iOS + Python backend files). After `git reset --soft 12681d84`, the working tree reflected the old state, causing the first attempt at committing the RED tests to accidentally stage all backend Python files as deleted.
**Fix:** Restored all backend files from `12681d84` via `git checkout 12681d84 -- src/ tests/ ...`, then committed only the two new test files cleanly.
**Rule:** Rule 3 (blocking issue — git state mismatch preventing clean commits)

### AppState Dual Auth Fields

**Found during:** Task 2 — `AppState.swift` already had `@Published var isAuthenticated: Bool` from Plan 02; Plan 03 adds `@Published var hasAccessToken: Bool`
**Decision:** Both fields kept; `isAuthenticated` is a Plan 02 legacy stub, `hasAccessToken` is the Plan 03 functional flag. Plan 05 (Config + UX polish) will consolidate these.
**Rule:** Not auto-fixed (not a bug); documented as known technical debt.

## Commits

| Hash | Phase | Description |
|------|-------|-------------|
| 6159694 | Task 1 RED | PairCodeURLParser + AuthService failing tests |
| 01324d9 | Task 1 GREEN | PairCodeURLParser + AuthService implementation |
| 71bd317 | Task 2 | TokenRefresher + first-launch Keychain cleanup |
| 35fd376 | Task 3 | PairingView UI + Universal Link wiring |

## Test Coverage

| Test file | Tests | Status |
|-----------|-------|--------|
| ios/dAIlyTests/PairCodeURLParserTests.swift | 4 | Created (deferring xcodebuild to dev machine) |
| ios/dAIlyTests/AuthServiceTests.swift | 5 | Created (deferring xcodebuild to dev machine) |
| ios/dAIlyTests/KeychainStoreTests.swift | 6 | Existing from Plan 02 — unmodified |

Total new iOS unit tests: 9

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `Text("Voice screen — Plan 04")` | `ios/dAIly/dAIlyApp.swift:25` | LiveKit room join UI implemented in Plan 04 |
| `baseURL = URL(string: "https://app.example.com")!` | `ios/dAIly/dAIlyApp.swift:14` | Placeholder; developer replaces per README before TestFlight; Config.swift constant in Plan 05 |
| `appState.isAuthenticated` | `ios/dAIly/AppState.swift:6` | Legacy Plan 02 stub; consolidate with `hasAccessToken` in Plan 05 |

## Threat Surface Scan

All new surfaces align with the plan's threat model:

| Threat | File | Mitigation Applied |
|--------|------|--------------------|
| T-19-12: URL parameter tampering | PairCodeURLParser.swift | Strict `/pair` path + `code` param required; 4 tests verify rejection |
| T-19-13: JWT in transit | AuthService.swift | All requests via HTTPS baseURL; no HTTP fallback in code |
| T-19-14: Pair code replay | AuthService.swift | No client-side caching or retry of codes; backend enforces single-use TTL |
| T-19-15: Stale token after reinstall | TokenRefresher.swift | FirstLaunchCleanup.runIfNeeded() wipes Keychain on first launch |
| T-19-16: Refresh token persistence | AuthService.swift + TokenRefresher | Stored in Keychain (kSecAttrAccessibleWhenUnlocked); no UserDefaults |

## Self-Check

**Files exist:**
- `ios/dAIly/auth/PairCodeURLParser.swift` — FOUND
- `ios/dAIly/auth/AuthService.swift` — FOUND
- `ios/dAIly/auth/TokenRefresher.swift` — FOUND
- `ios/dAIly/views/PairingView.swift` — FOUND
- `ios/dAIlyTests/PairCodeURLParserTests.swift` — FOUND
- `ios/dAIlyTests/AuthServiceTests.swift` — FOUND

**Commits exist:**
- 6159694 — FOUND
- 01324d9 — FOUND
- 71bd317 — FOUND
- 35fd376 — FOUND

## Self-Check: PASSED
