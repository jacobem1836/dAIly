---
phase: 15
slug: deployment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + Docker CLI |
| **Config file** | `pytest.ini` / `pyproject.toml` |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v && docker compose up --build -d && docker compose ps` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run full suite + `docker compose up --build -d`
- **Before `/gsd-verify-work`:** Full suite must be green + containers healthy
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | DEPLOY-01 | — | N/A | integration | `docker compose build --no-cache` | ✅ / ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 1 | DEPLOY-01 | — | N/A | integration | `docker compose up -d && docker compose ps` | ✅ / ❌ W0 | ⬜ pending |
| 15-01-03 | 01 | 1 | DEPLOY-01 | — | N/A | manual | verify containers healthy, API responds | — | ⬜ pending |
| 15-02-01 | 02 | 1 | DEPLOY-02 | — | no secrets committed | manual | diff .env.example vs config.py Settings fields | — | ⬜ pending |
| 15-03-01 | 03 | 1 | DEPLOY-03 | — | N/A | manual | follow VPS guide from scratch | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `docker compose up --build` succeeds from fresh clone
- [ ] Health checks pass for postgres and redis services

*Existing infrastructure covers unit/integration tests; this phase adds infra validation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh clone works end-to-end | DEPLOY-01 | Requires clean environment | Clone to temp dir, copy .env.example, run docker compose up, verify API at :8000 |
| All env vars documented | DEPLOY-02 | Requires human review | Compare .env.example to all Settings fields in config.py |
| VPS deployment guide accuracy | DEPLOY-03 | Requires live VPS or simulation | Follow guide step-by-step; verify nginx proxy + TLS termination |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
