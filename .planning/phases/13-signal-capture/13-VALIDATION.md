---
phase: 13
slug: signal-capture
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-18
audited: 2026-04-19
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest config section) |
| **Quick run command** | `pytest tests/test_adaptive_ranker.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_adaptive_ranker.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 0 | SIG-03 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py -x -q` | ✅ | ✅ green |
| 13-01-02 | 01 | 1 | SIG-03 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py -x -q` | ✅ | ✅ green |
| 13-02-01 | 02 | 1 | SIG-01, SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "state"` | ✅ | ✅ green |
| 13-02-02 | 02 | 1 | SIG-01, SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "pipeline"` | ✅ | ✅ green |
| 13-03-01 | 03 | 2 | SIG-01 | — | N/A | unit | `pytest tests/ -x -q -k "skip"` | ✅ | ✅ green |
| 13-03-02 | 03 | 2 | SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "re_request"` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_adaptive_ranker.py` — 12 tests for get_sender_multipliers ✅
- [x] Existing `tests/conftest.py` — async DB session fixture confirmed ✅

*Existing pytest-asyncio infrastructure covers integration with the test suite.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Voice "skip" intent routes to skip_node and advances briefing | SIG-01 | Requires live voice session with Deepgram STT | Start voice session, say "skip this", verify next briefing item plays and signal appears in signal_log |
| Voice "repeat that" intent triggers re_request_node | SIG-02 | Requires live voice session | Start voice session during briefing, say "repeat that", verify current item replays and signal logged |
| Implicit skip (barge-in + 2s silence) fires signal | SIG-01 | Requires voice loop timing test | Start briefing playback, barge in and stay silent 2s, verify skip signal written |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-04-19

---

## Validation Audit 2026-04-19

| Metric | Count |
|--------|-------|
| Gaps found | 6 |
| Resolved | 6 |
| Escalated | 0 |

Tests added: `tests/test_orchestrator_graph.py` (+4 methods), `tests/test_orchestrator_nodes.py` (new, 2 tests)
