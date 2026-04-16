---
phase: "08"
plan: "02"
subsystem: orchestrator
tags: [signal-capture, sender-metadata, adaptive-ranking, fire-and-forget]
dependency_graph:
  requires: [adaptive_ranker.get_sender_multipliers]
  provides: [signal_log.metadata_json.sender]
  affects: [orchestrator/nodes.py, profile/adaptive_ranker.py]
tech_stack:
  added: []
  patterns: [defensive-get, fire-and-forget, optional-param-backward-compat]
key_files:
  created:
    - tests/test_capture_signal.py
  modified:
    - src/daily/orchestrator/nodes.py
decisions:
  - "_capture_signal sender param is optional with default None — fully backward-compatible; follow_up signals continue with null metadata"
  - "Sender lookup uses e.get() defensively for both message_id and sender keys — missing keys fall back to None"
  - "Normalisation applied before storage: sender.lower().strip()"
metrics:
  duration_minutes: 12
  completed_at: "2026-04-16T01:15:00Z"
  tasks_completed: 1
  files_changed: 2
---

# Phase 8 Plan 2: Capture Sender in Signal Metadata Summary

## One-liner

`_capture_signal` extended with optional `sender` param that stores normalised email as `metadata_json={"sender": ...}`, wired into `summarise_thread_node`'s expand callsite via `state.email_context` lookup.

## What Was Built

### `src/daily/orchestrator/nodes.py`

Two targeted changes:

1. **`_capture_signal` signature**: Added `sender: str | None = None`. When truthy, normalises via `sender.lower().strip()` and passes `metadata={"sender": normalised}` to `append_signal()`. When `None`, metadata remains `None` — `follow_up` callsite in `respond_node` unchanged.

2. **`summarise_thread_node` expand callsite**: Before firing `asyncio.create_task(_capture_signal(...))`, looks up sender from `state.email_context`:
   ```python
   sender = next(
       (e.get("sender") for e in state.email_context if e.get("message_id") == message_id),
       None,
   )
   ```
   Passes `sender=sender` to `_capture_signal`. Falls back to `None` when `message_id` is unmatched.

### `tests/test_capture_signal.py`

5 new tests:
- `test_capture_signal_with_sender_stores_metadata` — verifies `metadata_json == {"sender": "alice@example.com"}` for mixed-case input
- `test_capture_signal_without_sender_stores_null_metadata` — verifies `metadata is None` for follow_up (backward-compat)
- `test_capture_signal_normalises_sender_lowercase_strip` — verifies `"  BOB@EXAMPLE.COM  "` → `"bob@example.com"`
- `test_summarise_thread_captures_expand_with_sender` — verifies sender propagated from email_context to _capture_signal
- `test_summarise_thread_unknown_message_id_captures_null_sender` — verifies None fallback when message_id not in email_context

## Decisions Made

1. **Backward-compatible `sender=None` default**: `respond_node`'s `follow_up` callsite requires no changes — it passes no sender, metadata stays null.

2. **Defensive `.get()` on email_context entries**: Both `message_id` and `sender` keys accessed via `.get()` to handle entries with missing keys without raising `KeyError`.

3. **Normalisation at capture time**: `lower().strip()` applied in `_capture_signal` so normalisation is centralised and consistent regardless of call site.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — `metadata_json` is now populated for `expand` signals with sender information. The adaptive ranker from Plan 08-01 can now aggregate per-sender multipliers once signal data accumulates.

## Threat Flags

None beyond the plan's threat model (T-08-05, T-08-06, T-08-07 all addressed as designed).

## Self-Check: PASSED

- `src/daily/orchestrator/nodes.py` — FOUND (modified)
- `tests/test_capture_signal.py` — FOUND (created)
- Commit `1de2829` — present in git log
- `pytest tests/test_capture_signal.py` — 5 passed
- Full suite (excluding pre-existing failures in test_action_draft.py, test_briefing_scheduler.py) — 517 passed
