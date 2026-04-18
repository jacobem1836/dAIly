# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- 🚧 **v1.1 Intelligence Layer** — Phases 7–12 (in progress)

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

### 🚧 v1.1 Intelligence Layer (In Progress)

**Milestone Goal:** Transform the briefing from a consistent daily output into a personalised, adaptive system that learns the user over time and earns increasing autonomy.

- [ ] **Phase 7: Tech Debt Fixes** - Correct three broken paths that corrupt signal data and block intelligence features
- [x] **Phase 8: Adaptive Ranker** - Replace static email heuristics with signal-learned personal scoring — completed 2026-04-16
- [x] **Phase 9: Cross-Session Memory** - Persist durable user facts across days via pgvector extraction and retrieval — completed 2026-04-17
- [x] **Phase 10: Memory Transparency** - Voice interface for user to inspect, edit, and reset what the system knows (completed 2026-04-17)
- [ ] **Phase 11: Trusted Actions** - User-configurable autonomy levels with explicit opt-in and safety locks
- [ ] **Phase 12: Conversational Flow** - Natural interruption, fluid mode switching, and adaptive tone

## Phase Details

### Phase 7: Tech Debt Fixes
**Goal**: Three broken paths are corrected so signals captured from this point forward are accurate and complete
**Depends on**: Nothing (first phase of v1.1)
**Requirements**: FIX-01, FIX-02, FIX-03
**Success Criteria** (what must be TRUE):
  1. A scheduled morning briefing correctly scores a direct-to-user email at 10pts (WEIGHT_DIRECT), not 2pts (WEIGHT_CC)
  2. Slack ingestion for a multi-page workspace retrieves messages beyond the first page
  3. Thread summarisation on demand resolves the real message ID from briefing metadata rather than using the last message content as a stub
**Plans**: 3 plans
  - [x] 07-01-PLAN.md — Fix FIX-01: normalize RFC 2822 recipient addresses in ranker
  - [x] 07-02-PLAN.md — Fix FIX-02: paginate Slack conversations_history within time window
  - [x] 07-03-PLAN.md — Fix FIX-03: resolve message_id from email_context in summarise_thread_node

### Phase 8: Adaptive Ranker ✅
**Goal**: Morning briefing email order reflects the user's observed attention patterns, not static keyword weights
**Depends on**: Phase 7
**Requirements**: INTEL-01
**Completed**: 2026-04-16
**Success Criteria** (all passed):
  1. A sender the user has repeatedly expanded or re-requested appears higher in the briefing than a sender they consistently skip
  2. At cold start (fewer than 30 signals) the ranker falls back to heuristic defaults without error
  3. The briefing pipeline continues to deliver on schedule if signal retrieval fails (graceful degradation)
**Plans**: 4/4 complete
  - [x] 08-01-PLAN.md — Adaptive ranker core (signal scoring model)
  - [x] 08-02-PLAN.md — Sender metadata capture
  - [x] 08-03-PLAN.md — Wire multipliers into pipeline
  - [x] 08-04-PLAN.md — Pipeline session wiring

### Phase 9: Cross-Session Memory ✅
**Goal**: The system recalls user-specific facts from previous sessions when building each day's briefing
**Depends on**: Phase 7
**Requirements**: INTEL-02
**Completed**: 2026-04-17
**Success Criteria** (all passed):
  1. A fact stated during a voice session ("I'm travelling next week") is recalled and reflected in the next morning's briefing context
  2. Memory extraction fires at session end without delaying the voice response
  3. Recalled memories do not create a hallucination loop — facts injected back into context are not re-extracted as new facts
  4. A user with memory_enabled=False has no facts extracted or injected
**Plans**: 4/4 complete
  - [x] 09-01-PLAN.md — Foundation (pgvector, MemoryFact ORM, migration 005)
  - [x] 09-02-PLAN.md — Memory extraction module (LLM-driven fact extraction)
  - [x] 09-03-PLAN.md — Memory retrieval and injection (narrator + SessionState)
  - [x] 09-04-PLAN.md — Memory extraction trigger (voice session wiring)

### Phase 10: Memory Transparency
**Goal**: User can inspect, delete, and disable the memory the system holds about them entirely via voice
**Depends on**: Phase 9
**Requirements**: MEM-01, MEM-02, MEM-03
**Success Criteria** (what must be TRUE):
  1. Asking "what do you know about me?" returns a verbal summary of up to 10 stored facts
  2. User can delete a specific stored fact by stating it; subsequent briefings no longer reflect that fact
  3. User can say "forget everything" and all stored memories are cleared
  4. User can disable memory learning; no new facts are extracted after disabling
**Plans**: 2 plans
Plans:
  - [x] 10-01-PLAN.md — Memory helpers + intent routing + memory_node implementation
  - [x] 10-02-PLAN.md — Tests for memory transparency (helpers + routing + node)



### Phase 11: Trusted Actions
**Goal**: User can configure specific action types to execute without per-action approval; high-impact actions remain locked to approve
**Depends on**: Phase 7
**Requirements**: ACT-07
**Success Criteria** (what must be TRUE):
  1. With autonomy set to auto for a trusted action type (e.g., create_draft), the action executes without prompting the user for approval
  2. Send-email and create-external-calendar-invite are never auto-executed regardless of user autonomy settings
  3. The approve level (default) behaves identically to v1.0 — no regression in the approval gate
  4. User can change autonomy level via config command; the change takes effect on the next session
**Plans**: 2 plans
Plans:
  - [ ] 11-01-PLAN.md — Autonomy constants, UserPreferences field, and approval gate bypass
  - [ ] 11-02-PLAN.md — CLI config commands and comprehensive tests

### Phase 12: Conversational Flow
**Goal**: User can interrupt the briefing, switch modes, and receive tone-adapted responses without breaking session state
**Depends on**: Phase 9, Phase 11
**Requirements**: CONV-01, CONV-02, CONV-03
**Success Criteria** (what must be TRUE):
  1. User can speak mid-briefing and the system stops playback, processes the interruption, and can resume the briefing from the correct section
  2. User can switch from briefing to asking a question to requesting an action and back, all within one session, without the system losing context
  3. When user signals time pressure ("I'm in a rush"), subsequent responses in that session are compressed and more direct
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
| 7. Tech Debt Fixes | v1.1 | 0/3 | Not started | — |
| 8. Adaptive Ranker | v1.1 | 4/4 | Complete | 2026-04-16 |
| 9. Cross-Session Memory | v1.1 | 4/4 | Complete | 2026-04-17 |
| 10. Memory Transparency | v1.1 | 2/2 | Complete   | 2026-04-17 |
| 11. Trusted Actions | v1.1 | 0/2 | Not started | — |
| 12. Conversational Flow | v1.1 | 0/? | Not started | — |
