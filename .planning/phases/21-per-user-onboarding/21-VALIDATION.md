---
phase: 21
slug: per-user-onboarding
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` or `pyproject.toml` |
| **Quick run command** | `pytest tests/test_integrations.py tests/test_auth.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_integrations.py tests/test_auth.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | — | — | OAuth state validated against Redis before token exchange | unit | `pytest tests/test_integrations.py::test_oauth_state_csrf -x -q` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | — | — | Encrypted token stored per user_id, not globally | unit | `pytest tests/test_integrations.py::test_token_stored_per_user -x -q` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | — | — | GET /integrations/{provider}/connect returns 401 without auth | unit | `pytest tests/test_integrations.py::test_connect_requires_auth -x -q` | ❌ W0 | ⬜ pending |
| 21-02-01 | 02 | 2 | — | — | PUT /users/me/preferences stores valid IANA timezone | unit | `pytest tests/test_preferences.py::test_briefing_schedule_stored -x -q` | ❌ W0 | ⬜ pending |
| 21-02-02 | 02 | 2 | — | — | Scheduler registers one cron job per BriefingConfig row | unit | `pytest tests/test_scheduler.py::test_per_user_cron -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_integrations.py` — stubs for OAuth connect + callback endpoint tests
- [ ] `tests/test_preferences.py` — stubs for briefing schedule/preferences tests
- [ ] `tests/test_scheduler.py` — stubs for multi-user scheduler registration tests
- [ ] `tests/conftest.py` — shared fixtures (test user, mock Redis, mock DB session)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OAuth redirect lands on correct provider | — | Requires live OAuth provider interaction | Test with real Google/Microsoft/Slack OAuth in dev environment |
| Universal Link deep-link back to iOS app | — | Requires physical device + AASA file | Install app on device, complete OAuth flow, verify redirect |
| Briefing fires at user's scheduled time | — | Requires waiting for scheduled cron | Set briefing time to +2 min, verify cron fires and briefing is generated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
