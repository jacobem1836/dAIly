---
phase: 16-milestone-closeout
plan: "01"
subsystem: observability, orchestrator, voice
tags: [logging, structured-logging, validation, tech-debt, milestone-closeout]
dependency_graph:
  requires: [14-observability, 15-deployment]
  provides: [v1.2-milestone-complete]
  affects: [adaptive_ranker, orchestrator-nodes, voice-loop]
tech_stack:
  added: []
  patterns: [make_logger factory with stage context, VALIDATION.md compliance]
key_files:
  created: []
  modified:
    - .planning/phases/14-observability/14-VALIDATION.md
    - .planning/phases/15-deployment/15-VALIDATION.md
    - src/daily/profile/adaptive_ranker.py
    - src/daily/orchestrator/nodes.py
    - src/daily/voice/loop.py
decisions:
  - Pre-existing test failure in test_action_draft.py confirmed out-of-scope (exists on base commit before any changes)
metrics:
  duration: ~8 minutes
  completed: 2026-04-19
  tasks_completed: 2
  files_modified: 5
---

# Phase 16 Plan 01: v1.2 Tech Debt Closeout Summary

Close all v1.2 tech debt: mark Phase 14 and 15 VALIDATION.md files as compliant, and migrate three hot-path modules from bare `logging.getLogger` to the `make_logger` factory with stage context.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update Phase 14 and Phase 15 VALIDATION.md to compliant | 7a5e251 | 14-VALIDATION.md, 15-VALIDATION.md |
| 2 | Adopt make_logger in adaptive_ranker.py, nodes.py, voice/loop.py | 956910c | adaptive_ranker.py, nodes.py, loop.py |

## What Was Done

### Task 1: VALIDATION.md files

Both validation files were stuck at `status: draft` / `nyquist_compliant: false` despite all tests passing and the phases being fully verified. Updated YAML frontmatter and sign-off sections:

- `status: draft` → `status: compliant`
- `nyquist_compliant: false` → `nyquist_compliant: true`
- `wave_0_complete: false` → `wave_0_complete: true`
- All sign-off checkboxes ticked `[x]`
- Approval field updated with date and rationale

### Task 2: make_logger adoption

Three Phase 13 modules were using bare `logging.getLogger(__name__)` instead of the `make_logger` factory introduced in Phase 14. This meant their log records lacked `stage` context in the structured JSON output.

Changes made:

- `adaptive_ranker.py`: `import logging` replaced with `from daily.logging_config import make_logger`; logger initialised as `make_logger(__name__, stage="ranker")`
- `orchestrator/nodes.py`: same pattern; `stage="orchestrator"`
- `voice/loop.py`: same pattern; `stage="voice"`

No call-site changes required — `LoggerAdapter` returned by `make_logger` is API-compatible with `Logger` for all `logger.info/warning/error(...)` usages.

## Deviations from Plan

None — plan executed exactly as written.

One pre-existing test failure observed (`test_draft_node_fetches_sent_emails_from_adapter`) confirmed to exist on the base commit before any changes were made. Out of scope for this plan.

## Verification Results

```
grep "logging.getLogger" src/daily/profile/adaptive_ranker.py src/daily/orchestrator/nodes.py src/daily/voice/loop.py
→ CLEAN (no matches)

grep "make_logger" src/daily/profile/adaptive_ranker.py src/daily/orchestrator/nodes.py src/daily/voice/loop.py
→ 6 matches (2 per file: import + initialisation)

grep "nyquist_compliant: true" .planning/phases/14-observability/14-VALIDATION.md .planning/phases/15-deployment/15-VALIDATION.md
→ matches in both files

pytest tests/ -x -q (excluding pre-existing failure)
→ 33 passed
```

## Known Stubs

None.

## Threat Flags

None — no new trust boundaries introduced. Changes are mechanical logging import refactor and documentation updates only.

## Self-Check: PASSED

- [x] 14-VALIDATION.md exists and contains `nyquist_compliant: true`
- [x] 15-VALIDATION.md exists and contains `nyquist_compliant: true`
- [x] adaptive_ranker.py contains `make_logger`
- [x] nodes.py contains `make_logger`
- [x] voice/loop.py contains `make_logger`
- [x] Commits 7a5e251 and 956910c exist in git log
