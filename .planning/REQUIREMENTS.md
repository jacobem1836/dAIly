# Requirements: dAIly

**Defined:** 2026-04-28
**Core Value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.

## v1.4 Requirements

Requirements for Mobile Voice milestone. Each maps to roadmap phases.

### Backend Infrastructure

- [ ] **INFRA-01**: User can connect to a LiveKit room via self-hosted LiveKit server with TURN support
- [ ] **INFRA-02**: User receives a short-lived JWT session token from `POST /livekit/token` authenticated against their existing session
- [ ] **INFRA-03**: User's voice session is handled by a LiveKit Agent worker that wraps the existing LangGraph orchestrator via `LLMAdapter`
- [ ] **INFRA-04**: User's morning briefing precomputes on schedule without interruption after LiveKit migration (APScheduler continuity verified)
- [ ] **INFRA-05**: User's voice session uses Deepgram STT and Cartesia TTS via LiveKit plugins (same providers, new plumbing)
- [ ] **INFRA-06**: Old `voice/` module (stt.py, tts.py, barge_in.py, loop.py) is deleted — hard cutover via feature flag

### iOS Client

- [ ] **IOS-01**: User can start a voice session from an iOS app with hardware AEC (AVAudioEngine, speaker routing)
- [ ] **IOS-02**: User can listen to the briefing while the screen is locked or app is backgrounded
- [ ] **IOS-03**: User sees a live rolling transcript of both their speech and the assistant's responses
- [ ] **IOS-04**: User sees clear connection state feedback (connecting, connected, reconnecting, error)
- [ ] **IOS-05**: User grants microphone permission with a clear rationale before first voice session

### Android Client

- [ ] **AND-01**: User can start a voice session from an Android app with WebRTC AEC3 (Oboe, speaker routing)
- [ ] **AND-02**: User can listen to the briefing while the screen is locked or app is backgrounded (foreground service)
- [ ] **AND-03**: User sees a live rolling transcript of both their speech and the assistant's responses
- [ ] **AND-04**: User sees clear connection state feedback (connecting, connected, reconnecting, error)
- [ ] **AND-05**: User grants microphone permission with a clear rationale before first voice session

### Web & Delivery

- [ ] **WEB-01**: User can start a voice session from a desktop browser via LiveKit web SDK with WebRTC AEC
- [ ] **PUSH-01**: User receives a push notification at their configured briefing time that starts the session (APNs on iOS, FCM on Android)

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Push & Polish

- **PUSH-02**: Pre-connected audio buffering — session feels instant via LiveKit room pre-warm before push
- **VOICE-11**: Action approval via voice — "send it" / "cancel" confirms pending actions hands-free

### Anti-Features (Explicitly Deferred)

- **WAKE-01**: Always-on wake word ("Hey Daily") — battery drain, privacy surface, false positives; push notification is cleaner for briefing product
- **CLONE-01**: Voice cloning / custom agent voice — not differentiated at v1.4; Cartesia quality is strong
- **OFFLINE-01**: On-device STT (Whisper) — no streaming, CPU latency 2-5x cloud, contradicts sub-800ms target
- **VIDEO-01**: Video / avatar agent — battery drain, CPU load, doesn't serve voice briefing use case
- **MULTI-01**: Multi-user / family mode — scope explosion at v1.4

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Full in-app settings editor | Duplicates v2.0 web dashboard; surface only mobile-critical settings |
| Always-on background listening | iOS restricts background mic; kills battery; App Store review flags |
| Cross-platform framework (Flutter/RN) | Voice quality is core differentiator; no abstraction on audio path |
| OpenAI Realtime API integration | Deferred — LiveKit gives model flexibility without vendor lock-in |
| Web dashboard | v2.0 scope |
| Ecosystem integrations | v2.0+ scope |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 18 | Pending |
| INFRA-02 | Phase 18 | Pending |
| INFRA-03 | Phase 19 | Pending |
| INFRA-04 | Phase 19 | Pending |
| INFRA-05 | Phase 19 | Pending |
| INFRA-06 | Phase 19 | Pending |
| IOS-01 | Phase 20 | Pending |
| IOS-02 | Phase 20 | Pending |
| IOS-03 | Phase 20 | Pending |
| IOS-04 | Phase 20 | Pending |
| IOS-05 | Phase 20 | Pending |
| AND-01 | Phase 21 | Pending |
| AND-02 | Phase 21 | Pending |
| AND-03 | Phase 21 | Pending |
| AND-04 | Phase 21 | Pending |
| AND-05 | Phase 21 | Pending |
| WEB-01 | Phase 22 | Pending |
| PUSH-01 | Phase 22 | Pending |

**Coverage:**
- v1.4 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-04-28*
*Last updated: 2026-04-28 after roadmap creation — all 18 requirements mapped*
