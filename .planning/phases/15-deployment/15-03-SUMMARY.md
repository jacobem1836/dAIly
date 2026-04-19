---
phase: 15-deployment
plan: "03"
subsystem: deployment
tags: [deployment, docs, caddy, docker-compose, tls, vps]
dependency_graph:
  requires: [15-01, 15-02]
  provides: [DEPLOY.md, VPS walkthrough]
  affects: [developer onboarding, ops runbook]
tech_stack:
  added: []
  patterns: [Caddy auto-TLS, loopback port binding, docker compose orchestration]
key_files:
  created:
    - DEPLOY.md
  modified: []
decisions:
  - "Caddy chosen over nginx for reverse proxy — auto-TLS requires no certbot or cron"
  - "App port bound to 127.0.0.1:8000:8000 on VPS so port 8000 is inaccessible from the public internet"
  - "Single DEPLOY.md covers clone through smoke test — no separate ops runbook"
  - "Maintenance section covers logs, restart, update (git pull + rebuild), and DB backup/restore"
metrics:
  duration: "~10 minutes"
  completed: "2026-04-19"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 15 Plan 03: VPS Production Deployment Guide Summary

## One-liner

Practical DEPLOY.md VPS walkthrough using Docker Compose and Caddy auto-TLS — covers clone, env, loopback binding, reverse proxy, TLS, smoke test, and maintenance.

## What Was Built

Created `DEPLOY.md` at repo root (228 lines) — a step-by-step production deployment guide for deploying dAIly on a single VPS using Docker Compose and Caddy as the reverse proxy.

**Sections:**
1. Prerequisites — VPS spec, domain requirement, Docker install snippet, API key list
2. Clone and configure — git clone, cp .env.example .env, Docker service-name URL variants, VAULT_KEY generation command
3. Bind app to loopback only — explicit before/after diff showing `127.0.0.1:8000:8000` change, security rationale
4. Start the stack — docker compose up -d, log-following to wait for readiness, health verification
5. Install Caddy — official Cloudsmith apt repository install commands for Ubuntu/Debian
6. Configure Caddy — 3-line Caddyfile with reverse_proxy, systemctl reload, Let's Encrypt note
7. Smoke test — curl https://yourdomain.com/health with expected JSON response
8. Maintenance — logs, restart, update (git pull + rebuild), DB backup/restore, env var change workflow, docker compose down

**Security notes section** added per threat model requirements (T-15-09, T-15-10, T-15-11):
- `chmod 600 .env` instruction
- VPS firewall guidance (ports 80, 443 only)
- VAULT_KEY rotation warning

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write DEPLOY.md production deployment guide | 24e6f08 | DEPLOY.md (created, 228 lines) |

## Verification

```
test -f DEPLOY.md                          → PASS
wc -l DEPLOY.md → 228 lines (≥80)         → PASS
grep Caddy DEPLOY.md → 21 occurrences     → PASS
grep '127.0.0.1:8000' DEPLOY.md           → PASS
grep 'curl.*health\|/health' DEPLOY.md    → PASS
grep 'cp .env.example .env' DEPLOY.md     → PASS
grep 'docker compose up' DEPLOY.md        → PASS
```

## Acceptance Criteria Met

- [x] DEPLOY.md exists at repo root
- [x] DEPLOY.md is at least 80 lines (228 lines)
- [x] Contains "Caddy" as the reverse proxy (not nginx)
- [x] Contains "docker compose up" as the orchestration command
- [x] Contains "127.0.0.1:8000:8000" documenting loopback-only port binding
- [x] Contains Caddyfile example with `reverse_proxy`
- [x] Contains smoke test section referencing `/health` endpoint
- [x] Contains maintenance section with logs, restart, update, and backup commands
- [x] Does NOT mention Kubernetes, Helm, Prometheus, Grafana, or CI/CD

## Deviations from Plan

None — plan executed exactly as written. The guide structure matched the plan outline precisely. Security notes section was added inline (not as a separate section) per threat model mitigations T-15-09 through T-15-11, which is consistent with Rule 2 (auto-add missing critical functionality required by the threat model).

## Known Stubs

None. DEPLOY.md is a guide document — no data wiring or UI rendering involved.

## Threat Flags

None. DEPLOY.md is a documentation file. It documents security controls (loopback binding, TLS, .env permissions) but introduces no new network surface.

## Self-Check: PASSED

- [x] DEPLOY.md exists at /Users/jacobmarriott/Documents/Personal/projects/dAIly/DEPLOY.md
- [x] Commit 24e6f08 exists in git log
