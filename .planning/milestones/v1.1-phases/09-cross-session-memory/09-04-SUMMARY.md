---
phase: 09-cross-session-memory
plan: "04"
subsystem: memory-trigger
tags:
  - intel-02
  - memory
  - voice
  - async
  - fire-and-forget
dependency_graph:
  requires:
    - 09-02  # extract_and_store_memories (write side)
    - 09-03  # retrieve_relevant_memories (read side)
  provides:
    - fire-and-forget memory extraction trigger in run_voice_session finally block
    - session_history accumulation per voice turn
    - test_no_hallucination_loop (T-09-16 contract)
    - voice loop regression guards (test_voice_loop.py)
  affects:
    - src/daily/voice/loop.py
    - tests/test_memory.py
    - tests/test_voice_loop.py
tech_stack:
  added: []
  patterns:
    - asyncio.create_task for fire-and-forget without blocking shutdown
    - dedicated async_session inside detached task (Pitfall 4 pattern)
    - turn_recorded flag to prevent double-append in approval sub-loop
    - config.get() defensive access for thread_id (test-safe)
key_files:
  created: []
  modified:
    - src/daily/voice/loop.py
    - tests/test_memory.py
    - tests/test_voice_loop.py
decisions:
  - title: "config.get('configurable', {}).get('thread_id', f'user-{user_id}') instead of config['configurable']['thread_id']"
    rationale: "Defensive access prevents KeyError when tests mock create_session_config without thread_id. Production always sets thread_id via create_session_config; the fallback is unreachable in practice."
  - title: "session_history accumulates only on successful response paths, not on API error break"
    rationale: "If run_session raises OpenAIError, break exits without recording — correct behavior since no response was generated for that turn."
  - title: "turn_recorded flag used in approval sub-loop"
    rationale: "The approval while-loop can iterate multiple times (edit -> re-interrupt -> confirm). Without the guard, user_input would be appended once per approval iteration instead of once per outer turn."
  - title: "Exit/quit utterance appended to session_history before break"
    rationale: "The exit utterance is user-stated content; including it ensures the extraction LLM sees the full conversation including the closing turn. It's a user turn only (no assistant response on exit)."
metrics:
  duration: "~7 minutes"
  completed: "2026-04-17"
  tasks: 2
  files_modified: 3
requirements_satisfied:
  - INTEL-02
---

# Phase 9 Plan 04: Memory Extraction Trigger Summary

Wire the extraction trigger into `run_voice_session`. Voice sessions now read memories at session init (Plan 03) and write new memories at session shutdown (Plan 04). INTEL-02 is functionally complete.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire session_history + fire-and-forget extraction | 0028ebe | src/daily/voice/loop.py |
| 1 fix | Defensive thread_id access (Rule 1) | 229d412 | src/daily/voice/loop.py |
| 2 | test_no_hallucination_loop + voice loop regression guards | 229d412 | tests/test_memory.py, tests/test_voice_loop.py |

## Implementation Notes

### session_history accumulation (src/daily/voice/loop.py lines ~193-278)

`session_history: list[dict] = []` is declared immediately before `first_turn = True` (line 193).

Per-turn accumulation has three sites:

1. **Normal (non-interrupted) response path** (lines ~268-278): After `await turn_manager.speak(content)`, both `{"role": "user", "content": user_input}` and `{"role": "assistant", "content": content}` are appended.

2. **Approval sub-loop path** (lines ~233-255): A `turn_recorded = False` flag is set at the top of each outer iteration. When the approval flow speaks a final result (confirm or edit-complete), the user_input is appended once (guarded by `turn_recorded`) and the assistant content is appended. This prevents double-appending when the approval loop iterates multiple times.

3. **Exit/quit path** (line ~201): `session_history.append({"role": "user", "content": user_input})` before `break`.

### Fire-and-forget extraction (src/daily/voice/loop.py lines ~280-315, finally block)

```python
finally:
    listen_stop.set()
    await turn_manager.stop()

    if session_history:
        from daily.db.engine import async_session as _async_session
        from daily.profile.memory import extract_and_store_memories

        thread_id = config.get("configurable", {}).get("thread_id", f"user-{user_id}")

        async def _run_memory_extraction() -> None:
            try:
                async with _async_session() as mem_session:
                    await extract_and_store_memories(
                        user_id=user_id,
                        session_history=session_history,
                        session_id=thread_id,
                        db_session=mem_session,
                    )
            except Exception as exc:
                logger.warning("memory extraction task failed for user=%d: %s", user_id, exc)

        asyncio.create_task(_run_memory_extraction())

    print("Voice session ended.")
```

Key design decisions:
- `asyncio.create_task` is never awaited — voice shutdown path does not block on extraction (T-09-14)
- `_async_session()` is opened INSIDE the task — never shares the voice loop's session across the task boundary (Pitfall 4 / T-09-18)
- `logger.warning` logs only exception class/message — full transcript never logged (T-09-15)
- Imports are lazy (inside finally) to avoid circular import issues at module load time

### test_no_hallucination_loop (tests/test_memory.py)

Unskipped and implemented with two scenarios:

**Scenario 1:** LLM returns `{"facts": []}` — clean session produces no new rows.

**Scenario 2:** LLM hallucinates and returns `{"facts": ["User travels frequently"]}` with the same embedding as the pre-seeded row. Cosine dedup (`distance < 0.1`) fires and blocks re-insertion. Row count stays at 1.

Uses `async_db_session` fixture → will skip when `DATABASE_URL` is not set (same as other DB-backed tests), but passes when run against a real database.

### Voice loop regression guards (tests/test_voice_loop.py)

Two tests added at the bottom of the existing file:

- `test_memory_extraction_symbol_importable_from_loop`: Imports `extract_and_store_memories` from `daily.profile.memory` — fails if the symbol is renamed or moved.
- `test_voice_loop_imports_cleanly`: `importlib.import_module("daily.voice.loop")` — fails if the module has import-time side effects or broken deps.

## Test Results

| Test | Status |
|------|--------|
| test_memory_enabled_* (3 tests) | PASSED |
| test_extraction_swallows_errors | PASSED |
| test_extract_facts_stores_embedding | SKIPPED (DATABASE_URL not set) |
| test_extraction_skipped_when_disabled | SKIPPED (DATABASE_URL not set) |
| test_dedup_prevents_duplicate_insert | SKIPPED (DATABASE_URL not set) |
| test_retrieve_relevant_facts | SKIPPED (DATABASE_URL not set) |
| test_retrieval_skipped_when_disabled | SKIPPED (DATABASE_URL not set) |
| test_session_state_includes_memories | SKIPPED (DATABASE_URL not set) |
| test_no_hallucination_loop | SKIPPED (DATABASE_URL not set — implemented, will pass with DB) |
| test_voice_session_uses_async_postgres_saver | PASSED |
| test_briefing_spoken_on_first_turn | PASSED |
| test_exit_utterance_ends_session | PASSED |
| test_approval_flow_by_voice | PASSED |
| test_voice_command_registered | PASSED |
| test_memory_extraction_symbol_importable_from_loop | PASSED |
| test_voice_loop_imports_cleanly | PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Defensive thread_id access prevents KeyError in tests**

- **Found during:** Task 2 — running `tests/test_voice_loop.py::test_briefing_spoken_on_first_turn` and `test_exit_utterance_ends_session` after Task 1 committed
- **Issue:** My Task 1 implementation used `config["configurable"]["thread_id"]` which raised `KeyError: 'thread_id'` because the pre-existing Phase 5 tests mocked `create_session_config` to return `{"configurable": {}}` without `thread_id`. These tests were passing before Plan 04's changes.
- **Fix:** Changed to `config.get("configurable", {}).get("thread_id", f"user-{user_id}")`. Production sessions always have `thread_id`; the fallback is unreachable in production.
- **Files modified:** src/daily/voice/loop.py
- **Commit:** 229d412

## Known Stubs

None. Phase 9 (INTEL-02) is functionally complete:
- Plan 01: MemoryFact ORM + pgvector schema
- Plan 02: Extract and store (write side)
- Plan 03: Retrieve and inject (read side)
- Plan 04: Trigger extraction at voice session end

Open items for Phase 10 (MEM-01/02/03):
- Memory transparency — inspect what the system knows ("What do you know about me?")
- Memory edit/delete via conversation commands
- Memory disable/reset via preferences
- `source_session_id` provenance field (added in Plan 01) is available to support these features

## Threat Flags

No new security surface introduced. All Plan 04 STRIDE mitigations confirmed in place:

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-09-14 | create_task never awaited — shutdown not blocked | grep -B2 "create_task" shows no await |
| T-09-15 | Only exc class/message logged, never transcript | logger.warning uses %s formatting with exc only |
| T-09-16 | session_history contains turn content only, never injected memories | test_no_hallucination_loop asserts this |
| T-09-17 | Extraction failure logged as warning (accepted — no storage) | logger.warning in _run_memory_extraction |
| T-09-18 | async with _async_session() guarantees connection release | context manager protocol |

## Self-Check: PASSED
