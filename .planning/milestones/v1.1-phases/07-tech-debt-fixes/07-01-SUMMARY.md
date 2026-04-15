---
phase: "07"
plan: "01"
subsystem: briefing/ranker
tags: [bug-fix, tdd, email-parsing, rfc2822]
dependency_graph:
  requires: []
  provides: [FIX-01]
  affects: [briefing-ranker, phase-08-signal-collection]
tech_stack:
  added: []
  patterns: [RFC 2822 address normalization, regex-based extraction]
key_files:
  created: []
  modified:
    - src/daily/briefing/ranker.py
    - tests/test_briefing_ranker.py
decisions:
  - "Use _ADDR_RE regex consistent with nodes.py _EMAIL_RE pattern for codebase consistency"
  - "Fix is surgical — only _is_direct_recipient body changed, no weight constants or score_email signature touched"
metrics:
  duration: "~10 min"
  completed: "2026-04-15"
  tasks_completed: 2
  files_modified: 2
---

# Phase 07 Plan 01: FIX-01 RFC 2822 Recipient Normalization Summary

## One-liner

Fixed `_is_direct_recipient` to extract bare email addresses via regex so RFC 2822 display-name format (`"Name <email>"`) correctly scores WEIGHT_DIRECT (10) instead of falling through to WEIGHT_CC (2).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add failing RFC 2822 regression tests (RED) | 823ac60 | tests/test_briefing_ranker.py |
| 2 | Normalize RFC 2822 recipient addresses in _is_direct_recipient (GREEN) | a4e7337 | src/daily/briefing/ranker.py |

## What Was Done

**Bug:** `_is_direct_recipient` compared the full recipient string directly after splitting by comma. When a recipient was formatted as `"Jacob Marriott" <jacob@example.com>`, the lowercase string `'"jacob marriott" <jacob@example.com>'` would never match the bare `"jacob@example.com"` — so all display-name emails mis-scored as WEIGHT_CC (2) instead of WEIGHT_DIRECT (10).

**Fix:** Added `_ADDR_RE = re.compile(r"[\w.+\-]+@[\w.\-]+")` module-level constant (consistent with `nodes.py` `_EMAIL_RE` pattern) and rewrote `_is_direct_recipient` to extract the bare email from each comma-separated part using regex search before comparing. Empty recipient fields return False correctly.

**Tests added (6 new, all passing):**
- `test_direct_recipient_bare_address` — baseline bare address still works
- `test_direct_recipient_display_name` — RFC 2822 format now correctly detected
- `test_direct_recipient_mixed_list` — mixed display-name + bare in one field
- `test_cc_recipient_user_absent` — absent user still scores WEIGHT_CC
- `test_bcc_empty_recipient` — empty recipient field scores WEIGHT_CC
- `test_vip_override_beats_direct` — VIP override still wins (WEIGHT_VIP - WEIGHT_DIRECT == 30)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundary changes introduced.

## Self-Check: PASSED

- `src/daily/briefing/ranker.py` exists and contains `_ADDR_RE`
- `tests/test_briefing_ranker.py` exists and contains `display_name`, `mixed_list`, `vip_override`
- Commits 823ac60 and a4e7337 present in git log
- `uv run pytest tests/test_briefing_ranker.py -x` exits 0 (12/12 passed)
