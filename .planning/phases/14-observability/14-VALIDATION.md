---
phase: 14
slug: observability
status: compliant
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-19
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/test_logging_config.py tests/test_health_endpoint.py tests/test_metrics_endpoint.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_logging_config.py tests/test_health_endpoint.py tests/test_metrics_endpoint.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-W0-01 | 01 | 0 | OBS-01, OBS-02 | — | N/A | unit | `pytest tests/test_logging_config.py -x` | ❌ W0 | ⬜ pending |
| 14-W0-02 | 01 | 0 | OBS-03 | — | N/A | unit | `pytest tests/test_health_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 14-W0-03 | 01 | 0 | OBS-04 | — | N/A | unit | `pytest tests/test_metrics_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 14-01-01 | 01 | 1 | OBS-01 | — | JSONFormatter emits valid JSON with all required fields | unit | `pytest tests/test_logging_config.py -x` | ❌ W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | OBS-01 | — | ctx field carries user_id and stage via LoggerAdapter | unit | `pytest tests/test_logging_config.py -x` | ❌ W0 | ⬜ pending |
| 14-01-03 | 01 | 1 | OBS-02 | — | LOG_LEVEL env var controls verbosity without code changes | unit | `pytest tests/test_logging_config.py -x` | ❌ W0 | ⬜ pending |
| 14-01-04 | 01 | 2 | OBS-03 | — | GET /health 200 when all healthy; 503 when degraded | unit | `pytest tests/test_health_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 14-01-05 | 01 | 2 | OBS-04 | — | GET /metrics returns signal counts and latency from Redis | unit | `pytest tests/test_metrics_endpoint.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_logging_config.py` — stubs for OBS-01, OBS-02
- [ ] `tests/test_health_endpoint.py` — stubs for OBS-03
- [ ] `tests/test_metrics_endpoint.py` — stubs for OBS-04

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Log output readable in Docker/terminal at runtime | OBS-01 | Requires live process inspection | Run app, tail logs, verify JSON format visually |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (2026-04-19 — all 14 tests passing)
