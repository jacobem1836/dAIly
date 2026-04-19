---
phase: 15-deployment
plan: "01"
subsystem: deployment
tags: [docker, dockerfile, docker-compose, alembic, deployment]
dependency_graph:
  requires: []
  provides: [docker-stack, app-container, health-checked-compose]
  affects: [vps-deployment, local-dev-stack]
tech_stack:
  added: [ghcr.io/astral-sh/uv multi-stage Dockerfile, docker-compose health checks]
  patterns: [multi-stage-dockerfile, entrypoint-migrations, service_healthy-depends_on]
key_files:
  created:
    - Dockerfile
    - .dockerignore
    - scripts/entrypoint.sh
  modified:
    - alembic/env.py
    - docker-compose.yml
decisions:
  - Multi-stage Dockerfile uses ghcr.io/astral-sh/uv for the uv binary only; python:3.11-slim for runtime
  - Layer caching: pyproject.toml + uv.lock copied before src/ so dep layer is stable across code changes
  - entrypoint.sh uses set -e + exec so migration failures stop the container and uvicorn gets SIGTERM
  - alembic/env.py patched to prefer DATABASE_URL env var — enables postgres service hostname in Docker
  - app service uses env_file not hardcoded environment block to avoid baking config into compose
metrics:
  duration: "15m"
  completed: "2026-04-19"
  tasks_completed: 2
  files_changed: 5
requirements_satisfied: [DEPLOY-01]
---

# Phase 15 Plan 01: Docker Infrastructure Summary

**One-liner:** Multi-stage uv Dockerfile, entrypoint with Alembic auto-migrations, and docker-compose.yml with health-checked app + postgres + redis services.

## What Was Done

Tasks 1 and 2 created the complete Docker infrastructure for a fresh-clone deployment.

**Task 1** produced four artifacts: a multi-stage Dockerfile using the uv binary for reproducible installs, a `.dockerignore` excluding secrets and build noise from the image, `scripts/entrypoint.sh` that runs `alembic upgrade head` before `exec uvicorn`, and a one-line patch to `alembic/env.py` to read `DATABASE_URL` from the environment (allowing Docker's `postgres` hostname to override the `localhost` default in `alembic.ini`).

**Task 2** extended `docker-compose.yml` with postgres and redis health checks, and a new `app` service that waits for both dependencies to be healthy before starting.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Dockerfile, .dockerignore, entrypoint, alembic patch | 8297010 | Dockerfile, .dockerignore, scripts/entrypoint.sh, alembic/env.py |
| 2 | Extend docker-compose.yml with app service and health checks | cba7905 | docker-compose.yml |

## Verification Results

- `docker compose config --quiet` exits 0 — schema valid
- All must-have files exist: Dockerfile, .dockerignore, scripts/entrypoint.sh
- alembic/env.py contains `os.environ.get` in both offline and online migration paths
- .dockerignore contains `.env` and `.git`
- docker-compose.yml contains `pg_isready`, `redis-cli ping`, `service_healthy`, `build: .`, `env_file: .env`, `unless-stopped`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All files are fully wired — no placeholder content.

## Threat Flags

Threat mitigations confirmed per threat model:
- T-15-01: `.env` excluded from .dockerignore — secrets never baked into image layers
- T-15-02: `.git` excluded from .dockerignore — no repo history in container
- T-15-03: entrypoint.sh uses `set -e` (fail fast on migration error) + `exec` (proper SIGTERM handling)
- T-15-04: depends_on with `condition: service_healthy` prevents startup race condition
- T-15-05: Accepted — container runs as root; tracked as v2.0 hardening item

## Self-Check: PASSED

- [x] Dockerfile exists: `test -f Dockerfile` passes
- [x] .dockerignore exists: `test -f .dockerignore` passes
- [x] scripts/entrypoint.sh exists: `test -f scripts/entrypoint.sh` passes
- [x] alembic/env.py patched: `grep -c 'os.environ.get' alembic/env.py` returns 2
- [x] docker-compose.yml valid: `docker compose config --quiet` exits 0
- [x] Commit 8297010 exists
- [x] Commit cba7905 exists

## Checkpoint Pending

Task 3 is a `checkpoint:human-verify` — user must verify the Docker stack starts end-to-end. Plan execution is paused at this checkpoint.
