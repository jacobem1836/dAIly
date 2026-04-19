# Phase 15: Deployment - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the full dAIly stack deployable from a fresh clone — locally and on a VPS. Deliver: a Dockerfile for the app, a complete docker-compose.yml (app + postgres + redis), a complete .env.example, and a DEPLOY.md VPS production guide. No new features, no new services beyond the container layer.

</domain>

<decisions>
## Implementation Decisions

### Docker Compose Scope
- **D-01:** `docker compose up` starts the full stack — app (FastAPI + APScheduler), Postgres, and Redis. App runs as a Docker service, not natively via uv. This is the correct choice for public release readiness and future UI service addition.
- **D-02:** The existing `docker-compose.yml` (postgres + redis only) is extended with an `app` service. Same file for local dev and VPS — no separate prod compose file.
- **D-03:** App service uses `restart: unless-stopped` so the stack recovers from reboots on VPS without extra tooling.

### Dockerfile
- **D-04:** Multi-stage Dockerfile using `uv` — build stage installs dependencies with `uv sync`, final stage copies the venv. Uses Python 3.11 slim base.
- **D-05:** Alembic migrations run in the container entrypoint before starting uvicorn (`alembic upgrade head && uvicorn ...`). Developer doesn't need to run migrations manually.
- **D-06:** App listens on `0.0.0.0:8000` inside the container, exposed via compose port mapping.

### .env.example
- **D-07:** `.env.example` is fully complete — every env var in `config.py` has a corresponding entry with a description and placeholder. Currently missing: `REDIS_URL`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `LOG_LEVEL`, `BRIEFING_EMAIL_TOP_N`, `BRIEFING_SCHEDULE_TIME`, `DATABASE_URL_PSYCOPG`.
- **D-08:** For Docker Compose, `DATABASE_URL` and `REDIS_URL` use service names (`postgres`, `redis`) as hostnames. `.env.example` documents both local (localhost) and Docker (service name) variants with comments.
- **D-09:** `VAULT_KEY` includes the generation command inline as a comment (already present, keep it).

### VPS Production Guide (DEPLOY.md)
- **D-10:** Reverse proxy: **Caddy**. Auto-TLS via Let's Encrypt, 3-line Caddyfile. No certbot/cron required.
- **D-11:** VPS orchestration: **docker compose** (not systemd). Same compose file, prod env vars swapped in via `.env`. Stack managed entirely through Docker.
- **D-12:** DEPLOY.md covers: prerequisites (VPS, domain, Docker), clone + env setup, `docker compose up -d`, Caddy install + Caddyfile, and a post-deploy smoke test (hit `/health`).
- **D-13:** DEPLOY.md is a practical walkthrough, not exhaustive documentation. Assume a developer audience who knows Linux basics.

### Claude's Discretion
- Exact Dockerfile layer ordering and caching optimisation
- Whether `.dockerignore` is added (yes, it should be)
- docker-compose.yml service dependency ordering (`depends_on` with health checks)
- Specific Caddy version or install method in DEPLOY.md
- Healthcheck configuration in Dockerfile/compose

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DEPLOY-01, DEPLOY-02, DEPLOY-03 definitions

### Existing deployment artifacts (to extend, not replace)
- `docker-compose.yml` — current postgres + redis services; add app service here
- `.env.example` — current incomplete template; complete it

### App entrypoint and config
- `src/daily/main.py` — FastAPI app; entrypoint for uvicorn in Dockerfile CMD
- `src/daily/config.py` — full list of env vars (`Settings` class); source of truth for `.env.example` completeness
- `pyproject.toml` — project name, scripts, Python version constraint; informs Dockerfile setup
- `alembic.ini` — alembic config; migrations command reference for entrypoint script

### Phase context for integration points
- `.planning/phases/14-observability/14-CONTEXT.md` — `/health` endpoint shape; use as smoke test target in DEPLOY.md

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker-compose.yml` — postgres + redis services already correct; extend with app service block
- `.env.example` — base structure exists; add missing vars following same format
- `pyproject.toml` `[project.scripts]` — `daily = "daily.cli:app"` (CLI entrypoint); uvicorn runs `daily.main:app`
- `uv.lock` / `uv 2.lock` — lock files exist; Dockerfile should use `uv sync --frozen` for reproducibility

### Established Patterns
- `config.py` uses `pydantic_settings.BaseSettings` with `env_file=".env"` — Docker passes env vars directly; `.env` file not needed inside container, env vars set in compose `environment:` or `env_file:`
- App starts cleanly with `uvicorn daily.main:app --host 0.0.0.0 --port 8000`
- Alembic configured in `alembic.ini` at repo root; `alembic upgrade head` is the migration command

### Integration Points
- Dockerfile CMD must run migrations then start uvicorn (or use an entrypoint script)
- Docker Compose `app` service needs `DATABASE_URL` with `postgres` hostname (not `localhost`)
- `depends_on: [postgres, redis]` with health checks ensures DB is ready before app starts
- `/health` endpoint (from Phase 14) is the correct smoke test in DEPLOY.md

</code_context>

<specifics>
## Specific Ideas

- Stack is intended for public release and will have a web UI added (v2.0) — docker-compose.yml structure should make adding a `frontend` service easy (it already will be, with separate service blocks)
- Caddy chosen over nginx specifically for auto-TLS — no certbot/cron maintenance burden for a solo deployer
- VPS deployment uses the same compose file as local dev, just with production env vars — "one file manages everything" principle
- Smoke test in DEPLOY.md should hit `GET /health` and confirm `{"status": "ok"}` — Phase 14 endpoint

</specifics>

<deferred>
## Deferred Ideas

- Kubernetes/Helm charts — out of scope until significant scale
- Docker secrets (vs env file) for secret management — overkill for single-host M1 deployment; worth revisiting at v2.0
- Monitoring stack (Prometheus + Grafana) — Phase 14 deferred this; out of scope for Phase 15
- CI/CD pipeline (GitHub Actions build + push) — future phase
- Multi-stage prod vs dev compose files — premature; single compose file is correct for now

</deferred>

---

*Phase: 15-deployment*
*Context gathered: 2026-04-19*
