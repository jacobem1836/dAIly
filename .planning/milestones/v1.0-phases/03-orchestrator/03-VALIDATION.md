---
phase: 3
slug: orchestrator
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-07
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `pytest tests/test_orchestrator*.py tests/test_profile*.py tests/test_signal*.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_orchestrator*.py tests/test_profile*.py tests/test_signal*.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | BRIEF-07 | T-03-01 | Redactor runs before email enters LLM context | unit | `pytest tests/test_orchestrator_thread.py -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | PERS-01 | — | N/A | unit | `pytest tests/test_profile_service.py -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | PERS-01 | — | N/A | integration | `pytest tests/test_profile_cli.py -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 0 | PERS-02 | — | N/A | unit | `pytest tests/test_signal_log.py -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 0 | D-03/SEC-05 | T-03-02 | LLM output validated against intent schema; no tool calls | unit | `pytest tests/test_orchestrator_graph.py::test_intent_validation -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 01 | 1 | D-09 | T-03-03 | thread_id scoped per user; no cross-user access | unit | `pytest tests/test_orchestrator_graph.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_orchestrator_graph.py` — stubs for D-03/SEC-05 intent validation and graph routing
- [ ] `tests/test_orchestrator_thread.py` — stubs for BRIEF-07 on-demand thread summarisation
- [ ] `tests/test_profile_service.py` — stubs for PERS-01 preference CRUD
- [ ] `tests/test_profile_cli.py` — stubs for PERS-01 CLI commands
- [ ] `tests/test_signal_log.py` — stubs for PERS-02 signal append

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Conversational follow-up feels natural | BRIEF-07 | Subjective quality of LLM response | Ask "summarise that email chain" during a briefing session; verify response is coherent and uses in-session context |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
