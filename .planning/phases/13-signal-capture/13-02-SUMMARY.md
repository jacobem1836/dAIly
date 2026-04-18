---
phase: 13-signal-capture
plan: 02
subsystem: briefing-pipeline / orchestrator-session
tags: [signal-tracking, briefing-items, redis-cache, session-state]
dependency_graph:
  requires: []
  provides: [BriefingItem, build_briefing_items, briefing_items redis key, SessionState.briefing_items]
  affects: [src/daily/briefing/pipeline.py, src/daily/orchestrator/session.py, src/daily/orchestrator/state.py]
tech_stack:
  added: []
  patterns: [BriefingItem Pydantic model, Redis item cache with TTL, graceful degradation on cache failure]
key_files:
  created: [src/daily/briefing/items.py]
  modified: [src/daily/orchestrator/state.py, src/daily/briefing/pipeline.py, src/daily/orchestrator/session.py]
decisions:
  - Use list[dict] for SessionState.briefing_items to avoid LangGraph checkpointer serialisation issues with Pydantic nested models
  - Use CalendarEvent.attendees[0] as organizer proxy since CalendarEvent has no organizer field
  - Use MessageMetadata.sender_id (not .sender) for Slack item sender
  - Wrap item cache write in try/except so pipeline always delivers even if item caching fails
metrics:
  duration: ~15 minutes
  completed: 2026-04-18
  tasks: 2
  files: 4
---

# Phase 13 Plan 02: Item Tracking Infrastructure Summary

BriefingItem model with Redis item list caching and SessionState tracking fields wired end-to-end.

## What Was Built

### Task 1: BriefingItem model and SessionState extensions

Created `src/daily/briefing/items.py` with:
- `BriefingItem(BaseModel)` — five primitive fields: `item_id`, `type`, `sender`, `sentence_range_start`, `sentence_range_end`
- `_split_sentences(text)` — same regex as `voice/loop.py` (Pitfall 5: cursor sync)
- `build_briefing_items(context, narrative)` — distributes narrative sentences proportionally across email/calendar/slack items

Extended `SessionState` in `src/daily/orchestrator/state.py`:
- `briefing_items: list[dict]` — stores item dicts (not BriefingItem objects) for LangGraph serialisation
- `current_item_index: int = 0` — tracks which item the user is currently hearing

### Task 2: Pipeline cache and session init wiring

Updated `src/daily/briefing/pipeline.py`:
- Imports `json`, `CACHE_TTL`, and `build_briefing_items`
- After narrative cache, writes item list to `briefing:{user_id}:{date}_items` key in Redis
- Wrapped in try/except — item cache failure does not block briefing delivery

Updated `src/daily/orchestrator/session.py`:
- Imports `json` and `_cache_key`
- After briefing load, reads `_items` key from Redis if briefing exists
- Returns `briefing_items` and `current_item_index: 0` in the initial state dict

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CalendarEvent has no `organizer` field**
- **Found during:** Task 1 implementation
- **Issue:** Plan's code used `getattr(event, "organizer", "")` but `CalendarEvent` only has `attendees: list[str]`
- **Fix:** Use `event.attendees[0]` as organizer proxy when attendees present, else empty string
- **Files modified:** `src/daily/briefing/items.py`
- **Commit:** bec5174

**2. [Rule 1 - Bug] MessageMetadata uses `sender_id`, not `sender`**
- **Found during:** Task 1 implementation
- **Issue:** Plan's code used `getattr(msg, "sender", "")` but `MessageMetadata` has `sender_id`
- **Fix:** Use `msg.sender_id` directly (not via getattr)
- **Files modified:** `src/daily/briefing/items.py`
- **Commit:** bec5174

**3. [Rule 2 - Missing critical functionality] Import `_cache_key` at module level**
- **Found during:** Task 2 implementation
- **Issue:** Plan suggested using `from daily.briefing.cache import _cache_key` as an inline import inside the function. The function is already importing from that module at the top level.
- **Fix:** Added `_cache_key` to the top-level import in `session.py` instead of an inline import, which is cleaner and avoids the `noqa: PLC0415` suppression.
- **Files modified:** `src/daily/orchestrator/session.py`
- **Commit:** 96ecfb2

## Test Results

- Pre-existing failures (3 tests) confirmed to exist before changes: `test_draft_node_fetches_sent_emails_from_adapter`, `test_vip_override`, `test_briefing_spoken_on_first_turn`
- No new test failures introduced by this plan
- 598 tests pass, 18 skipped

## Known Stubs

None. All fields are wired: `build_briefing_items` constructs real items from context, pipeline writes to Redis, session reads from Redis, and SessionState carries the values.

## Threat Flags

No new threat surface beyond what is documented in the plan's threat model (T-13-03 and T-13-04). Items key is constructed from system-controlled user_id and date. JSON parsed with stdlib `json.loads` (not eval/pickle).

## Self-Check: PASSED

- FOUND: src/daily/briefing/items.py
- FOUND: src/daily/orchestrator/state.py (modified)
- FOUND: src/daily/briefing/pipeline.py (modified)
- FOUND: src/daily/orchestrator/session.py (modified)
- FOUND: .planning/phases/13-signal-capture/13-02-SUMMARY.md
- FOUND: commit bec5174 (Task 1)
- FOUND: commit 96ecfb2 (Task 2)
