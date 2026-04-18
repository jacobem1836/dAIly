---
phase: 11-trusted-actions
plan: "02"
subsystem: cli/autonomy-config
tags: [trusted-actions, autonomy, cli, tests, validation]
dependency_graph:
  requires: [11-01]
  provides: [profile.autonomy CLI commands, test_trusted_actions]
  affects: [cli.py, profile/service.py, tests/]
tech_stack:
  added: []
  patterns: [cli-validation-before-db, upsert-preference-dict-value, pytest-asyncio-unit-tests]
key_files:
  created:
    - tests/test_trusted_actions.py
  modified:
    - src/daily/cli.py
    - src/daily/profile/service.py
decisions:
  - "Validation in _upsert_autonomy runs before any DB access — invalid inputs rejected cheaply (T-11-03)"
  - "upsert_preference signature widened to str | dict | list to support autonomy_levels dict writes without breaking existing string callers"
  - "profile.autonomy.* routing check placed before generic profile.* in config_set — prevents misrouting autonomy keys"
metrics:
  duration: "~15 minutes"
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_modified: 3
requirements_satisfied: [ACT-07]
---

# Phase 11 Plan 02: CLI Autonomy Config and Tests Summary

**CLI autonomy configuration with validation gates and 15-test suite covering all four trusted-actions success criteria.**

## What Was Built

**Task 1 — CLI profile.autonomy.* commands:**
- Added `_upsert_autonomy(user_id, action_type, level) -> str` to `cli.py`. Validates level against `{"approve", "auto", "suggest"}` first (fast rejection, no DB call). Then validates action_type against `ActionType` enum. Then rejects if in `BLOCKED_ACTION_TYPES`. Then rejects if not in `CONFIGURABLE_ACTION_TYPES`. Only proceeds to DB write if all checks pass.
- Added `_get_autonomy(user_id) -> str` to `cli.py`. Iterates `CONFIGURABLE_ACTION_TYPES` sorted by value, reads `autonomy_levels` from loaded profile, defaults to `"approve"` for unset types.
- Updated `config_set` to route `profile.autonomy.*` before `profile.*` (line 267 before 272) to prevent generic profile handler from intercepting autonomy keys.
- Updated `config_get` to route `profile.autonomy` to `_get_autonomy` before the generic `profile` branch.
- Updated `upsert_preference` in `service.py` to accept `str | dict | list` — dict values (autonomy_levels) are stored directly; str `category_order` values are still parsed as comma-separated; all other types pass through unchanged.

**Task 2 — Comprehensive test suite (`tests/test_trusted_actions.py`):**
- `TestAutonomyConstants` (4 tests): frozenset type, compose_email in blocked, exactly 4 configurable types, zero overlap between blocked and configurable.
- `TestUserPreferencesAutonomy` (2 tests): defaults to empty dict, accepts valid autonomy_levels on model_validate.
- `TestApprovalNodeAutonomy` (6 tests): auto bypasses interrupt for draft_email and schedule_event, blocked type (compose_email) always calls interrupt even when autonomy set to "auto", approve level calls interrupt, missing autonomy_levels calls interrupt, suggest level calls interrupt.
- `TestCliAutonomyValidation` (3 tests): rejects blocked type (compose_email) with "always requires approval" message, rejects invalid level "yolo" with "Invalid autonomy level" message, rejects unknown action type "fly_plane" with "Unknown action type" message.

**Total: 15 tests, all pass.**

## Decisions Made

1. **Validation-before-DB in _upsert_autonomy:** Level and action_type checks happen before any DB session is opened. This means unit tests for validation don't need DB mocking at all — clean fast tests (T-11-03 mitigated).

2. **upsert_preference widened to str | dict | list:** The existing `str`-only signature worked for all callers but needed to accept dict for `autonomy_levels`. The type union preserves backward compatibility — existing callers passing str continue to work unchanged; the `category_order` comma-split logic is gated on `isinstance(value, str)`.

3. **profile.autonomy.* routing priority:** The specificity-first ordering (autonomy before generic profile) follows standard CLI routing patterns. Without this, `profile.autonomy.draft_email` would be routed to `_upsert_profile` with key `autonomy.draft_email`, which would fail validation.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all configurable types fully wired through CLI → upsert_preference → JSONB → approval_node.

## Threat Flags

None — all surfaces match the plan's threat model (T-11-03, T-11-04). No new endpoints or auth paths introduced.

## Self-Check: PASSED

Files exist:
- `tests/test_trusted_actions.py` — FOUND
- `src/daily/cli.py` — FOUND (contains _upsert_autonomy, _get_autonomy)
- `src/daily/profile/service.py` — FOUND (upsert_preference accepts str | dict | list)

Commits:
- `d3a1641` — feat(11-02): extend CLI for profile.autonomy config commands
- `d5fb0dc` — test(11-02): comprehensive tests for trusted actions

Verification checks:
1. `python -m pytest tests/test_trusted_actions.py -x -v` — 15/15 passed
2. `from daily.cli import _upsert_autonomy, _get_autonomy` — Import OK
3. `profile.autonomy.*` check at line 267, generic `profile.*` at line 272 — correct ordering
