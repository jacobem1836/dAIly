# Phase 19: Native iOS App - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-30
**Phase:** 19-native-ios-app
**Areas discussed:** App location, Device pairing UX, Voice UI design, STT/TTS architecture

---

## App Location

| Option | Description | Selected |
|--------|-------------|----------|
| ios/ in this repo | Monorepo — one clone, one PR for backend+client changes | ✓ |
| Separate repo (dAIly-ios) | Cleaner git history, isolated CI/CD | |

**User's choice:** ios/ in this repo
**Notes:** User asked whether separate repo has advantages. Discussed: clean git history (Xcode binary artifacts), isolated CI, App Store secret isolation. Concluded: for a solo developer, monorepo is simpler and cross-repo coordination overhead outweighs the benefits.

---

## Device Pairing UX

| Option | Description | Selected |
|--------|-------------|----------|
| Manual server URL + pair code | User enters URL + 6-digit code from CLI/admin | |
| QR code scan | Backend displays QR, app scans | |
| Magic link via email | Email with deep link, user taps on device | ✓ |

**User's choice:** Magic link via email (Resend API)
**Notes:** User identified this as the right production UX before being prompted. Confirmed Resend as the delivery mechanism.

### Deep link mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Universal Links (HTTPS) | apple-app-site-association, Apple-preferred | ✓ |
| Custom URL scheme (daily://) | Simpler but hijackable | |

### Token storage

| Option | Description | Selected |
|--------|-------------|----------|
| iOS Keychain | Secure enclave-backed, production standard | ✓ |
| UserDefaults | Plaintext, insecure | |

---

## Voice UI Design

| Option | Description | Selected |
|--------|-------------|----------|
| VAD-only UI | No mode toggle exposed | ✓ |
| VAD + PTT toggle | User can switch modes | |

**User's choice:** VAD-only in production UI
**Notes:** User's view: "VAD is the point of the app." PTT exists in code behind a debug flag — useful for testing, not a user-facing feature.

**Visual design:** Deferred to Claude's discretion. User indicated this doesn't need to be decided in the discuss phase.

---

## STT/TTS Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Server-side via LiveKit Agent | iOS is thin room participant; Python handles STT/TTS | ✓ |
| Client-direct (MOB-05) | Deepgram + Cartesia Swift SDKs in iOS client | |

**User's choice:** Server-side
**Notes:** User asked "what is best for actually releasing the app." Explained that server-side is architecturally correct for dAIly because: API keys stay on server, backend owns conversation control, LiveKit WebRTC handles latency (not client-direct), and the Python agent is already being built. MOB-05 deferred as a future optimisation.

---

## Claude's Discretion

- Voice screen visual design (orb vs waveform, exact layout)
- Exact animation behaviour for connection states
