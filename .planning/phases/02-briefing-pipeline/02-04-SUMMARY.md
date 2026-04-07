---
phase: 02-briefing-pipeline
plan: "04"
subsystem: briefing-pipeline
tags: [cache, scheduler, pipeline, cli, apscheduler, redis, fastapi]
requirements: [BRIEF-01, BRIEF-02]

dependency_graph:
  requires:
    - 02-01 (briefing models — BriefingContext, BriefingOutput)
    - 02-02 (context_builder — build_context interface)
    - 02-03 (redactor/narrator — redact_emails, redact_messages, generate_narrative)
  provides:
    - Redis briefing cache with 24h TTL (BRIEF-01 fast path)
    - APScheduler cron job for precomputed briefings (BRIEF-02)
    - End-to-end pipeline orchestrator connecting all Wave 1/2 outputs
    - CLI config and VIP management commands
    - FastAPI app with lifespan-managed scheduler
  affects:
    - src/daily/db/engine.py (added module-level async_session)

tech_stack:
  added:
    - fakeredis (test)
    - APScheduler 3.10.x AsyncIOScheduler
    - Redis 7.x asyncio client
  patterns:
    - asyncio.run() bridges sync Typer CLI to async SQLAlchemy (D-16)
    - _build_pipeline_kwargs resolves all pipeline dependencies from DB tokens
    - SEC-02: raw_bodies in-memory only, cleared after redaction, never cached
    - UTC date cache keys for timezone-safe Redis storage

key_files:
  created:
    - src/daily/briefing/cache.py
    - src/daily/briefing/scheduler.py
    - src/daily/briefing/pipeline.py
    - src/daily/main.py
    - tests/test_briefing_cache.py
    - tests/test_briefing_scheduler.py
    - tests/test_briefing_pipeline.py
  modified:
    - src/daily/cli.py (added config and vip sub-commands)
    - src/daily/db/engine.py (added async_session module-level factory)

decisions:
  - asyncio.run() for CLI async/sync bridge instead of a separate sync engine
  - _build_pipeline_kwargs pattern centralises all dependency resolution in scheduler
  - _scheduled_pipeline_run wrapper decouples cron entry point from pipeline signature
  - UTC date in cache keys avoids off-by-one at midnight in non-UTC timezones
  - Module-level async_session in engine.py for scheduler use without DI wiring

metrics:
  duration: "~25 minutes"
  completed: "2026-04-07T09:54:21Z"
  tasks_completed: 2
  files_created: 9
---

# Phase 2 Plan 4: Pipeline Wiring (Cache, Scheduler, Orchestrator, CLI) Summary

**One-liner:** Redis cache (24h TTL, UTC date keys) + APScheduler cron + end-to-end pipeline orchestrator (build_context -> redact -> narrate -> cache) + CLI config/VIP commands via asyncio.run() bridge, all wired into FastAPI lifespan.

## What Was Built

### Task 1: Redis Cache + APScheduler + FastAPI Lifespan + CLI (commit 45f4164)

**`src/daily/briefing/cache.py`**
- `cache_briefing(redis, user_id, output)`: stores BriefingOutput JSON in Redis with key `briefing:{user_id}:{YYYY-MM-DD}` (UTC date), TTL=86400 (24h per D-14).
- `get_briefing(redis, user_id, date)`: reads from Redis, returns BriefingOutput or None on miss.
- Only stores narrative/generated_at/version — never raw bodies (SEC-02/T-02-11).

**`src/daily/briefing/scheduler.py`**
- `scheduler`: module-level `AsyncIOScheduler(timezone="UTC")`.
- `_build_pipeline_kwargs(user_id, settings)`: resolves all pipeline dependencies from DB (VIP senders, integration tokens → adapter instances, redis, openai_client). Addresses HIGH review concern about scheduler-to-pipeline parameter gap.
- `_scheduled_pipeline_run(user_id)`: APScheduler cron entry point; calls `_build_pipeline_kwargs` then `run_briefing_pipeline`. Closes redis connection in finally block.
- `setup_scheduler(hour, minute, user_id)`: registers the cron job (uses `_scheduled_pipeline_run`, not pipeline directly).
- `update_schedule(hour, minute)`: reschedules live job via `reschedule_job`.

**`src/daily/main.py`**
- FastAPI app with `lifespan` context manager.
- On startup: parses `settings.briefing_schedule_time` → calls `setup_scheduler` → `scheduler.start()`.
- On shutdown: `scheduler.shutdown(wait=False)`.
- Includes `/health` endpoint.

**`src/daily/cli.py`** (extended)
- `daily config set <key> <value>`: upserts BriefingConfig in DB.
  - Keys: `briefing.schedule_time` (HH:MM), `briefing.email_top_n` (int).
- `daily vip add/remove/list`: manage VipSender rows in DB.
- All commands use `asyncio.run()` to bridge sync Typer to async SQLAlchemy.

**`src/daily/db/engine.py`** (extended)
- Added `async_session` module-level session factory using default Settings (for scheduler and CLI use without FastAPI DI).

### Task 2: Pipeline Orchestrator + Tests (commit 8d60f2b)

**`src/daily/briefing/pipeline.py`**
- `run_briefing_pipeline(user_id, email_adapters, calendar_adapters, message_adapters, vip_senders, user_email, top_n, redis, openai_client)`:
  1. `build_context(...)` → populates `context.raw_bodies`
  2. Extract per-source raw bodies from `context.raw_bodies` (SEC-02 handoff)
  3. `redact_emails(emails, email_bodies, openai_client)` — actual bodies, not empty dicts
  4. `redact_messages(slack_messages, slack_texts, openai_client)`
  5. `context.raw_bodies.clear()` — explicit clear after redaction (T-02-11)
  6. `generate_narrative(context, openai_client)`
  7. `cache_briefing(redis, user_id, output)` → TTL=24h

- `get_or_generate_briefing(user_id, redis, generate_kwargs)`:
  - Cache hit: Redis read, returns in <0.1s (BRIEF-01).
  - Cache miss: triggers `run_briefing_pipeline` on-demand (D-15, briefing always delivers).

## Test Coverage

| File | Tests | What |
|------|-------|------|
| test_briefing_cache.py | 4 | cache_briefing stores with TTL, get_briefing hit/miss, key format `briefing:1:2026-04-05` |
| test_briefing_scheduler.py | 3 | reschedule_job called, setup_scheduler uses _scheduled_pipeline_run, _build_pipeline_kwargs returns all required keys |
| test_briefing_pipeline.py | 5 | full pipeline produces cached output, cache hit <0.1s (BRIEF-01), cache miss triggers generation, partial adapter failure resilience, raw_bodies passed to redactor (SEC-02) |

**Total new tests: 12. Full suite: 157 passed.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing `async_session` in `db/engine.py`**
- **Found during:** Task 1 — scheduler.py imports `async_session` from `daily.db.engine` but the symbol didn't exist.
- **Issue:** engine.py only had `make_engine` and `make_session_factory` factory functions; no module-level session factory.
- **Fix:** Added `_default_session_factory()` and `async_session` module-level factory to engine.py using the default Settings database_url.
- **Files modified:** `src/daily/db/engine.py`
- **Commit:** 45f4164

**2. [Rule 3 - Ordering] pipeline.py created during Task 1 to unblock scheduler tests**
- **Found during:** Task 1 — scheduler.py imports `run_briefing_pipeline` from pipeline.py at module level, so scheduler tests failed with `ModuleNotFoundError` even though pipeline.py was Task 2.
- **Fix:** Created pipeline.py during Task 1 execution (before its own test pass). Full pipeline tests written and committed in Task 2 per plan.
- **Files modified:** None — pipeline.py created as planned, just earlier.

## Known Stubs

None — all implemented functions wire real logic. The only hardcoded value is `user_id=1` in CLI commands and `setup_scheduler`, which is intentional M1 single-user behavior (T-02-12: accepted risk, documented in threat model).

## Threat Flags

None — all files are within the threat model established in the plan:
- `cache.py` → Pipeline -> Redis boundary (T-02-10: accepted, local Redis only)
- `pipeline.py` → raw_bodies cleared after redaction (T-02-11: mitigated)
- `scheduler.py` → tokens decrypted in-memory only (T-02-16: mitigated)
- `cli.py` → user_id=1 hardcoded for M1 (T-02-12: accepted)

## Self-Check: PASSED

- FOUND: src/daily/briefing/cache.py
- FOUND: src/daily/briefing/scheduler.py
- FOUND: src/daily/briefing/pipeline.py
- FOUND: src/daily/main.py
- FOUND: src/daily/cli.py
- FOUND: commit 45f4164
- FOUND: commit 8d60f2b
