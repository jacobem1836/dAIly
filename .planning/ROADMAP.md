# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- ✅ **v1.1 Intelligence Layer** — Phases 7–12 (shipped 2026-04-18)
- ✅ **v1.2 Deployability Layer** — Phases 13–16 (shipped 2026-04-20)
- ✅ **v1.3 Voice Polish** — Phase 17 (shipped 2026-04-28)
- 📋 **v2.0 Mobile Voice** — Phases 18–21 (planned)
- 📋 **v2.1 Ecosystem Expansion** — Phases 22–25 (planned)

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

### 📋 v2.0 Mobile Voice (Next)

- [x] Phase 18: LiveKit Backend Integration — wire LangGraph orchestrator into LiveKit Agents framework via livekit-plugins-langchain; replace Python sounddevice voice loop with LiveKit room-based transport (completed 2026-04-29)
- [ ] Phase 19: Native iOS App — Swift + LiveKit iOS SDK, AVAudioEngine/AUVoiceIO hardware AEC, minimal voice UI (push-to-talk + auto VAD modes)
- [ ] Phase 20: Native Android App — Kotlin + LiveKit Android SDK, Oboe hardware AEC, minimal voice UI matching iOS
- [ ] Phase 21: Desktop Web Fallback — LiveKit web SDK in a minimal web app; replaces current Python sounddevice loop for macOS users; WebRTC AEC handles echo

### Phase 19: Native iOS App

**Goal:** Build a native iOS app in Swift using the LiveKit iOS SDK with AVAudioEngine/AUVoiceIO hardware AEC, providing push-to-talk and auto VAD voice modes for the dAIly briefing experience.

**Requirements:** MOB-01

**Success Criteria:**
1. iOS app connects to LiveKit room and authenticates via token endpoint
2. Push-to-talk and auto VAD voice modes both functional
3. AVAudioEngine/AUVoiceIO hardware AEC eliminates echo without software DSP
4. Daily briefing playback works end-to-end on device
5. App launches and connects reliably in under 3 seconds

**Canonical refs:**
- `.planning/phases/18-livekit-infrastructure/18-CONTEXT.md` — LiveKit token endpoint, room naming
- `.planning/PROJECT.md` — MOB-01 requirement, mobile-first architecture decision

**Plans:** 5 plans

Plans:
- [ ] 19-01-PLAN.md — Backend prerequisites: POST /auth/pair/send-link (Resend) + AASA endpoint
- [ ] 19-02-PLAN.md — Xcode project scaffold + LiveKit SPM dep + KeychainStore
- [ ] 19-03-PLAN.md — Magic link pairing flow: AuthService, PairingView, Universal Link, TokenRefresher
- [ ] 19-04-PLAN.md — LiveKit voice session, VoiceView UI (auto VAD; PTT debug-only)
- [ ] 19-05-PLAN.md — Integration polish + VALIDATION.md + manual device test checkpoint

---

### Phase 20: Native Android App

**Goal:** Build a native Android app in Kotlin using the LiveKit Android SDK with Oboe hardware AEC, matching the iOS voice UI.

**Requirements:** MOB-02

**Success Criteria:**
1. Android app connects to LiveKit room with token authentication
2. Push-to-talk and auto VAD voice modes functional
3. Oboe hardware AEC eliminates echo
4. Daily briefing playback works end-to-end on device

---

### Phase 21: Desktop Web Fallback

**Goal:** Minimal web app using LiveKit web SDK to replace the Python sounddevice voice loop for macOS users; WebRTC AEC handles echo.

**Requirements:** MOB-04

**Success Criteria:**
1. Web app connects to LiveKit room via browser WebRTC
2. Briefing plays back correctly
3. Voice input (VAD) functional in browser
4. WebRTC AEC handles echo without additional DSP

---

### 📋 v2.1 Ecosystem Expansion (Planned)

- [ ] Phase 22: Developer Pack — GitHub (PRs, issues, CI status), Linear (tasks/issues), Hacker News (top stories); briefing gains a "work tools" section
- [ ] Phase 23: Knowledge Pack — Notion (pages, tasks, meetings), Google Maps Routes (commute ETA); deep-link action layer to create Notion tasks via voice
- [ ] Phase 24: Operator Pack — WhatsApp Business (via Twilio), PagerDuty (incidents/on-call), Vercel (deploy status); real-time alerting triggers
- [ ] Phase 25: Finance Pack — Stripe (MRR, payment failures), Brex/Mercury (spend, cash position); morning briefing gains financial digest section

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
| 18. LiveKit Backend | v2.0 | 3/2 | Complete    | 2026-04-29 |
| 19. Native iOS App | v2.0 | 0/5 | Planned | — |
| 20. Native Android App | v2.0 | — | ○ Not started | — |
| 21. Desktop Web Fallback | v2.0 | — | ○ Not started | — |
| 22. Developer Pack | v2.1 | — | ○ Not started | — |
| 23. Knowledge Pack | v2.1 | — | ○ Not started | — |
| 24. Operator Pack | v2.1 | — | ○ Not started | — |
| 25. Finance Pack | v2.1 | — | ○ Not started | — |

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
