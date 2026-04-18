# Phase 14: Observability - Research

**Researched:** 2026-04-19
**Domain:** Python stdlib logging, FastAPI endpoint design, APScheduler job inspection, Redis/DB health probing
**Confidence:** HIGH

## Summary

Phase 14 is an additive, zero-new-dependency phase. Every module already calls `logging.getLogger(__name__)`. The only change to the logging path is wiring a `JSONFormatter` into the root logger's `StreamHandler` at startup — all 17 existing logger call sites remain unchanged. The formatter intercepts at the handler level; no module edits are required for log format compliance.

The health and metrics endpoints are two new FastAPI routes. The health endpoint probes DB (async `SELECT 1`), Redis (`PING`), and APScheduler (job count > 0) and returns a structured dict. The metrics endpoint queries three data sources: `signal_log` table (COUNT with 7-day window and GROUP BY signal_type), `memory_facts` table (COUNT), and Redis keys matching `briefing:*:latency_s` (aggregate average).

The one discretionary decision is how to thread `stage` context into log records without touching every call site. The `logging.LoggerAdapter` pattern is the right answer — it wraps a logger and injects extra fields into every record without requiring callers to pass explicit kwargs.

**Primary recommendation:** One `JSONFormatter` in `main.py` lifespan startup + one `LoggerAdapter` factory function modules opt into + two new FastAPI routes. No new packages, no middleware, no structural changes to any existing module.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use stdlib `logging` with a custom `JSONFormatter` — zero new dependencies. All 58 existing `logger.*()` calls work unchanged; the formatter intercepts at the handler level.
- **D-02:** JSON log shape: `{"ts": "<ISO-8601>", "level": "INFO", "module": "briefing.pipeline", "msg": "...", "ctx": {...}}`
- **D-03:** Log context (`ctx` field) carries `user_id` and `stage` (pipeline stage label, e.g. `"precompute"`, `"voice.loop"`). No request_id at this scale.
- **D-04:** `LOG_LEVEL` env var controls verbosity. `LOG_LEVEL=DEBUG` → verbose; `LOG_LEVEL=WARNING` → suppress info. Applied at root logger setup in `main.py`. Default: `INFO`.
- **D-05:** `/health` is liveness-only — fast, cheap, safe to hammer from uptime monitors. Returns: DB connectivity, Redis connectivity, scheduler state. No metrics on this endpoint.
- **D-06:** DB check: `SELECT 1`. Redis check: `PING`. Scheduler check: verify APScheduler has at least one active job.
- **D-07:** Response shape: `{"status": "ok", "db": "ok", "redis": "ok", "scheduler": "running"}`. On failure: `{"status": "degraded", "db": "error: <msg>", ...}` with HTTP 503.
- **D-08:** Separate `/metrics` route — liveness and performance concerns separated.
- **D-09:** Metrics computed via live DB queries at request time.
- **D-10:** Briefing latency stored in Redis per user as `briefing:{user_id}:latency_s`; `/metrics` reads all per-user values, returns aggregate average.
- **D-11:** Signal counts use 7-day rolling window.
- **D-12:** Metrics response: `{"briefing_latency_avg_s": 4.2, "signals_7d": {"skip": 12, "expand": 34, "re_request": 5}, "memory_entries": 87}`

### Claude's Discretion
- Exact `JSONFormatter` implementation (subclass `logging.Formatter`, override `format()`)
- Where logging setup lives (`main.py` lifespan, or a `logging_config.py` imported at startup)
- How `stage` context is passed (thread-local, `logging.LoggerAdapter`, or explicit kwarg pattern)
- Whether `/metrics` is authenticated or open (open is fine for M1 single-host deployment)

### Deferred Ideas (OUT OF SCOPE)
- Switch to `structlog`
- Add `request_id` (UUID) to log context
- Replace live DB queries with Prometheus counters
- Add p95/p99 latency percentiles
- Per-user latency breakdown in metrics
- Per-dependency response time in /health
- Separate liveness vs readiness probes (k8s pattern)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | All modules emit structured JSON logs with consistent fields (timestamp, level, module, message, context) | JSONFormatter on root logger handler intercepts all 17 existing logger call sites transparently |
| OBS-02 | Log level configurable via environment variable without code changes | `LOG_LEVEL` added to Settings, applied to `logging.root.setLevel()` in lifespan startup |
| OBS-03 | Health check endpoint (`GET /health`) returns service status including DB, Redis, and scheduler state | Replace stub in `main.py`; async SELECT 1, Redis PING, APScheduler job count |
| OBS-04 | Key metrics tracked and queryable: briefing generation latency, signal counts by type, memory store size | New `/metrics` route; signal_log COUNT query, memory_facts COUNT query, Redis latency key scan |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `logging` (stdlib) | Python 3.11 | Structured log emission | Already used in all 17 modules; formatter-level intervention requires no call-site changes [VERIFIED: codebase grep] |
| `fastapi` | 0.115+ | HTTP routes for /health and /metrics | Already the application framework [VERIFIED: codebase] |
| `sqlalchemy` (asyncpg) | 2.0.x | Async DB queries for metrics | Already wired via `async_session` + `AsyncSession` dependency [VERIFIED: codebase] |
| `redis.asyncio` | 5.x | Health PING + latency key reads | Already imported in pipeline.py; `aioredis` API [VERIFIED: codebase] |
| `apscheduler` | 3.10.x | Scheduler job count for health check | Already the scheduler; `scheduler.get_jobs()` returns list [VERIFIED: codebase] |

### No New Dependencies Required
All capabilities needed for this phase are provided by libraries already in the project. [VERIFIED: codebase — no new `pip install` needed]

## Architecture Patterns

### Recommended Project Structure

New files created this phase:

```
src/daily/
├── logging_config.py       # JSONFormatter class + configure_logging() function
├── main.py                 # (modified) wire configure_logging() in lifespan, new /health + /metrics
└── config.py               # (modified) add log_level: str = "INFO"

tests/
├── test_logging_config.py  # JSONFormatter output shape, LOG_LEVEL env var
├── test_health_endpoint.py # /health 200 ok + 503 degraded paths
└── test_metrics_endpoint.py # /metrics response shape
```

### Pattern 1: JSONFormatter via stdlib logging.Formatter subclass

**What:** Subclass `logging.Formatter`, override `format()` to return a `json.dumps(...)` string. Wire onto the root logger's `StreamHandler` in the lifespan startup (or `configure_logging()` called from lifespan). All downstream loggers inherit the handler via logger propagation.

**When to use:** Any time you need structured logs without adding structlog as a dependency. Zero call-site changes required.

**Example:**
```python
# src/daily/logging_config.py
import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON per D-02."""

    def format(self, record: logging.LogRecord) -> str:
        log_dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,           # set by getLogger(__name__)
            "msg": record.getMessage(),
            "ctx": getattr(record, "ctx", {}),  # injected by LoggerAdapter
        }
        if record.exc_info:
            log_dict["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_dict)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logger with JSONFormatter. Call once at startup."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
```
[ASSUMED — pattern is standard Python; exact implementation is Claude's discretion per CONTEXT.md]

### Pattern 2: LoggerAdapter for stage/user_id context injection

**What:** `logging.LoggerAdapter` wraps a module's existing logger and injects `ctx` into every record via the `process()` method. Modules that want context call `make_logger(__name__, user_id=..., stage=...)` once (e.g., at session start) and use the returned adapter for the rest of the session.

**When to use:** When you need per-call context (user_id, stage) in logs without threading extra arguments through every `logger.info()` call. Better than thread-locals for async code because each async task can hold its own adapter reference.

**Example:**
```python
# src/daily/logging_config.py (continued)
import logging
from typing import MutableMapping, Any


class ContextAdapter(logging.LoggerAdapter):
    """Injects ctx dict into every log record."""

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        kwargs.setdefault("extra", {})["ctx"] = self.extra.get("ctx", {})
        return msg, kwargs


def make_logger(name: str, **ctx_fields) -> logging.LoggerAdapter:
    """Return a ContextAdapter that injects ctx_fields into every record."""
    return ContextAdapter(logging.getLogger(name), extra={"ctx": ctx_fields})
```
[ASSUMED — standard LoggerAdapter usage; exact shape is Claude's discretion]

### Pattern 3: /health endpoint — async probe, HTTP 503 on failure

**What:** FastAPI async route that probes DB, Redis, and scheduler concurrently. Returns `{"status": "ok", ...}` with 200, or `{"status": "degraded", ...}` with 503. Uses `Response` to set status code dynamically.

**When to use:** Any liveness probe where you want a single route that both returns structured data AND sets HTTP status for uptime monitors.

**Key detail:** Inject Redis as a FastAPI dependency or access it from a module-level reference. The DB uses a short-lived `async_session()` context manager (same pattern as the lifespan DB query in `main.py`).

**APScheduler job count API:** [VERIFIED: codebase — `scheduler.get_jobs()` is used in `scheduler.py`; returns a list; `len(scheduler.get_jobs()) > 0` is the check]

```python
# main.py
from fastapi import Response
from daily.briefing.scheduler import scheduler
from daily.db.engine import async_session
from redis.asyncio import Redis as AsyncRedis

@app.get("/health")
async def health(response: Response) -> dict:
    result: dict = {}
    degraded = False

    # DB check
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception as exc:
        result["db"] = f"error: {exc}"
        degraded = True

    # Redis check
    try:
        redis = AsyncRedis.from_url(Settings().redis_url)
        await redis.ping()
        await redis.aclose()
        result["redis"] = "ok"
    except Exception as exc:
        result["redis"] = f"error: {exc}"
        degraded = True

    # Scheduler check
    jobs = scheduler.get_jobs()
    result["scheduler"] = "running" if jobs else "no_jobs"
    if not jobs:
        degraded = True

    result["status"] = "degraded" if degraded else "ok"
    if degraded:
        response.status_code = 503
    return result
```
[ASSUMED — implementation detail is Claude's discretion; pattern is correct]

### Pattern 4: /metrics endpoint — live DB queries + Redis scan

**What:** FastAPI async route querying three data sources. Uses `async_session()` for two DB COUNT queries and direct Redis for latency key scan.

**Signal count query (7-day rolling window):**
```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from daily.profile.signals import SignalLog

cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
result = await session.execute(
    select(SignalLog.signal_type, func.count(SignalLog.id))
    .where(SignalLog.created_at >= cutoff)
    .group_by(SignalLog.signal_type)
)
signals_7d = {row[0]: row[1] for row in result.all()}
```

**Memory entries count:**
```python
from daily.db.models import MemoryFact

count_result = await session.execute(
    select(func.count(MemoryFact.id))
)
memory_entries = count_result.scalar_one()
```

**Briefing latency — Redis SCAN pattern:**
```python
# Redis keys: briefing:{user_id}:latency_s
latencies = []
async for key in redis.scan_iter("briefing:*:latency_s"):
    val = await redis.get(key)
    if val:
        latencies.append(float(val))
avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
```
[ASSUMED — SCAN pattern is standard Redis; exact key pattern from CONTEXT.md D-10]

**Latency key write in pipeline.py:**
```python
# After pipeline run, before/after cache_briefing call
import time
latency_s = time.monotonic() - pipeline_start
await redis.set(
    f"briefing:{user_id}:latency_s",
    str(latency_s),
    ex=86400,  # 24h TTL — refreshed each precompute
)
```
[ASSUMED — exact placement in pipeline.py is implementation detail]

### Anti-Patterns to Avoid

- **Calling `basicConfig()` after any logger has been used:** `logging.basicConfig()` is a no-op if the root logger already has handlers (which it does after any `logging.warning()` call, for example). Always clear handlers before adding the JSON handler.
- **Mutating `record.__dict__` in the formatter:** Formatters can be called from multiple threads/tasks; mutating the record is not safe. Build a new dict from record fields.
- **Using `thread-local` for async context injection:** Thread-locals do not work in asyncio — a single thread may be executing tasks for multiple users. Use `LoggerAdapter` references held per-task.
- **`redis.scan_iter` without a limit in production:** At M1 scale (single user), scan of `briefing:*:latency_s` is 1–2 keys. Safe. At scale, add a `count` hint or switch to a sorted set.
- **Importing `Settings()` at module level for the Redis URL in the health route:** `Settings()` reads env vars at instantiation; module-level instantiation happens at import time and ignores `.env` files loaded later. Instantiate inside the route function or pass via dependency injection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Log field serialisation | Custom dict builder with manual datetime formatting | `json.dumps` + `datetime.isoformat()` in `JSONFormatter.format()` | One method, stdlib only |
| APScheduler job state | Custom "scheduler started" boolean flag | `scheduler.get_jobs()` — already returns live job list | [VERIFIED: APScheduler 3.x API exists in codebase] |
| Redis connectivity test | Custom connection attempt with timeout | `redis.ping()` — returns `True` or raises | Standard Redis health check pattern |
| DB connectivity test | Full query, table existence check | `SELECT 1` — lightest possible valid query | Cannot fail unless connection itself is broken |

## Common Pitfalls

### Pitfall 1: `root.handlers.clear()` needed before adding JSON handler

**What goes wrong:** If any log call happens before `configure_logging()` runs (e.g., during module import), Python auto-creates a default `StreamHandler` on the root logger. Adding a second handler means every log line is emitted twice — once as plain text, once as JSON.

**Why it happens:** Python's `logging` module lazily creates a `lastResort` handler; any `logger.warning()` before `basicConfig/addHandler` triggers it.

**How to avoid:** In `configure_logging()`, call `root.handlers.clear()` before `root.addHandler(handler)`.

**Warning signs:** Duplicate log lines, one plain-text and one JSON, in output.

### Pitfall 2: APScheduler 3.x vs 4.x API differences

**What goes wrong:** APScheduler 4.x (pre-release as of 2025) has breaking changes. The codebase pins 3.10.x. `scheduler.get_jobs()` returns a list in 3.x. In 4.x the API changes to `scheduler.get_jobs()` returning an awaitable. Using 4.x patterns against the 3.x install will fail.

**Why it happens:** The pyproject.toml pins 3.10.x per the CLAUDE.md stack notes, but web documentation for APScheduler often surfaces 4.x content.

**How to avoid:** Use `scheduler.get_jobs()` (synchronous call) — this is the correct 3.x API. [VERIFIED: codebase — scheduler.py uses AsyncIOScheduler from apscheduler.schedulers.asyncio 3.x]

**Warning signs:** `TypeError: object AsyncIOScheduler is not iterable` or similar if 4.x patterns are used.

### Pitfall 3: `MemoryFact` table may not exist in test DB

**What goes wrong:** The `/metrics` endpoint queries `memory_facts` table. In unit tests that mock the DB session, this is fine. In integration tests against a real DB, the table must be migrated in. Alembic migration 005 creates the HNSW index — tests that skip migrations will fail with "relation memory_facts does not exist".

**Why it happens:** Most existing tests mock the DB session; no test hits `memory_facts` via a real connection.

**How to avoid:** Unit-test `/metrics` by mocking `async_session` and returning mock results. Don't assert against a live DB in Nyquist tests.

### Pitfall 4: `logger.name` vs `record.name` in the formatter

**What goes wrong:** `record.name` is set by `getLogger(__name__)` — it gives the module dotted path (e.g., `daily.briefing.pipeline`). If you use `record.module` instead, you get only the filename without the package prefix (e.g., `pipeline`). D-02 specifies `"module": "briefing.pipeline"` — use `record.name` and strip the `daily.` prefix if needed, or keep it for full fidelity.

**How to avoid:** Use `record.name` in the formatter, not `record.module`.

### Pitfall 5: Redis client lifecycle in /health

**What goes wrong:** Creating a new `AsyncRedis.from_url()` client per `/health` request and not closing it leaks connections. At high polling rates (uptime monitors every 30s), this exhausts the Redis connection pool.

**How to avoid:** Either (a) reuse the module-level Redis client instance already used by the pipeline, or (b) create a fresh client per request and always call `await redis.aclose()` in a `finally` block. Option (a) is preferred if the Redis URL is the same instance.

## Code Examples

### JSONFormatter complete implementation

```python
# Source: stdlib logging docs [CITED: https://docs.python.org/3/library/logging.html#logging.Formatter]
import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
            "ctx": getattr(record, "ctx", {}),
        }
        if record.exc_info:
            log_dict["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_dict)
```

### configure_logging wired in lifespan

```python
# Source: FastAPI lifespan pattern [CITED: https://fastapi.tiangolo.com/advanced/events/]
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    configure_logging(settings.log_level)  # must be first
    # ... rest of startup
    yield
    # ... shutdown
```

### Settings LOG_LEVEL addition

```python
# src/daily/config.py
class Settings(BaseSettings):
    # ... existing fields ...
    log_level: str = "INFO"  # D-04: configurable via LOG_LEVEL env var
```

Note: Pydantic-settings maps env var `LOG_LEVEL` to field `log_level` automatically (case-insensitive). [VERIFIED: pydantic-settings behaviour — env var names are uppercased by convention but matched case-insensitively]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (inferred from existing test suite pattern) |
| Quick run command | `pytest tests/test_logging_config.py tests/test_health_endpoint.py tests/test_metrics_endpoint.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | JSONFormatter emits valid JSON with all required fields | unit | `pytest tests/test_logging_config.py -x` | ❌ Wave 0 |
| OBS-01 | `ctx` field carries user_id and stage when LoggerAdapter used | unit | `pytest tests/test_logging_config.py -x` | ❌ Wave 0 |
| OBS-02 | LOG_LEVEL=DEBUG makes DEBUG records appear; LOG_LEVEL=WARNING suppresses INFO | unit | `pytest tests/test_logging_config.py -x` | ❌ Wave 0 |
| OBS-03 | GET /health returns 200 + all-ok body when DB/Redis/scheduler healthy | unit | `pytest tests/test_health_endpoint.py -x` | ❌ Wave 0 |
| OBS-03 | GET /health returns 503 + degraded body when DB raises | unit | `pytest tests/test_health_endpoint.py -x` | ❌ Wave 0 |
| OBS-03 | GET /health returns 503 when scheduler has no jobs | unit | `pytest tests/test_health_endpoint.py -x` | ❌ Wave 0 |
| OBS-04 | GET /metrics returns correct signal_7d counts from mocked DB | unit | `pytest tests/test_metrics_endpoint.py -x` | ❌ Wave 0 |
| OBS-04 | GET /metrics reads latency from Redis keys and computes average | unit | `pytest tests/test_metrics_endpoint.py -x` | ❌ Wave 0 |
| OBS-04 | pipeline.py writes latency_s key to Redis after run | unit | `pytest tests/test_briefing_pipeline.py -x` | ✅ (extend) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_logging_config.py tests/test_health_endpoint.py tests/test_metrics_endpoint.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_logging_config.py` — covers OBS-01, OBS-02
- [ ] `tests/test_health_endpoint.py` — covers OBS-03
- [ ] `tests/test_metrics_endpoint.py` — covers OBS-04

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | /health and /metrics are open (M1 single-host, per CONTEXT.md) |
| V3 Session Management | no | Stateless endpoints |
| V4 Access Control | no | Open endpoints acceptable for M1 per user decision |
| V5 Input Validation | no | Both endpoints take no user input |
| V6 Cryptography | no | No secrets in log output or metric values |

### Known Threat Patterns for Observability Endpoints

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Log injection (newlines in log msg) | Tampering | `json.dumps` auto-escapes newlines — formatter handles this |
| Sensitive data in log ctx | Information Disclosure | ctx carries only user_id (int) and stage (string) — no tokens, no email bodies |
| /metrics leaks user count | Information Disclosure | memory_entries and signal counts reveal usage data; acceptable for M1 single-host; gate behind auth in M2 if multi-tenant |

**Note:** Both `/health` and `/metrics` are intentionally open for M1 (single-host, no external exposure). If the VPS is internet-facing, consider nginx `allow 127.0.0.1; deny all;` for these routes at the reverse proxy level — but this is Phase 15 scope.

## Environment Availability

Step 2.6: SKIPPED — all dependencies (Python stdlib logging, FastAPI, SQLAlchemy, Redis, APScheduler) are already installed and in use. No new external tools required.

## Open Questions

1. **Redis client reuse in /health vs fresh client**
   - What we know: The pipeline creates a Redis client from settings inside `_build_pipeline_kwargs()` in `scheduler.py`. There is no module-level Redis singleton.
   - What's unclear: Whether to create a fresh `AsyncRedis.from_url()` per `/health` call (simple, slightly wasteful) or to wire a shared Redis client through FastAPI state/lifespan.
   - Recommendation: Create fresh client per `/health` call and close in `finally`. At polling rates ≤ 1/min (uptime monitor), this is fine. A shared client via `app.state.redis` is the right M2 pattern but adds lifespan wiring complexity not in scope here.

2. **Where to write `briefing:{user_id}:latency_s` in pipeline.py**
   - What we know: The pipeline starts with `logger.info("Starting briefing pipeline...")` and ends with `logger.info("Briefing pipeline complete...")`. Timing should wrap the entire call.
   - What's unclear: Whether to time from function entry or from after the DB session setup.
   - Recommendation: Use `time.monotonic()` at the top of `run_briefing_pipeline()` and write the key after `cache_briefing()` succeeds. This measures total pipeline duration including context building, redaction, narration, and caching — the most useful latency signal.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `logging.LoggerAdapter` is the right pattern for stage context injection | Architecture Patterns — Pattern 2 | Low — alternative (explicit kwarg) still works; just more verbose |
| A2 | `configure_logging()` in `logging_config.py` (separate file) is better than inlining in `main.py` | Architecture — file structure | Low — either location works; separate file is more testable |
| A3 | `redis.scan_iter("briefing:*:latency_s")` correctly matches keys written as `briefing:{user_id}:latency_s` | Pattern 4 | Low — glob pattern is standard Redis; verify key format matches D-10 |
| A4 | Pydantic-settings maps env var `LOG_LEVEL` to field `log_level` automatically | Code Examples | Low — pydantic-settings uses case-insensitive matching by default |
| A5 | `scheduler.get_jobs()` is synchronous in APScheduler 3.10.x | Pitfall 2 | Medium — if codebase uses a 4.x shim, the API may differ; check pyproject.toml pin |

## Sources

### Primary (HIGH confidence)
- Codebase grep — all 17 files with `logging.getLogger(__name__)` confirmed [VERIFIED: codebase]
- `src/daily/main.py` — existing `/health` stub (line 94–97), lifespan pattern confirmed [VERIFIED: codebase]
- `src/daily/config.py` — Settings pattern (pydantic-settings BaseSettings) confirmed [VERIFIED: codebase]
- `src/daily/briefing/scheduler.py` — `scheduler = AsyncIOScheduler(...)`, `get_jobs()` call implied by 3.x usage [VERIFIED: codebase]
- `src/daily/profile/signals.py` — `SignalLog` model with `signal_type`, `created_at` confirmed [VERIFIED: codebase]
- `src/daily/db/models.py` — `MemoryFact` table confirmed [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- Python stdlib logging documentation — `logging.Formatter`, `LoggerAdapter`, handler hierarchy [CITED: https://docs.python.org/3/library/logging.html]
- FastAPI events documentation — lifespan pattern for startup setup [CITED: https://fastapi.tiangolo.com/advanced/events/]

### Tertiary (LOW confidence — flagged as ASSUMED)
- LoggerAdapter ctx injection pattern — standard Python idiom, not verified against a running test in this session
- Redis SCAN pattern for latency key aggregation — standard Redis, not integration-tested here

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in the project, confirmed via codebase
- Architecture: HIGH — JSONFormatter and lifespan patterns are well-established stdlib patterns
- Pitfalls: HIGH — root.handlers.clear() and APScheduler version issues confirmed from codebase inspection
- Test gaps: HIGH — test files confirmed absent via directory listing

**Research date:** 2026-04-19
**Valid until:** 2026-06-01 (stdlib patterns are stable; APScheduler 3.x pin is project-controlled)
