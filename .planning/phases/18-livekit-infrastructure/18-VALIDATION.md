---
phase: 18
slug: livekit-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pytest.ini` or `pyproject.toml` |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | INFRA-01 | T-18-01 | LiveKit server only accessible via TURN relay | integration | `docker compose ps livekit \| grep Up` | ✅ | ⬜ pending |
| 18-01-02 | 01 | 1 | INFRA-01 | — | TURN relay port 3478 open externally | manual | See Manual-Only Verifications | ✅ | ⬜ pending |
| 18-02-01 | 02 | 2 | INFRA-02 | T-18-02 | Token endpoint returns 401 for unauthenticated | unit | `pytest tests/test_livekit_token.py -k test_unauthorized` | ✅ | ⬜ pending |
| 18-02-02 | 02 | 2 | INFRA-02 | T-18-02 | Token endpoint returns valid JWT for auth user | unit | `pytest tests/test_livekit_token.py -k test_valid_token` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_livekit_token.py` — stubs for INFRA-02 token endpoint tests
- [ ] `tests/conftest.py` — shared fixtures (existing or updated)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LiveKit server reachable from outside localhost | INFRA-01 | Requires external network test (VPS or staging) | Connect LiveKit client app to server URL from mobile/external network; verify successful room join |
| TURN relay routes audio without firewall issues | INFRA-01 | Requires external network test | Use LiveKit diagnostics to verify TURN relay is used and media flows |

*All other behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
