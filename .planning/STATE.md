---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Mobile Voice
status: planning
last_updated: "2026-04-28T10:06:27.468Z"
last_activity: 2026-04-28 — v1.4 roadmap written (5 phases, 18 requirements mapped)
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.
**Current focus:** v1.4 — Mobile Voice

## Current Position

Phase: 18 — LiveKit Infrastructure + Token Endpoint (not started)
Plan: —
Status: Roadmap created — ready to plan Phase 18
Last activity: 2026-04-28 — v1.4 roadmap written (5 phases, 18 requirements mapped)

```
v1.4 progress: [░░░░░░░░░░] 0% (0/5 phases)
```

## Completed Milestones

| Milestone | Phases | Shipped | What it delivered |
|-----------|--------|---------|-------------------|
| v1.0 MVP | 1–6 | 2026-04-14 | OAuth integrations, briefing pipeline, orchestrator, action layer, voice loop, preferences |
| v1.1 Intelligence Layer | 7–12 | 2026-04-18 | Tech debt fixes, adaptive ranker (pgvector), cross-session memory (mem0), memory transparency, trusted actions, conversational flow |
| v1.2 Deployability Layer | 13–16 | 2026-04-20 | Signal capture (skip/re_request/expand), JSON observability, Docker/VPS deployment, milestone closeout |
| v1.3 Voice Polish | 17 | 2026-04-28 | Graceful fade-out, mic-mute AEC, 600ms barge-in safety window, backchannel detection, streaming LLM→TTS |

## v1.4 Phase Map

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 18 | LiveKit Infrastructure + Token Endpoint | INFRA-01, INFRA-02 | Not started |
| 19 | LiveKit Agent Worker | INFRA-03, INFRA-04, INFRA-05, INFRA-06 | Not started |
| 20 | iOS Native Client | IOS-01, IOS-02, IOS-03, IOS-04, IOS-05 | Not started |
| 21 | Android Native Client | AND-01, AND-02, AND-03, AND-04, AND-05 | Not started |
| 22 | Desktop Web Fallback + Push Notifications | WEB-01, PUSH-01 | Not started |

## Accumulated Context

### Architecture Decisions

| Decision | Date | Details |
|----------|------|---------|
| Mobile-first voice | 2026-04-27 | Native iOS (Swift) + Android (Kotlin) with LiveKit; macOS AEC unsolvable in software |
| Native over cross-platform | 2026-04-27 | Flutter/RN rejected — audio abstraction layers unacceptable for voice-first product |
| LiveKit for transport | 2026-04-27 | WebRTC, ML barge-in, livekit-plugins-langchain bridges to existing LangGraph backend |
| Tier structure | 2026-04-27 | Pro ($15/mo) = voice briefing read-back; Premium ($30-35/mo) = full conversational voice |
| OpenAI Realtime deferred | 2026-04-27 | LiveKit gives model flexibility; Realtime API still viable for Premium tier later |
| Phase 22 combines WEB + PUSH | 2026-04-28 | WEB-01 and PUSH-01 are both thin delivery-layer additions; combining avoids a single-requirement phase |

See `KEY_DECISIONS` in PROJECT.md and `.planning/research/voice-strategy-decision.md` for full rationale.

### Blockers/Concerns

None active.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260411-vlh | Fix Google credentials reconstruction | 2026-04-11 | dc41c9f | [260411-vlh-fix-google-credentials-reconstruction-bu](./quick/260411-vlh-fix-google-credentials-reconstruction-bu/) |
| 260412-gak | Fix null recipient in draft_node — pass email metadata to LLM prompt | 2026-04-12 | 60975dd | [260412-gak-fix-null-recipient-in-draft-node-pass-em](./quick/260412-gak-fix-null-recipient-in-draft-node-pass-em/) |

## Session Continuity

Last session: 2026-04-28T10:06:27.466Z
v1.4 roadmap created — 5 phases (18–22), 18 requirements fully mapped. Next: `/gsd-plan-phase 18`
