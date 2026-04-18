---
phase: 13
slug: signal-capture
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
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
| 13-01-01 | 01 | 0 | SIG-03 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py -x -q` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | SIG-03 | — | N/A | unit | `pytest tests/test_adaptive_ranker.py -x -q` | ✅ W0 | ⬜ pending |
| 13-02-01 | 02 | 1 | SIG-01, SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "state"` | ✅ | ⬜ pending |
| 13-02-02 | 02 | 1 | SIG-01, SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "pipeline"` | ✅ | ⬜ pending |
| 13-03-01 | 03 | 2 | SIG-01 | — | N/A | unit | `pytest tests/ -x -q -k "skip"` | ✅ | ⬜ pending |
| 13-03-02 | 03 | 2 | SIG-02 | — | N/A | unit | `pytest tests/ -x -q -k "re_request"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_adaptive_ranker.py` — stubs for SIG-03 (get_sender_multipliers unit tests)
- [ ] Existing `tests/conftest.py` — verify async DB session fixture is available

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
