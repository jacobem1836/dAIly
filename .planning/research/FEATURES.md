# Feature Research

**Domain:** Voice-first AI personal assistant — mobile voice (LiveKit + native iOS + Android + web fallback)
**Researched:** 2026-04-28 (update; original 2026-04-05)
**Confidence:** MEDIUM-HIGH (LiveKit docs HIGH, mobile UX patterns MEDIUM, morning briefing app comparators MEDIUM)

---

## Context: What Already Exists (v1.0–v1.3)

The original feature landscape (researched 2026-04-05) covered the full product. This document has been updated to focus on **v1.4 Mobile Voice** — what the native iOS, Android, and web fallback clients need, how to prioritise, and what to defer.

**Already shipped — not re-scoped here:**
- Precomputed morning briefing pipeline (Redis-cached, <1s delivery)
- LangGraph orchestrator with approval-gated action layer
- Deepgram STT + Cartesia TTS streaming pipeline
- Barge-in detection, backchannel detection, streaming LLM→TTS
- OAuth integrations (Gmail, GCal, Outlook, Slack)
- Cross-session memory (mem0 + pgvector)
- CLI voice interface (`daily voice`, `daily briefing`, `daily chat`)

**v1.4 scope:** Move audio I/O from Python CLI to native mobile clients via LiveKit. Python backend becomes orchestration-only. macOS AEC (structurally unsolvable in software) replaced by OS-level hardware AEC on iOS/Android.

---

## Feature Landscape — v1.4 Mobile Voice

### Table Stakes (Users Expect These)

Features users assume exist in any mobile voice app. Missing these makes the product feel broken or incomplete.

| Feature | Why Expected | Complexity | Backend Dependency | Notes |
|---------|--------------|------------|-------------------|-------|
| **Hardware AEC (acoustic echo cancellation)** | Without AEC, TTS bleeds into mic — phantom barge-in makes the product unusable on speaker | HIGH value, LOW cost on native | None (OS layer, free on native) | Core reason for going native. iOS: AVAudioEngine voice processing mode. Android: Oboe `AAUDIO_INPUT_PRESET_VOICE_COMMUNICATION`. LiveKit Swift SDK manages AVAudioSession automatically. This is the structural fix for the v1.3 macOS blocker. |
| **Native audio session management** | Mic permissions, speaker routing, background audio must work without configuration | MEDIUM | None (client-side) | iOS: AVAudioSession `.playAndRecord` with `.defaultToSpeaker`. Android: Oboe stream + `AudioManager.MODE_IN_COMMUNICATION`. LiveKit SDK handles session flags when local track is published. |
| **Real-time barge-in / interruption** | Users expect to speak over the assistant mid-sentence, like a phone call | MEDIUM | LiveKit Agents ML turn detection | LiveKit Agents uses a custom ML turn detection model — not a silence timer. Replaces the 4-fix `barge_in.py` system. Sub-200ms barge-in stop is 2025 table stakes per industry research. |
| **Connection state feedback** | Users must know whether the app is connected, connecting, or failed | LOW | LiveKit room state events | Connecting / connected / reconnecting / disconnected UI states required. Silent failures cause abandoned sessions. Pulse animation while connecting; clear error on failure. |
| **Microphone permission handling** | OS permission must be requested with a clear rationale before use | LOW | None (client-side) | iOS: `NSMicrophoneUsageDescription`. Android: `RECORD_AUDIO` runtime permission. Explain "to deliver your briefing hands-free" before requesting — reduces denial rate. |
| **Speaker routing (not earpiece)** | Voice briefing must come from the speaker, not the earpiece | LOW | None (client-side) | iOS: AVAudioSession `.defaultToSpeaker`. Android: `AudioManager.setSpeakerphoneOn(true)`. |
| **Background audio continuation** | Briefing must play when screen locks or user switches apps | MEDIUM | None (client-side) | iOS: Background Modes → Audio + AirPlay entitlement. Android: foreground service with `FOREGROUND_SERVICE_MEDIA_PLAYBACK`. Critical for morning use case — user locks phone while getting ready. |
| **Graceful offline / network failure handling** | WebRTC degrades under poor network; users need clear feedback, not silent hang | MEDIUM | LiveKit reconnect events | LiveKit WebRTC handles transient drops with automatic reconnect. Client must surface "Reconnecting…" state. Clear manual retry option. No silent hang. |
| **Session token flow (auth)** | LiveKit rooms require a JWT access token per session | MEDIUM | FastAPI `/livekit/token` endpoint | Backend generates LiveKit access tokens via `livekit-server-sdk`. Client requests token at session start — never hardcoded. Token endpoint authenticated against existing user session. |
| **Live transcription display** | Users need to verify the assistant heard them correctly — key trust signal at launch | MEDIUM | LiveKit transcription events from agent | LiveKit Agents emit transcription events from the STT pipeline. Display rolling user + agent transcript. Required for trust especially with early users who will scrutinise accuracy. |

### Differentiators (Competitive Advantage)

Features that match dAIly's core value ("life briefs you") and go beyond what any morning briefing or generic voice assistant app provides.

| Feature | Value Proposition | Complexity | Backend Dependency | Notes |
|---------|-------------------|------------|-------------------|-------|
| **Push-triggered briefing delivery** | Briefing arrives at the user's scheduled time as a notification — no manual launch | HIGH | APScheduler + APNs/FCM integration in FastAPI | Backend sends silent push at 05:30 (user-configured). iOS: PushKit or APNs background notification wakes app, app initiates LiveKit session. Android: FCM high-priority message. This is the "pocket companion" differentiator — briefing comes to you. Direct competitors (DayStart, Morning Call) require manual launch or phone call. |
| **Pre-connected audio buffering** | Session feels instant — no perceptible LiveKit connection delay when briefing starts | MEDIUM | LiveKit room pre-warm | LiveKit Swift SDK `preConnectAudio: true` captures audio before room connection completes. Pre-warm LiveKit room 30s before scheduled briefing push. Combine both for sub-second perceived startup. 1-day add once connection flow is stable. |
| **Action approval via voice** | "Send it" / "cancel" approves or rejects pending actions hands-free | MEDIUM | Existing LangGraph ACT-04 approval gate | LangGraph human-in-the-loop interrupt already exists. Mobile client surfaces pending approval as an overlay card + voice confirmation ("say 'send' to confirm"). No tap required. Matches "without touching a single app" core value. |
| **Conversational mode persistence** | User finishes briefing then asks follow-up questions without reconnecting | MEDIUM | LangGraph thread continuity (AsyncPostgresSaver) | LiveKit session stays alive post-briefing. User can say "reply to that email" without relaunching. Requires LiveKit session keepalive and LangGraph thread continuity — both are architectural constraints already in place. |
| **Adaptive briefing length (brief mode)** | Mobile users commuting or getting ready want a 90-second summary, not 5 minutes | LOW | Existing PERS-01 preference system | Simple toggle: "brief mode" vs "full briefing." Reuses existing user preference infrastructure. Mobile context (motion, time pressure) differs from desktop. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem obviously good but create meaningful problems at v1.4 scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Always-on wake word ("Hey Daily")** | Magical, hands-free, no button | Continuous mic = battery drain + privacy surface. Picovoice/Sensory add non-trivial integration complexity. False positives in ambient sound erode trust rapidly — competitors report this as a top user complaint. | Push notification at scheduled time is cleaner for a briefing product. Button or widget for ad hoc queries. Wake word is v2+ only if user demand clearly validates it. |
| **Voice cloning / custom agent voice** | Personalisation appeal | ElevenLabs voice cloning adds cost, latency, and a consent flow. Not differentiated at v1.4 — Cartesia Sonic-3 quality is already strong. Ships a distraction, not value. | 2–3 curated Cartesia voice options in settings. Low-effort personalisation without the complexity. |
| **Offline STT (on-device Whisper)** | Privacy appeal, works without network | No streaming support out of the box; CPU latency on mobile is 2–5x cloud; model download 40–150MB; significant battery impact. Contradicts sub-800ms latency target. | Deepgram Nova-3 via LiveKit plugin. Add on-device as a future privacy tier only if user demand is strong and acceptable latency is confirmed. |
| **Video / avatar agent** | Novelty, "like FaceTime with AI" | Video encoding/decoding adds battery drain, CPU load, and UI work. LiveKit supports it but it does not serve the voice briefing use case. | Voice-only with a polished audio visualiser (waveform or orb). Video is out of scope until v2+. |
| **Full in-app settings / preference editor** | Users want to configure everything on mobile | Duplicates the v2.0 web dashboard. Building it natively first doubles the work and creates two sources of truth. | Surface only mobile-critical settings: briefing time, voice selection, brief mode toggle. Full settings in v2.0 web dashboard. |
| **Multi-user / family mode** | Household appeal | Requires per-user token management, briefing isolation, and voice identification — scope explosion at v1.4. | Single-user per installation. Multiple accounts via separate installs. Revisit v2+. |
| **Background always-on listening (Siri-style ambient)** | True hands-free throughout the day | iOS restricts microphone in background without explicit background audio entitlement and an active audio session. Kills battery. Triggers App Store review flags. | Foreground voice sessions triggered by notification or button. Clear session start/end. |

---

## Feature Dependencies

```
[LiveKit Agents backend (MOB-03)]
    └──required by──> all mobile client voice features
    └──required by──> live transcription display
    └──required by──> real-time barge-in (ML turn detection)

[Session token endpoint (FastAPI)]
    └──required by──> iOS client connection (MOB-01)
    └──required by──> Android client connection (MOB-02)
    └──required by──> Desktop web fallback (MOB-04)

[Background audio continuation]
    └──required by──> push-triggered briefing delivery
    └──required by──> adaptive briefing length (brief plays through lock screen)

[Push-triggered briefing delivery]
    └──requires──> APNs certificate (Apple Developer account)
    └──requires──> FCM project (Firebase, Android)
    └──requires──> FastAPI APNs/FCM notification sender
    └──enhances──> pre-connected audio buffering

[Pre-connected audio buffering]
    └──requires──> session token flow
    └──enhances──> perceived startup latency

[Action approval via voice]
    └──requires──> existing LangGraph ACT-04 approval gate (already built)
    └──requires──> LiveKit session keepalive
    └──requires──> conversational mode persistence

[Conversational mode persistence]
    └──requires──> LiveKit session keepalive
    └──requires──> LangGraph thread continuity (AsyncPostgresSaver, already built)

[Live transcription display]
    └──requires──> LiveKit Agents backend (MOB-03)
    └──requires──> LiveKit transcription event subscription in client

[Hardware AEC]
    └──requires──> correct AVAudioSession flags (iOS)
    └──requires──> Oboe VOICE_COMMUNICATION preset (Android)
    └──provided by──> LiveKit SDK (automatic when local track published)

[Offline briefing playback — stretch]
    └──requires──> backend TTS pre-render to file
    └──requires──> local device file cache
    └──requires──> background download capability
    └──conflicts with──> online-only LiveKit session model
```

### Dependency Notes

- **MOB-03 is the critical path.** All mobile audio features depend on the LiveKit Agents backend being live and the LangGraph adapter wired. iOS and Android clients (MOB-01, MOB-02) can be scaffolded in parallel but cannot be end-to-end tested until MOB-03 is running.
- **Session token endpoint must exist before any client testing.** Without a real token endpoint, the LiveKit room handshake fails at the first connection attempt. FastAPI endpoint is a small addition — build it first.
- **Push notifications require platform certificates with non-trivial setup time.** APNs requires an Apple Developer account certificate + provisioning profile. FCM requires a Firebase project. Both have setup lead time — start before they're needed.
- **Hardware AEC is free on native but requires correct flags.** LiveKit Swift SDK handles AVAudioSession automatically. The key is ensuring `.voiceProcessing` input mode is active. On Android, `AAUDIO_INPUT_PRESET_VOICE_COMMUNICATION` must be set on the Oboe stream. Wrong flags = no AEC.
- **Action approval via voice wires into existing backend — no new backend work.** The LangGraph human-in-the-loop interrupt is already implemented (ACT-04). The mobile work is UI-only: surfacing the approval card and wiring voice confirmation.

---

## MVP Definition — v1.4

### Launch With (v1.4 core)

Minimum viable for a working native mobile voice experience. Validates the mobile-first architecture decision and the hardware AEC fix.

- [ ] **LiveKit Agents backend (MOB-03)** — VoicePipelineAgent wrapping existing LangGraph orchestrator; Deepgram + Cartesia plugins
- [ ] **Session token endpoint (FastAPI)** — `/livekit/token` returning short-lived JWT; authenticated against user session
- [ ] **Native iOS client (MOB-01)** — Swift, LiveKit Swift SDK, AVAudioEngine AEC, mic/speaker routing, connection state UI
- [ ] **Native Android client (MOB-02)** — Kotlin, LiveKit Android SDK, Oboe AEC, mic/speaker routing, connection state UI
- [ ] **Desktop web fallback (MOB-04)** — LiveKit web SDK; basic HTML/JS; functional, not polished
- [ ] **Real-time barge-in via LiveKit ML turn detection** — replaces `barge_in.py`; no silence timer
- [ ] **Live transcription display** — rolling user + agent transcript; trust signal for early users
- [ ] **Connection state feedback** — connecting / connected / reconnecting / disconnected; no silent failures
- [ ] **Mic permission handling** — graceful request flow with rationale on both platforms
- [ ] **Background audio continuation** — briefing plays when screen locks; required for morning use case
- [ ] **Client-direct STT/TTS via LiveKit plugins (MOB-05)** — Deepgram + Cartesia wired through LiveKit Agents pipeline

### Add After Validation (v1.4 polish / v1.5)

Add once the core voice loop is confirmed working on real devices with real hardware AEC.

- [ ] **Push-triggered briefing delivery** — APNs + FCM; high user value but significant setup; unblocks the "no manual launch" promise
- [ ] **Pre-connected audio buffering** — `preConnectAudio: true` on LiveKit; 1-day add once connection flow is stable
- [ ] **Adaptive briefing length (brief mode toggle)** — surfaces existing preference system; surfaces via settings screen
- [ ] **Action approval via voice** — wires existing LangGraph ACT-04 to mobile UI; approval card + voice confirmation

### Future Consideration (v2+)

- [ ] **Lock screen / widget controls** — high value but significant platform-specific work; defer until usage patterns validated
- [ ] **Offline briefing playback** — requires backend TTS pre-render pipeline change; v2.0 with web dashboard
- [ ] **Wake word ("Hey Daily")** — only if user research validates demand; battery + privacy implications must be evaluated first
- [ ] **Voice selection (Cartesia voices)** — settings screen feature; low effort but belongs with full settings in v2.0 web dashboard

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| LiveKit Agents backend (MOB-03) | HIGH | MEDIUM | P1 |
| Session token endpoint | HIGH | LOW | P1 |
| Native iOS client (MOB-01) | HIGH | HIGH | P1 |
| Native Android client (MOB-02) | HIGH | HIGH | P1 |
| Hardware AEC (OS-level, free on native) | HIGH | LOW | P1 |
| Real-time barge-in (LiveKit VAD) | HIGH | LOW | P1 |
| Background audio continuation | HIGH | MEDIUM | P1 |
| Connection state feedback | MEDIUM | LOW | P1 |
| Live transcription display | MEDIUM | MEDIUM | P1 |
| Mic permission handling | MEDIUM | LOW | P1 |
| Desktop web fallback (MOB-04) | MEDIUM | LOW | P1 |
| Client-direct STT/TTS plugins (MOB-05) | HIGH | LOW | P1 |
| Push-triggered briefing delivery | HIGH | HIGH | P2 |
| Pre-connected audio buffering | MEDIUM | LOW | P2 |
| Action approval via voice | HIGH | MEDIUM | P2 |
| Adaptive briefing length | MEDIUM | LOW | P2 |
| Lock screen / widget controls | HIGH | HIGH | P3 |
| Offline briefing playback | MEDIUM | HIGH | P3 |
| Wake word | LOW-MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.4 launch
- P2: Add after core voice loop validated; within v1.4 polish sprint
- P3: v2+ consideration

---

## Competitor Feature Analysis

| Feature | DayStart AI | Morning Call (AI alarm) | WakeMind | dAIly v1.4 approach |
|---------|-------------|------------------------|----------|---------------------|
| Briefing delivery trigger | Manual tap | AI phone call | Alarm-triggered | Push notification → auto LiveKit session |
| Voice interaction after briefing | None (audio only) | None (one-way call) | Limited | Full bidirectional conversation via LiveKit |
| Personalised content (email/calendar) | No (news/weather/markets) | No (news/weather) | Calendar + weather only | Full OAuth: Gmail, GCal, Outlook, Slack |
| Action execution | No | No | No | LangGraph approval-gated actions |
| Natural barge-in | No | No (phone call model) | No | LiveKit ML turn detection |
| Audio quality | Web-based | Carrier telephony | Unknown | Native iOS + Android, OS-level AEC |
| Live transcription | No | No | No | LiveKit transcription events |
| Background audio | No | N/A (phone call) | No | iOS background audio mode |

**Key finding:** Direct competitors are one-way audio briefing players. None offer bidirectional voice conversation after the briefing, none integrate email/calendar actions, and none use WebRTC for audio quality. dAIly v1.4 positions in a different product category — closer to a mobile-native voice agent than a morning briefing podcast.

---

## Sources

- [LiveKit Agents Documentation — Voice Agents](https://docs.livekit.io/agents/voice-agent/) — HIGH confidence
- [LiveKit agent-starter-swift GitHub](https://github.com/livekit-examples/agent-starter-swift) — HIGH confidence
- [LiveKit agent-starter-android GitHub](https://github.com/livekit-examples/agent-starter-android) — HIGH confidence
- [livekit-plugins-langchain PyPI](https://pypi.org/project/livekit-plugins-langchain/) — HIGH confidence
- [LiveKit MultimodalAgent vs VoicePipelineAgent](https://docs.livekit.io/agents/voice-agent/multimodal-agent/) — HIGH confidence
- [LiveKit — Build Voice AI That Actually Sounds Human (2026)](https://www.forasoft.com/blog/article/voice-ai-agents-livekit-guide) — MEDIUM confidence
- [DayStart AI App Store listing](https://apps.apple.com/us/app/daystart-ai-morning-briefing/id6751055528) — MEDIUM confidence
- [Morning Call AI App Store listing](https://apps.apple.com/us/app/morning-call-ai-alarm-clock/id6654901061) — MEDIUM confidence
- [WakeMind product page](https://wake-mind.com/) — MEDIUM confidence
- [Picovoice — 7 Voice AI Pitfalls 2025](https://picovoice.ai/blog/voice-ai-projects-pitfalls/) — MEDIUM confidence
- [SparkCo — Barge-in detection 2025](https://sparkco.ai/blog/master-voice-agent-barge-in-detection-handling) — MEDIUM confidence
- [Sensory — Wake Words on Mobile](https://sensory.com/sensory-brings-low-power-wake-words-to-mobile-apps/) — MEDIUM confidence
- [Speechmatics — Voice AI in 2026](https://www.speechmatics.com/company/articles-and-news/voice-ai-in-2026-9-numbers-that-signal-whats-next) — MEDIUM confidence
- [Apple Audio Session Programming Guide](https://developer.apple.com/library/archive/documentation/Audio/Conceptual/AudioSessionProgrammingGuide/AudioGuidelinesByAppType/AudioGuidelinesByAppType.html) — HIGH confidence
- [iOS Background Modes Guide — getstream.io](https://getstream.io/blog/ios-background-modes/) — MEDIUM confidence
- [Forasoft — AI Voice Recognition in Mobile Apps Complete Guide](https://forasoft.medium.com/ai-powered-voice-recognition-in-mobile-apps-the-complete-guide-to-building-voice-activated-apps-3c9c2a87c94f) — MEDIUM confidence

---
*Feature research for: dAIly v1.4 — Mobile Voice (LiveKit + native iOS + Android + web fallback)*
*Researched: 2026-04-28 (updated from 2026-04-05 original)*
