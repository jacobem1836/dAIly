---
phase: 02-briefing-pipeline
plan: 01
subsystem: briefing-pipeline
tags: [models, pydantic, sqlalchemy, alembic, adapters, redis, openai, apscheduler]
dependency_graph:
  requires: []
  provides:
    - src/daily/briefing/models.py
    - src/daily/integrations/base.py (get_email_body, get_message_text)
    - src/daily/db/models.py (BriefingConfig, VipSender)
    - alembic/versions/56a7489e1608_add_briefing_config_vip_senders.py
  affects:
    - src/daily/integrations/google/adapter.py
    - src/daily/integrations/slack/adapter.py
    - src/daily/integrations/microsoft/adapter.py
tech_stack:
  added:
    - apscheduler==3.10.4 (pinned 3.10.x per D-12)
    - redis==7.4.0 (redis-py 7.x asyncio)
    - openai==2.30.0 (GPT-4.1 API, pinned <3.0.0)
    - python-dateutil==2.9.0 (timezone handling)
    - fakeredis==2.34.1 (dev — mock Redis for tests)
  patterns:
    - Pydantic Field(exclude=True) for in-memory-only fields (SEC-02 raw_bodies)
    - SQLAlchemy ARRAY(String) for PostgreSQL array columns
    - Explicit UniqueConstraint in __table_args__ for composite uniqueness
    - Abstract method extension on base adapter classes (D-01 body-fetch contract)
key_files:
  created:
    - src/daily/briefing/__init__.py
    - src/daily/briefing/models.py
    - alembic/versions/56a7489e1608_add_briefing_config_vip_senders.py
    - alembic/script.py.mako
    - tests/test_briefing_models.py
  modified:
    - pyproject.toml
    - src/daily/config.py
    - src/daily/integrations/base.py
    - src/daily/integrations/google/adapter.py
    - src/daily/integrations/slack/adapter.py
    - src/daily/integrations/microsoft/adapter.py
    - src/daily/db/models.py
    - tests/conftest.py
decisions:
  - "Pinned apscheduler to 3.10.x (not 4.x) per D-12 and STATE.md blocker note"
  - "raw_bodies uses Pydantic Field(exclude=True) — in-memory SEC-02 contract, never serialised"
  - "slack_channels uses ARRAY(String) with server_default='{}' for PostgreSQL array semantics"
  - "Explicit UniqueConstraint('user_id', 'email', name='uq_vip_user_email') in __table_args__ per review feedback"
  - "to_prompt_string() fully implemented (not a stub) — plan owns implementation because model defines data shape"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-07"
  tasks_completed: 3
  tasks_total: 3
  files_created: 5
  files_modified: 8
  tests_added: 9
  tests_total: 113
---

# Phase 2 Plan 01: Briefing Pipeline Foundation Summary

**One-liner:** Pydantic pipeline models (BriefingContext with SEC-02 raw_bodies exclusion), extended adapter interfaces with body-fetch methods, DB models for BriefingConfig/VipSender, Alembic migration applied, and test fixtures for Phase 2.

## What Was Built

### Task 1: Phase 2 Dependencies + Briefing Pipeline Models

Added four production dependencies (`apscheduler>=3.10.0,<3.11.0`, `redis>=7.0.0`, `openai>=2.0.0,<3.0.0`, `python-dateutil>=2.9`) and one dev dependency (`fakeredis>=2.0.0`) to `pyproject.toml`. All installed via `uv sync`.

Created `src/daily/briefing/models.py` with six Pydantic models:
- `RankedEmail` — email + priority score + redacted summary
- `CalendarContext` — events list + conflict pairs
- `SlackContext` — messages list + per-message summaries dict
- `BriefingContext` — top-level pipeline context with `raw_bodies: dict[str, str] = Field(exclude=True)` for SEC-02
- `BriefingOutput` — Redis-cached final narrative
- `RedactedItem` — post-redaction item per D-09/D-10

`BriefingContext.to_prompt_string()` is fully implemented (not a stub): formats EMAILS, CALENDAR (next 48h), and SLACK sections with graceful empty-state handling.

Extended `src/daily/config.py` with `redis_url`, `openai_api_key`, `briefing_email_top_n`, and `briefing_schedule_time`.

### Task 2: Adapter Interface Extension + DB Models + Test Fixtures

Extended `src/daily/integrations/base.py`:
- `EmailAdapter.get_email_body(message_id: str) -> str` (abstract, per D-01)
- `MessageAdapter.get_message_text(message_id: str, channel_id: str) -> str` (abstract, per D-01)

Concrete implementations:
- `GmailAdapter.get_email_body()` — calls Gmail API `messages.get(format='full')`, recursively extracts `text/plain` part, base64-decodes
- `SlackAdapter.get_message_text()` — calls `conversations_history(latest=..., inclusive=True, limit=1)`
- `OutlookAdapter.get_email_body()` — calls Graph API `GET /me/messages/{id}?$select=body,bodyPreview`

Extended `src/daily/db/models.py` with:
- `BriefingConfig` — schedule config per user (schedule_hour, schedule_minute, email_top_n, slack_channels ARRAY)
- `VipSender` — VIP email list per user with explicit `UniqueConstraint("user_id", "email", name="uq_vip_user_email")`

Added Phase 2 fixtures to `tests/conftest.py`: `sample_emails` (6 diverse items), `sample_events` (4 events with overlap pair), `sample_messages` (4 items with mentions/DMs), `vip_senders`.

Created `tests/test_briefing_models.py` with 9 tests covering all acceptance criteria.

### Task 3: Alembic Migration

Generated and applied migration `56a7489e1608_add_briefing_config_vip_senders`:
- Creates `briefing_config` table with ARRAY slack_channels column
- Creates `vip_senders` table with `uq_vip_user_email` unique constraint
- Migration chain: `001 -> 56a7489e1608` (head)

Also added missing `alembic/script.py.mako` template (pre-existing omission from repo initialisation — copied from alembic's async template).

## Verification Results

- `uv run pytest tests/ -x -q` → 113 passed, 8 warnings
- `from daily.briefing.models import BriefingContext, BriefingOutput` → OK
- `from daily.integrations.base import EmailAdapter` shows `get_email_body` → OK
- `from daily.db.models import BriefingConfig, VipSender` → OK
- `uv run alembic upgrade head` → 001 -> 56a7489e1608 applied
- `BriefingContext.model_fields['raw_bodies'].exclude` → True
- `BriefingContext(...).model_dump()` does NOT include `raw_bodies` → confirmed by test

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing alembic/script.py.mako template**
- **Found during:** Task 3
- **Issue:** `alembic revision --autogenerate` failed with `FileNotFoundError: alembic/script.py.mako`. The file was never committed during project initialisation.
- **Fix:** Copied the async template from `alembic/templates/async/script.py.mako` in the alembic package to `alembic/script.py.mako`.
- **Files modified:** `alembic/script.py.mako` (new)
- **Commit:** fa46efa

**2. [Rule 3 - Blocking] `daily` module not on sys.path for pytest/alembic**
- **Found during:** Tasks 2 and 3
- **Issue:** `uv run pytest` and `uv run alembic` could not find `daily` module. Package was installed as wheel (not editable) so path discovery failed after new files were added.
- **Fix:** Ran `uv pip install -e .` to install in editable mode; used `PYTHONPATH=src` prefix for alembic commands where needed.
- **Impact:** No code changes — environment-level fix. Tests pass reliably.

## Known Stubs

None. All methods are fully implemented:
- `to_prompt_string()` has complete section rendering for EMAILS, CALENDAR, SLACK
- All `get_email_body()` / `get_message_text()` implementations call real APIs (not placeholder raises)

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary surfaces introduced beyond what the plan's threat model covers (T-02-01, T-02-02).

## Self-Check: PASSED

Files exist:
- FOUND: src/daily/briefing/models.py
- FOUND: src/daily/briefing/__init__.py
- FOUND: alembic/versions/56a7489e1608_add_briefing_config_vip_senders.py
- FOUND: alembic/script.py.mako
- FOUND: tests/test_briefing_models.py

Commits exist:
- d36aeef — feat(02-01): install Phase 2 deps and define briefing pipeline models
- e64d6ad — feat(02-01): extend adapter interfaces, add DB models, create test fixtures
- fa46efa — feat(02-01): add Alembic migration for briefing_config and vip_senders tables
