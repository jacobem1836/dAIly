---
phase: 01-foundation
plan: 02
subsystem: integrations
tags: [adapter-interfaces, pydantic-models, cli, privacy, tdd]
dependency_graph:
  requires: []
  provides: [integration-adapter-contract, pydantic-output-models, cli-entrypoint]
  affects: [01-03-google-oauth, 01-04-slack, 01-05-microsoft]
tech_stack:
  added: [typer>=0.24.0, pydantic>=2.12.0]
  patterns: [abstract-adapter-interface, metadata-only-models, typer-sub-app-pattern]
key_files:
  created:
    - src/daily/integrations/models.py
    - src/daily/integrations/base.py
    - src/daily/integrations/__init__.py
    - src/daily/cli.py
    - src/daily/__init__.py
    - tests/test_models.py
    - pyproject.toml
  modified: []
decisions:
  - "Pydantic v2 BaseModel used for all output types — metadata-only enforced architecturally (no body field exists)"
  - "Abstract base classes use ABC + abstractmethod; async methods match D-08 contract exactly"
  - "Typer sub-app pattern (connect_app added to main app) gives `daily connect <provider>` structure"
  - "pyproject.toml created in this plan (Rule 3: blocked test infrastructure) — Plan 01 will merge or reconcile"
metrics:
  duration_seconds: 143
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 7
  files_modified: 0
  tests_added: 17
  tests_passing: 17
---

# Phase 1 Plan 2: Adapter Interface Contracts and CLI Entrypoint Summary

**One-liner:** Pydantic v2 metadata-only output models and abstract adapter base classes defining the D-08 integration contract, plus a Typer CLI entrypoint with four stubbed `daily connect <provider>` commands.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Adapter interfaces and Pydantic output models | b72505e | src/daily/integrations/models.py, src/daily/integrations/base.py, src/daily/integrations/__init__.py, src/daily/__init__.py |
| 2 | Typer CLI entrypoint with connect command group | 63c972f | src/daily/cli.py |

## What Was Built

### Integration Adapter Contracts (Task 1)

**`src/daily/integrations/models.py`** — Five Pydantic v2 models:
- `EmailMetadata` — message_id, thread_id, subject, sender, recipient, timestamp, is_unread, labels
- `EmailPage` — emails: list[EmailMetadata], next_page_token: str | None
- `CalendarEvent` — event_id, title, start, end, attendees, location, is_all_day
- `MessageMetadata` — message_id, channel_id, sender_id, timestamp, is_mention, is_dm
- `MessagePage` — messages: list[MessageMetadata], next_cursor: str | None

No model has body, raw_body, content, text, or message_body fields — enforced structurally (SEC-04/D-06).

**`src/daily/integrations/base.py`** — Three abstract base classes implementing the D-08 contract exactly:
- `EmailAdapter.list_emails(since: datetime, page_token: str | None = None) -> EmailPage`
- `CalendarAdapter.list_events(since: datetime, until: datetime) -> list[CalendarEvent]`
- `MessageAdapter.list_messages(channels: list[str], since: datetime) -> MessagePage`

### CLI Entrypoint (Task 2)

**`src/daily/cli.py`** — Typer app with connect sub-app:
- `daily connect gmail` — Google OAuth placeholder (Plan 03)
- `daily connect calendar` — Google Calendar OAuth placeholder (Plan 03)
- `daily connect slack` — Slack OAuth placeholder (Plan 04)
- `daily connect outlook` — Microsoft OAuth placeholder (Plan 05)

Registered in pyproject.toml as `daily = "daily.cli:app"`.

## Verification Results

```
uv run pytest tests/test_models.py -v
17 passed in 0.07s

uv run daily connect --help
Shows: gmail, calendar, slack, outlook commands

grep "body" src/daily/integrations/models.py (excluding comments)
No field definitions found — only docstring comments
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created pyproject.toml to unblock test infrastructure**
- **Found during:** Task 1 RED phase
- **Issue:** No pyproject.toml existed in the worktree (Plan 01 runs in parallel and creates it). Tests could not run without a project definition.
- **Fix:** Created pyproject.toml with all required dependencies matching the stack spec (Python 3.11+, pydantic, typer, pytest, etc.) and `daily = "daily.cli:app"` script entry. This aligns with what Plan 01 will also create — the merge/reconciliation between worktrees is the orchestrator's responsibility.
- **Files modified:** pyproject.toml (created)
- **Commit:** 21e0bc9 (included with RED phase test commit)

**2. [Rule 3 - Blocking] Required `uv pip install -e .` for editable install**
- **Found during:** Task 1 GREEN phase
- **Issue:** `uv sync` alone does not put the local package on the Python path for pytest. Module not found errors persisted.
- **Fix:** Ran `uv pip install -e .` to install the package in editable mode. Tests then resolved correctly.
- **Impact:** No file changes; runtime environment fix only.

## Threat Surface Scan

T-1-06 (Information Disclosure — models.py): MITIGATED. Verified no body/raw_body/content/text/message_body fields exist in any model. The privacy constraint is structural — there is no column/field to store raw content in. Tested in 3 dedicated privacy tests in test_models.py.

T-1-07 (Elevation of Privilege — cli.py): ACCEPTED. CLI runs locally as current user. All connect commands are stubs that print placeholder messages — no privileged operations performed.

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| src/daily/cli.py:28 | `gmail()` prints placeholder | Plan 03 implements Google OAuth |
| src/daily/cli.py:34 | `calendar()` prints placeholder | Plan 03 implements Google Calendar OAuth |
| src/daily/cli.py:40 | `slack()` prints placeholder | Plan 04 implements Slack OAuth |
| src/daily/cli.py:46 | `outlook()` prints placeholder | Plan 05 implements Microsoft OAuth |

These stubs are intentional — this plan establishes the CLI structure only. Plans 03-05 wire the actual OAuth flows.

## Self-Check: PASSED

- [x] `src/daily/integrations/models.py` exists
- [x] `src/daily/integrations/base.py` exists
- [x] `src/daily/cli.py` exists
- [x] `tests/test_models.py` exists
- [x] Commit b72505e exists (adapter interfaces)
- [x] Commit 63c972f exists (CLI)
- [x] 17/17 tests pass
