# Roadmap: dAIly

## Overview

dAIly is built in five phases that mirror the system's dependency graph. Authenticated data access comes first because every layer above depends on it. The briefing pipeline ships next because it is the precomputed backbone the voice interface serves from — generating briefings on-demand at delivery time is an irrecoverable UX failure. The orchestrator wraps the pipeline with conversational intelligence. The action layer adds gated, auditable write capability. Voice is last because real-time latency pressure before the pipeline is solid creates misattributed debugging. Each phase delivers a coherent, independently testable capability before the next begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Encrypted OAuth token vault, read adapters for Gmail/GCal/Outlook/Slack, PostgreSQL schema with correct data lifecycle
- [x] **Phase 2: Briefing Pipeline** - Precomputed briefing cron, async context builder, Redis cache, heuristic priority ranking, LLM narrative generation (completed 2026-04-07)
- [ ] **Phase 3: Orchestrator** - LLM gateway with dual-model routing, LangGraph agent loop, in-session context, user profile, signal capture
- [ ] **Phase 4: Action Layer** - Approval gate, action executor (email/Slack/calendar), append-only action log, action sandboxing
- [ ] **Phase 5: Voice Interface** - Deepgram STT with VAD, Cartesia TTS streaming, barge-in detection, end-to-end voice session loop

## Phase Details

### Phase 1: Foundation
**Goal**: Users can connect their accounts and the system can securely read their data
**Depends on**: Nothing (first phase)
**Requirements**: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, SEC-01, SEC-03, SEC-04
**Success Criteria** (what must be TRUE):
  1. User can connect a Gmail account via OAuth and the system stores an encrypted access token (no plaintext token anywhere in logs or DB)
  2. User can connect a Google Calendar, Outlook, and Slack account via OAuth — each with only minimum required scopes
  3. System can successfully read emails, calendar events, and Slack messages from connected accounts using stored tokens
  4. Background process proactively refreshes tokens before they expire without user interaction
  5. Raw email and message bodies are not persisted to the database — only summaries and metadata columns exist in the schema
**Plans:** 5 plans
Plans:
- [x] 01-01-PLAN.md — Project scaffold, DB schema, token vault, test infrastructure
- [x] 01-02-PLAN.md — Adapter interfaces, Pydantic models, CLI entrypoint
- [x] 01-03-PLAN.md — Google OAuth flow, Gmail + Calendar adapters
- [x] 01-04-PLAN.md — Slack OAuth flow, Slack adapter
- [x] 01-05-PLAN.md — Microsoft Graph OAuth, Outlook adapters, token refresh

### Phase 2: Briefing Pipeline
**Goal**: The system produces a ranked, LLM-generated briefing narrative on a precomputed schedule every morning
**Depends on**: Phase 1
**Requirements**: BRIEF-01, BRIEF-02, BRIEF-03, BRIEF-04, BRIEF-05, BRIEF-06, PERS-03, SEC-02, SEC-05
**Success Criteria** (what must be TRUE):
  1. A briefing is precomputed and cached in Redis overnight (default 05:00) — serving from cache takes under 1 second
  2. User can configure the precompute schedule time and the change persists across restarts
  3. Briefing correctly ranks emails by heuristic priority (sender weight, deadline keywords, thread activity recency)
  4. Briefing includes today's and next 48h calendar events with conflict detection noted
  5. Briefing includes Slack mentions and DMs from priority channels
  6. External data passes through a summarisation/redaction layer before reaching the LLM — no raw bodies in LLM context
**Plans:** 5/5 plans complete
Plans:
- [x] 02-01-PLAN.md — Dependencies, pipeline models, adapter extensions, DB schema
- [x] 02-02-PLAN.md — Heuristic email ranker, context builder, calendar conflicts
- [x] 02-03-PLAN.md — Redactor (LLM summarise + credential strip), narrator (LLM narrative)
- [x] 02-04-PLAN.md — Redis cache, APScheduler cron, pipeline orchestrator, CLI config
- [x] 02-05-PLAN.md — Gap closure: BRIEF-02 schedule persistence (DB read on startup)

### Phase 3: Orchestrator
**Goal**: Users can ask follow-up questions during the briefing and receive contextually-aware answers; the system knows their preferences
**Depends on**: Phase 2
**Requirements**: BRIEF-07, PERS-01, PERS-02
**Success Criteria** (what must be TRUE):
  1. User can ask for a thread summary on demand ("summarise that email chain") and receive a coherent answer using in-session context
  2. User preferences (tone, briefing length, category order) are stored in a profile and applied to subsequent briefings
  3. Interaction signals (skips, corrections, re-requests) are captured and stored for future ranking use
  4. LLM outputs are structured intent JSON only — the orchestrator dispatches all actions; no LLM tool calls invoke external APIs directly
**Plans:** 4 plans
Plans:
- [x] 03-01-PLAN.md — Dependencies, profile package (UserProfile ORM, UserPreferences, service functions)
- [x] 03-01b-PLAN.md — Signal log, orchestrator models (SessionState, OrchestratorIntent), Alembic migration
- [x] 03-02-PLAN.md — LangGraph StateGraph, orchestrator nodes, CLI chat command with real adapter wiring (BRIEF-07)
- [x] 03-03-PLAN.md — CLI profile commands, narrator preference injection

### Phase 4: Action Layer
**Goal**: Users can instruct the system to draft replies and calendar changes, approve them by voice, and see a full audit trail
**Depends on**: Phase 3
**Requirements**: ACT-01, ACT-02, ACT-03, ACT-04, ACT-05, ACT-06
**Success Criteria** (what must be TRUE):
  1. User can instruct the system to draft an email reply or Slack message and see the draft before it is sent
  2. User can instruct the system to create or reschedule a calendar event and confirm the change before it executes
  3. No external-facing action executes without an explicit confirm from the user — there is no code path that bypasses approval
  4. Every action attempt is recorded in an append-only log with timestamp, type, target, content summary, approval status, and outcome
  5. Action executor validates recipient, content type, and scope against a whitelist before dispatch — malformed or out-of-scope actions are rejected
**Plans:** 3 plans
Plans:
- [x] 04-01-PLAN.md — Action layer models, ABCs, action log, whitelist, LangGraph approval gate
- [x] 04-02-PLAN.md — LLM draft generation with style matching, CLI approval flow
- [x] 04-03-PLAN.md — Concrete ActionExecutors (Gmail, Slack, Calendar, Outlook) and dispatch wiring

### Phase 5: Voice Interface
**Goal**: Users can receive the morning briefing, interrupt it, and complete the full action workflow entirely by voice
**Depends on**: Phase 4
**Requirements**: VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05
**Success Criteria** (what must be TRUE):
  1. Briefing playback begins within 1 second of user request (served from cache) — TTS audio starts streaming before full response is generated
  2. User speech is transcribed with interim results in real time; end-to-end follow-up response latency is under 1.5 seconds
  3. User can interrupt the briefing mid-sentence and the system stops speaking and responds to the new input
  4. User can ask follow-up questions and receive answers that reflect the current session context (not isolated single-turn responses)
**UI hint**: yes
**Plans:** 4 plans
Plans:
- [x] 05-01-PLAN.md — TTS pipeline (Cartesia WebSocket + sentence splitter + sounddevice playback)
- [x] 05-02-PLAN.md — STT pipeline (Deepgram WebSocket + mic capture + transcript handling)
- [x] 05-03-PLAN.md — Barge-in (asyncio task coordination, stop_event, VAD interrupt loop)
- [x] 05-04-PLAN.md — Full voice loop integration (daily voice command, AsyncPostgresSaver, end-to-end wiring)

### Phase 6: Wire User Preferences to Scheduled Briefing
**Goal:** PERS-01 fully satisfied — user-configured tone/length/category_order applied to the precomputed morning briefing, not just the CLI chat session
**Depends on:** Phase 3 (UserPreferences ORM + load_profile()), Phase 5 (voice briefing loop)
**Requirements:** PERS-01
**Gap Closure:** Closes PERS-01 wiring gap from v1.0 audit; fixes Phase 3→2 integration link and "Preferences-applied briefing" E2E flow
**Plans:** TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/5 | Planning complete | - |
| 2. Briefing Pipeline | 5/5 | Complete   | 2026-04-07 |
| 3. Orchestrator | 0/4 | Planning complete | - |
| 4. Action Layer | 0/3 | Planning complete | - |
| 5. Voice Interface | 0/4 | Planning complete | - |
| 6. Wire Preferences to Briefing | 0/1 | Gap closure — Pending | - |
