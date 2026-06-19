# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- ✅ **v1.1 Intelligence Layer** — Phases 7–12 (shipped 2026-04-18)
- ✅ **v1.2 Deployability Layer** — Phases 13–16 (shipped 2026-04-20)
- ✅ **v1.3 Voice Polish** — Phase 17 (shipped 2026-04-28)
- 📋 **v2.0 Mobile Voice** — Phases 18–20 (partially complete)
- 📋 **v2.1 TestFlight Ready** — Phases 21–23 (planned)
- 📋 **v2.2 Ecosystem Expansion** — Phases 24–28 (planned)

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

### Phase 18: LiveKit Backend Integration

**Goal:** Wire the LangGraph orchestrator into LiveKit Agents framework via livekit-plugins-langchain; replace the Python sounddevice voice loop with LiveKit room-based WebRTC transport.
**Plans:** TBD

- [ ] TBD

### Phase 19: Native iOS App

**Goal:** Swift + LiveKit iOS SDK, AVAudioEngine/AUVoiceIO hardware AEC, minimal voice UI (push-to-talk + auto VAD modes).
**Plans:** 5 plans — completed 2026-04-30

- [x] Phase 19: Native iOS App — completed 2026-04-30

- [x] Phase 20: Native Android App — Kotlin + LiveKit Android SDK, Oboe hardware AEC, minimal voice UI matching iOS (completed 2026-04-30)

---

### 📋 v2.1 TestFlight Ready (Planned)

### Phase 20.1: LiveKit Agent Worker (INSERTED)

**Goal:** Build the server-side LiveKit Agents worker that dispatches into a user's room on connect, delivers the briefing from Redis as TTS audio via LiveKit, and handles voice turns via the existing LangGraph orchestrator — making the iOS and Android apps fully functional end-to-end.
**Requirements:** WORKER-01, WORKER-02, WORKER-03, WORKER-04, WORKER-05
**Depends on:** Phase 19, Phase 20
**Plans:** 4/4 plans complete

Plans:
- [x] 20.1-01-PLAN.md — Install livekit-agents, scaffold worker package, identity parser
- [x] 20.1-02-PLAN.md — Per-user session bootstrap + LangGraph LLM bridge
- [x] 20.1-03-PLAN.md — Voice pipeline (STT/TTS/VAD) + briefing-on-connect entrypoint
- [x] 20.1-04-PLAN.md — Dockerize worker + end-to-end smoke test (checkpoint)

### Phase 21: Per-User Onboarding (Backend)

**Goal:** Backend signup flow, per-user OAuth credential storage (Google, Microsoft, Slack), magic-link auth, briefing schedule configuration API. Every new user can independently connect their own accounts via API — no shared credentials. Frontend UI is Phase 21.1.
**Plans:** 5/5 plans complete

Plans:
- [x] 21-01-PLAN.md — Add timezone column to BriefingConfig (model + Alembic migration)
- [x] 21-02-PLAN.md — Wave 0 test scaffolding (integrations, users, AASA, conftest fixtures)
- [x] 21-03-PLAN.md — Mobile OAuth integrations router (Google, Microsoft, Slack connect/callback)
- [x] 21-04-PLAN.md — Users router (integration status + briefing schedule preferences)
- [x] 21-05-PLAN.md — Wire routers into main.py, add /oauth/success to AASA, multi-user scheduler lifespan

### Phase 21.1: Per-User Onboarding UI (INSERTED)

**Goal:** Native iOS onboarding screens: welcome/signup, OAuth connect cards (Google, Microsoft, Slack), briefing schedule picker. Users complete full onboarding in-app without leaving to a browser (except OAuth deeplink redirect). Depends on Phase 21 backend.
**Plans:** 4/4 plans complete

Plans:
- [x] 21.1-01-PLAN.md — State + model layer (AppState extension, IntegrationState, IntegrationProvider, OAuthCallbackParser) + Wave 0 tests
- [x] 21.1-02-PLAN.md — AuthService extensions (getIntegrationConnectURL, openOAuthSession, savePreferences) with Bearer auth + tests
- [x] 21.1-03-PLAN.md — Onboarding leaf views (WelcomeView, IntegrationView, ScheduleView, CompletionView)
- [x] 21.1-04-PLAN.md — OnboardingView TabView + dAIlyApp routing + deep-link wiring (manual verification checkpoint)

### Phase 21.2: Bug Fixes and Polish (INSERTED)

**Goal:** Iron out all known bugs before production deploy. Speaking state indicator not surfacing on iOS while agent responds, first-load briefing not playing on session connect, and any other issues surfaced during onboarding testing. Zero known bugs before TestFlight.
**Plans:** 4 plans

Plans:
- [ ] 21.2-01-PLAN.md – Briefing trigger endpoint + iOS call + multi-provider audit (D-03, D-04)
- [ ] 21.2-02-PLAN.md – APPLE_TEAM_ID / AASA / Universal Links + Google OAuth test users (D-02, D-06)
- [ ] 21.2-03-PLAN.md – LiveKit connect_failed friendly errors + worker runbook (D-01)
- [ ] 21.2-04-PLAN.md – iOS UX polish: OTP keypad, page dots, link copy, mic permissions (D-05, D-07, D-08, D-09)

### Phase 21.3: UI Tidy-Up (INSERTED)

**Goal:** Visual polish pass across all iOS screens — consistency in spacing, typography, colours, and interaction states. Ensure the app looks intentional and production-ready before TestFlight, not like a prototype.
**Plans:** TBD

- [ ] TBD

### Phase 21.4: Test Coverage (INSERTED)

**Goal:** Comprehensive test suite for production readiness. Python backend: pytest for auth, integrations router, briefing pipeline, and new trigger endpoint. iOS unit tests: VoiceSession state machine, OAuthCallbackParser, AuthService. iOS onboarding flow and deep link routing tests. E2E smoke test covering pairing → onboarding → voice connect happy path. Target 80%+ backend coverage, all critical iOS state machines covered.
**Depends on:** Phase 21.2, Phase 21.3
**Plans:** 3/3 plans complete

Plans:
- [x] 21.4-01-PLAN.md — Backend OAuth + auth router coverage uplift to 80%+ per module, enforce coverage floor
- [x] 21.4-02-PLAN.md — iOS onboarding flow, deep-link routing, AppState routing tests
- [x] 21.4-03-PLAN.md — Backend E2E smoke test: pairing → onboarding → voice connect

### Phase 21.45: Architecture Consolidation (INSERTED)

**Goal:** Retire the half-finished voice migration and remove duplicated/premature surface BEFORE building Phase 21.5 on top of it. Closes the unresolved STATE.md decision ("keep Python voice loop alive as desktop fallback, or stub it") by deleting it. This is **Option A** from the 2026-06-19 integration-friction review (`.planning/reviews/2026-06-19-integration-friction-review.md`). No user-facing feature is removed — only duplicated implementations and premature infra.
**Depends on:** Phase 21.4
**Plans:** 2/5 plans executed

Plans:
- [x] 21.45-01-PLAN.md — Voice-path consolidation: import-gate, delete `src/daily/voice/`, remove `daily voice` CLI command, collapse to AsyncPostgresSaver (wave 1)
- [x] 21.45-02-PLAN.md — Config drift fix: regenerate `.env.example` (24 vars) + fail-fast required-var validation in config.py (wave 1)
- [ ] 21.45-03-PLAN.md — Cleanup + decision: delete 199 `* 2.*` iCloud duplicates, record Android-freeze in ROADMAP/STATE (wave 1)
- [ ] 21.45-04-PLAN.md — iOS hardening: token-refresh exponential backoff + retry affordance, scenePhase pause/reconnect (wave 1, has checkpoint)
- [ ] 21.45-05-PLAN.md — E2E smoke test: extend pairing→voice smoke with agent greeting + approval round-trip on the real graph (wave 2, depends on 21.45-01)

Scope (high-ROI 20%):
- [ ] Delete `src/daily/voice/` (1,316 LOC local CLI audio pipeline) + the `cli.py` voice command; unify all voice on the `worker/` livekit-agents path; collapse to a single checkpointer (`AsyncPostgresSaver`). Confirm nothing in the production mobile flow depends on `voice/` before deleting.
- [ ] Add one E2E smoke test for the production mobile voice path (pair → `/livekit/token` → LiveKit room → worker agent greeting → one approval round-trip) so live-session bugs become CI signal, not manual whack-a-mole.
- [ ] Fix config drift: regenerate `.env.example` from the actual 25 required vars (10 currently documented) + startup validation that fails fast on missing required env.
- [ ] iOS hardening: token-refresh exponential backoff + user-facing retry; iOS `scenePhase` lifecycle handling so backgrounding/network-drop don't silently kill the LiveKit session.
- [ ] Decisions recorded: freeze Android (iOS-only for TestFlight); remove the ~199 `* 2.*` iCloud sync-conflict duplicate files.

**Out of scope (Option B / later):** LiveKit Cloud migration + drop coturn, flatten LangGraph ceremony, extract marketing/content/automation to its own repo, api+worker consolidation. Captured as follow-ups.

### Phase 21.5: Adaptive Learning and Memory (INSERTED)

**Goal:** Make dAIly actually learn about the user over time — the core product promise. Voice-expressed preference detection and persistence ("make it shorter", "skip weather", "I don't use Slack"), briefing adapting to stored preferences on next run, signal-driven ranking using already-captured skip/expand/correction signals to re-order briefing sections, cross-session memory via mem0 (extract facts from conversations and inject into future briefing context).
**Depends on:** Phase 21.45 (build the differentiator on the consolidated base, not the dual-path one)
**Plans:** TBD

- [ ] TBD (run /gsd-plan-phase 21.5 to break down)

### Phase 22: Apple Integrations

**Goal:** iCloud Mail + Apple Calendar via EventKit/CloudKit. Alternative to Google for iOS users. Also covers iCloud contacts.
**Plans:** TBD

- [ ] TBD

### Phase 23: Production Backend Deploy

**Goal:** Stable public backend URL, multi-user hardening, SSL/TLS, secrets management, environment config for real users. Backend runs independently of any dev machine.
**Plans:** TBD

- [ ] TBD

---

### 📋 v2.2 Ecosystem Expansion (Planned)

### Phase 24: Desktop Web Fallback

**Goal:** LiveKit web SDK in a minimal web app; replaces current Python sounddevice loop for macOS users; WebRTC AEC handles echo.
**Plans:** TBD

- [ ] TBD

### Phase 25: Developer Pack

**Goal:** GitHub (PRs, issues, CI status), Linear (tasks/issues), Hacker News (top stories); briefing gains a "work tools" section.
**Plans:** TBD

- [ ] TBD

### Phase 26: Knowledge Pack

**Goal:** Notion (pages, tasks, meetings), Google Maps Routes (commute ETA); deep-link action layer to create Notion tasks via voice.
**Plans:** TBD

- [ ] TBD

### Phase 27: Operator Pack

**Goal:** WhatsApp Business (via Twilio), PagerDuty (incidents/on-call), Vercel (deploy status); real-time alerting triggers.
**Plans:** TBD

- [ ] TBD

### Phase 28: Finance Pack

**Goal:** Stripe (MRR, payment failures), Brex/Mercury (spend, cash position); morning briefing gains financial digest section.
**Plans:** TBD

- [ ] TBD

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
| 18. LiveKit Backend | v2.0 | 3/3 | ✅ Complete (agent missing) | 2026-04-29 |
| 19. Native iOS App | v2.0 | 5/5 | ✅ Complete | 2026-04-30 |
| 20. Native Android App | v2.0 | 5/5 | ✅ Complete | 2026-04-30 |
| 21. Per-User Onboarding | v2.1 | 5/5 | ✅ Complete | 2026-05-01 |
| 21.1. Per-User Onboarding UI | v2.1 | 4/4 | ✅ Complete | 2026-05-10 |
| 21.2. Bug Fixes and Polish | v2.1 | 4/4 | ✅ Complete | 2026-05-12 |
| 21.3. UI Tidy-Up | v2.1 | 1/1 | ✅ Complete | 2026-05-12 |
| 21.4. Test Coverage | v2.1 | 3/3 | ✅ Complete | 2026-05-11 |
| 21.45. Architecture Consolidation | v2.1 | 2/5 | In Progress|  |
| 21.5. Adaptive Learning and Memory | v2.1 | — | ○ Not started | — |
| 22. Apple Integrations | v2.1 | — | ○ Not started | — |
| 23. Production Backend Deploy | v2.1 | — | ○ Not started | — |
| 24. Desktop Web Fallback | v2.2 | — | ○ Not started | — |
| 25. Developer Pack | v2.2 | — | ○ Not started | — |
| 26. Knowledge Pack | v2.2 | — | ○ Not started | — |
| 27. Operator Pack | v2.2 | — | ○ Not started | — |
| 28. Finance Pack | v2.2 | — | ○ Not started | — |

## Backlog

### Phase 999.1: Voice-First Onboarding (BACKLOG)

**Goal:** Make the entire app setup/onboarding experience voice-driven (or offer it as an option). Instead of menus and clicking, the user has a conversation in the same style as the rest of dAIly — that conversation IS the setup. Covers connecting integrations, setting preferences, and configuring the briefing. Should feel like talking to the assistant from day one.
**Requirements:** TBD
**Plans:** 0 plans

- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Deep Customization (BACKLOG)

**Goal:** Everything needs to be highly customizable and easy to configure. Briefing length, data sources, news preferences, three-tier privacy/security options, and as many other layers as possible. The customization surface must be discoverable and easy — not buried. May warrant its own milestone given scope.
**Requirements:** TBD
**Plans:** 0 plans

- [ ] TBD (promote with /gsd-review-backlog when ready)
