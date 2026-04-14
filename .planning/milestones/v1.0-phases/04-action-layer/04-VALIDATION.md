---
phase: 04
slug: action-layer
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-10
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `uv run pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `uv run pytest tests/ -v --timeout=60`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|--------|
| 04-01-1a | 01 | 1 | ACT-05, ACT-06 | T-04-04 | Whitelist rejects unknown recipients | unit | `uv run pytest tests/test_action_executor.py -x` | pending |
| 04-01-1b | 01 | 1 | ACT-04 | T-04-03 | Body hash stored, no raw body | unit | `uv run pytest tests/test_action_log.py -x` | pending |
| 04-01-02 | 01 | 1 | ACT-05, ACT-06 | T-04-02 | No action executes without approval | unit | `uv run pytest tests/test_action_approval.py -x` | pending |
| 04-02-01 | 02 | 2 | ACT-01, ACT-02 | T-04-09 | No tools= on LLM call | unit | `uv run pytest tests/test_action_draft.py -x` | pending |
| 04-02-02 | 02 | 2 | ACT-03, ACT-04 | T-04-10 | Approval input validated | unit | `uv run pytest tests/test_cli_approval.py -x` | pending |
| 04-03-01 | 03 | 2 | ACT-01, ACT-02, ACT-06 | T-04-11, T-04-17 | Scope + whitelist validation before API call | unit | `uv run pytest tests/test_action_executors.py -x` | pending |
| 04-03-02 | 03 | 2 | ACT-03, ACT-05 | T-04-16 | Provider routing + dispatch | unit | `uv run pytest tests/test_action_executors.py -x` | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 — Not Required

All plans use `tdd="true"` on tasks, meaning tests are created inline within each task's
execution (RED-GREEN-REFACTOR cycle). No separate Wave 0 test scaffold plan is needed.

Test files created by each plan:
- Plan 01: `tests/test_action_executor.py`, `tests/test_action_log.py`, `tests/test_action_approval.py`
- Plan 02: `tests/test_action_draft.py`, `tests/test_cli_approval.py`
- Plan 03: `tests/test_action_executors.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Voice approval flow | ACT-03 | Requires real STT/TTS loop (Phase 5) | Trigger action via CLI, speak "confirm", verify execution |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 not needed (TDD inline creates tests)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
