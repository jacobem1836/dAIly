---
phase: 05-voice-interface
plan: 04
subsystem: voice
tags: [voice, tts, stt, langgraph, async-postgres-saver, cli]
dependency_graph:
  requires: [05-01, 05-02, 05-03]
  provides: [run_voice_session, daily-voice-command]
  affects: [src/daily/cli.py, src/daily/voice/__init__.py]
tech_stack:
  added: [langgraph-checkpoint-postgres]
  patterns: [AsyncPostgresSaver, voice-session-loop, voice-approval-flow]
key_files:
  created:
    - src/daily/voice/loop.py
    - tests/test_voice_loop.py
  modified:
    - src/daily/cli.py
    - src/daily/voice/__init__.py
decisions:
  - "AsyncPostgresSaver uses database_url_psycopg (not asyncpg URL) — Pitfall 4 from research"
  - "Module-level imports in loop.py required for pytest patch() to intercept correctly"
  - "Pre-existing test failure in test_action_draft.py::test_draft_node_fetches_sent_emails_from_adapter is out of scope"
metrics:
  completed: "2026-04-13"
  tasks_completed: 1
  tasks_total: 2
  files_created: 2
  files_modified: 2
---

# Phase 05 Plan 04: Voice Session Loop Summary

**One-liner:** Voice session loop with AsyncPostgresSaver persistence, briefing-first turn from Redis cache, and voice approval flow via VoiceTurnManager speak/listen.

## What Was Built

`src/daily/voice/loop.py` provides `run_voice_session()` — the top-level voice session function that mirrors `_run_chat_session()` from `cli.py` but replaces `input()/print()` with `VoiceTurnManager` (mic + speaker I/O).

`src/daily/cli.py` gains a `daily voice` command that calls `asyncio.run(run_voice_session(user_id=1))`.

### Key integration points

- **AsyncPostgresSaver (D-11):** `AsyncPostgresSaver.from_conn_string(settings.database_url_psycopg)` provides persistent session state across voice turns. The psycopg URL (not asyncpg) is used as required by the LangGraph Postgres checkpointer.
- **Briefing-first turn (VOICE-03):** `initialize_session_state()` loads the Redis-cached briefing narrative; if non-empty, it is spoken via `turn_manager.speak()` before waiting for user utterance — sub-1s from cache.
- **Voice approval flow (T-05-10):** `_handle_voice_approval()` reuses `_parse_approval_decision` from `cli.py` — same decision logic as CLI, no bypass path. Draft is spoken, decision is listened for, graph resumed with `Command(resume=decision)`.
- **Barge-in (VOICE-04):** Inherited from `VoiceTurnManager.speak()` which coordinates `TTSPipeline` stop_event with `STTPipeline` speech-started callback.
- **Clean shutdown:** `try/finally` in the main loop sets `listen_stop` event and calls `turn_manager.stop()`.

## Tasks Completed

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| 5-04-01 | run_voice_session + daily voice CLI + tests | Done | ceff76d |
| 5-04-02 | End-to-end voice session verification | Awaiting human verify | — |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Module-level imports required for pytest patching**
- **Found during:** Task 1 (test run)
- **Issue:** `Settings`, `TTSPipeline`, `STTPipeline`, `VoiceTurnManager`, `AsyncPostgresSaver`, `_resolve_email_adapters` were inside the function body, making `patch("daily.voice.loop.Settings", ...)` fail with `AttributeError: does not have the attribute 'Settings'`.
- **Fix:** Moved all patched names to module-level imports in `loop.py`.
- **Files modified:** `src/daily/voice/loop.py`
- **Commit:** ceff76d

### Out-of-scope pre-existing failures

`tests/test_action_draft.py::TestDraftNodeStyleExamples::test_draft_node_fetches_sent_emails_from_adapter` — pre-existing failure confirmed by running on the base commit (cee28c3) before any changes. Logged to deferred-items, not fixed.

## Known Stubs

None — `run_voice_session()` is fully wired to real orchestrator, Redis, and voice I/O. No placeholder data.

## Threat Flags

No new security surface introduced beyond what is in the plan's threat model:
- T-05-10: Approval flow reuses `_parse_approval_decision` — no bypass path confirmed
- T-05-11: AsyncPostgresSaver uses existing database scoped by thread_id
- T-05-12: Transcript input passes through same `route_intent` keyword filter

## Self-Check: PASSED

- [x] `src/daily/voice/loop.py` exists with `run_voice_session()`
- [x] `database_url_psycopg` used (grep confirmed, no asyncpg)
- [x] `checkpointer.setup()` awaited (grep confirmed)
- [x] No `MemorySaver` in loop.py code (only in comments)
- [x] `daily voice` command in cli.py (grep confirmed `def voice`)
- [x] `run_voice_session` exported from `src/daily/voice/__init__.py`
- [x] `uv run pytest tests/test_voice_loop.py -x -q` — 5/5 pass
- [x] `uv run python -c "from daily.voice import run_voice_session"` — import succeeds
- [x] `uv run daily voice --help` — shows voice command help
- [x] Commit ceff76d exists
