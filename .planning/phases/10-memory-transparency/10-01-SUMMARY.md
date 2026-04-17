---
phase: 10-memory-transparency
plan: 01
subsystem: orchestrator
tags: [memory, pgvector, langgraph, voice, transparency, postgresql]

# Dependency graph
requires:
  - phase: 09-memory-system
    provides: "MemoryFact ORM model, extract_and_store_memories, retrieve_relevant_memories, _embed, _get_openai_client"
  - phase: 06-wire-preferences-to-briefing
    provides: "upsert_preference signature (value: str), load_profile, UserPreferences"
provides:
  - "list_all_memories(user_id, db_session, limit) — bypasses memory_enabled gate"
  - "delete_memory_fact(user_id, description, db_session, threshold=0.2) — cosine match delete"
  - "clear_all_memories(user_id, db_session) — bulk DELETE with count return"
  - "memory_node() — orchestrator node dispatching four sub-paths via keyword matching"
  - "route_intent() extended with memory keywords at top priority (before summarise)"
  - "Graph wired: START -> memory -> END path"
affects: [phase-11, conversation-flow, voice-session-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Transparency bypass: helper functions that skip the memory_enabled gate intentionally"
    - "Sub-intent dispatch within a single orchestrator node via nested keyword checks"
    - "Node creates own DB session via async_session() (not config-injected)"
    - "Clear-before-delete priority ordering to prevent ambiguous keyword routing"

key-files:
  created: []
  modified:
    - src/daily/profile/memory.py
    - src/daily/orchestrator/nodes.py
    - src/daily/orchestrator/graph.py

key-decisions:
  - "memory_node uses async_session() directly (same as _capture_signal/_log_action) — plan specified config[configurable][db_session] but that key is not populated in this codebase (config only has thread_id)"
  - "Clear (forget everything) checked before delete (forget that) to prevent ambiguous routing (Research Pitfall 1)"
  - "upsert_preference called with string 'false' not Python bool False (type-safe, D-05)"
  - "Transparency helpers bypass memory_enabled gate — retrieve_relevant_memories hard-gates on it and would hide facts when disabled"
  - "No approval gate for memory commands — local DB operations, user-initiated, D-06"

patterns-established:
  - "Transparency pattern: functions that must work even when a feature is disabled get separate implementations without the gate"
  - "Sub-intent node pattern: single node handles multiple related operations via keyword priority checks"

requirements-completed:
  - MEM-01
  - MEM-02
  - MEM-03

# Metrics
duration: 20min
completed: 2026-04-18
---

# Phase 10 Plan 01: Memory Transparency Summary

**Voice-driven memory audit and control: three transparency helpers in memory.py plus memory_node with query/delete/clear/disable sub-paths, wired into the orchestrator graph with keyword-first routing**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-17T23:20:00Z
- **Completed:** 2026-04-17T23:36:26Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `list_all_memories()`, `delete_memory_fact()`, `clear_all_memories()` to memory.py — all bypass the `memory_enabled` gate so transparency always works even when learning is disabled
- Implemented `memory_node()` with four sub-paths (query, delete, clear, disable) using priority-ordered keyword dispatch (clear before delete to prevent "forget everything" routing to single-fact delete)
- Extended `route_intent()` in graph.py with memory keywords checked before summarise/draft (most-specific-first ordering per D-01), wired memory node into the graph with terminal edge to END

## Task Commits

1. **Task 1: Add memory helpers + intent routing** - `f6c1a77` (feat)
2. **Task 2: Implement memory_node** - `d13dc66` (feat)

## Files Created/Modified

- `src/daily/profile/memory.py` — Added `list_all_memories`, `delete_memory_fact`, `clear_all_memories`; added `func` and `delete` to sqlalchemy imports
- `src/daily/orchestrator/nodes.py` — Added `memory_node()` with four sub-paths; added imports for memory helpers and `upsert_preference`
- `src/daily/orchestrator/graph.py` — Extended `route_intent()` with memory keywords at top priority; wired `memory_node` into graph with conditional edge mapping and terminal edge to END

## Decisions Made

1. **DB session via `async_session()` not config injection**: The plan's context section claimed `config["configurable"]["db_session"]` was an established pattern, but inspection of the actual codebase showed the config only carries `thread_id`. All existing nodes that need DB access create their own sessions via `async_session()` (see `_capture_signal`, `_log_action`). Applied same pattern to `memory_node`.

2. **Sub-intent dispatch in single node**: All four memory operations live in one `memory_node` rather than separate nodes — sub-intent routing is via keyword priority inside the node body, avoiding graph complexity for closely related commands.

3. **Cosine threshold 0.2 for delete**: Looser than the 0.1 dedup threshold used during storage (users paraphrase when deleting — D-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DB session via async_session() instead of config["configurable"]["db_session"]**
- **Found during:** Task 2 (memory_node implementation)
- **Issue:** Plan specified `db_session = config["configurable"]["db_session"]` with a `config: RunnableConfig` parameter, but this pattern does not exist in the codebase. The LangGraph config only contains `thread_id` in `configurable`. Using `config["configurable"]["db_session"]` at runtime would raise a `KeyError`.
- **Fix:** Used `async with async_session() as db_session:` inside the node, matching the `_capture_signal` and `_log_action` patterns already established in nodes.py.
- **Files modified:** src/daily/orchestrator/nodes.py
- **Verification:** `from daily.orchestrator.nodes import memory_node` and `build_graph()` both succeed.
- **Committed in:** d13dc66 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug prevention, wrong runtime key)
**Impact on plan:** Essential correction — plan's described interface would cause KeyError in production. Fix follows the codebase's established session pattern.

## Issues Encountered

None beyond the deviation above.

## Known Stubs

None — all four sub-paths (query, delete, clear, disable) are fully implemented with real DB operations. No placeholder text or hardcoded empty returns in the flow.

## Threat Flags

No new network endpoints, auth paths, file access, or schema changes introduced. All operations are scoped to the existing `memory_facts` table with `WHERE user_id = :user_id` constraints (T-10-01, T-10-02, T-10-03 mitigations applied).

## Next Phase Readiness

- MEM-01, MEM-02, MEM-03 complete — memory transparency fully functional via voice
- Plan 02 can proceed (if applicable) or phase can be verified
- Voice session loop requires no changes — memory_node integrates via existing graph invocation path

---

*Phase: 10-memory-transparency*
*Completed: 2026-04-18*
