# Phase 14: Observability - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Add structured logging, configurable log level, an enhanced health endpoint, and a metrics endpoint to the existing FastAPI backend. Every module already uses `logging.getLogger(__name__)` — this phase wires a JSON formatter into the root logger and adds two endpoints. No new services, no new infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Structured Logging
- **D-01:** Use stdlib `logging` with a custom `JSONFormatter` — zero new dependencies. All 58 existing `logger.*()` calls work unchanged; the formatter intercepts at the handler level.
- **D-02:** JSON log shape: `{"ts": "<ISO-8601>", "level": "INFO", "module": "briefing.pipeline", "msg": "...", "ctx": {...}}`
- **D-03:** Log context (`ctx` field) carries `user_id` and `stage` (pipeline stage label, e.g. `"precompute"`, `"voice.loop"`). No request_id at this scale — see Deferred.
- **D-04:** `LOG_LEVEL` env var controls verbosity. `LOG_LEVEL=DEBUG` → verbose; `LOG_LEVEL=WARNING` → suppress info. Applied at root logger setup in `main.py`. Default: `INFO`.

### Health Endpoint (`GET /health`)
- **D-05:** `/health` is liveness-only — fast, cheap, safe to hammer from uptime monitors. Returns: DB connectivity, Redis connectivity, scheduler state. No metrics on this endpoint.
- **D-06:** DB check: attempt a lightweight query (`SELECT 1`). Redis check: `PING`. Scheduler check: verify APScheduler has at least one active job.
- **D-07:** Response shape:
  ```json
  {"status": "ok", "db": "ok", "redis": "ok", "scheduler": "running"}
  ```
  On any failure: `{"status": "degraded", "db": "error: <msg>", ...}` with HTTP 503.

### Metrics Endpoint (`GET /metrics`)
- **D-08:** Separate `/metrics` route — keeps liveness and performance concerns separated. Load balancers/uptime monitors hit `/health`; ops tooling hits `/metrics`.
- **D-09:** Metrics computed via live DB queries at request time. Tables are small (signal_log, user_memory_embeddings); COUNT queries on indexed columns run sub-millisecond at 100 users.
- **D-10:** Briefing latency stored in Redis per user at precompute time (`briefing:{user_id}:latency_s = <float>`). `/metrics` reads all per-user values and returns aggregate average. Accurate, zero extra DB overhead.
- **D-11:** Signal counts use a 7-day rolling window. Matches the adaptive ranker's 30-day window but gives a more operationally relevant recent view.
- **D-12:** Metrics response shape:
  ```json
  {
    "briefing_latency_avg_s": 4.2,
    "signals_7d": {"skip": 12, "expand": 34, "re_request": 5},
    "memory_entries": 87
  }
  ```
  Field names chosen to mirror Prometheus gauge/counter naming conventions (snake_case, unit suffix `_s`, window suffix `_7d`) — makes a future Prometheus exporter a drop-in swap.

### Claude's Discretion
- Exact `JSONFormatter` implementation (subclass `logging.Formatter`, override `format()`)
- Where logging setup lives (`main.py` lifespan, or a `logging_config.py` imported at startup)
- How `stage` context is passed (thread-local, `logging.LoggerAdapter`, or explicit kwarg pattern)
- Whether `/metrics` is authenticated or open (open is fine for M1 single-host deployment)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — OBS-01, OBS-02, OBS-03, OBS-04 definitions

### Existing logging surface
- `src/daily/main.py` — FastAPI app, lifespan, existing basic `/health` endpoint (line ~94), scheduler startup; central logging setup goes here
- `src/daily/config.py` — settings/env var loading; `LOG_LEVEL` env var should be added here

### Modules with existing logger calls (all need context threading)
- `src/daily/briefing/pipeline.py` — briefing precompute; latency timing and Redis write go here
- `src/daily/briefing/context_builder.py` — integration ingestion; highest value for stage logging
- `src/daily/orchestrator/nodes.py` — LangGraph nodes; user_id available in SessionState
- `src/daily/voice/loop.py` — voice session; stage = "voice.loop"
- `src/daily/profile/signals.py` — signal writes; stage = "profile.signals"

### Data sources for metrics
- `src/daily/profile/signals.py` — `SignalLog` table (signal counts query)
- `src/daily/profile/memory.py` — user memory embeddings table (memory_entries count)
- Redis — `briefing:{user_id}:latency_s` keys (briefing latency)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `logging.getLogger(__name__)` — already in every module; formatter change is transparent to call sites
- Existing `/health` endpoint in `main.py` — replace body, keep route
- `config.py` settings pattern — add `LOG_LEVEL: str = "INFO"` following existing env var pattern
- Redis client already available in briefing pipeline — write latency key alongside narrative key

### Established Patterns
- FastAPI lifespan (`@asynccontextmanager`) in `main.py` — logging setup belongs in lifespan startup
- `settings` object from `config.py` imported across modules — `LOG_LEVEL` follows same pattern
- `AsyncSession` dependency injection — metrics DB queries use same `get_db_session` dependency
- Redis `aioredis` client already used in pipeline — reuse for latency key reads in `/metrics`

### Integration Points
- `briefing/pipeline.py` precompute: after `await pipeline.run()`, write `time.monotonic()` delta to Redis key `briefing:{user_id}:latency_s`
- `main.py` lifespan startup: configure root logger with `JSONFormatter` and `LOG_LEVEL` from settings
- `main.py` routes: replace existing stub `/health`, add new `/metrics`

</code_context>

<specifics>
## Specific Ideas

- Field names on `/metrics` mirror Prometheus conventions (`_s` for seconds, `_7d` for 7-day window) so a future Prometheus exporter is a drop-in swap — no endpoint redesign needed
- `/health` returns HTTP 503 on any dependency failure — uptime monitors can alert on non-200 without parsing the body
- `stage` in log context should be a short dotted string matching the module path: `"briefing.pipeline"`, `"voice.loop"`, `"orchestrator.nodes"` — consistent with the `module` field but at a logical level

</specifics>

<deferred>
## Deferred Ideas — Production Scale Notes

These are the choices that would change at significantly larger scale (1k+ users, high concurrency, production SLA). Captured here so they're not forgotten when v2.0 planning begins.

### Logging
- **Switch to `structlog`** — at high volume, structlog's processor chain (context binding, sampling, async-safe output) is cleaner than a stdlib formatter. Zero behaviour change at the call site.
- **Add `request_id` (UUID) to log context** — when many users' pipelines run concurrently, request_id lets you filter a single briefing run or voice session across all modules. Not needed at 100 users (same-user concurrency is near-zero), valuable at 1k+.

### Metrics
- **Replace live DB queries with Prometheus counters** — at scale, hitting the DB on every `/metrics` scrape (Prometheus scrapes every 15s) creates unnecessary load. Increment in-memory Prometheus counters on each event; expose `/metrics` in Prometheus exposition format. Run Prometheus + Grafana for time series, alerting, and dashboards.
- **Add p95/p99 latency percentiles** — aggregate average hides outliers. Prometheus histograms give p95/p99 for free. At 100 users, average is sufficient; at 1k+ users, percentiles are the right signal.
- **Per-user latency breakdown** — expose individual user latencies (not just aggregate) for diagnosing one user with slow integrations. Noisy at scale; useful for smaller deployments or admin views.

### Health
- **Add per-dependency response time** — include DB query latency and Redis PING latency in `/health` response for SLA monitoring. Useful when dependencies are remote (RDS, ElastiCache) rather than local Docker containers.
- **Separate liveness vs readiness probes** — k8s pattern: `/health/live` (is the process alive?) vs `/health/ready` (can it serve traffic?). Overkill for Docker Compose single-host; required for k8s deployments.

</deferred>

---

*Phase: 14-observability*
*Context gathered: 2026-04-19*
