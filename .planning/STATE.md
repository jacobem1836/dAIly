---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Mobile Voice
status: verifying
last_updated: "2026-06-19T05:28:39.961Z"
last_activity: 2026-06-19
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 7
  completed_plans: 8
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-15)

**Core value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.
**Current focus:** Phase 21.45 — Architecture Consolidation

## Current Position

Phase: 21.45 (Architecture Consolidation) — EXECUTING
Plan: 5 of 5
Status: Phase complete — ready for verification
Last activity: 2026-06-19

## Completed Milestones

| Milestone | Phases | Shipped | What it delivered |
|-----------|--------|---------|-------------------|
| v1.0 MVP | 1–6 | 2026-04-14 | OAuth integrations, briefing pipeline, orchestrator, action layer, voice loop, preferences |
| v1.1 Intelligence Layer | 7–12 | 2026-04-18 | Tech debt fixes, adaptive ranker (pgvector), cross-session memory (mem0), memory transparency, trusted actions, conversational flow |
| v1.2 Deployability Layer | 13–16 | 2026-04-20 | Signal capture (skip/re_request/expand), JSON observability, Docker/VPS deployment, milestone closeout |
| v1.3 Voice Polish | 17 | 2026-04-28 | Graceful fade-out, mic-mute AEC, 600ms barge-in safety window, backchannel detection, streaming LLM→TTS |

## Accumulated Context

### Architecture Decisions

| Decision | Date | Details |
|----------|------|---------|
| Mobile-first voice | 2026-04-27 | Native iOS (Swift) + Android (Kotlin) with LiveKit; macOS AEC unsolvable in software |
| Native over cross-platform | 2026-04-27 | Flutter/RN rejected — audio abstraction layers unacceptable for voice-first product |
| LiveKit for transport | 2026-04-27 | WebRTC, ML barge-in, livekit-plugins-langchain bridges to existing LangGraph backend |
| Tier structure | 2026-04-27 | Pro ($15/mo) = voice briefing read-back; Premium ($30-35/mo) = full conversational voice |
| OpenAI Realtime deferred | 2026-04-27 | LiveKit gives model flexibility; Realtime API still viable for Premium tier later |
| Freeze Android (iOS-only TestFlight) | 2026-06-19 | iOS is the sole TestFlight target for v2.1. Android voice plumbing exists but onboarding/integration/permissions UI absent; parity deferred until iOS validated with real users. iOS-hardening in Phase 21.45 is NOT mirrored to Android. Per ADR-003 (2026-06-19 integration-friction review). |

See `KEY_DECISIONS` in PROJECT.md and `.planning/research/voice-strategy-decision.md` for full rationale.

### What Phase 17 Built (and Closed)

- `barge_in.py` — 600ms timer replaces immediate stop_event; `_pending_barge_in_cancelled` flag for backchannel suppression
- `voice/utils.py` — `_is_backchannel()` + `_BACKCHANNEL_PHRASES` list
- `stt.py` — `_select_chunk()` returns silent audio during TTS (mic mute)
- `tts.py` — `play_streaming_tokens()` with sentence-boundary chunking for streaming LLM→TTS
- `loop.py` — `astream_session()` + streaming bridge wired into main turn

**Structural AEC on macOS closed as won't-fix.** Mobile solves it at the OS layer. Desktop becomes secondary platform (web fallback via LiveKit SDK).

### Pending Decisions for Phase 18

- LiveKit Cloud vs self-hosted — Cloud is simpler for dev/testing (~$4.50/user/month transport); self-host (Apache 2.0) saves cost at scale (~$50-100/mo VPS)
- Prompt caching strategy for Realtime API — mandatory if that path is used ($6-8/user/month with caching vs $18-40 without)
- ~~Whether to keep Python voice loop alive as desktop fallback during Phase 18, or stub it out immediately~~ **RESOLVED 2026-06-19 (Phase 21.45): delete it.** Keeping it created two parallel voice architectures (the dual-path friction surfaced in the integration-friction review). Desktop fallback is deferred to Phase 24 (LiveKit web SDK), not the Python loop.

### Roadmap Evolution

- Phase 20.1 inserted after Phase 20: LiveKit Agent Worker (INSERTED) — server-side agent that speaks into LiveKit rooms; prerequisite for mobile apps being functional end-to-end
- Phase 21.2, 21.3 marked complete (were done, roadmap not updated)
- Phase 21.5 inserted after 21.4: Adaptive Learning and Memory — voice preference detection, signal-driven ranking, mem0 cross-session memory; core product promise, required before TestFlight
- Phase 21.45 inserted between 21.4 and 21.5: Architecture Consolidation (URGENT) — Option A of the 2026-06-19 integration-friction review. Delete legacy `voice/` + CLI voice path (resolves the open Phase-18 decision below — **decision: stub/delete, do not keep**), single checkpointer, add E2E voice smoke test, fix .env drift, iOS lifecycle/refresh hardening, freeze Android for TestFlight. 21.5 now depends on 21.45. Full report: `.planning/reviews/2026-06-19-integration-friction-review.md`.
- Android frozen for v2.1 TestFlight (2026-06-19, Phase 21.45-03): iOS is the sole active mobile platform through TestFlight validation. Android resumes after. 221 iCloud `* 2.*` sync-conflict duplicates purged from repo in same plan. iCloud-path move deferred (open follow-up).

### Blockers/Concerns

None active.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260411-vlh | Fix Google credentials reconstruction | 2026-04-11 | dc41c9f | [260411-vlh-fix-google-credentials-reconstruction-bu](./quick/260411-vlh-fix-google-credentials-reconstruction-bu/) |
| 260412-gak | Fix null recipient in draft_node — pass email metadata to LLM prompt | 2026-04-12 | 60975dd | [260412-gak-fix-null-recipient-in-draft-node-pass-em](./quick/260412-gak-fix-null-recipient-in-draft-node-pass-em/) |
| 260503-gdw | Update magic link email to also include the OTP code as plain text | 2026-05-03 | c381b03 | [260503-gdw-update-magic-link-email-to-also-include-](./quick/260503-gdw-update-magic-link-email-to-also-include-/) |

## Session Continuity

Last activity: 2026-05-03 - Completed quick task 260503-gdw: Update magic link email to also include the OTP code as plain text

Last session: 2026-06-19T05:28:39.958Z
Phase 17 (voice polish) complete. Planning docs reconstructed to reflect full v1.0–v1.3 history — the phase-17 branch had branched from phase-06 and the ROADMAP/STATE/MILESTONES had overwritten all intermediate milestone history. Now corrected.

Next session: plan Phase 18 (LiveKit Backend Integration) via `/gsd-plan-phase 18`.
