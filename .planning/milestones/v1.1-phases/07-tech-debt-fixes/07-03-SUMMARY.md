---
phase: 07
plan: 03
subsystem: orchestrator
tags: [bug-fix, tdd, email-context, message-id, security]
dependency_graph:
  requires: []
  provides: [summarise_thread_node-email-context-resolution]
  affects: [orchestrator/nodes.py, tests/test_orchestrator_thread.py]
tech_stack:
  added: []
  patterns: [two-step LLM identify+summarise, email_context resolution]
key_files:
  created: []
  modified:
    - src/daily/orchestrator/nodes.py
    - tests/test_orchestrator_thread.py
decisions:
  - Two-step LLM flow (IDENTIFY then SUMMARISE) required because message_id must be resolved before fetching body
  - Early fallback when email_context empty avoids unnecessary LLM calls
  - Existing TestSummariseThreadNode tests updated to match new two-step flow contract
metrics:
  duration: "~5 minutes"
  completed: "2026-04-15"
  tasks_completed: 2
  files_modified: 2
---

# Phase 07 Plan 03: FIX-03 summarise_thread_node email_context Resolution Summary

Two-step LLM identify+summarise flow resolves real Gmail/Outlook message_id from state.email_context instead of passing user's raw utterance to get_email_body.

## What Was Built

### Bug Fixed

`summarise_thread_node` was passing `last_content` (the user's raw voice utterance, e.g. "summarise the Q2 report email") directly to `adapters[0].get_email_body()`. The Gmail/Outlook adapters expect a real message_id (e.g. `msg-001`), not a natural language string. This caused thread summarisation to silently fail.

### Solution

Replaced the single-step node with a two-step flow:

1. **IDENTIFY step**: LLM receives `state.email_context` via `IDENTIFY_SYSTEM_PROMPT` and picks the `target_id` (message_id) that matches the user's request. Returns `OrchestratorIntent.target_id`.
2. **SUMMARISE step**: `get_email_body(message_id)` fetches real content, `summarise_and_redact()` processes it (SEC-04), then LLM generates summary via `SUMMARISE_SYSTEM_PROMPT`.

Early fallback when `email_context` is empty returns a graceful "couldn't identify which email" message without calling the adapter.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Failing regression tests (RED) | f0dc90e | tests/test_orchestrator_thread.py |
| 2 | Wire email_context + target_id (GREEN) | 2a7fd4e | src/daily/orchestrator/nodes.py, tests/test_orchestrator_thread.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing TestSummariseThreadNode tests for two-step flow**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** 7 existing tests in `TestSummariseThreadNode` called `_make_state()` (no `email_context`) and patched `AsyncOpenAI` class. The new implementation requires non-empty `email_context` to proceed (early fallback) and makes two sequential LLM calls instead of one.
- **Fix:** Updated all `TestSummariseThreadNode` tests to: (a) provide `email_context` via `SessionState` directly, (b) patch `_openai_client` function rather than `AsyncOpenAI` class, (c) use `side_effect=[identify_resp, summarise_resp]` for two-step calls.
- **Files modified:** tests/test_orchestrator_thread.py
- **Commit:** 2a7fd4e

## Known Stubs

None — all changes are functional.

## Threat Flags

No new security surface introduced. Security boundaries explicitly preserved:
- SEC-04/T-03-07: `raw_body` local variable only, passes through `summarise_and_redact()` before use
- SEC-05/T-03-06: No `tools=` parameter on any LLM call
- D-08: Fire-and-forget expand signal still captured

## Out-of-Scope Issues Deferred

Pre-existing `F821` ruff lint error in `_build_executor_for_type` (`-> "ActionExecutor"` forward ref) — unrelated to this plan's changes, not introduced here.

## Self-Check: PASSED

- `src/daily/orchestrator/nodes.py` exists with `IDENTIFY_SYSTEM_PROMPT`, `_format_email_context(state.email_context)`, `intent.target_id`
- `tests/test_orchestrator_thread.py` has 4 new email_context tests + 21 total passing
- Commits f0dc90e and 2a7fd4e exist in git log
- `grep "message_id = last_content" src/daily/orchestrator/nodes.py` returns no match
