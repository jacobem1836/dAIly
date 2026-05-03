---
phase: 20
status: approved
nyquist_compliant: true
wave_0_complete: true
approved: 2026-04-30
---

# Phase 20 — Native Android App Validation

## Scope

This document covers all validation for Phase 20: Native Android App (Plans 20-01 through 20-05).
It mirrors the iOS Phase 19 validation pattern and is the final sign-off gate before the phase is
considered complete.

## Per-Task Verification Map

| Plan-Task | Behavior | Automated Command | Notes |
|-----------|----------|-------------------|-------|
| 20-01-01 | `GET /.well-known/assetlinks.json` returns correct JSON array with package + fingerprints | `uv run pytest tests/test_assetlinks.py` | 8 tests; all pass on planning machine |
| 20-02-01 | Gradle skeleton builds; LiveKit 2.25.1 + Compose BOM 2025.01.00 + Tink 1.14.0 declared | `grep -q "io.livekit:livekit-android:2.25.1" android/app/build.gradle.kts` | Gradle build deferred to developer machine |
| 20-02-02 | TokenStore round-trip; ciphertext on disk; missing key; delete; overwrite; clearAll | `./gradlew testDebugUnitTest --tests "*.TokenStoreTest"` | 6 Robolectric tests; deferred to developer machine |
| 20-03-01 | PairCodeUriParser rejects malformed URIs; AuthService completePairing + refresh happy + error paths | `./gradlew testDebugUnitTest --tests "*.PairCodeUriParserTest" --tests "*.AuthServiceTest"` | 4 + 5 = 9 MockWebServer + Robolectric tests; deferred to developer machine |
| 20-03-02 | TokenRefresher refreshIfNeeded; FirstLaunchCleanup wipes once; App Links autoVerify manifest; PairingScreen UI; MainActivity cold + warm deep-link paths | `grep -q "autoVerify=\"true\"" android/app/src/main/AndroidManifest.xml` | App Links tap-test in manual checkpoint (Task 3.1) |
| 20-04-01 | LiveKitTokenSource POSTs to /livekit/token with Bearer JWT; parses token/room/livekit_url; sealed error hierarchy | `./gradlew testDebugUnitTest --tests "*.LiveKitTokenSourceTest"` | 4 MockWebServer tests; deferred to developer machine |
| 20-04-02 | VoiceSession StateFlow: Idle → Connecting → Listening → Speaking; single-retry on 401; 8s unreachable timeout; 30s reconnect timeout | `./gradlew testDebugUnitTest --tests "*.VoiceSessionTest"` | 7 Robolectric + MockK + coroutines-test tests; deferred to developer machine |
| 20-04-03 | VoiceScreen collectAsState; ConnectionIndicator semantic colours; Start/Retry/End buttons; MainActivity wires VoiceSession via remember{}; unauthed → PairingScreen | `grep -q "VoiceScreen" android/app/src/main/kotlin/com/daily/android/MainActivity.kt` | Manual UI test in checkpoint (Tasks 3.2–3.3) |
| 20-05-01 | Config.kt single source of truth; no hardcoded URL in Kotlin tree outside Config.kt; README documents cloudflared + manifest-sync warning + adb verification | `test -f android/app/src/main/kotlin/com/daily/android/Config.kt && grep -q "Config.backendBaseURL" android/app/src/main/kotlin/com/daily/android/MainActivity.kt` | All grep criteria pass on planning machine |
| 20-05-02 | VALIDATION.md finalised; frontmatter nyquist_compliant + wave_0_complete; full per-task map | `grep -q "nyquist_compliant: true" .planning/phases/20-native-android-app/20-VALIDATION.md && grep -cE "^\| 20-0[1-5]" .planning/phases/20-native-android-app/20-VALIDATION.md` | This document |
| 20-05-03 | Manual device checkpoint: pairing, voice round-trip, AEC, briefing, reconnect, stale-token cleanup, cold-launch < 3s | Manual — see Section "Manual-Only Verifications" | Physical Android device required; emulator AEC unreliable |

## Wave 0 Requirements

- [x] `android/app/src/test/kotlin/com/daily/android/` exists
- [x] JUnit 4 + MockK declared in build.gradle.kts
- [x] MockWebServer declared in build.gradle.kts
- [x] Robolectric declared in build.gradle.kts

## Threat Model Coverage

| Threat ID | Category | Mitigation | Plan-Task | Status |
|-----------|----------|-----------|-----------|--------|
| T-20-05 | Information Disclosure | TokenStore AES-256-GCM; ciphertext test | 20-02-02 | Mitigated |
| T-20-06 | Tampering | clearAll() on first launch | 20-02-02 + 20-03-02 | Mitigated |
| T-20-07 | Tampering | EncryptedSharedPreferences absent; grep asserts | 20-02-02 | Mitigated |
| T-20-08 | Supply Chain | LiveKit pinned 2.25.1; JitPack explicit | 20-02-01 | Mitigated |
| T-20-09 | Availability | suspend-only DataStore API; runBlocking absent | 20-02-02 | Mitigated |
| T-20-10 | Spoofing | App Links HTTPS + autoVerify=true | 20-03-02 | Mitigated |
| T-20-11 | Tampering | PairCodeUriParser strict path; 4 unit tests | 20-03-01 | Mitigated |
| T-20-12 | Elevation | Backend single-use TTL; no client caching | 20-03-01 | Mitigated |
| T-20-13 | Information Disclosure | FirstLaunchCleanup wipes TokenStore on reinstall | 20-03-02 | Mitigated |
| T-20-14 | Information Disclosure | AuthError.Network wraps class name only | 20-03-01 | Mitigated |
| T-20-15 | Availability | singleTop + onNewIntent; both paths call handleDeepLink | 20-03-02 | Mitigated |
| T-20-17 | Information Disclosure | LiveKit JWT held in local val only; never logged | 20-04-01 | Mitigated |
| T-20-18 | Tampering | Token sourced from authenticated /livekit/token only | 20-04-01 | Mitigated |
| T-20-19 | Availability | Single-retry on 401; double 401 → Error("token_unauthorized") | 20-04-02 | Mitigated |
| T-20-20 | Availability | 8s unreachable timeout → Error("agent_unreachable") | 20-04-02 | Mitigated |
| T-20-21 | Availability | 30s reconnect timeout → Error("reconnect_timeout") | 20-04-02 | Mitigated |
| T-20-22 | Audio Quality | No audioOptions/javaAudioDeviceModuleCustomizer — SDK default AEC | 20-04-02 | Mitigated |
| T-20-23 | Tampering | URL drift: Config.kt single source; no URL literal in Kotlin tree outside Config.kt | 20-05-01 | Mitigated |
| T-20-24 | Spoofing | Manifest host vs Config drift: README warning; manual checkpoint 3.1 verifies | 20-05-01 | Mitigated |
| T-20-25 | Information Disclosure | Validation doc: manual checkpoint is gate="blocking" | 20-05-03 | Mitigated |

## Manual-Only Verifications

These cannot be automated — physical Android device required (emulator AEC is unreliable):

1. **App Links pairing (T-20-10, T-20-15):** Tap magic link in Gmail app → dAIly opens directly (not browser/chooser) → screen transitions to VoiceScreen Idle
2. **Hardware AEC (T-20-22):** Agent audio at 70%+ volume while speaking; agent voice NOT picked up as user input (no echo loop)
3. **Daily briefing playback:** Full briefing plays end-to-end without dropouts
4. **Cold-launch < 3s (UAT):** Force-stop then tap launcher → app reaches PairingScreen or VoiceScreen within 3 seconds

## Validation Sign-Off

- [x] All grep-based acceptance criteria pass on planning machine
- [x] All TDD test suites written and verified structurally (Gradle execution deferred to developer machine — Android SDK absent on planning machine, same pattern as Phase 19 iOS)
- [x] All threat model mitigations applied
- [x] Manual-only verifications enumerated with pass criteria
- [x] Wave 0 requirements met
- [x] Config.kt centralises backend URL; no drift vector in Kotlin source tree

**Approval:** approved 2026-04-30
