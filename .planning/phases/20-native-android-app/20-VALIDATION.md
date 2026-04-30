---
phase: 20
slug: native-android-app
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-30
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 4 + MockK (Android unit tests) |
| **Config file** | android/app/build.gradle |
| **Quick run command** | `cd android && ./gradlew testDebugUnitTest` |
| **Full suite command** | `cd android && ./gradlew testDebugUnitTest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd android && ./gradlew testDebugUnitTest`
- **After every plan wave:** Run `cd android && ./gradlew testDebugUnitTest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Populated during execution.

---

## Wave 0 Requirements

- [ ] `android/app/src/test/java/com/daily/android/` — test directory exists
- [ ] JUnit 4 + MockK declared in `build.gradle`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hardware AEC eliminates echo on device | MOB-02 | Requires physical Android device with hardware AEC | Start voice session with speaker playing; confirm no echo in mic capture |
| Magic-link deep link opens app and completes pairing | MOB-02 | Requires real email + Android device | Tap link from email; confirm app opens and voice screen appears |
| Daily briefing audio plays end-to-end | MOB-02 | Requires full backend + LiveKit running | Start session; confirm briefing audio plays through speaker |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
