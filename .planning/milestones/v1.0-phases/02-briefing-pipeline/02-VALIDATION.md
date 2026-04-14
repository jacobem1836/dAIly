---
phase: 2
slug: briefing-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_briefing_pipeline.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_briefing_pipeline.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | BRIEF-03 | — | N/A | unit | `pytest tests/test_briefing_models.py -xq` | Yes (Plan 01) | ⬜ pending |
| 02-01-02 | 01 | 1 | BRIEF-05 | — | N/A | unit | `pytest tests/test_briefing_models.py -xq` | Yes (Plan 01) | ⬜ pending |
| 02-02-01 | 02 | 2 | BRIEF-03 | — | N/A | unit | `pytest tests/test_briefing_ranker.py -xq` | Yes (Plan 02) | ⬜ pending |
| 02-02-02 | 02 | 2 | BRIEF-04 | — | N/A | unit | `pytest tests/test_briefing_context.py -xq` | Yes (Plan 02) | ⬜ pending |
| 02-03-01 | 03 | 2 | SEC-02 | T-02-06, T-02-07 | Raw message bodies never passed to LLM; credentials regex-stripped | unit | `pytest tests/test_briefing_redactor.py -xq` | Yes (Plan 03) | ⬜ pending |
| 02-03-02 | 03 | 2 | SEC-05 | T-02-08 | Structured JSON output enforced; no tools/function_call | unit | `pytest tests/test_briefing_narrator.py -xq` | Yes (Plan 03) | ⬜ pending |
| 02-04-01 | 04 | 3 | BRIEF-02 | — | N/A | unit | `pytest tests/test_briefing_scheduler.py -xq` | Yes (Plan 04) | ⬜ pending |
| 02-04-02 | 04 | 3 | BRIEF-01 | — | N/A | unit+integration | `pytest tests/test_briefing_cache.py tests/test_briefing_pipeline.py -xq` | Yes (Plan 04) | ⬜ pending |
| 02-04-03 | 04 | 3 | PERS-03 | — | N/A | unit | `pytest tests/test_briefing_ranker.py::test_vip_override -xq` | Yes (Plan 02) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_briefing_models.py` — model validation tests (created by Plan 01 Task 2)
- [ ] `tests/test_briefing_ranker.py` — heuristic ranking tests (created by Plan 02 Task 1)
- [ ] `tests/test_briefing_context.py` — context builder tests (created by Plan 02 Task 2)
- [ ] `tests/test_briefing_redactor.py` — SEC-02 redaction layer tests (created by Plan 03 Task 1)
- [ ] `tests/test_briefing_narrator.py` — SEC-05 structured output tests (created by Plan 03 Task 2)
- [ ] `tests/test_briefing_cache.py` — BRIEF-01 Redis cache tests (created by Plan 04 Task 1)
- [ ] `tests/test_briefing_scheduler.py` — BRIEF-02 APScheduler config tests (created by Plan 04 Task 1)
- [ ] `tests/test_briefing_pipeline.py` — end-to-end pipeline + latency tests (created by Plan 04 Task 2)
- [ ] `tests/conftest.py` — shared fixtures (mock Redis, mock LLM responses, mock adapter data)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Briefing serves from cache within 1 second | BRIEF-01 | Real Redis timing varies; automated test uses fakeredis with <0.1s assertion as proxy | Start server, wait for precomputed briefing, request via API, measure wall-clock response time |
| Schedule change persists across restarts | BRIEF-02 | Requires process restart | Update schedule via CLI, restart server, verify scheduler fires at new time |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
