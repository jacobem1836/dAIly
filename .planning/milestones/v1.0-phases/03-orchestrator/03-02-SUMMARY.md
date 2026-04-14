---
phase: 03-orchestrator
plan: 02
subsystem: orchestrator
tags: [langgraph, openai, gpt-4.1, gpt-4.1-mini, orchestrator, cli, briefing, security]

# Dependency graph
requires:
  - phase: 03-orchestrator
    plan: 01
    provides: UserProfile ORM, LangGraph ecosystem, Settings.database_url_psycopg
  - phase: 03-orchestrator
    plan: 01b
    provides: SessionState, OrchestratorIntent, SignalType, append_signal, SignalLog
  - phase: 02-briefing-pipeline
    provides: BriefingOutput cache, summarise_and_redact, EmailAdapter base class

provides:
  - build_graph(): compiled LangGraph StateGraph with respond + summarise_thread nodes
  - route_intent(): conditional routing dispatch on message keywords
  - run_session(): session entry point via graph.ainvoke (Pitfall 2 compliant)
  - set_email_adapters() / get_email_adapters(): runtime adapter registry
  - create_session_config(): scoped thread_id per user per date (T-03-04)
  - initialize_session_state(): loads cached briefing + profile into initial state
  - respond_node(): GPT-4.1 mini follow-up answer node (SEC-05 enforced)
  - summarise_thread_node(): GPT-4.1 thread summarisation node (SEC-02/SEC-04)
  - daily chat CLI command with real adapter wiring (BRIEF-07)

affects: [03-03, phase-05, briefing, personalization, voice-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "route_intent keyword dispatch: pure function on state.messages[-1].content — no user-controlled code execution"
    - "Adapter registry pattern: module-level list in session.py, injected at CLI startup, consumed by nodes at call time"
    - "SEC-05 enforcement: response_format=json_object + OrchestratorIntent.model_validate_json() — no tools= parameter on any LLM call"
    - "SEC-04/T-03-07: raw_body is a local variable only in summarise_thread_node — never assigned to state fields"
    - "D-08 fire-and-forget: asyncio.create_task(_capture_signal()) — signal write never blocks voice response path"
    - "Dual-model routing: gpt-4.1-mini for respond (low latency), gpt-4.1 for summarise_thread (reasoning-heavy)"
    - "Module-level orchestrator imports in cli.py for test patchability (set_email_adapters, build_graph, run_session)"

key-files:
  created:
    - src/daily/orchestrator/graph.py
    - src/daily/orchestrator/session.py
    - src/daily/orchestrator/nodes.py
    - tests/test_orchestrator_graph.py
    - tests/test_orchestrator_thread.py
    - tests/test_cli_chat.py
  modified:
    - src/daily/cli.py (added chat command, _run_chat_session, _resolve_email_adapters)

key-decisions:
  - "Module-level imports in cli.py for session functions — required for test patchability; local imports inside _run_chat_session cannot be patched via daily.cli.X"
  - "tools= check in tests uses ast.parse + keyword arg inspection, not source text grep — docstrings may reference 'tools=' as security notes"
  - "summarise_and_redact moved to module-level import in nodes.py — enables patch('daily.orchestrator.nodes.summarise_and_redact') in tests"
  - "MemorySaver used for Phase 3 CLI — AsyncPostgresSaver deferred to Phase 5 FastAPI lifespan"
  - "message_id for summarise_thread_node passes user message content as-is to adapter in Phase 3 — real ID extraction deferred to Phase 5"

patterns-established:
  - "Orchestrator graph topology: START -> conditional edge -> [respond | summarise_thread] -> END"
  - "session.py adapter registry: set before build_graph(), consumed by nodes via get_email_adapters() at call time"
  - "CLI async bridge: asyncio.run(_run_chat_session()) in Typer command, all infra calls inside async helper"

requirements-completed: [BRIEF-07, PERS-02]

# Metrics
duration: 10min
completed: 2026-04-07
---

# Phase 03 Plan 02: Orchestrator Graph and CLI Chat Summary

**LangGraph orchestrator with dual-model routing, SEC-05 intent validation, SEC-04 redaction boundary, and `daily chat` CLI command wiring real email adapters for BRIEF-07 thread summarisation**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-07T13:29:09Z
- **Completed:** 2026-04-07T13:39:00Z
- **Tasks:** 3 (all TDD: RED + GREEN)
- **Tests:** 49 total (22 graph/session + 17 nodes + 10 CLI)
- **Files modified:** 7

## Accomplishments

- `graph.py`: StateGraph with respond + summarise_thread nodes, `route_intent` conditional edge dispatching on message keywords, `build_graph()` accepting any checkpointer
- `session.py`: email adapter registry (`set_email_adapters`/`get_email_adapters`), scoped `thread_id` per user per date (T-03-04), `initialize_session_state` loads cached briefing + profile, `run_session` via `ainvoke` (Pitfall 2 compliant — never `invoke`)
- `nodes.py`: `respond_node` (GPT-4.1 mini, response_format=json_object, OrchestratorIntent validation, follow_up signal fire-and-forget), `summarise_thread_node` (GPT-4.1, raw body through summarise_and_redact before state write SEC-04, expand signal fire-and-forget, no-adapters fallback)
- `cli.py chat` command: `_resolve_email_adapters` following scheduler.py token decryption pattern, `_run_chat_session` interactive loop, BRIEF-07 fully invocable
- All security mitigations from threat model implemented: T-03-04, T-03-06, T-03-07, T-03-12

## Task Commits

1. **Task 1 RED: failing tests for graph and session** — `58b379d` (test)
2. **Task 1 GREEN: graph.py, session.py, nodes.py (stub)** — `233f97c` (feat)
3. **Task 2 RED+GREEN: node tests pass, nodes.py complete** — `f0ff8a1` (feat)
4. **Task 3 RED: failing tests for CLI chat** — `4f8e141` (test)
5. **Task 3 GREEN: CLI chat command** — `b3ae747` (feat)

## Files Created/Modified

- `src/daily/orchestrator/graph.py` — `build_graph()`, `route_intent()`, StateGraph topology
- `src/daily/orchestrator/session.py` — adapter registry, session config, `run_session()`
- `src/daily/orchestrator/nodes.py` — `respond_node`, `summarise_thread_node`, `_capture_signal()`
- `src/daily/cli.py` — `chat` command, `_run_chat_session`, `_resolve_email_adapters`, module-level session imports
- `tests/test_orchestrator_graph.py` — 22 tests: build_graph, route_intent, session config, run_session, adapter registry
- `tests/test_orchestrator_thread.py` — 17 tests: respond_node, summarise_thread_node, SEC-05/04 enforcement, signals
- `tests/test_cli_chat.py` — 10 tests: command registration, adapter wiring, thread_id pattern, interactive loop

## Decisions Made

- Module-level imports in `cli.py` for orchestrator session functions so tests can patch them via `daily.cli.X`
- `tools=` presence verified via AST keyword-argument inspection (not source grep) because docstrings legitimately reference the string as a security note
- `summarise_and_redact` imported at module level in `nodes.py` (not inside function) so `patch('daily.orchestrator.nodes.summarise_and_redact')` works in tests
- `MemorySaver` used for Phase 3 CLI; `AsyncPostgresSaver` deferred to Phase 5 FastAPI lifespan (as designed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] summarise_and_redact local import not patchable**
- **Found during:** Task 2 node tests
- **Issue:** `summarise_and_redact` imported inside `summarise_thread_node` function body — `patch("daily.orchestrator.nodes.summarise_and_redact")` raised AttributeError
- **Fix:** Moved to module-level import so the name exists in the module namespace
- **Files modified:** `src/daily/orchestrator/nodes.py`
- **Commit:** `f0ff8a1`

**2. [Rule 1 - Bug] test_respond_node_does_not_use_tools_parameter matched docstring text**
- **Found during:** Task 2 node tests
- **Issue:** Source-text grep for `tools=` matched security comment strings in docstrings
- **Fix:** Changed test to inspect actual `chat.completions.create` call_kwargs at runtime
- **Files modified:** `tests/test_orchestrator_thread.py`
- **Commit:** `f0ff8a1`

**3. [Rule 1 - Bug] Redis mock not async in CLI tests**
- **Found during:** Task 3 CLI tests
- **Issue:** `patch("daily.cli.Redis")` returned plain `MagicMock`; `redis.aclose()` is awaited and raised `TypeError: object MagicMock can't be used in 'await' expression`
- **Fix:** Created `_mock_redis()` helper returning `AsyncMock` instance with `aclose = AsyncMock()`; also created `_mock_async_session_ctx()` for `async_session` context manager
- **Files modified:** `tests/test_cli_chat.py`
- **Commit:** `b3ae747`

**4. [Rule 1 - Bug] orchestrator imports inside _run_chat_session not patchable**
- **Found during:** Task 3 CLI tests
- **Issue:** `set_email_adapters`, `build_graph`, `run_session` etc. imported inside `_run_chat_session` function body — tests cannot patch `daily.cli.set_email_adapters`
- **Fix:** Moved orchestrator session imports to module level in `cli.py`
- **Files modified:** `src/daily/cli.py`
- **Commit:** `b3ae747`

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `message_id = last_content` (user message used as adapter message_id) | `src/daily/orchestrator/nodes.py` | 151 | Phase 3 best-effort: real message_id extraction from briefing context requires Phase 5 wiring where briefing metadata is available in SessionState. Adapter receives user's raw text — matching by subject is adapter-specific. |

This stub does not prevent the plan's goal (BRIEF-07 is invocable, adapter is called) but real thread lookup requires Phase 5 context enrichment.

## Threat Flags

No new threat surface beyond the threat model already documented in the plan.

All STRIDE mitigations implemented:
- T-03-04: thread_id scoping (user-{id}-{date}) — in `session.py`
- T-03-05: prompt injection via summarise_and_redact — in `nodes.py`
- T-03-06: no tools= on any LLM call — verified by AST + runtime test
- T-03-07: raw_body local variable only — verified by state inspection test
- T-03-12: token decryption in-memory only — follows scheduler.py pattern

## Self-Check: PASSED

- FOUND: src/daily/orchestrator/graph.py
- FOUND: src/daily/orchestrator/session.py
- FOUND: src/daily/orchestrator/nodes.py
- FOUND: src/daily/cli.py (chat command added)
- FOUND: tests/test_orchestrator_graph.py
- FOUND: tests/test_orchestrator_thread.py
- FOUND: tests/test_cli_chat.py
- FOUND commit 58b379d (Task 1 RED)
- FOUND commit 233f97c (Task 1 GREEN)
- FOUND commit f0ff8a1 (Task 2)
- FOUND commit 4f8e141 (Task 3 RED)
- FOUND commit b3ae747 (Task 3 GREEN)
- All 49 tests pass

---
*Phase: 03-orchestrator*
*Completed: 2026-04-07*
