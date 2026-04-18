---
phase: 13-signal-capture
plan: "03"
subsystem: orchestrator / voice-loop
tags: [signals, skip, re-request, voice, barge-in, item-cursor]
dependency_graph:
  requires:
    - src/daily/briefing/items.py (BriefingItem, _split_sentences — Plan 02)
    - src/daily/orchestrator/state.py (briefing_items, current_item_index — Plan 02)
    - src/daily/profile/signals.py (SignalType, append_signal)
  provides:
    - src/daily/orchestrator/nodes.py (skip_node, re_request_node, _get_current_item_sender)
    - src/daily/orchestrator/graph.py (skip/re_request routing, node registration)
    - src/daily/voice/loop.py (item cursor tracking, implicit skip detection)
  affects:
    - src/daily/orchestrator/graph.py (route_intent priority order updated)
    - src/daily/voice/loop.py (_split_sentences delegates to shared implementation)
tech_stack:
  added: []
  patterns:
    - Fire-and-forget signal capture via asyncio.create_task()
    - Keyword-based intent routing (no user-controlled code execution)
    - Barge-in + silence threshold for implicit skip detection
    - Sentence boundary item cursor advancement
key_files:
  created: []
  modified:
    - src/daily/orchestrator/nodes.py
    - src/daily/orchestrator/graph.py
    - src/daily/voice/loop.py
decisions:
  - id: D-A
    summary: "Kept _split_sentences as a local wrapper in loop.py (delegating to items.py) rather than removing the function, to avoid updating all call sites in the voice loop resume re-entry block"
requirements:
  - SIG-01
  - SIG-02
metrics:
  duration_minutes: 18
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_created: 0
  files_modified: 3
---

# Phase 13 Plan 03: Orchestrator Signal Nodes and Voice Loop Cursor — Summary

**One-liner:** skip_node and re_request_node in the orchestrator fire typed signals with current-item sender, while the voice loop advances an item cursor and fires implicit skip on barge-in + 2s silence.

## What Was Built

### Task 1: skip_node and re_request_node

Added to `src/daily/orchestrator/nodes.py`:

- `_get_current_item_sender(state)` — defensive helper that reads `state.briefing_items[current_item_index].sender`, returning `None` if items are empty or index is out of range (old cached briefing graceful degradation per Pitfall 2)
- `skip_node(state)` — fires `SignalType.skip` via `asyncio.create_task(_capture_signal(...))` with current item sender as `target_id`, returns "Skipping to the next item."
- `re_request_node(state)` — fires `SignalType.re_request` and re-speaks the current item's sentences extracted via `_split_sentences` on `state.briefing_narrative`

Updated `src/daily/orchestrator/graph.py`:

- `route_intent()` now checks `skip_keywords = ["skip", "next", "move on", "next item", "skip this"]` and `re_request_keywords = ["repeat that", "say that again", "repeat", "say again", "come again", "pardon", "what was that"]` at priority slots 3 and 4 (after memory and resume_briefing, before summarise)
- `build_graph()` registers "skip" and "re_request" nodes with terminal `END` edges
- Conditional edges map updated with "skip" and "re_request" entries

### Task 2: Voice Loop Item Cursor and Implicit Skip

Updated `src/daily/voice/loop.py`:

- `from daily.profile.signals import SignalType` added at module level
- `_split_sentences()` now delegates to `daily.briefing.items._split_sentences` for cursor sync (Pitfall 5)
- `_capture_signal_inline()` async helper added — mirrors `_capture_signal` in nodes.py but avoids circular imports
- Briefing delivery loop now:
  1. Loads `briefing_items` and `current_item_idx = 0` before iterating sentences
  2. Advances `current_item_idx` when `i >= item.sentence_range_end`
  3. On barge-in: calls `asyncio.wait_for(turn_manager.wait_for_utterance(), timeout=2.0)`
  4. On timeout (silence): fires `_capture_signal_inline(user_id, SignalType.skip, sender)` and continues
  5. On spoken utterance: stores as `initial_state["_pending_utterance"]` and breaks (existing interruption flow)
- Surfaces `current_item_index` into `initial_state` after briefing delivery

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add skip_node and re_request_node to orchestrator | bcf29f5 | src/daily/orchestrator/nodes.py, src/daily/orchestrator/graph.py |
| 2 | Wire voice loop item cursor and implicit skip detection | b13309a | src/daily/voice/loop.py |

## Deviations from Plan

### Auto-fixed Issues

None.

### Minor Adjustments

**1. [D-A] Kept _split_sentences as wrapper in loop.py**
- **Found during:** Task 2
- **Reason:** The resume briefing re-entry block (lines 320-335) also calls `_split_sentences`. Removing the function would require updating those call sites. A local wrapper that delegates to the shared implementation is cleaner and maintains all call sites unchanged.
- **Impact:** Same behavior, one extra function in the file. Pitfall 5 is still satisfied — both paths use `daily.briefing.items._split_sentences`.

## Test Results

- Pre-existing failures (3 tests) confirmed to exist before these changes: `test_draft_node_fetches_sent_emails_from_adapter`, `test_vip_override`, `test_briefing_spoken_on_first_turn`
- No new test failures introduced by this plan
- 598 tests pass, 18 skipped

## Known Stubs

None. Both skip_node and re_request_node fire real signals via the established `_capture_signal` pattern. The voice loop cursor is wired to real `briefing_items` from Redis via `initial_state`.

## Threat Flags

No new threat surface beyond what is documented in the plan's threat model (T-13-05, T-13-06, T-13-07 all accepted/mitigated by existing patterns). The `target_id` passed to signals is always sourced from server-side `briefing_items` (Redis cache), never from the user transcript.

## Self-Check: PASSED

- [x] `src/daily/orchestrator/nodes.py` contains `async def skip_node`
- [x] `src/daily/orchestrator/nodes.py` contains `async def re_request_node`
- [x] `src/daily/orchestrator/nodes.py` contains `def _get_current_item_sender`
- [x] `src/daily/orchestrator/graph.py` contains `skip_keywords` and `re_request_keywords`
- [x] `src/daily/orchestrator/graph.py` `route_intent` returns "skip" for "skip this"
- [x] `src/daily/orchestrator/graph.py` `route_intent` returns "re_request" for "repeat that"
- [x] `src/daily/voice/loop.py` contains `_capture_signal_inline`
- [x] `src/daily/voice/loop.py` contains `SignalType.skip` in implicit skip block
- [x] `src/daily/voice/loop.py` contains `current_item_idx` cursor tracking
- [x] `src/daily/voice/loop.py` contains `implicit_skip_threshold = 2.0`
- [x] Commit bcf29f5 exists (Task 1)
- [x] Commit b13309a exists (Task 2)
