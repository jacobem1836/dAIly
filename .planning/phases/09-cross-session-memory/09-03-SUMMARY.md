---
phase: 09-cross-session-memory
plan: "03"
subsystem: memory-retrieval
tags:
  - intel-02
  - memory
  - narrator
  - orchestrator
  - pgvector
dependency_graph:
  requires:
    - 09-01  # MemoryFact ORM + HNSW index
    - 09-02  # extract_and_store_memories (write side)
  provides:
    - retrieve_relevant_memories (read side)
    - narrator MEMORY_PREAMBLE injection
    - pipeline memory retrieval gate
    - SessionState.user_memories field
    - respond_node memory-aware system prompt
  affects:
    - daily.profile.memory
    - daily.briefing.narrator
    - daily.briefing.pipeline
    - daily.briefing.context_builder
    - daily.briefing.ranker
    - daily.orchestrator.state
    - daily.orchestrator.session
    - daily.orchestrator.nodes
tech_stack:
  added: []
  patterns:
    - cosine similarity retrieval via pgvector ORDER BY <=> LIMIT k
    - fail-silent retrieval (try/except returns [])
    - memory_enabled hard gate (belt-and-braces)
    - MEMORY_PREAMBLE -> PREFERENCE_PREAMBLE -> NARRATOR_SYSTEM_PROMPT ordering
    - Field(default_factory=list) for safe LangGraph checkpointer deserialization
key_files:
  created: []
  modified:
    - src/daily/profile/memory.py
    - src/daily/briefing/narrator.py
    - src/daily/briefing/pipeline.py
    - src/daily/briefing/context_builder.py
    - src/daily/briefing/ranker.py
    - src/daily/orchestrator/state.py
    - src/daily/orchestrator/session.py
    - src/daily/orchestrator/nodes.py
    - tests/test_memory.py
    - tests/test_narrator_preferences.py
decisions:
  - title: "Query text for briefing = 'today's daily briefing'; session = 'today's briefing context'"
    rationale: "Distinct query texts per injection point per CONTEXT.md recommendation — briefing gets broader recall, session gets conversational context framing"
  - title: "test_narrator_preferences.py extended (not new file)"
    rationale: "Memory preamble tests are logically adjacent to preference preamble tests; single file avoids fragmentation"
  - title: "Restore db_session + sender_multipliers to pipeline/context_builder/ranker"
    rationale: "Rule 1 Bug — phase-9-01 accidentally stripped phase-8-04's adaptive ranking wiring. All three files restored as part of this plan's fix."
  - title: "respond_node chosen for live-session memory injection"
    rationale: "respond_node is the primary follow-up answer node (handles route_intent=='follow_up'). Memory preamble prepended to its RESPOND_SYSTEM_PROMPT before the format() call."
metrics:
  duration: "~40 minutes"
  completed: "2026-04-17"
  tasks: 2
  files_modified: 10
requirements_satisfied:
  - INTEL-02
---

# Phase 9 Plan 03: Memory Retrieval and Injection Summary

Implemented the read side of the cross-session memory layer. Facts written by Plan 02's `extract_and_store_memories` are now retrieved at the two locked injection points — narrator (precomputed briefing) and SessionState (live session) — and surfaced into LLM system prompts, closing INTEL-02's Phase 9 success criterion.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | retrieve_relevant_memories + narrator MEMORY_PREAMBLE | 439ed66 | memory.py, narrator.py, pipeline.py, context_builder.py, ranker.py |
| 2 | SessionState.user_memories + respond_node injection | 439ed66 | state.py, session.py, nodes.py |
| - | RED tests | eb4ce93 | test_memory.py, test_narrator_preferences.py |
| - | Test isolation fix | 9971fbf | test_memory.py |

## Implementation Notes

### retrieve_relevant_memories (src/daily/profile/memory.py)

Added after `extract_and_store_memories`. Signature:
```python
async def retrieve_relevant_memories(
    user_id: int, query_text: str, db_session: AsyncSession, top_k: int = 10
) -> list[str]
```
- Hard gate: checks `memory_enabled` via `load_profile` before any embedding call
- Embeds `query_text` via `_embed()` (reuses existing `text-embedding-3-small` helper)
- Queries: `ORDER BY embedding.cosine_distance(query_embedding) LIMIT top_k`
- Fail-silent: returns `[]` on any exception — BRIEF-01 "always delivers" preserved

### Narrator injection (src/daily/briefing/narrator.py)

Added `MEMORY_PREAMBLE` constant. Updated `build_narrator_system_prompt` to accept `user_memories: list[str] | None = None`. Ordering: `MEMORY_PREAMBLE -> PREFERENCE_PREAMBLE -> NARRATOR_SYSTEM_PROMPT`. Backward-compatible: existing callers omitting `user_memories` get existing behavior.

`generate_narrative` extended with `user_memories` parameter, passed through to `build_narrator_system_prompt`.

### Pipeline wiring (src/daily/briefing/pipeline.py)

Memory retrieval is called with `query_text="today's daily briefing"` after `context.raw_bodies.clear()` and before `generate_narrative`. Gated on `db_session is not None` (on-demand path skips retrieval).

### Rule 1 Bug — Adaptive ranking wiring restored

Phase-9-01 (`fff9cff`) accidentally stripped the `db_session` parameter from `pipeline.py`, `context_builder.py`, and the `sender_multipliers` parameter from `ranker.py` — all introduced by phase-8-04 (`e004d10`). These were restored in this plan's implementation commit as part of the Rule 1 auto-fix.

Restored:
- `run_briefing_pipeline(db_session=None)` parameter
- `build_context(db_session=None)` parameter with adaptive ranker call
- `rank_emails(sender_multipliers=None)` parameter with multiplier application

### SessionState.user_memories (src/daily/orchestrator/state.py)

Added `user_memories: list[str] = Field(default_factory=list)` to `SessionState`. Safe LangGraph deserialization: old checkpoint rows missing this field load with empty default (T-09-12 mitigation).

### initialize_session_state wiring (src/daily/orchestrator/session.py)

Calls `retrieve_relevant_memories` with `query_text="today's briefing context"` when `preferences.memory_enabled` is True. Uses lazy import pattern (`from daily.profile.memory import retrieve_relevant_memories` inside the function) consistent with other nodes. Returns `"user_memories": user_memories` as the last key in the state dict.

### respond_node injection (src/daily/orchestrator/nodes.py, lines ~149-166)

The `respond_node` function (the node handling conversational follow-up queries) was chosen for memory injection. Memory preamble is prepended to `system_content` before the `RESPOND_SYSTEM_PROMPT.format(...)` call. Pattern:

```python
memory_preamble = ""
if state.user_memories:
    memory_lines = "\n".join(f"- {m}" for m in state.user_memories)
    memory_preamble = "User memories ...\n\n"
system_content = memory_preamble + RESPOND_SYSTEM_PROMPT.format(...)
```

## Test Results

| Test | Status |
|------|--------|
| test_retrieve_relevant_facts | PASSED |
| test_retrieval_skipped_when_disabled | PASSED |
| test_session_state_includes_memories | PASSED |
| TestNarratorMemoryPreamble (5 tests) | ALL PASSED |
| Full test_narrator_preferences.py (21 tests) | ALL PASSED |
| test_briefing_pipeline.py (8 tests) | ALL PASSED |
| test_orchestrator_graph.py + test_orchestrator_thread.py (39 tests) | ALL PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored phase-8-04 adaptive ranking wiring stripped by phase-9-01**

- **Found during:** Task 1 — discovered pipeline.py had no `db_session` parameter
- **Issue:** `fff9cff` (feat(09-01)) removed `TYPE_CHECKING`, `db_session` from pipeline.py and context_builder.py, and `sender_multipliers` from ranker.py — all added by `e004d10` (feat(08-04)) for INTEL-01 adaptive ranking
- **Fix:** Re-added `db_session: "AsyncSession | None" = None` to `run_briefing_pipeline` and `build_context`, restored `sender_multipliers` parameter and multiplier application loop in `rank_emails`, restored adaptive ranker call in `build_context`
- **Files modified:** pipeline.py, context_builder.py, ranker.py
- **Commit:** 439ed66

**2. [Rule 2 - Missing correctness] Added memory_enabled=True reset in test_session_state_includes_memories**

- **Found during:** Task 2 test run (second run)
- **Issue:** test used user_id=12 but a previous test run may have set `memory_enabled=False` for that user, causing the second run to fail non-deterministically
- **Fix:** Added `upsert_preference(12, "memory_enabled", "true", ...)` at test start to ensure clean state
- **Commit:** 9971fbf

## Known Stubs

None. Plan 03 closes the read side of INTEL-02. The extraction trigger (Plan 04) remains.

## Threat Flags

No new security surface introduced beyond the plan's threat model. T-09-10 through T-09-13 mitigations are all in place.

## Self-Check: PASSED
