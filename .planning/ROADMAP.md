# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- ✅ **v1.1 Intelligence Layer** — Phases 7–12 (shipped 2026-04-18)
- 🔄 **v1.2 Deployability Layer** — Phases 13–15 (in progress)

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

### v1.2 Deployability Layer

- [x] **Phase 13: Signal Capture** — Wire skip and re_request signals end-to-end into the adaptive ranker (completed 2026-04-18)
- [ ] **Phase 14: Observability** — Structured logging, configurable log level, health endpoint, and queryable metrics
- [ ] **Phase 15: Deployment** — Docker Compose stack, env var template, and VPS production guide

## Phase Details

### Phase 13: Signal Capture
**Goal**: The adaptive ranker learns from all three interaction signal types — not just expand
**Depends on**: Nothing (v1.2 start; adaptive ranker from Phase 8 is already in place)
**Requirements**: SIG-01, SIG-02, SIG-03
**Success Criteria** (what must be TRUE):
  1. When a user skips a briefing item, a skip signal is written to the signal table
  2. When a user asks to repeat or clarify a briefing item, a re_request signal is written to the signal table
  3. The adaptive ranker reads skip and re_request signals alongside expand when computing decay-adjusted scores — items skipped repeatedly rank lower over time
**Plans:** 3/3 plans complete
Plans:
- [x] 13-01-PLAN.md — Adaptive ranker TDD (get_sender_multipliers with decay formula)
- [x] 13-02-PLAN.md — Item tracking infrastructure (BriefingItem model, pipeline cache, session init)
- [x] 13-03-PLAN.md — Skip and re_request nodes + voice loop integration

### Phase 14: Observability
**Goal**: Every module emits structured logs and the system exposes its health and key metrics without touching code
**Depends on**: Phase 13
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. Every log line across the codebase is valid JSON with timestamp, level, module, message, and context fields
  2. Setting LOG_LEVEL=DEBUG in the environment increases verbosity; setting LOG_LEVEL=WARNING suppresses info-level output — no code change required
  3. GET /health returns 200 with a structured body showing DB connectivity, Redis connectivity, and scheduler state
  4. Briefing generation latency, signal counts by type, and memory store size are queryable (via the health endpoint or a dedicated metrics route)
**Plans:** 2 plans
Plans:
- [ ] 14-01-PLAN.md — Structured logging infrastructure (JSONFormatter, ContextAdapter, LOG_LEVEL)
- [ ] 14-02-PLAN.md — Health and metrics endpoints (/health, /metrics, pipeline latency)

### Phase 15: Deployment
**Goal**: Any developer can clone the repo, set environment variables, and run the full stack — locally or on a VPS
**Depends on**: Phase 14
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03
**Success Criteria** (what must be TRUE):
  1. Running docker compose up from a fresh clone starts the app, Postgres, and Redis with no manual steps beyond copying .env.example
  2. .env.example documents every required environment variable with a description and placeholder — no secrets are committed to the repo
  3. A production guide exists that walks through single-host VPS deployment: systemd or Docker, reverse proxy (nginx/caddy), and TLS termination
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 5/5 | Complete | 2026-04-06 |
| 2. Briefing Pipeline | v1.0 | 5/5 | Complete | 2026-04-07 |
| 3. Orchestrator | v1.0 | 4/4 | Complete | 2026-04-10 |
| 4. Action Layer | v1.0 | 3/3 | Complete | 2026-04-12 |
| 5. Voice Interface | v1.0 | 4/4 | Complete | 2026-04-13 |
| 6. Wire Preferences | v1.0 | 1/1 | Complete | 2026-04-14 |
| 7. Tech Debt Fixes | v1.1 | 3/3 | Complete | 2026-04-16 |
| 8. Adaptive Ranker | v1.1 | 4/4 | Complete | 2026-04-16 |
| 9. Cross-Session Memory | v1.1 | 4/4 | Complete | 2026-04-17 |
| 10. Memory Transparency | v1.1 | 2/2 | Complete | 2026-04-17 |
| 11. Trusted Actions | v1.1 | 2/2 | Complete | 2026-04-18 |
| 12. Conversational Flow | v1.1 | 2/2 | Complete | 2026-04-18 |
| 13. Signal Capture | v1.2 | 3/3 | Complete   | 2026-04-18 |
| 14. Observability | v1.2 | 0/2 | Not started | - |
| 15. Deployment | v1.2 | 0/? | Not started | - |
