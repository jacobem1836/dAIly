# Phase 15: Deployment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-19
**Phase:** 15-deployment
**Mode:** discuss

## Gray Areas Presented

| Area | Selected for discussion |
|------|------------------------|
| App in Docker Compose | ✓ |
| Reverse proxy for VPS | ✓ |
| VPS deployment method | ✓ |

## Decisions Made

### App in Docker Compose
- **Question:** Does `docker compose up` include the FastAPI app, or just postgres+redis?
- **Options:** Full stack (app + infra) vs Infra only (postgres+redis, app via uv)
- **User response:** Asked "which is best given UI is coming and it may be released publicly"
- **Decision:** Full stack — Dockerfile + app service in compose. Rationale: clone-and-go for public users, UI service adds trivially to compose, Docker restart policies replace systemd.

### Reverse Proxy
- **Question:** nginx vs Caddy for VPS guide
- **User response:** Asked "which is best for production"
- **Decision:** Caddy — auto-TLS (Let's Encrypt, no certbot/cron), minimal config, appropriate for single-host solo deploy.

### VPS Deployment Method
- **Question:** docker compose on VPS vs systemd service + Docker infra
- **User response:** Asked "which is best for production"
- **Decision:** docker compose on VPS — same file as local dev, prod env vars swapped in, `restart: unless-stopped` handles reboots. No split tooling.

## Corrections Made

None — user deferred all three decisions to recommended options.
