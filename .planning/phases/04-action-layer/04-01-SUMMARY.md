---
phase: 04
plan: 01
subsystem: action-layer
tags: [actions, langgraph, approval-gate, audit-log, whitelist, tdd]
dependency_graph:
  requires:
    - 03-03  # LangGraph orchestrator graph (nodes, state, graph)
  provides:
    - action-layer-foundation
    - approval-gate
    - action-audit-log
    - contact-whitelist
  affects:
    - 04-02  # Draft node LLM wiring
    - 04-03  # CLI approval UI
tech_stack:
  added:
    - langgraph.types.interrupt (human-in-the-loop gate)
    - hashlib.sha256 (audit log body integrity)
  patterns:
    - ActionExecutor ABC (validate + execute abstract methods)
    - fire-and-forget asyncio.create_task for audit logging (_log_action)
    - LangGraph interrupt/Command(resume=) approval pattern
key_files:
  created:
    - src/daily/actions/__init__.py
    - src/daily/actions/base.py
    - src/daily/actions/models.py
    - src/daily/actions/log.py
    - src/daily/actions/whitelist.py
    - alembic/versions/004_action_log.py
    - tests/test_action_executor.py
    - tests/test_action_log.py
    - tests/test_action_approval.py
  modified:
    - src/daily/orchestrator/models.py
    - src/daily/orchestrator/state.py
    - src/daily/orchestrator/nodes.py
    - src/daily/orchestrator/graph.py
    - src/daily/profile/models.py
decisions:
  - "draft_node is a stub in Plan 01 — pending_action must already be set in state; full LLM drafting wired in Plan 02"
  - "interrupt() placed at module-level import (not mid-file) for clarity; no try/except wrapper per LangGraph requirements"
  - "SessionState.pending_action typed as Any to avoid circular import with actions.base; always ActionDraft | None at runtime"
  - "route_intent summarise_keywords checked before draft_keywords — summarise thread takes priority over draft keywords"
metrics:
  duration_seconds: 828
  completed_date: "2026-04-11"
  tasks_completed: 3
  files_created: 9
  files_modified: 5
---

# Phase 4 Plan 01: Action Layer Foundation Summary

**One-liner:** Action layer skeleton with ActionExecutor ABC, SHA-256 audit log, contact whitelist, and LangGraph draft→approval→execute gate using interrupt().

## What Was Built

### Action Layer Package (`src/daily/actions/`)

- **`base.py`**: `ActionType` enum (5 whitelisted types), `REQUIRED_SCOPES` dict (OAuth scopes per provider per D-11), `ActionDraft` Pydantic model with `card_text()` for CLI preview, `ActionResult` model with `summary` property, `ActionExecutor` ABC with abstract `validate()` and `execute()` methods (ACT-06).
- **`models.py`**: `ApprovalStatus` enum, `ActionLog` ORM model — append-only, stores `body_hash` (SHA-256 hex) and `content_summary[:200]` only, no raw body column (T-04-03/SEC-04).
- **`log.py`**: `append_action_log()` async service — computes SHA-256 hash, truncates summary, creates row, commits. Mirrors `append_signal` pattern.
- **`whitelist.py`**: `check_recipient_whitelist()` pure function — case-insensitive match against known_addresses set, raises `ValueError` with user-displayable message for unknowns (T-04-04).

### Model Extensions

- **`OrchestratorIntent`**: Literal extended with Phase 4 action types (`draft_email`, `draft_message`, `compose_email`, `schedule_event`, `reschedule_event`). Added `draft_instruction` field. Invalid values (`execute`, `send`, `delete`) still raise `ValidationError` (T-04-01/SEC-05).
- **`SessionState`**: Added `pending_action: Any` (ActionDraft | None at runtime) and `approval_decision: str | None`.
- **`UserPreferences`**: Added `rejection_behaviour: Literal["ask_why", "discard"]` defaulting to `"ask_why"` (D-03).

### LangGraph Approval Gate

- **`draft_node`**: Stub — passes through when `pending_action` is already set; returns guidance message otherwise. Full LLM drafting in Plan 02.
- **`approval_node`**: Calls `interrupt({"preview": ..., "action_type": ...})` without try/except. Pauses graph execution until `Command(resume=...)` is received.
- **`execute_node`**: Checks `approval_decision == "confirm"`, fires `asyncio.create_task(_log_action(...))`, returns appropriate message. Pending_action and approval_decision cleared on completion.
- **`route_intent`**: Extended with `draft_keywords` list. Summarise check takes priority (checked first). Returns `"draft"` for keywords: draft, reply, send, compose, write, schedule, reschedule, book, move, create event, cancel meeting.
- **`build_graph`**: Added `draft → approval → execute → END` chain. No direct edge from START to execute (T-04-02).

### Alembic Migration

- `alembic/versions/004_action_log.py`: Creates `action_log` table with all ActionLog columns. Revises from 003.

## Test Results

- `tests/test_action_executor.py`: 47 tests — ActionDraft, ActionResult, ActionExecutor ABC, ActionLog ORM, whitelist, OrchestratorIntent extensions, SessionState extensions, UserPreferences extensions.
- `tests/test_action_log.py`: 6 tests — SHA-256 hash, 200-char truncation, field correctness.
- `tests/test_action_approval.py`: 23 tests — route_intent keywords, graph topology, interrupt/resume/reject flow, node structural tests.
- **Total: 76 new tests; 340 total suite passes.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Typo in graph.py import**
- **Found during:** Task 2 GREEN phase
- **Issue:** `approve_node` was accidentally included in the import list (copied from draft); correct name is `approval_node`
- **Fix:** Removed `approve_node` from the import, kept single `approval_node` import
- **Files modified:** `src/daily/orchestrator/graph.py`
- **Commit:** 6667bee

**2. [Rule 3 - Blocking] Mid-file interrupt import placement**
- **Found during:** Task 2 GREEN phase
- **Issue:** `from langgraph.types import interrupt` was placed mid-file after function definitions with a noqa comment
- **Fix:** Moved to top-level imports section, removed duplicate mid-file import
- **Files modified:** `src/daily/orchestrator/nodes.py`
- **Commit:** 6667bee

**3. [Rule 1 - Bug] SessionState circular import**
- **Found during:** Task 1a implementation
- **Issue:** Direct `from daily.actions.base import ActionDraft` in state.py would cause circular import (actions.base imports nothing from orchestrator, but future files might)
- **Fix:** Used `Any` type annotation with docstring noting the runtime type. Avoids circular import while preserving documentation intent.
- **Files modified:** `src/daily/orchestrator/state.py`
- **Commit:** f0d884b

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `draft_node` returns `{}` when `pending_action` is set | `src/daily/orchestrator/nodes.py` | Full LLM context reading + body generation is Plan 02 scope |
| `execute_node` returns hardcoded success message | `src/daily/orchestrator/nodes.py` | Real executor dispatch (GmailSendExecutor etc.) is Plan 03 scope |

These stubs are intentional — they allow the approval gate topology and interrupt/resume tests to pass without the full implementation. Plans 02 and 03 will replace them.

## Threat Flags

No new threat surface introduced beyond what was modeled in the plan's threat register (T-04-01 through T-04-06). All mitigations from the threat model were implemented:

| Threat | Mitigation Implemented |
|--------|----------------------|
| T-04-01 | OrchestratorIntent Literal rejects unknown actions (ValidationError) |
| T-04-02 | No direct START→execute edge; approval_node interrupt fires first |
| T-04-03 | ActionLog has no raw body column; only body_hash + content_summary[:200] |
| T-04-04 | check_recipient_whitelist() pure function enforced in whitelist.py |

## Self-Check: PASSED

All 9 created files exist on disk. All 3 task commits verified in git log (f0d884b, 7eedfff, 6667bee). 76 new tests pass, 340 total suite passes.
