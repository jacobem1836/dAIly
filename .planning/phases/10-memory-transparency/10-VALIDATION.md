# Phase 10: Memory Transparency - Validation

**Created:** 2026-04-18
**Source:** Promoted from 10-RESEARCH.md Validation Architecture section

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| Quick run command | `pytest tests/test_memory.py tests/test_orchestrator_graph.py -x` |
| Full suite command | `pytest tests/ -x` |

## Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | "what do you know about me?" returns up to 10 facts | unit (async) | `pytest tests/test_memory.py -k "list_all_memories_returns_facts" -x` | Wave 0 gap |
| MEM-01 | Returns "I don't know anything about you yet" when no facts | unit (async) | `pytest tests/test_memory.py -k "list_all_memories_empty" -x` | Wave 0 gap |
| MEM-01 | Query bypasses memory_enabled gate (transparency always works) | unit (async) | `pytest tests/test_memory.py -k "list_all_memories_bypasses_memory_enabled" -x` | Wave 0 gap |
| MEM-01 | Results ordered by created_at desc (most recent first) | unit (async) | `pytest tests/test_memory.py -k "list_all_memories_orders_by_created_at_desc" -x` | Wave 0 gap |
| MEM-01 | Respects limit parameter | unit (async) | `pytest tests/test_memory.py -k "list_all_memories_respects_limit" -x` | Wave 0 gap |
| MEM-02 | Delete a specific fact by cosine match; fact no longer returned | unit (async) | `pytest tests/test_memory.py -k "delete_memory_fact_removes_closest_match" -x` | Wave 0 gap |
| MEM-02 | No match found returns None | unit (async) | `pytest tests/test_memory.py -k "delete_memory_fact_no_match" -x` | Wave 0 gap |
| MEM-02 | Delete bypasses memory_enabled gate | unit (async) | `pytest tests/test_memory.py -k "delete_memory_fact_bypasses_memory_enabled" -x` | Wave 0 gap |
| MEM-03 | "forget everything" clears all facts; returns count | unit (async) | `pytest tests/test_memory.py -k "clear_all_memories_deletes_all" -x` | Wave 0 gap |
| MEM-03 | Clear returns 0 when no facts exist | unit (async) | `pytest tests/test_memory.py -k "clear_all_memories_returns_zero_when_empty" -x` | Wave 0 gap |
| MEM-03 | Clear scoped to user (other users unaffected) | unit (async) | `pytest tests/test_memory.py -k "clear_all_memories_scoped_to_user" -x` | Wave 0 gap |
| MEM-03 | Disable memory sets memory_enabled=False; extraction no longer fires | unit (async) | existing `test_extraction_skipped_when_disabled` | EXISTING |
| MEM-01/02/03 | route_intent returns "memory" for query keywords | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "route_intent_memory_query" -x` | Wave 0 gap |
| MEM-01/02/03 | route_intent returns "memory" for delete keywords | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "route_intent_memory_delete" -x` | Wave 0 gap |
| MEM-01/02/03 | route_intent returns "memory" for clear keywords | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "route_intent_memory_clear" -x` | Wave 0 gap |
| MEM-01/02/03 | route_intent returns "memory" for disable keywords | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "route_intent_memory_disable" -x` | Wave 0 gap |
| MEM-01/02/03 | Memory keywords take priority over summarise keywords | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "route_intent_memory_priority_over_summarise" -x` | Wave 0 gap |
| MEM-01/02/03 | build_graph includes memory node | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "build_graph_has_memory_node" -x` | Wave 0 gap |
| All | Fail-silent: DB unavailable returns graceful message | unit (async) | `pytest tests/test_memory.py -k "fail_silent" -x` | Wave 0 gap |

## Sampling Rate

- **Per task commit:** `pytest tests/test_memory.py tests/test_orchestrator_graph.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

## Wave 0 Gaps

All test gaps are extensions to existing test files (no new test files needed):

- [ ] `tests/test_memory.py` — add Phase 10 memory helper tests (list_all_memories, delete_memory_fact, clear_all_memories)
- [ ] `tests/test_orchestrator_graph.py` — add memory routing tests (route_intent memory keywords, build_graph memory node)

## Coverage by Plan

| Plan | Tests Created | Requirements Covered |
|------|---------------|---------------------|
| 10-02 Task 1 | test_memory.py (11 tests), test_orchestrator_graph.py (6 tests) | MEM-01, MEM-02, MEM-03 |

## Security Validation

| ASVS Category | Applies | Standard Control | Verified By |
|---------------|---------|-----------------|-------------|
| V4 Access Control | yes | `WHERE user_id = :user_id` on all memory queries | `test_clear_all_memories_scoped_to_user` |
| V5 Input Validation | yes | spoken description used for embedding only — never as SQL | cosine distance operator (ORM-safe) |
