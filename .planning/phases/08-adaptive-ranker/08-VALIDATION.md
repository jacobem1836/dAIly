---
phase: 8
slug: adaptive-ranker
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-18
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]` |
| **Quick run command** | `pytest tests/test_adaptive_ranker.py tests/test_briefing_ranker.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_adaptive_ranker.py tests/test_briefing_ranker.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | INTEL-01 (SC1) | — | N/A | unit | `pytest tests/test_adaptive_ranker.py::test_engaged_sender_ranks_higher -x` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | INTEL-01 (SC2) | — | N/A | unit | `pytest tests/test_adaptive_ranker.py::test_cold_start_returns_empty -x` | ✅ | ✅ green |
| 08-01-03 | 01 | 1 | INTEL-01 (SC3) | T-8-01 | `user_id` scoped query — no cross-user leakage | unit | `pytest tests/test_adaptive_ranker.py::test_db_error_returns_empty -x` | ✅ | ✅ green |
| 08-01-04 | 01 | 1 | INTEL-01 (SC3) | — | N/A | unit | `pytest tests/test_briefing_context.py::test_build_context_no_db_session -x` | ✅ | ✅ green |
| 08-01-05 | 01 | 1 | INTEL-01 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py::test_decay_half_life -x` | ✅ | ✅ green |
| 08-01-06 | 01 | 1 | INTEL-01 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py::test_sigmoid_zero_score -x` | ✅ | ✅ green |
| 08-01-07 | 01 | 1 | INTEL-01 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py::test_null_metadata_excluded -x` | ✅ | ✅ green |
| 08-04-01 | 04 | 2 | INTEL-01 | — | N/A | unit | `pytest tests/test_briefing_ranker.py::test_rank_emails_unknown_sender_defaults_to_1 -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Phase 8 is complete — Wave 0 was delivered at execution time.

- [x] `tests/test_adaptive_ranker.py` — covers all SC1/SC2/SC3 scenarios plus decay, sigmoid, null guard
- [x] `tests/test_briefing_context.py::test_build_context_no_db_session` — SC3 wiring
- [x] `tests/test_briefing_ranker.py::test_rank_emails_unknown_sender_defaults_to_1` — backward compatibility

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sigmoid midpoint produces 1.25 for a sender with balanced signals | INTEL-01 | Product intent verification (not a bug check) | Run `python3 -c "import math; s=lambda x: 0.5+1.5/(1+math.exp(-x)); print(s(0))"` — should print `1.25` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-18
