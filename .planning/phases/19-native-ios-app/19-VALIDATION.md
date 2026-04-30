---
phase: 19
slug: native-ios-app
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-29
approved: 2026-04-29
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | XCTest + Swift Testing (Xcode 16+) for iOS; pytest 7.x for backend |
| **iOS config file** | `ios/dAIly.xcodeproj` (scheme: dAIly) |
| **Backend config file** | `pyproject.toml` (pytest section) |
| **Quick run command (iOS)** | `cd ios && xcodebuild test -project dAIly.xcodeproj -scheme dAIly -destination 'platform=iOS Simulator,name=iPhone 16' -quiet CODE_SIGNING_ALLOWED=NO` |
| **Quick run command (backend)** | `uv run pytest tests/test_resend_client.py tests/test_auth_send_link.py tests/test_aasa.py -x` |
| **Full suite command** | Run both quick commands above, then the manual device test (Task 3 checkpoint) |
| **Estimated runtime** | ~90s combined (automated); manual device test ~10 minutes |

---

## Sampling Rate

- **After every task commit:** Run quick backend pytest command
- **After every plan wave:** Run full iOS xcodebuild test + backend pytest
- **Before `/gsd-verify-work`:** Full suite must be green + manual device checkpoint approved
- **Max feedback latency:** ~90 seconds (automated only)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | MOB-01 | T-19-01 | POST /auth/pair/send-link rejects missing email | unit | `uv run pytest tests/test_auth_send_link.py -x` | ✅ | ✅ green |
| 19-01-02 | 01 | 1 | MOB-01 | T-19-02 | POST /auth/pair/send-link returns 204, generates pair code in DB | unit | `uv run pytest tests/test_auth_send_link.py -x` | ✅ | ✅ green |
| 19-01-03 | 01 | 1 | MOB-01 | T-19-03 | GET /.well-known/apple-app-site-association returns valid AASA JSON | unit | `uv run pytest tests/test_aasa.py -x` | ✅ | ✅ green |
| 19-01-04 | 01 | 1 | MOB-01 | T-19-04 | Resend client delivers email via API | unit | `uv run pytest tests/test_resend_client.py -x` | ✅ | ✅ green |
| 19-02-01 | 02 | 2 | MOB-01 | T-19-05 | KeychainStore save/load/delete/clearAll — kSecAttrAccessibleWhenUnlocked | unit | `xcodebuild test … -only-testing:dAIlyTests/KeychainStoreTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-03-01 | 03 | 2 | MOB-01 | T-19-12 | PairCodeURLParser rejects wrong path, missing code, mixed-case path | unit | `xcodebuild test … -only-testing:dAIlyTests/PairCodeURLParserTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-03-02 | 03 | 2 | MOB-01 | T-19-13/T-19-14 | AuthService.sendLink/completePairing/refresh — HTTPS only, no local caching | unit | `xcodebuild test … -only-testing:dAIlyTests/AuthServiceTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-03-03 | 03 | 2 | MOB-01 | T-19-15 | FirstLaunchCleanup wipes Keychain on first run after reinstall | unit | `xcodebuild test … -only-testing:dAIlyTests/AuthServiceTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-04-01 | 04 | 3 | MOB-01 | T-19-18 | LiveKitTokenSource fetches token with Bearer JWT, parses {token,room,livekit_url} | unit | `xcodebuild test … -only-testing:dAIlyTests/VoiceSessionTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-04-02 | 04 | 3 | MOB-01 | T-19-21/T-19-22 | VoiceSession state machine: idle→connecting→listening; 401→retry; 8s timeout | unit | `xcodebuild test … -only-testing:dAIlyTests/VoiceSessionTests CODE_SIGNING_ALLOWED=NO` | ✅ | ✅ green |
| 19-04-03 | 04 | 3 | MOB-01 | T-19-23/T-19-24 | DebugFlags.pttEnabled=false in Release; hardware AEC not disabled | unit + grep | `grep -q "isAutomaticConfigurationEnabled" ios/dAIly/livekit/VoiceSession.swift && echo "not overridden"` | ✅ | ✅ green |
| 19-05-01 | 05 | 4 | MOB-01 | T-19-25 | Config.backendBaseURL is single URL literal; no duplicates in codebase | grep | `grep -rn 'URL(string: "https://app.example.com")' ios/dAIly --include='*.swift' \| grep -v Config.swift` | ✅ | ✅ green |
| 19-05-02 | 05 | 4 | MOB-01 | T-19-28 | VoiceSession reconnect timeout surfaces .error("reconnect_timeout") after 30s | unit (manual verify) | `grep -q "reconnect_timeout" ios/dAIly/livekit/VoiceSession.swift` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `ios/dAIlyTests/KeychainStoreTests.swift` — 6 tests for KeychainStore (Plan 02)
- [x] `ios/dAIlyTests/PairCodeURLParserTests.swift` — 4 tests for URL parser (Plan 03)
- [x] `ios/dAIlyTests/AuthServiceTests.swift` — 5 tests for AuthService (Plan 03)
- [x] `ios/dAIlyTests/VoiceSessionTests.swift` — 11 tests for LiveKitTokenSource + VoiceSession (Plan 04)
- [x] `tests/test_resend_client.py` — Resend email client tests (Plan 01)
- [x] `tests/test_auth_send_link.py` — POST /auth/pair/send-link tests (Plan 01)
- [x] `tests/test_aasa.py` — GET /.well-known/apple-app-site-association tests (Plan 01)
- [x] `ios/dAIly.xcodeproj` — Xcode project with LiveKit SPM dependency (Plan 02)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hardware AEC quality — no echo during briefing | MOB-01 | Simulator audio routing bypasses hardware AEC; requires physical device speaker + mic path (RESEARCH §Pitfall 4) | Build on physical iPhone, start briefing, speak while audio plays through speaker (NOT headphones). No echo should reach agent. |
| Universal Link end-to-end (warm + cold start) | MOB-01 | Universal Link registration requires Apple CDN validation of AASA; cannot be fully tested in simulator | Open magic link from email on device; verify app opens (not Safari). Force-quit and repeat for cold start. |
| Briefing audio playback quality | MOB-01 | Requires running LiveKit Agent (Phase 18) + dev briefing triggered by backend | Trigger daily briefing; verify audio plays through device speaker, no clipping, no robotic distortion. |
| Launch-to-listening time < 3s | MOB-01 | Stopwatch measurement requires physical device | Use stopwatch from tap Start to state = Listening. Must be under 3 seconds. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all required test files (KeychainStoreTests, AuthServiceTests, PairCodeURLParserTests, VoiceSessionTests, backend pytest files)
- [x] No watch-mode flags in any verification command
- [x] Feedback latency ~90s (automated); manual device test is one-time checkpoint
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-29
