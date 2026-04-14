---
phase: 03-orchestrator
plan: 01b
subsystem: database
tags: [sqlalchemy, pydantic, langgraph, alembic, signal-log, jsonb, orchestrator]

# Dependency graph
requires:
  - phase: 03-orchestrator
    plan: 01
    provides: UserProfile ORM, Base class, LangGraph ecosystem installed
  - phase: 01-foundation
    provides: Base ORM class, async_session, db engine infrastructure

provides:
  - SignalType enum (skip, correction, re_request, follow_up, expand)
  - SignalLog ORM model (signal_log append-only table)
  - append_signal() async service (D-08 fire-and-forget)
  - daily.orchestrator package with SessionState and OrchestratorIntent
  - Alembic migration 003 covering user_profile and signal_log tables

affects: [03-02, 03-03, orchestrator, profile, personalization]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SignalType as str Enum: values compare directly with DB string values"
    - "append_signal fire-and-forget: callers wrap in asyncio.create_task() to avoid blocking voice path"
    - "OrchestratorIntent Literal whitelist: Pydantic rejects any action not in the four-value set (SEC-05)"
    - "SessionState.messages Annotated[list, add_messages]: LangGraph merge semantics on state update"

key-files:
  created:
    - src/daily/profile/signals.py
    - src/daily/orchestrator/__init__.py
    - src/daily/orchestrator/state.py
    - src/daily/orchestrator/models.py
    - alembic/versions/003_add_user_profile_signal_log.py
    - tests/test_signal_log.py

key-decisions:
  - "SignalLog.signal_type stored as String(50) not PG Enum — avoids migration churn if signal taxonomy evolves"
  - "OrchestratorIntent action whitelist is Literal (not Enum) — Pydantic ValidationError is the enforcement mechanism"
  - "Migration 003 includes user_profile (from Plan 01) and signal_log — combines both tables in one migration"

patterns-established:
  - "OrchestratorIntent Literal whitelist: all LLM output must validate through this before dispatch"
  - "append_signal: always async, always fire-and-forget from caller perspective"

requirements-completed: [PERS-02]

# Metrics
duration: 15min
completed: 2026-04-07
---

# Phase 03 Plan 01b: Signal Log and Orchestrator Type Contracts Summary

**SignalType enum, SignalLog append-only ORM, append_signal service, SessionState with add_messages, and OrchestratorIntent Literal whitelist — completing the PERS-02 data layer and orchestrator type contracts**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-07T13:30:00Z
- **Completed:** 2026-04-07T13:45:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments
- `SignalType` str Enum with five values (skip, correction, re_request, follow_up, expand) per D-07
- `SignalLog` ORM model with append-only schema and JSONB metadata column
- `append_signal()` async service function following D-08 fire-and-forget pattern
- `daily.orchestrator` package with `SessionState` (LangGraph-ready with add_messages annotation) and `OrchestratorIntent` (Literal action whitelist per SEC-05)
- Alembic migration 003 covering both `user_profile` (Plan 01) and `signal_log` tables
- 21 tests all passing

## Task Commits

1. **Task 1 RED: Failing tests for signal log, orchestrator state and intent** - `8531f1d` (test)
2. **Task 1 GREEN: Implementation of all modules and migration** - `3d4842b` (feat)

## Files Created/Modified
- `src/daily/profile/signals.py` - SignalType enum, SignalLog ORM, append_signal() service
- `src/daily/orchestrator/__init__.py` - Empty package init
- `src/daily/orchestrator/state.py` - SessionState Pydantic model with add_messages annotation
- `src/daily/orchestrator/models.py` - OrchestratorIntent with Literal whitelist (SEC-05)
- `alembic/versions/003_add_user_profile_signal_log.py` - Migration for user_profile + signal_log
- `tests/test_signal_log.py` - 21 tests covering enum values, ORM structure, service, SessionState, OrchestratorIntent

## Decisions Made
- `signal_type` stored as `String(50)` rather than a PostgreSQL native Enum — allows adding signal types without schema migrations if the taxonomy grows in Phase 4
- `OrchestratorIntent.action` uses `Literal` (not `Enum`) — Pydantic ValidationError is the enforcement mechanism at parse time, which satisfies SEC-05 without an extra Enum class
- Migration 003 combines both `user_profile` (established in Plan 01 ORM but never migrated) and `signal_log` into a single migration to keep the chain coherent

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required for this plan.

## Next Phase Readiness
- Plan 02 (orchestrator graph) can import `SessionState` from `daily.orchestrator.state` and `OrchestratorIntent` from `daily.orchestrator.models`
- `append_signal()` is ready to be called from graph nodes after any user interaction signal
- Migration 003 brings the schema fully up to date with the ORM definitions through Phase 03 Plan 01b
- `AsyncPostgresSaver` from Plan 01 + `SessionState` from this plan = complete LangGraph checkpointing foundation

---
*Phase: 03-orchestrator*
*Completed: 2026-04-07*

## Self-Check: PASSED

- FOUND: src/daily/profile/signals.py
- FOUND: src/daily/orchestrator/__init__.py
- FOUND: src/daily/orchestrator/state.py
- FOUND: src/daily/orchestrator/models.py
- FOUND: alembic/versions/003_add_user_profile_signal_log.py
- FOUND: tests/test_signal_log.py
- FOUND commit 8531f1d (RED: failing tests)
- FOUND commit 3d4842b (GREEN: implementation)
- All 21 tests pass
