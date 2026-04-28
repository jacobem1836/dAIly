# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- ✅ **v1.1 Intelligence Layer** — Phases 7–12 (shipped 2026-04-18)
- ✅ **v1.2 Deployability Layer** — Phases 13–16 (shipped 2026-04-20)
- ✅ **v1.3 Voice Polish** — Phase 17 (shipped 2026-04-28)
- 🔄 **v1.4 Mobile Voice** — Phases 18–22 (in progress)
- 📋 **v2.0 Ecosystem Expansion** — Phases 23–26 (planned)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–6) — SHIPPED 2026-04-14</summary>

- [x] Phase 1: Foundation (5/5 plans) — completed 2026-04-06
- [x] Phase 2: Briefing Pipeline (5/5 plans) — completed 2026-04-07
- [x] Phase 3: Orchestrator (4/4 plans) — completed 2026-04-10
- [x] Phase 4: Action Layer (3/3 plans) — completed 2026-04-12
- [x] Phase 5: Voice Interface (4/4 plans) — completed 2026-04-13
- [x] Phase 6: Wire Preferences to Briefing (1/1 plan) — completed 2026-04-14

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.1 Intelligence Layer (Phases 7–12) — SHIPPED 2026-04-18</summary>

- [x] Phase 7: Tech Debt Fixes (3/3 plans) — completed 2026-04-16
- [x] Phase 8: Adaptive Ranker (4/4 plans) — completed 2026-04-16
- [x] Phase 9: Cross-Session Memory (4/4 plans) — completed 2026-04-17
- [x] Phase 10: Memory Transparency (2/2 plans) — completed 2026-04-17
- [x] Phase 11: Trusted Actions (2/2 plans) — completed 2026-04-18
- [x] Phase 12: Conversational Flow (2/2 plans) — completed 2026-04-18

See `.planning/milestones/v1.1-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.2 Deployability Layer (Phases 13–16) — SHIPPED 2026-04-20</summary>

- [x] Phase 13: Signal Capture (3/3 plans) — completed 2026-04-18
- [x] Phase 14: Observability (2/2 plans) — completed 2026-04-19
- [x] Phase 15: Deployment (3/3 plans) — completed 2026-04-19
- [x] Phase 16: Milestone Closeout (1/1 plan) — completed 2026-04-19

See `.planning/milestones/v1.2-ROADMAP.md` for full phase details.

</details>

<details>
<summary>✅ v1.3 Voice Polish — Phase 17 — SHIPPED 2026-04-28</summary>

- [x] Phase 17: Voice Polish (4/4 plans) — completed 2026-04-28

**What shipped:** Graceful TTS fade-out (completes current audio chunk on barge-in), mic-mute echo suppression (500ms), barge-in safety window (600ms asyncio timer before committing interrupt), backchannel detection (swallows "yeah/right/got it" without stopping TTS), streaming LLM→TTS bridge (sentence-boundary chunking, lower TTFB). Structural AEC limitation on macOS documented — solved by mobile.

**Note:** Structurally unsolvable AEC issue on macOS (no hardware echo cancellation) closed as won't-fix — the mobile architecture (Phase 18+) solves it at the OS layer.

</details>

### 🔄 v1.4 Mobile Voice (Active)

- [ ] **Phase 18: LiveKit Infrastructure + Token Endpoint** — self-hosted LiveKit server with TURN support; `POST /livekit/token` JWT endpoint authenticated against existing session
- [ ] **Phase 19: LiveKit Agent Worker** — LangGraph orchestrator wrapped via LLMAdapter; Deepgram STT + Cartesia TTS via LiveKit plugins; APScheduler continuity verified; hard cutover from `voice/` module
- [ ] **Phase 20: iOS Native Client** — Swift + LiveKit iOS SDK; AVAudioEngine hardware AEC; background audio; live transcript; connection state UI; microphone permission flow
- [ ] **Phase 21: Android Native Client** — Kotlin + LiveKit Android SDK; Oboe WebRTC AEC3; foreground service for background audio; live transcript; connection state UI; microphone permission flow
- [ ] **Phase 22: Desktop Web Fallback + Push Notifications** — LiveKit web SDK in minimal web app; WebRTC AEC; APNs (iOS) and FCM (Android) push at configured briefing time

### 📋 v2.0 Ecosystem Expansion (Planned)

- [ ] Phase 23: Developer Pack — GitHub (PRs, issues, CI status), Linear (tasks/issues), Hacker News (top stories); briefing gains a "work tools" section
- [ ] Phase 24: Knowledge Pack — Notion (pages, tasks, meetings), Google Maps Routes (commute ETA); deep-link action layer to create Notion tasks via voice
- [ ] Phase 25: Operator Pack — WhatsApp Business (via Twilio), PagerDuty (incidents/on-call), Vercel (deploy status); real-time alerting triggers
- [ ] Phase 26: Finance Pack — Stripe (MRR, payment failures), Brex/Mercury (spend, cash position); morning briefing gains financial digest section

## Phase Details

### Phase 18: LiveKit Infrastructure + Token Endpoint
**Goal**: User can connect to a live LiveKit room and receive a valid session token from the backend
**Depends on**: Phase 17 (existing backend)
**Requirements**: INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):
  1. User can connect a LiveKit client to the self-hosted LiveKit server through a TURN relay without firewall issues
  2. User receives a short-lived JWT from `POST /livekit/token` using their existing authenticated session — no separate login
  3. The token endpoint rejects unauthenticated requests with a 401
  4. The LiveKit server and TURN relay are reachable from outside localhost (staging or VPS)
**Plans**: TBD

### Phase 19: LiveKit Agent Worker
**Goal**: User's voice session is handled end-to-end by a LiveKit Agent that drives the existing LangGraph orchestrator — old voice/ module is gone
**Depends on**: Phase 18
**Requirements**: INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):
  1. User can complete a full voice session (briefing delivery + follow-up question) via a LiveKit room with no Python sounddevice involvement
  2. Deepgram STT and Cartesia TTS function through LiveKit plugins — same providers, new plumbing — with no regression in transcription quality
  3. The scheduled morning briefing precomputes and writes to Redis on schedule without interruption after the migration
  4. The `voice/` directory (stt.py, tts.py, barge_in.py, loop.py) is deleted and the feature flag for the old loop is removed — no dead code remains
**Plans**: TBD

### Phase 20: iOS Native Client
**Goal**: User can run a complete voice session — briefing and follow-up — from their iPhone with hardware-level echo cancellation
**Depends on**: Phase 19
**Requirements**: IOS-01, IOS-02, IOS-03, IOS-04, IOS-05
**Success Criteria** (what must be TRUE):
  1. User can tap once to start a voice session from the iOS app and hear the briefing without echo, even through the built-in speaker
  2. User can lock the screen during the briefing and audio continues uninterrupted
  3. User sees a live scrolling transcript of the assistant's speech and their own detected utterances as the session progresses
  4. User sees a clearly labelled connection state (connecting / connected / reconnecting / error) at all times during a session
  5. User is prompted for microphone permission with a plain-language rationale before their first session, and the app functions gracefully if permission is denied
**Plans**: TBD
**UI hint**: yes

### Phase 21: Android Native Client
**Goal**: User can run a complete voice session from their Android device with hardware-level echo cancellation via Oboe
**Depends on**: Phase 19
**Requirements**: AND-01, AND-02, AND-03, AND-04, AND-05
**Success Criteria** (what must be TRUE):
  1. User can tap once to start a voice session from the Android app and hear the briefing without echo through the built-in speaker
  2. User can lock the screen during the briefing and audio continues via foreground service without interruption
  3. User sees a live scrolling transcript of the assistant's speech and their own detected utterances as the session progresses
  4. User sees a clearly labelled connection state (connecting / connected / reconnecting / error) at all times during a session
  5. User is prompted for microphone permission with a plain-language rationale before their first session, and the app functions gracefully if permission is denied
**Plans**: TBD
**UI hint**: yes

### Phase 22: Desktop Web Fallback + Push Notifications
**Goal**: User can start a voice session from a desktop browser, and receive a push notification at their configured briefing time on iOS and Android
**Depends on**: Phase 20, Phase 21
**Requirements**: WEB-01, PUSH-01
**Success Criteria** (what must be TRUE):
  1. User can open a browser on desktop, click to connect, and complete a voice session via the LiveKit web SDK with WebRTC browser AEC — no plugin required
  2. User receives a push notification on their iOS device at the scheduled briefing time that, when tapped, opens the app and starts the session
  3. User receives a push notification on their Android device at the scheduled briefing time that, when tapped, opens the app and starts the session
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Foundation | v1.0 | 5/5 | ✅ Complete | 2026-04-06 |
| 2. Briefing Pipeline | v1.0 | 5/5 | ✅ Complete | 2026-04-07 |
| 3. Orchestrator | v1.0 | 4/4 | ✅ Complete | 2026-04-10 |
| 4. Action Layer | v1.0 | 3/3 | ✅ Complete | 2026-04-12 |
| 5. Voice Interface | v1.0 | 4/4 | ✅ Complete | 2026-04-13 |
| 6. Wire Preferences | v1.0 | 1/1 | ✅ Complete | 2026-04-14 |
| 7. Tech Debt Fixes | v1.1 | 3/3 | ✅ Complete | 2026-04-16 |
| 8. Adaptive Ranker | v1.1 | 4/4 | ✅ Complete | 2026-04-16 |
| 9. Cross-Session Memory | v1.1 | 4/4 | ✅ Complete | 2026-04-17 |
| 10. Memory Transparency | v1.1 | 2/2 | ✅ Complete | 2026-04-17 |
| 11. Trusted Actions | v1.1 | 2/2 | ✅ Complete | 2026-04-18 |
| 12. Conversational Flow | v1.1 | 2/2 | ✅ Complete | 2026-04-18 |
| 13. Signal Capture | v1.2 | 3/3 | ✅ Complete | 2026-04-18 |
| 14. Observability | v1.2 | 2/2 | ✅ Complete | 2026-04-19 |
| 15. Deployment | v1.2 | 3/3 | ✅ Complete | 2026-04-19 |
| 16. Milestone Closeout | v1.2 | 1/1 | ✅ Complete | 2026-04-19 |
| 17. Voice Polish | v1.3 | 4/4 | ✅ Complete | 2026-04-28 |
| 18. LiveKit Infrastructure + Token Endpoint | v1.4 | 0/? | ○ Not started | — |
| 19. LiveKit Agent Worker | v1.4 | 0/? | ○ Not started | — |
| 20. iOS Native Client | v1.4 | 0/? | ○ Not started | — |
| 21. Android Native Client | v1.4 | 0/? | ○ Not started | — |
| 22. Desktop Web Fallback + Push Notifications | v1.4 | 0/? | ○ Not started | — |
| 23. Developer Pack | v2.0 | — | ○ Not started | — |
| 24. Knowledge Pack | v2.0 | — | ○ Not started | — |
| 25. Operator Pack | v2.0 | — | ○ Not started | — |
| 26. Finance Pack | v2.0 | — | ○ Not started | — |

## Backlog

### Phase 999.1: Voice-First Onboarding (BACKLOG)

**Goal:** Make the entire app setup/onboarding experience voice-driven (or offer it as an option). Instead of menus and clicking, the user has a conversation in the same style as the rest of dAIly — that conversation IS the setup. Covers connecting integrations, setting preferences, and configuring the briefing. Should feel like talking to the assistant from day one.
**Requirements:** TBD
**Plans:** 0 plans

- [ ] TBD (promote with /gsd-review-backlog when ready)

---

### Phase 999.2: Deep Customization (BACKLOG)

**Goal:** Everything needs to be highly customizable and easy to configure. Briefing length, data sources, news preferences, three-tier privacy/security options, and as many other layers as possible. The customization surface must be discoverable and easy — not buried. May warrant its own milestone given scope.
**Requirements:** TBD
**Plans:** 0 plans

- [ ] TBD (promote with /gsd-review-backlog when ready)
