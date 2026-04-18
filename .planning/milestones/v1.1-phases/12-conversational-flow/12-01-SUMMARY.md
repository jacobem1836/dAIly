---
phase: 12-conversational-flow
plan: 01
subsystem: orchestrator/voice
tags: [conversational-flow, briefing-resume, tone-compression, langgraph]
dependency_graph:
  requires: []
  provides: [briefing_cursor, tone_override, resume_briefing_node, sentence-level-delivery]
  affects: [orchestrator, voice-loop]
tech_stack:
  added: []
  patterns: [cursor-tracking, keyword-routing, implicit-signal-detection, session-scoped-state]
key_files:
  created: []
  modified:
    - src/daily/orchestrator/state.py
    - src/daily/voice/loop.py
    - src/daily/orchestrator/graph.py
    - src/daily/orchestrator/nodes.py
decisions:
  - "Simpler alternative for resume: resume_briefing_node returns a verbal cue only; voice loop handles TTS re-entry to avoid LangGraph TTS coupling"
  - "briefing_cursor clamped via max(0, min(cursor, len-1)) before indexing (T-12-01 mitigation)"
  - "tone_override returned via state_updates dict merge — persists in LangGraph checkpointer but no upsert_preference call (D-09)"
  - "Implicit tone trigger on 2 consecutive human messages under 5 words — no external NLP dependency"
metrics:
  duration: ~15 minutes
  completed: "2026-04-18"
  tasks_completed: 3
  files_modified: 4
---

# Phase 12 Plan 01: Conversational Flow — Sentence Delivery, Resume, and Tone Compression

One-liner: Sentence-level briefing segmentation with interrupt/resume cursor tracking plus session-scoped tone compression via keyword and implicit signal detection.

## What Was Built

### Task 1: State Fields and Sentence Splitter

Added `briefing_cursor: int | None` and `tone_override: str | None` to `SessionState`. Added `_split_sentences()` helper in `loop.py` using stdlib `re` (no new dependencies). Replaced the monolithic `await turn_manager.speak(briefing_narrative)` call with a sentence-by-sentence iteration loop that stores the cursor on barge-in and sets it to `None` on full delivery. The cursor is surfaced into `initial_state` so the LangGraph graph has it available from the first turn.

### Task 2: Resume Route, Node, and Auto-Offer

Added `resume_briefing_keywords` block to `route_intent()` at priority slot 2 (after memory, before summarise). Added `resume_briefing_node` to `nodes.py` that returns "Resuming your briefing now." when cursor is set, or a "no briefing to resume" message when cursor is None. Wired the node in `build_graph()` with a terminal edge. Added D-04 auto-offer ("Want me to continue your briefing?") after non-resume turns when cursor is set. Added briefing resume re-entry loop in `loop.py` that iterates from `safe_cursor` with T-12-01 cursor clamping and supports re-interruption mid-resume.

### Task 3: Tone Compression Detection and System Prompt Injection

Added `COMPRESSION_PHRASES` with six explicit trigger phrases and `_IMPLICIT_TONE_MIN_TURNS`/`_IMPLICIT_TONE_MAX_WORDS` thresholds. Modified `respond_node` to check both explicit (substring match) and implicit (word count on last 2 human messages) triggers before building the system prompt. When triggered, `effective_tone = "brief"` and the compression instruction ("Max 2 sentences per response. Skip pleasantries.") is appended. `tone_override` is persisted in LangGraph state via `{**state_updates}` merge — never written to DB.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | c719768 | feat(12-01): add briefing_cursor and tone_override state fields, sentence splitter |
| 2 | a2472ee | feat(12-01): add resume_briefing route, node, auto-offer, and resume re-entry |
| 3 | 50bde97 | feat(12-01): add tone compression detection and system prompt injection |

## Deviations from Plan

None - plan executed exactly as written.

Threat model mitigations applied as specified:
- T-12-01: cursor clamped with `max(0, min(cursor, len(sentences) - 1))` before array indexing
- T-12-03: verbal acknowledgements use `turn_manager.speak()` (not raw TTS) throughout

## Known Stubs

None. All wiring is complete:
- `briefing_cursor` flows from voice loop through `initial_state` into LangGraph state
- `resume_briefing_node` is fully wired with route and terminal edge
- `tone_override` propagates through LangGraph state for the session lifetime

## Self-Check: PASSED

All modified files exist. All task commits found: c719768, a2472ee, 50bde97.
