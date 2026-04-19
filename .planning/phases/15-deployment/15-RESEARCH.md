# Phase 15: Deployment - Research

**Researched:** 2026-04-19
**Domain:** Docker, Docker Compose, Caddy reverse proxy, VPS deployment, uv-based Python containers
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `docker compose up` starts the full stack — app (FastAPI + APScheduler), Postgres, and Redis. App runs as a Docker service.
- **D-02:** Extend the existing `docker-compose.yml` (postgres + redis only) with an `app` service. Same file for local dev and VPS.
- **D-03:** App service uses `restart: unless-stopped`.
- **D-04:** Multi-stage Dockerfile using `uv` — build stage installs with `uv sync`, final stage copies the venv. Python 3.11 slim base.
- **D-05:** Alembic migrations run in the container entrypoint before starting uvicorn (`alembic upgrade head && uvicorn ...`).
- **D-06:** App listens on `0.0.0.0:8000` inside the container.
- **D-07:** `.env.example` is fully complete — every env var in `config.py` has an entry. Currently missing: `REDIS_URL`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `LOG_LEVEL`, `BRIEFING_EMAIL_TOP_N`, `BRIEFING_SCHEDULE_TIME`, `DATABASE_URL_PSYCOPG`.
- **D-08:** Docker Compose uses service names (`postgres`, `redis`) as hostnames. `.env.example` documents both local and Docker variants with comments.
- **D-09:** `VAULT_KEY` includes the generation command inline as a comment (already present, keep it).
- **D-10:** Reverse proxy: **Caddy**. Auto-TLS via Let's Encrypt, 3-line Caddyfile.
- **D-11:** VPS orchestration: **docker compose** (not systemd). Same compose file, prod env vars swapped in via `.env`.
- **D-12:** DEPLOY.md covers: prerequisites, clone + env setup, `docker compose up -d`, Caddy install + Caddyfile, and smoke test (`GET /health`).
- **D-13:** DEPLOY.md is a practical walkthrough for a developer audience who knows Linux basics.

### Claude's Discretion

- Exact Dockerfile layer ordering and caching optimisation
- Whether `.dockerignore` is added (yes, it should be)
- docker-compose.yml service dependency ordering (`depends_on` with health checks)
- Specific Caddy version or install method in DEPLOY.md
- Healthcheck configuration in Dockerfile/compose

### Deferred Ideas (OUT OF SCOPE)

- Kubernetes/Helm charts
- Docker secrets (vs env file) for secret management
- Monitoring stack (Prometheus + Grafana)
- CI/CD pipeline (GitHub Actions build + push)
- Multi-stage prod vs dev compose files
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Docker Compose file defines the full stack (app + Postgres + Redis) and starts cleanly from a fresh clone | Dockerfile pattern + compose extension + depends_on health checks |
| DEPLOY-02 | `.env.example` documents all required environment variables with descriptions; no secrets committed | Config.py audit complete — 8 missing vars identified in D-07 |
| DEPLOY-03 | Production configuration guide covers single-host VPS deployment (Docker, reverse proxy, TLS) | Caddy auto-TLS pattern + docker compose on VPS |
</phase_requirements>

---

## Summary

Phase 15 is a pure infrastructure deliverable: three files created/extended (Dockerfile, docker-compose.yml, .env.example) plus one new file (DEPLOY.md). No application logic changes.

The project already has `docker-compose.yml` (postgres + redis) and a partial `.env.example`. The task is to add an `app` service with a multi-stage uv-based Dockerfile, complete the env var template, and write a VPS walkthrough using Caddy for reverse proxy/TLS.

The one non-obvious technical finding is the alembic URL override problem: `alembic/env.py` reads `sqlalchemy.url` from `alembic.ini` hardcoded to `localhost`. The entrypoint must override this for Docker. The cleanest approach — confirmed by alembic docs — is to set `DATABASE_URL` as an environment variable and have `env.py` read it via `os.environ.get("DATABASE_URL")` before falling back to the ini file, OR use the alembic CLI `--url` flag in the entrypoint script. The entrypoint script approach (shell script) is the standard pattern for migration-before-start in containers.

**Primary recommendation:** Use a shell entrypoint script (`scripts/entrypoint.sh`) that overrides the alembic URL via env var, runs `alembic upgrade head`, then execs uvicorn. This keeps the Dockerfile CMD clean and makes the migration step visible and debuggable.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11-slim | Container base image | Matches `requires-python = ">=3.11"` in pyproject.toml [VERIFIED: pyproject.toml] |
| uv | latest (via ghcr.io/astral-sh/uv) | Dependency install in Dockerfile | Project already uses uv; `--frozen` flag ensures reproducible installs from uv.lock [VERIFIED: project uv.lock exists] |
| Docker | 29.2.1 | Container runtime | Available on this machine [VERIFIED: docker --version] |
| Caddy | 2.x | Reverse proxy + auto-TLS | Chosen in D-10; auto-TLS with no certbot maintenance [ASSUMED: latest stable 2.x] |
| pgvector/pgvector:pg15 | pg15 | Postgres with pgvector | Already used in existing compose file [VERIFIED: docker-compose.yml] |
| redis:7 | 7 | Redis cache | Already used in existing compose file [VERIFIED: docker-compose.yml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | 1.18.4 | DB migration runner | In entrypoint before app start [VERIFIED: uv run] |

**Version verification:**
- Docker: 29.2.1 [VERIFIED: docker --version]
- Alembic: 1.18.4 [VERIFIED: uv run python -c "import alembic; print(alembic.__version__)"]

---

## Architecture Patterns

### Dockerfile: Multi-Stage with uv

The standard uv Docker pattern copies the uv binary from the official image, installs deps in a build stage, then copies the venv to a slim final image. [ASSUMED based on uv project documentation patterns; the astral-sh/uv Docker integration is well-established as of 2025]

```dockerfile
# Source: uv Docker integration pattern
FROM ghcr.io/astral-sh/uv:latest AS uv-source
FROM python:3.11-slim AS builder

COPY --from=uv-source /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS final

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/entrypoint.sh ./entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
```

**Layer caching note:** Copy `pyproject.toml` and `uv.lock` before `src/` so dependency install is cached when only application code changes.

### Alembic URL Override — Critical Pitfall

`alembic/env.py` reads `sqlalchemy.url` from `alembic.ini` (hardcoded to `localhost`). Inside a container, the Postgres host is `postgres` (the compose service name). The ini file cannot be changed at runtime. [VERIFIED: alembic/env.py line 42 reads `config.get_main_option("sqlalchemy.url")` with no env override]

**Solution — env.py modification:**

```python
# In alembic/env.py, replace the URL read with:
import os
url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
```

This is a one-line change to `alembic/env.py` that makes migrations use `DATABASE_URL` from the environment when set, falling back to `alembic.ini` for local non-Docker use. [ASSUMED: this is standard practice; alembic also supports `%%(DATABASE_URL)s` interpolation in the ini file but env.py override is simpler and avoids ini file changes]

### Entrypoint Script

```bash
#!/bin/sh
# scripts/entrypoint.sh
set -e
alembic upgrade head
exec uvicorn daily.main:app --host 0.0.0.0 --port 8000
```

Key points:
- `set -e` exits on any failure — if migrations fail, the container does not start
- `exec` replaces the shell process so uvicorn receives signals correctly (SIGTERM for graceful shutdown)
- `alembic upgrade head` uses `DATABASE_URL` from the environment (requires the env.py fix above)

### Docker Compose: App Service Addition

```yaml
# Extension to existing docker-compose.yml
app:
  build: .
  env_file: .env
  ports:
    - "8000:8000"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped

# Health checks to add to existing postgres service:
postgres:
  image: pgvector/pgvector:pg15
  ...
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U daily -d daily"]
    interval: 5s
    timeout: 5s
    retries: 5

# Health checks to add to existing redis service:
redis:
  image: redis:7
  ...
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 5
```

`depends_on` with `condition: service_healthy` ensures Postgres and Redis are accepting connections before the app starts and runs migrations. Without this, `alembic upgrade head` may fail on a race condition. [ASSUMED: standard Docker Compose health check pattern; well documented]

### .env.example Completion

Current state (from `.env.example`): 8 vars present — `DATABASE_URL`, `VAULT_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_TENANT_ID`.

Missing vars from `config.py` Settings class (D-07): `DATABASE_URL_PSYCOPG`, `REDIS_URL`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `LOG_LEVEL`, `BRIEFING_EMAIL_TOP_N`, `BRIEFING_SCHEDULE_TIME`. [VERIFIED: config.py]

Note: `DATABASE_URL_PSYCOPG` uses `postgresql://` (psycopg3 sync driver) not `postgresql+asyncpg://`. For Docker, host is `postgres`. For local dev, host is `localhost`. `.env.example` must document both variants.

### Caddy Reverse Proxy (DEPLOY.md)

```caddyfile
# /etc/caddy/Caddyfile
yourdomain.com {
    reverse_proxy localhost:8000
}
```

Caddy auto-obtains and renews TLS from Let's Encrypt. No certbot, no cron. [ASSUMED: Caddy 2.x auto-TLS behavior is well established]

**Caddy install on Ubuntu/Debian VPS:**
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

### .dockerignore

Must exclude: `.git`, `__pycache__`, `*.pyc`, `tests/`, `.env`, `.venv`, `*.egg-info`, `uv 2.lock` (old lock file), `landing/`, `marketing/`, `*.png`. This keeps the build context small and prevents `.env` from leaking into the image. [ASSUMED: standard .dockerignore patterns]

### Anti-Patterns to Avoid

- **No `CMD` with shell form for signal forwarding:** Use `exec` in entrypoint script so uvicorn gets SIGTERM directly. Shell form wraps process in `/bin/sh -c` and swallows signals.
- **No migration in Dockerfile RUN:** Migrations touch the database, which doesn't exist at build time. Run them in the entrypoint.
- **No hardcoded credentials in compose or Dockerfile:** Use `env_file: .env` in compose, never `environment: OPENAI_API_KEY=sk-...`.
- **No `COPY . .` before dependency install:** Breaks layer caching every time source changes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS certificate management | certbot + cron | Caddy auto-TLS | Caddy handles ACME, renewal, and rotation automatically |
| Process supervision | Custom shell wrapper | `restart: unless-stopped` in compose | Docker handles restart policy natively |
| Dependency snapshot | pip freeze | `uv sync --frozen` with uv.lock | uv.lock guarantees byte-for-byte reproducible installs |
| Health check retry logic | Custom wait loop | `depends_on: condition: service_healthy` | Docker Compose handles retry with configurable interval/retries |

---

## Common Pitfalls

### Pitfall 1: Alembic URL Points to localhost Inside Container
**What goes wrong:** `alembic upgrade head` fails with connection refused because `alembic.ini` has `localhost` hardcoded, but Postgres is at `postgres` inside the Docker network.
**Why it happens:** `alembic/env.py` calls `config.get_main_option("sqlalchemy.url")` without checking environment variables.
**How to avoid:** Patch `env.py` to read `os.environ.get("DATABASE_URL", ...)` before the ini file value. This is a required code change in this phase.
**Warning signs:** `alembic upgrade head` exits non-zero; container exits immediately on startup.

### Pitfall 2: App Starts Before Postgres Accepts Connections
**What goes wrong:** Container starts, migrations fail because Postgres is still initialising, container exits.
**Why it happens:** `depends_on: [postgres]` without a health check condition only waits for container start, not DB readiness.
**How to avoid:** Add `healthcheck` to postgres service + `depends_on: condition: service_healthy` for the app service.
**Warning signs:** Intermittent startup failures on first `docker compose up`.

### Pitfall 3: .env File Committed to Git
**What goes wrong:** Real credentials leaked to the repository.
**Why it happens:** Developer copies `.env.example` to `.env`, sets real keys, forgets that `.env` is not gitignored.
**How to avoid:** Verify `.gitignore` contains `.env`. Add it if missing.
**Warning signs:** `git status` shows `.env` as untracked.

### Pitfall 4: sounddevice Fails in Container
**What goes wrong:** `sounddevice` imports fail because there are no audio devices in a headless container; app refuses to start.
**Why it happens:** `sounddevice` is in the main dependencies and may attempt device enumeration at import time.
**How to avoid:** This is a known issue for voice apps deployed as servers — the voice input path is only used when running the CLI, not the FastAPI server. Confirm that `daily.main` does not import `sounddevice` at module level. If it does, lazy-import it inside the CLI commands only.
**Warning signs:** `ImportError` or `RuntimeError` mentioning PortAudio or ALSA in container logs.

### Pitfall 5: DATABASE_URL_PSYCOPG Uses Wrong Driver Prefix in Container
**What goes wrong:** LangGraph checkpoint or psycopg-based code fails because `DATABASE_URL_PSYCOPG` still uses `localhost`.
**Why it happens:** This setting is separate from `DATABASE_URL` (asyncpg) — it must also be updated for Docker service name.
**How to avoid:** `.env.example` must document both vars with the Docker service name variant clearly commented.
**Warning signs:** LangGraph checkpoint connection errors; psycopg pool errors at startup.

---

## Code Examples

### Verified: settings.py full var list
```python
# Source: src/daily/config.py (verified)
class Settings(BaseSettings):
    database_url: str          # asyncpg — Docker host: postgres
    database_url_psycopg: str  # psycopg3 — Docker host: postgres
    vault_key: str
    google_client_id: str
    google_client_secret: str
    slack_client_id: str
    slack_client_secret: str
    microsoft_client_id: str
    microsoft_tenant_id: str
    redis_url: str             # Docker host: redis
    openai_api_key: str
    deepgram_api_key: str
    cartesia_api_key: str
    briefing_email_top_n: int  # default 5
    briefing_schedule_time: str # default "05:00"
    log_level: str             # default "INFO"
```

### .env.example Complete Template
```bash
# --- Database ---
# Local dev: postgresql+asyncpg://daily:daily_dev@localhost:5432/daily
# Docker Compose: postgresql+asyncpg://daily:daily_dev@postgres:5432/daily
DATABASE_URL=postgresql+asyncpg://daily:daily_dev@localhost:5432/daily

# Sync driver (psycopg3) used by LangGraph checkpointer
# Local dev: postgresql://daily:daily_dev@localhost:5432/daily
# Docker Compose: postgresql://daily:daily_dev@postgres:5432/daily
DATABASE_URL_PSYCOPG=postgresql://daily:daily_dev@localhost:5432/daily

# --- Redis ---
# Local dev: redis://localhost:6379/0
# Docker Compose: redis://redis:6379/0
REDIS_URL=redis://localhost:6379/0

# --- Encryption ---
VAULT_KEY=  # Generate with: python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"

# --- OAuth: Google ---
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# --- OAuth: Slack ---
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=

# --- OAuth: Microsoft ---
MICROSOFT_CLIENT_ID=
MICROSOFT_TENANT_ID=

# --- LLM ---
OPENAI_API_KEY=

# --- Voice: STT ---
DEEPGRAM_API_KEY=

# --- Voice: TTS ---
CARTESIA_API_KEY=

# --- Briefing pipeline ---
BRIEFING_EMAIL_TOP_N=5
BRIEFING_SCHEDULE_TIME=05:00

# --- Observability ---
LOG_LEVEL=INFO
```

---

## Runtime State Inventory

> Step 2.5: Not a rename/refactor/migration phase. SKIPPED.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container build/run | ✓ | 29.2.1 | — |
| Caddy | DEPLOY.md walkthrough | ✗ | — | nginx (not chosen; Caddy is locked) |
| uv | Dockerfile build | ✓ | available in project | — |
| alembic | Entrypoint migration | ✓ | 1.18.4 | — |

**Missing dependencies with no fallback:**
- Caddy: not installed on this development machine, but DEPLOY.md is a guide for a VPS — Caddy is installed on the VPS, not the dev machine. No blocker.

**Missing dependencies with fallback:**
- None blocking.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-01 | docker compose up starts full stack from fresh clone | manual smoke | `docker compose up -d && curl http://localhost:8000/health` | ❌ Wave 0 — manual verification only |
| DEPLOY-02 | .env.example has all vars, no secrets in git | automated | `git diff HEAD -- .env.example; grep -v '=.*[a-zA-Z0-9]' .env.example` | ❌ Wave 0 — script check |
| DEPLOY-03 | DEPLOY.md exists and is non-trivial | file existence check | `test -f DEPLOY.md && wc -l DEPLOY.md` | ❌ Wave 0 |

**Note:** DEPLOY-01 is fundamentally a manual verification. The planner should include a smoke test step at the end of the phase (run compose locally, hit /health) rather than a unit test.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ --tb=short`
- **Phase gate:** Full suite green + manual `docker compose up` smoke test before `/gsd-verify-work`

### Wave 0 Gaps
- No new test files needed — this phase is infrastructure only
- Smoke test is manual: `docker compose up -d && sleep 10 && curl -f http://localhost:8000/health`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | no | — |
| V6 Cryptography | yes | AES-256-GCM via cryptography lib (already in place) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets in Docker image layers | Information disclosure | Never `COPY .env` into image; use `env_file:` in compose at runtime only |
| Secrets committed to git | Information disclosure | `.gitignore` must contain `.env`; `.env.example` must have no real values |
| Exposed port 8000 on VPS | Spoofing/tampering | Bind app to localhost only on VPS; Caddy proxies from 443 |

**Critical:** On VPS, the compose port mapping for the app should be `127.0.0.1:8000:8000` (bind to loopback only) so port 8000 is not publicly accessible. Caddy proxies to `localhost:8000`. This should be documented in DEPLOY.md. [ASSUMED: standard VPS hardening pattern]

---

## Open Questions

1. **sounddevice in container**
   - What we know: `sounddevice` is in `pyproject.toml` dependencies; it requires PortAudio at the OS level
   - What's unclear: Whether `daily.main` imports it at module level (which would crash the server container)
   - Recommendation: Planner should include a task to verify `daily.main` doesn't transitively import sounddevice; if it does, add PortAudio to the final Docker image (`apt-get install -y libportaudio2`) or make the import lazy

2. **alembic.ini URL override**
   - What we know: `alembic/env.py` does not read `DATABASE_URL` from the environment
   - What's unclear: Whether the user wants to modify `env.py` (application code change) or use a workaround in the entrypoint script (`alembic -x sqlalchemy.url=... upgrade head`)
   - Recommendation: Modify `env.py` — it is the cleaner solution and is idiomatic. The `-x` flag approach is brittle with shell quoting.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | uv Docker integration uses `ghcr.io/astral-sh/uv` as the source image for the binary | Standard Stack / Architecture | Wrong image name; fix by checking uv docs. Low risk — well known. |
| A2 | `depends_on: condition: service_healthy` is supported in Compose v2 (Docker Compose standalone 2.x) | Architecture Patterns | Falls back to `depends_on: [postgres]` without health guarantee. Docker 29.2.1 confirmed on this machine. |
| A3 | Caddy 2.x auto-TLS works by pointing the Caddyfile domain to the server's public IP | Architecture Patterns | User needs a real domain pointed at VPS IP for Let's Encrypt to work — DEPLOY.md must note this prerequisite |
| A4 | On VPS, compose port should bind to `127.0.0.1:8000:8000` not `0.0.0.0:8000:8000` | Security Domain | If wrong: port 8000 is publicly accessible without TLS. Low consequence (health endpoint is public anyway) but bad practice. |
| A5 | `sounddevice` does not import at `daily.main` module load time | Common Pitfalls | If wrong: container startup fails due to missing PortAudio. Needs verification during implementation. |

---

## Sources

### Primary (HIGH confidence)
- `docker-compose.yml` — existing services (postgres, redis) verified in repo
- `src/daily/config.py` — complete Settings class, all env vars verified
- `alembic/env.py` — URL read logic verified (no DATABASE_URL env override)
- `pyproject.toml` — Python version constraint, project name, uv.lock presence verified
- Docker 29.2.1 — verified via `docker --version`
- Alembic 1.18.4 — verified via `uv run python -c "import alembic; print(alembic.__version__)"`

### Secondary (MEDIUM confidence)
- `.env.example` — existing var list verified; identified 8 missing vars matching config.py

### Tertiary (LOW confidence — ASSUMED)
- uv Docker integration patterns [ASSUMED based on training knowledge of astral-sh/uv project]
- Caddy 2.x auto-TLS Caddyfile syntax [ASSUMED]
- Docker Compose `depends_on: condition: service_healthy` behaviour [ASSUMED — well documented pattern]

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — versions verified from project files and running docker
- Architecture: MEDIUM — Dockerfile/compose patterns are assumed from training; core logic (alembic URL) verified from source
- Pitfalls: HIGH — alembic URL pitfall verified from code; others are standard Docker pitfalls

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (stable domain — Docker/Compose patterns don't shift rapidly)
