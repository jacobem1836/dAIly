---
phase: 10-memory-transparency
plan: 02
subsystem: testing
tags: [pytest, memory, pgvector, langgraph, sqlalchemy, asyncio]

# Dependency graph
requires:
  - phase: 10-01
    provides: list_all_memories, delete_memory_fact, clear_all_memories, memory_node, route_intent memory routing
provides:
  - Phase 10 test suite: 19 passing tests for MEM-01, MEM-02, MEM-03 requirements
  - test_memory.py Phase 10 section: 11 DB-backed tests for memory transparency helpers
  - test_orchestrator_graph.py Phase 10 section: 8 tests for routing and graph topology
affects: [phase-11, verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_clear_user_facts() teardown helper to prevent test DB contamination between runs"
    - "DB-backed tests use explicit pre-test cleanup rather than relying on isolation"

key-files:
  created: []
  modified:
    - tests/test_memory.py
    - tests/test_orchestrator_graph.py

key-decisions:
  - "Added _clear_user_facts() helper to delete rows for a user_id before each test — prevents dirty DB failures on repeated runs"
  - "Phase 10 memory tests use dedicated user_id range (30-41) to avoid collision with Phase 9 tests (user_ids 1-20)"

patterns-established:
  - "Pattern: _clear_user_facts() before DB fixture setup ensures clean state regardless of prior run count"

requirements-completed:
  - MEM-01
  - MEM-02
  - MEM-03

# Metrics
duration: 6min
completed: 2026-04-18
---

# Phase 10 Plan 02: Memory Transparency Tests Summary

**19 pytest tests covering list_all_memories, delete_memory_fact, clear_all_memories helpers and memory intent routing — all passing against live PostgreSQL + pgvector**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-18T01:40:55Z
- **Completed:** 2026-04-18T01:47:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- 11 DB-backed tests for Phase 10 memory transparency helpers: list_all_memories (returns facts, limit, empty, gate bypass, ordering), delete_memory_fact (closest match deletion, no match, gate bypass), clear_all_memories (count returned, returns zero when empty, scoped to user)
- 8 tests for route_intent memory keywords and graph topology: query/delete/clear/disable routing, memory priority over summarise_thread, what_do_you_remember, clear_my_memory, build_graph has memory node
- Added _clear_user_facts() helper to clean up stale test DB state before each test — resolves contamination from multiple test runs

## Task Commits

1. **Task 1: Add Phase 10 tests to test_memory.py and test_orchestrator_graph.py** - `4290484` (test)

## Files Created/Modified
- `tests/test_memory.py` - Appended Phase 10 section: 11 tests for list_all_memories, delete_memory_fact, clear_all_memories with _clear_user_facts() cleanup helper
- `tests/test_orchestrator_graph.py` - Appended TestRouteIntentMemory class (7 tests) and TestBuildGraphPhase10 class (1 test)

## Decisions Made
- Used dedicated user_id range 30-41 for Phase 10 tests to avoid collision with Phase 9 user_ids (1-20)
- Added _clear_user_facts() pre-test cleanup to handle shared persistent DB state — tests were previously failing on re-runs due to stale rows

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added _clear_user_facts() cleanup helper**
- **Found during:** Task 1 (Phase 10 test execution)
- **Issue:** Tests failed on re-run because DB had stale MemoryFact rows from prior test runs. The test DB is shared and persistent, not reset between runs. Tests asserting exact row counts were seeing accumulated data.
- **Fix:** Added `_clear_user_facts(user_id, session)` helper that deletes all MemoryFact rows for a given user_id before each test inserts its fixtures. Added to all 9 tests that insert rows.
- **Files modified:** tests/test_memory.py
- **Verification:** All 19 Phase 10 tests pass on repeated runs
- **Committed in:** 4290484 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug: test state contamination)
**Impact on plan:** Required for test reliability. No scope creep.

## Issues Encountered
- Pre-existing test failures in Phase 9 tests (test_dedup_prevents_duplicate_insert, test_no_hallucination_loop, test_session_state_includes_memories) due to dirty DB state — these are pre-existing issues not introduced by this plan. Logged in deferred-items.
- Wave 1 source files (memory.py, models.py, session.py, state.py, nodes.py, graph.py) needed to be restored from HEAD in the worktree since working tree was behind staged index after soft reset.

## Known Stubs
None — no placeholder or hardcoded values in test files that prevent plan goals from being achieved.

## Threat Flags
None — test-only files, no new production surface introduced.

## Next Phase Readiness
- All MEM-01, MEM-02, MEM-03 requirements verified by passing tests
- Phase 10 test suite complete — ready for verification phase
- Pre-existing Phase 9 test failures (DB contamination) should be addressed in a separate tech-debt pass

## Self-Check: PASSED
- tests/test_memory.py: FOUND with Phase 10 section including test_list_all_memories_returns_facts
- tests/test_orchestrator_graph.py: FOUND with TestRouteIntentMemory and TestBuildGraphPhase10
- Commit 4290484: EXISTS

---
*Phase: 10-memory-transparency*
*Completed: 2026-04-18*
