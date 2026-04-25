# dAIly

## What This Is

A voice-first AI personal assistant that proactively synthesises a user's digital life into an intelligent daily briefing. It acts as a semi-autonomous operator for communication, scheduling, and decision support — combining executive briefing, conversational assistant, and action-taking agent. Built backend-first, targeting busy professionals and operators who want their life to brief them rather than manually checking multiple apps.

v1.0 shipped a complete backend: OAuth integrations (Gmail, GCal, Outlook, Slack), precomputed briefing pipeline, LangGraph orchestrator, approval-gated action layer, full voice session loop, and user preferences applied end-to-end.

## Core Value

The briefing always delivers: every morning, the user gets a prioritised, conversational summary of what matters — without touching a single app.

## Current Milestone: v1.1 Intelligence Layer

**Goal:** Transform the briefing from a consistent daily output into a personalised, adaptive system that learns the user over time and earns increasing autonomy.

**Target features:**
- Adaptive prioritisation — learned scoring replaces heuristics
- Cross-session memory — persistent user profile across days via pgvector
- Memory transparency — inspect, edit, and delete what the system knows
- Trusted actions — configurable autonomy levels (suggest / approve / auto)
- Conversational flow improvements — natural interruption, fluid mode switching, adaptive tone
- Tech debt fixes — scheduler user_email bug, Slack pagination, thread summarisation stub

## Milestone Plan

| Milestone | Scope | Status |
|-----------|-------|--------|
| **v1.0 — Core Backend** | OAuth integrations, briefing pipeline, orchestrator, action layer, voice interface, preferences | ✅ Shipped 2026-04-14 |
| **v1.1 — Intelligence Layer** | Adaptive prioritisation, deeper memory system, trusted actions, improved conversation flow | 🔄 In Progress |
| **v2.0 — Ecosystem Expansion** | Travel, finance, health, smart home, document platforms, web dashboard | Planned |

## Requirements

### Validated (v1.0)

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
- ✓ PERS-01: User profile stores preferences (tone, briefing length, category order); applied to scheduled briefing — v1.0 (Phase 6)
- ✓ PERS-02: Interaction signals captured (skips, corrections, re-requests) and stored — v1.0
- ✓ PERS-03: Heuristic defaults at cold start (sender importance, deadline keywords, thread recency) — v1.0
- ✓ SEC-01: OAuth tokens encrypted at rest (AES-256-GCM); never exposed to frontend, logs, or LLM — v1.0
- ✓ SEC-02: Pre-filter/redaction layer sanitises external data before LLM — v1.0
- ✓ SEC-03: Each integration requests only minimum required OAuth scopes — v1.0
- ✓ SEC-04: Raw email/message bodies not stored long-term — only summaries and metadata — v1.0
- ✓ SEC-05: LLM outputs are intents only; backend orchestrator validates and dispatches — v1.0

### Active (v1.1 targets)

- [ ] **INTEL-01**: Priority ranking learns from M1 signal data to replace heuristic defaults with personalised scoring
- [ ] **INTEL-02**: Cross-session conversational memory persists context across days (pgvector + structured user profile extraction)
- [ ] **MEM-01**: User can inspect what the system knows about them ("What do you know about me?")
- [ ] **MEM-02**: User can edit or delete specific memory entries
- [ ] **MEM-03**: User can disable learning or reset all memory
- [ ] **ACT-07**: User can configure autonomy level (suggest-only / approve-per-action / trusted-auto)
- [ ] **CONV-01**: Briefing supports natural mid-session interruption without breaking conversation state
- [ ] **CONV-02**: Fluid switching between briefing, discussion, and action modes
- [ ] **CONV-03**: Adaptive tone — system adjusts formality and verbosity based on context signals
- [ ] **FIX-01**: `user_email=""` in scheduler — WEIGHT_DIRECT (10pts) path never fires; direct-to-user emails always scored as WEIGHT_CC (2pts)
- [ ] **FIX-02**: Slack pagination single-page only — implement cursor-based pagination for multi-page workspaces
- [ ] **FIX-03**: `message_id = last_content` stub in summarise_thread_node — real message ID extraction from briefing metadata

### Out of Scope

- Mobile/iOS app — backend-first; UI comes in v2.0+
- Web dashboard — deferred to v2.0 (DASH-01, DASH-02, DASH-03)
- News integration — not in v1 integrations
- Travel, finance, health, smart home — v2.0+
- Full autonomous actions with no approval path — deferred to v2.0 (ACT-07 adds configurable levels, not full bypass)
- Apple Mail (IMAP/SMTP) — INTG-06, v2.0+
- Fully local LLM — GPT-class cloud model required for quality; out of scope indefinitely

## Context

**Current state (v1.0):** 7,049 Python LOC, FastAPI backend, PostgreSQL + pgvector + Redis, LangGraph orchestrator. Full voice pipeline operational. CLI-driven (`daily briefing`, `daily chat`, `daily voice`, `daily config`).

**Architecture:** `[Voice/UI] → [Orchestrator] → [Context Builder] → [LLM] → [Action Engine] → [Integrations]`

**Known gaps / tech debt:**
- Scheduler uses `user_email=""` — WEIGHT_DIRECT scoring path never fires for scheduled runs (tracked as FIX-01)
- Slack ingestion is single-page; multi-page workspaces miss messages beyond first page (tracked as FIX-02)
- Thread summarisation uses `message_id = last_content` as approximate stub (tracked as FIX-03)
- Slack channel whitelist is empty set — all channels pass validation (intentional M1 deferral)

## Constraints

- **Architecture**: LLM must not directly access APIs or hold credentials — backend mediates everything
- **Privacy**: Raw email/message bodies must not be stored long-term — only summaries and metadata
- **Latency**: Voice responses must feel instant — precompute briefings, stream TTS
- **Security**: OAuth tokens encrypted at rest (AES-256), stored in secure vault (never frontend)
- **Autonomy**: Trusted-auto level requires explicit user opt-in; high-impact actions (send email, create event) always surface for approval at default level

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend-first for v1.0 | Validates core agent loop before investing in UI | ✓ Good — delivered complete pipeline in 10 days |
| Cloud LLM (GPT-4.1) | GPT-class reasoning required for quality; local LLM insufficient | ✓ Good — instruction following solid; consider Claude 3.5 Sonnet for structured output in v1.1 |
| Orchestrator pattern (LLM ≠ executor) | Security + reliability — LLM plans, backend executes | ✓ Good — SEC-05 held throughout; no credentials touched by LLM |
| Approval-required for all v1.0 actions | Build user trust before enabling autonomy | ✓ Good — human-in-the-loop gate in place; expand in v1.1 |
| Precomputed briefing cache | Eliminates voice latency at delivery time | ✓ Good — <1s delivery from Redis confirmed |
| LangGraph over custom state machine | Stateful graph + human-in-the-loop interrupts required for approval flow | ✓ Good — approval gate clean; debugging multi-layer indirection is the cost |
| APScheduler 4.x in-process | No broker dependency for M1 single-process | ✓ Good — zero infra overhead; revisit if v1.1 requires distributed workers |
| Cartesia Sonic-3 for TTS | 40–90ms TTFB, WebSocket streaming | ✓ Good — latency target met |
| Deepgram Nova-3 for STT | Sub-300ms streaming, $0.0077/min | ✓ Good — real-time performance confirmed |

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
*Last updated: 2026-04-15 after v1.1 milestone start*
