---
phase: 07-tech-debt-fixes
plan: 03
subsystem: orchestrator
tags: [fix, thread-summarisation, email-context, tdd]
dependency_graph:
  requires: []
  provides: [email-context-resolution]
  affects: [summarise_thread_node, orchestrator-thread-tests]
tech_stack:
  added: []
  patterns: [case-insensitive-substring-match, early-return-on-no-match]
key_files:
  created: []
  modified:
    - src/daily/orchestrator/nodes.py
    - tests/test_orchestrator_thread.py
decisions:
  - "Two-pass matching: first check full substring match on subject/sender, then word-level match for longer queries"
  - "Return early with clear error when no email_context match — no fallback to last_content"
  - "Updated existing TestSummariseThreadNode tests to provide email_context (Rule 1 auto-fix)"
metrics:
  duration: "~15min"
  completed: "2026-04-17"
  tasks_completed: 2
  files_modified: 2
---

# Phase 07 Plan 03: Fix message_id Resolution in summarise_thread_node Summary

**One-liner:** Replaced `message_id = last_content` stub with `_resolve_message_id()` helper that searches `state.email_context` by subject/sender substring match, returning a clear error on no match.

## What Was Built

### `_resolve_message_id(user_query, email_context)` helper

A new pure function added above `summarise_thread_node` in `nodes.py`. Uses two-pass case-insensitive substring matching:

1. First pass: checks if the full subject or sender appears as a substring in the user's query
2. Second pass: tokenises the query into words (>3 chars) and checks each word against subject/sender

Returns `message_id` of the first match, or `None` if no email matches.

### Updated `summarise_thread_node`

The stub block:
```python
message_id = last_content  # pass through so adapter can match by subject/id
```

Replaced with:
```python
message_id = _resolve_message_id(last_content, state.email_context)
if message_id is None:
    return {"messages": [AIMessage(content="I can't find that email ...")]}
```

Node returns early with a user-friendly error when no match is found — the adapter is never called with garbage input.

### Test Updates

- Added `TestSummariseThreadNodeResolution` class (5 new tests) covering subject match, sender match, empty context, no-match, and case-insensitive matching
- Updated `_make_state` helper to accept `email_context` parameter
- Added `SAMPLE_EMAIL_CONTEXT` module-level fixture
- Updated 6 existing tests in `TestSummariseThreadNode` to provide proper `email_context` so they test real behavior (not stub behavior)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing tests incompatible with new implementation**
- **Found during:** Task 2 GREEN phase
- **Issue:** 6 existing tests in `TestSummariseThreadNode` called `summarise_thread_node` with empty `email_context`, then asserted adapter was called. With the fix, empty context returns an error early — adapter never reached.
- **Fix:** Updated each test to provide a minimal `email_context` entry matching the user message, restoring original test intent (verify adapter is called when email matches).
- **Files modified:** `tests/test_orchestrator_thread.py`
- **Commit:** 0965e72

## Verification Results

```
22 passed, 2 warnings in 0.77s
```

All 5 new resolution tests pass. All 17 pre-existing tests pass. No regressions.

Manual grep checks:
- `message_id = last_content` NOT in `nodes.py` — stub completely removed
- `_resolve_message_id` exists in `nodes.py`
- `state.email_context` used in `summarise_thread_node`
- `"I can't find that email"` exists in `nodes.py`

## Known Stubs

None — `_resolve_message_id` is fully wired and returns real message_ids from email_context.

## Threat Flags

None — no new network endpoints or auth paths introduced. The `_resolve_message_id` function performs substring matching on metadata only (T-07-05: accepted, no security-sensitive action on match result). The `summarise_and_redact()` boundary (T-07-06: accepted, SEC-04 preserved) is unchanged.

## Self-Check: PASSED

- `src/daily/orchestrator/nodes.py` — exists, contains `_resolve_message_id`, `email_context`, `I can't find that email`
- `tests/test_orchestrator_thread.py` — exists, contains `TestSummariseThreadNodeResolution`, `SAMPLE_EMAIL_CONTEXT`, `_make_state` with `email_context` param
- Commits verified: `11238d1` (RED tests), `0965e72` (implementation + GREEN)
