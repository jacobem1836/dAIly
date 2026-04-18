---
phase: 14-observability
plan: "02"
subsystem: observability
tags: [health, metrics, fastapi, redis, observability]
dependency_graph:
  requires: [14-01]
  provides: [GET /health, GET /metrics, pipeline latency_s Redis key]
  affects: [src/daily/main.py, src/daily/briefing/pipeline.py]
tech_stack:
  added: []
  patterns: [async Redis PING probe, SELECT 1 DB probe, scan_iter latency aggregation, time.monotonic() pipeline timing]
key_files:
  created:
    - tests/test_health_endpoint.py
    - tests/test_metrics_endpoint.py
  modified:
    - src/daily/main.py
    - src/daily/briefing/pipeline.py
    - tests/test_main_lifespan.py
    - tests/test_uat_integration.py
decisions:
  - "Use MagicMock(side_effect=[...]) pattern for async_session callable to provide distinct ctx per call (lifespan + endpoint)"
  - "mock async_session as a callable (not return_value) in metrics tests — lifespan consumes first call, endpoint consumes second"
  - "update test_uat_integration.py health assertions to match new /health response shape (full dependency status dict)"
metrics:
  duration_minutes: 8
  completed_date: "2026-04-19"
  tasks_completed: 3
  files_changed: 6
---

# Phase 14 Plan 02: Health and Metrics Endpoints Summary

**One-liner:** Real /health with DB/Redis/scheduler probes + /metrics with 7-day signal counts and Redis latency aggregation, plus pipeline latency instrumentation.

## What Was Built

### src/daily/main.py

**Enhanced `/health` endpoint** (per D-05/D-06/D-07):
- Async DB probe: `async with async_session() as session: await session.execute(text("SELECT 1"))`
- Async Redis probe: `AsyncRedis.from_url(settings.redis_url)` → `await redis.ping()` → `finally: await redis.aclose()`
- Scheduler check: `scheduler.get_jobs()` (synchronous APScheduler 3.x API) — empty list → `no_jobs` → degraded
- Returns `{"status": "ok"|"degraded", "db": ..., "redis": ..., "scheduler": ...}` with HTTP 200 / 503

**New `/metrics` endpoint** (per D-08 through D-12):
- Signal counts: 7-day rolling window query on `signal_log` grouped by `signal_type`
- Memory entries: `SELECT count(id) FROM memory_facts`
- Briefing latency: `redis.scan_iter("briefing:*:latency_s")` → average of all values (0.0 when no keys)
- Returns `{"briefing_latency_avg_s": float, "signals_7d": dict, "memory_entries": int}`

Both endpoints instantiate `Settings()` inside the route function (anti-pattern from RESEARCH.md respected — no module-level Settings instantiation for Redis URL).

### src/daily/briefing/pipeline.py

- `import time` added
- `pipeline_start = time.monotonic()` captured immediately after the opening `logger.info()`
- After `cache_briefing()` + item cache block: `redis.set(f"briefing:{user_id}:latency_s", str(round(latency_s, 3)), ex=86400)` in a try/except that logs but does not raise

### Tests

**`tests/test_health_endpoint.py`** — 4 tests (OBS-03):
- `test_health_all_ok` — mocked DB/Redis/scheduler all healthy → 200 ok
- `test_health_db_down` — DB raises → 503 degraded, db starts with "error:"
- `test_health_redis_down` — Redis ping raises → 503 degraded, redis starts with "error:"
- `test_health_no_scheduler_jobs` — empty get_jobs() → 503 degraded, scheduler = "no_jobs"

**`tests/test_metrics_endpoint.py`** — 3 tests (OBS-04):
- `test_metrics_returns_all_fields` — signal counts [("skip", 3), ("expand", 10)], memory 42, one latency key 4.5 → full response
- `test_metrics_empty_data` — no signals, no memory, no Redis keys → 0.0/{}/ 0
- `test_metrics_latency_averages_multiple` — 3 keys (2.0, 4.0, 6.0) → avg 4.0

## Verification

- [x] OBS-03: GET /health returns 200 + ok body when all healthy
- [x] OBS-03: GET /health returns 503 + degraded body when DB down
- [x] OBS-03: GET /health returns 503 when scheduler has no jobs
- [x] OBS-04: GET /metrics returns correct signal_7d counts
- [x] OBS-04: GET /metrics reads latency from Redis and computes average
- [x] OBS-04: pipeline.py writes latency_s key to Redis after run

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | c9c56fa | feat(14-02): replace /health stub with real dependency checks and add /metrics endpoint |
| Task 2 | d9dd48e | feat(14-02): instrument briefing pipeline with latency timing and Redis write |
| Task 3 | 69e281c | test(14-02): add test suites for /health and /metrics endpoints (OBS-03, OBS-04) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture session exhaustion in metrics tests**
- **Found during:** Task 3 — first run of metrics tests
- **Issue:** `async_session` was patched with `return_value=session_ctx`, but both the lifespan and the endpoint call `async_session()`, sharing the same mock session. The lifespan consumed one `execute` call, leaving the endpoint with insufficient mocked results → StopAsyncIteration
- **Fix:** Changed `async_session` mock from `return_value` to `MagicMock(side_effect=[lifespan_ctx, endpoint_ctx])` — each call returns a distinct context manager with its own execute mock
- **Files modified:** tests/test_metrics_endpoint.py
- **Commit:** 69e281c

**2. [Rule 1 - Bug] Pre-existing lifespan test failures (Plan 01 regression)**
- **Found during:** Task 3 — full suite run
- **Issue:** Plan 01 added `configure_logging(settings.log_level)` to the lifespan. `test_main_lifespan.py` and `test_uat_integration.py` didn't mock `configure_logging` or set `log_level` as a string, causing `TypeError: attribute name must be string, not 'MagicMock'`
- **Fix:** Added `patch("daily.main.configure_logging")` and `mock_settings_cls.return_value.log_level = "INFO"` to all lifespan-using tests
- **Files modified:** tests/test_main_lifespan.py, tests/test_uat_integration.py
- **Commit:** 69e281c

**3. [Rule 1 - Bug] UAT health test assertion outdated after /health enhancement**
- **Found during:** Task 3 — full suite run
- **Issue:** `test_uat_integration.py::TestHealthEndpoint::test_health_returns_ok` asserted `response.json() == {"status": "ok"}` but the new /health returns a richer dict including db/redis/scheduler fields. `test_health_works_without_db` asserted 200 but our /health now returns 503 when DB is down (correct behavior)
- **Fix:** Updated assertion to check `body["status"] == "ok"` (subset check), and updated `test_health_works_without_db` to assert 503 + degraded (which is the correct behavior)
- **Files modified:** tests/test_uat_integration.py
- **Commit:** 69e281c

## Known Stubs

None — all data sources are wired to real DB queries and Redis operations.

## Threat Surface Scan

No new network endpoints introduced beyond what the plan specified. The `/health` and `/metrics` endpoints were planned. Threat dispositions confirmed from plan's threat model:

- T-14-03 (metrics information disclosure): accepted — aggregate counts only, no PII
- T-14-04 (health info disclosure): accepted — stdlib exception messages only, no credentials
- T-14-05 (DoS via Redis scan): accepted — M1 scale (0-1 keys), deferred to M2

## Self-Check: PASSED
