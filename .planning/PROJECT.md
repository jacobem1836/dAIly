# dAIly

## What This Is

A voice-first AI personal assistant that proactively synthesises a user's digital life into an intelligent daily briefing. It acts as a semi-autonomous operator for communication, scheduling, and decision support — combining executive briefing, conversational assistant, and action-taking agent. Built backend-first, targeting busy professionals and operators who want their life to brief them rather than manually checking multiple apps.

v1.0 shipped a complete backend: OAuth integrations (Gmail, GCal, Outlook, Slack), precomputed briefing pipeline, LangGraph orchestrator, approval-gated action layer, full voice session loop, and user preferences applied end-to-end.

v1.1 added the intelligence layer: the briefing now learns the user. Adaptive ranking replaces heuristics, pgvector-powered memory persists context across days, users can inspect and manage what the system knows, action autonomy is configurable, and the conversation handles interrupts and tone adaptation natively.

v1.2 made the stack deployable: all three signal types (skip, re_request, expand) wire into the adaptive ranker, structured JSON logging covers all modules, `/health` and `/metrics` endpoints expose system state, and docker-compose brings up the full stack from a fresh clone.

## Core Value

The briefing always delivers: every morning, the user gets a prioritised, conversational summary of what matters — without touching a single app. And over time, it gets better at knowing what matters.

## Milestone Plan

| Milestone | Scope | Status |
|-----------|-------|--------|
| **v1.0 — Core Backend** | OAuth integrations, briefing pipeline, orchestrator, action layer, voice interface, preferences | ✅ Shipped 2026-04-14 |
| **v1.1 — Intelligence Layer** | Adaptive prioritisation, cross-session memory, memory transparency, trusted actions, conversational flow | ✅ Shipped 2026-04-18 |
| **v1.2 — Deployability Layer** | Signal capture, observability, Docker deployment | ✅ Shipped 2026-04-20 |
| **v2.0 — Ecosystem Expansion** | Travel, finance, health, smart home, document platforms, web dashboard | Planned |

## Requirements

### Validated (v1.0 + v1.1)

- ✓ BRIEF-01: System precomputes morning briefing overnight, caches for instant delivery — v1.0
- ✓ BRIEF-02: User can configure briefing precompute schedule time — v1.0 (Plan 02-05)
- ✓ BRIEF-03: Email ingestion ranked by heuristic priority (sender weight, deadline keywords, thread recency) — v1.0
- ✓ BRIEF-04: Calendar events (today + 48h) with conflict detection — v1.0
- ✓ BRIEF-05: Slack mentions, DMs, priority channels — v1.0
- ✓ BRIEF-06: LLM narrative generated from pre-ranked, pre-summarised context only — v1.0
- ✓ BRIEF-07: Thread summarisation on demand ("summarise that email chain") — v1.0
- ✓ VOICE-01: TTS streams sentence-by-sentence (Cartesia Sonic-3 WebSocket) — v1.0
- ✓ VOICE-02: STT with interim results (Deepgram Nova-3 WebSocket) — v1.0
- ✓ VOICE-03: E2E follow-up latency <1.5s; briefing delivery <1s from cache — v1.0
- ✓ VOICE-04: Barge-in detection via VAD (asyncio stop_event coordination) — v1.0
- ✓ VOICE-05: Follow-up questions with session context (AsyncPostgresSaver) — v1.0
- ✓ INTG-01: Gmail OAuth 2.0 — minimum scopes, read email + draft/send — v1.0
- ✓ INTG-02: Google Calendar OAuth 2.0 — read events + create/update — v1.0
- ✓ INTG-03: Microsoft Outlook/Exchange via Microsoft Graph OAuth — v1.0
- ✓ INTG-04: Slack OAuth 2.0 as internal custom app — v1.0
- ✓ INTG-05: Proactive background token refresh before briefing jobs — v1.0
- ✓ ACT-01: Draft email reply via LLM instruction — v1.0
- ✓ ACT-02: Draft Slack message reply via LLM instruction — v1.0
- ✓ ACT-03: Create/reschedule calendar event via LLM instruction — v1.0
- ✓ ACT-04: All external actions require explicit user approval — no bypass path — v1.0
- ✓ ACT-05: Every action logged with timestamp, type, target, content summary, approval status, outcome — v1.0
- ✓ ACT-06: Executor validates recipient, content type, and scope before dispatch — v1.0
- ✓ ACT-07: User can configure autonomy level (suggest-only / approve-per-action / trusted-auto) — v1.1
- ✓ PERS-01: User profile stores preferences (tone, briefing length, category order); applied to scheduled briefing — v1.0 (Phase 6)
- ✓ PERS-02: Interaction signals captured (skips, corrections, re-requests) and stored — v1.0
- ✓ PERS-03: Heuristic defaults at cold start (sender importance, deadline keywords, thread recency) — v1.0
- ✓ SEC-01: OAuth tokens encrypted at rest (AES-256-GCM); never exposed to frontend, logs, or LLM — v1.0
- ✓ SEC-02: Pre-filter/redaction layer sanitises external data before LLM — v1.0
- ✓ SEC-03: Each integration requests only minimum required OAuth scopes — v1.0
- ✓ SEC-04: Raw email/message bodies not stored long-term — only summaries and metadata — v1.0
- ✓ SEC-05: LLM outputs are intents only; backend orchestrator validates and dispatches — v1.0
- ✓ INTEL-01: Priority ranking learns from signal data to replace heuristic defaults with personalised scoring — v1.1
- ✓ INTEL-02: Cross-session conversational memory persists context across days (pgvector + structured user profile extraction) — v1.1
- ✓ MEM-01: User can inspect what the system knows about them ("What do you know about me?") — v1.1
- ✓ MEM-02: User can edit or delete specific memory entries — v1.1
- ✓ MEM-03: User can disable learning or reset all memory — v1.1
- ✓ CONV-01: Briefing supports natural mid-session interruption without breaking conversation state — v1.1
- ✓ CONV-02: Fluid switching between briefing, discussion, and action modes — v1.1
- ✓ CONV-03: Adaptive tone — system adjusts formality and verbosity based on context signals — v1.1
- ✓ FIX-01: RFC 2822 address normalization — WEIGHT_DIRECT scoring path fires correctly — v1.1
- ✓ FIX-02: Slack pagination — cursor-based multi-page ingestion — v1.1
- ✓ FIX-03: Real message ID extraction from briefing metadata in summarise_thread_node — v1.1
- ✓ SIG-01: Skip signals captured and stored; adaptive ranker ingests them — v1.2
- ✓ SIG-02: Re-request signals captured and stored; adaptive ranker ingests them — v1.2
- ✓ SIG-03: Adaptive ranker ingests all three signal types (skip, re_request, expand) with decay scoring — v1.2
- ✓ OBS-01: All modules emit structured JSON logs (JSONFormatter + ContextAdapter) — v1.2
- ✓ OBS-02: LOG_LEVEL env var controls verbosity without code changes — v1.2
- ✓ OBS-03: `/health` returns 200 with DB, Redis, and scheduler status — v1.2
- ✓ OBS-04: `/metrics` exposes briefing latency, signal counts, memory size — v1.2
- ✓ DEPLOY-01: `docker compose up` starts app + Postgres + Redis from fresh clone — v1.2
- ✓ DEPLOY-02: `.env.example` documents all 16 env vars with descriptions — v1.2
- ✓ DEPLOY-03: `DEPLOY.md` production guide covers VPS + Caddy + auto-TLS — v1.2

## Next Milestone: v2.0 Ecosystem Expansion

v1.2 shipped. The stack is now deployable, observable, and signal-complete.
Next: `/gsd-new-milestone` to define v2.0 scope.

### Active (v2.0 candidates)

- [ ] **DASH-01**: Web dashboard — briefing history, preference management, memory browser
- [ ] **DASH-02**: Mobile companion app (iOS)
- [ ] **INTG-06–10**: Travel, finance, health, smart home, document integrations

### Future (v2.0+ targets)

- [ ] **DASH-01**: Web dashboard — briefing history, preference management, memory browser
- [ ] **DASH-02**: Mobile companion app (iOS)
- [ ] **INTG-06**: Apple Mail (IMAP/SMTP) integration
- [ ] **INTG-07**: Travel integration (flights, hotels, itinerary)
- [ ] **INTG-08**: Finance integration (transactions, balances, alerts)
- [ ] **INTG-09**: Health integration (calendar-aware fitness/wellbeing)
- [ ] **INTG-10**: Smart home integration

### Out of Scope

- Fully local LLM — GPT-class cloud model required for quality; out of scope indefinitely
- News integration — not a core use case
- Full autonomous actions with no safety locks — BLOCKED_ACTION_TYPES enforced permanently
- Slack channel whitelist enforcement — intentional M1 deferral; revisit in v2.0

## Context

**Current state (v1.2 shipped):** Python backend, FastAPI, PostgreSQL + pgvector (1536-dim HNSW-indexed memory embeddings) + Redis, LangGraph orchestrator with sentence-level briefing delivery, cursor-tracked resume, and structured JSON logging. Docker Compose stack deployable from fresh clone. CLI-driven (`daily briefing`, `daily chat`, `daily voice`, `daily config`).

**Architecture:** `[Voice/UI] → [Orchestrator] → [Context Builder + Memory Retrieval] → [LLM] → [Action Engine (autonomy-gated)] → [Integrations]`

**Known gaps / tech debt:**
- Slack channel whitelist is empty set — all channels pass validation (intentional M1 deferral)
- Hallucination-loop guard is a binary flag check — could be made more robust with embedding dedup at injection time
- Sigmoid midpoint uses 1.25 (not 1.0) — intentional product decision, documented in Key Decisions

## Constraints

- **Architecture**: LLM must not directly access APIs or hold credentials — backend mediates everything
- **Privacy**: Raw email/message bodies must not be stored long-term — only summaries and metadata
- **Latency**: Voice responses must feel instant — precompute briefings, stream TTS
- **Security**: OAuth tokens encrypted at rest (AES-256), stored in secure vault (never frontend)
- **Autonomy**: `BLOCKED_ACTION_TYPES` (send-email, create-external-calendar-invite) are permanently approval-gated — no user setting can bypass

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend-first for v1.0 | Validates core agent loop before investing in UI | ✓ Good — delivered complete pipeline in 10 days |
| Cloud LLM (GPT-4.1) | GPT-class reasoning required for quality; local LLM insufficient | ✓ Good — instruction following solid |
| Orchestrator pattern (LLM ≠ executor) | Security + reliability — LLM plans, backend executes | ✓ Good — SEC-05 held throughout |
| Approval-required for all v1.0 actions | Build user trust before enabling autonomy | ✓ Good — ACT-07 (v1.1) extends with explicit opt-in |
| Precomputed briefing cache | Eliminates voice latency at delivery time | ✓ Good — <1s delivery from Redis confirmed |
| LangGraph over custom state machine | Stateful graph + human-in-the-loop interrupts | ✓ Good — approval gate clean; sentence-cursor extension natural |
| APScheduler 4.x in-process | No broker dependency for M1 single-process | ✓ Good — zero infra overhead |
| Cartesia Sonic-3 for TTS | 40–90ms TTFB, WebSocket streaming | ✓ Good — latency target met |
| Deepgram Nova-3 for STT | Sub-300ms streaming | ✓ Good — real-time performance confirmed |
| pgvector for memory (not separate vector DB) | Zero additional infra; same Postgres instance | ✓ Good — HNSW cosine dedup working at M1 scale |
| Sigmoid midpoint at 1.25 (not 1.0) | Neutral sender gets a slight uplift; pure-heuristic behaviour preserved at cold start | ✓ Good — product intent confirmed |
| BLOCKED_ACTION_TYPES frozenset constant | User config cannot bypass high-impact actions (T-11-01) | ✓ Good — security constraint enforced at code level |
| Sentence-level briefing segmentation | Enables cursor-tracked resume after interruption | ✓ Good — CONV-01 verified; implementation cleaner than expected |
| Fire-and-forget memory extraction | Session end doesn't block voice loop shutdown | ✓ Good — asyncio.create_task pattern with dedicated async_session |
| Fire-and-forget signal capture | Signal writes don't block voice loop; skip/re_request captured asynchronously | ✓ Good — asyncio.create_task in skip_node and re_request_node |
| stdlib logging over structlog | Zero new dependencies; JSONFormatter subclass intercepts all existing getLogger call sites | ✓ Good — 17+ call sites migrated without code change |
| In-process /health endpoint | No sidecar dependency; checks DB, Redis, APScheduler state inline | ✓ Good — OBS-03 satisfied with minimal infra |
| Multi-stage Dockerfile (uv + python:3.11-slim) | Stable dep layer for build cache; uv binary sourced from upstream image | ✓ Good — DEPLOY-01 satisfied; clean layer caching |
| make_logger factory with stage ctx | Structured ctx field (user_id, stage) propagated without threading context | ✓ Good — v1.2 tech debt closed; hot-path modules compliant |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-20 after v1.2 milestone completion — Deployability Layer shipped*
