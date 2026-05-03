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
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_integrations_router.py tests/test_users_router.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_integrations_router.py tests/test_users_router.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Plan-03 Task-1 | 03 | 2 | INT-01/02 | T-21-01 | OAuth state validated against Redis before token exchange | unit | `pytest tests/test_integrations_router.py::test_google_connect tests/test_integrations_router.py::test_google_callback -x -q` | ❌ W0 | ⬜ pending |
| Plan-03 Task-2 | 03 | 2 | INT-03/04 | T-21-02 | Microsoft token stored with provider="outlook", not "microsoft" | unit | `pytest tests/test_integrations_router.py::test_microsoft_connect tests/test_integrations_router.py::test_microsoft_callback -x -q` | ❌ W0 | ⬜ pending |
| Plan-03 Task-3 | 03 | 2 | INT-05/06/07 | T-21-03 | Slack async token exchange; expired state returns 400 | unit | `pytest tests/test_integrations_router.py::test_slack_connect tests/test_integrations_router.py::test_slack_callback tests/test_integrations_router.py::test_invalid_state -x -q` | ❌ W0 | ⬜ pending |
| Plan-04 Task-1 | 04 | 2 | USR-01 | — | Integration status returns correct booleans per provider | unit | `pytest tests/test_users_router.py::test_integration_status -x -q` | ❌ W0 | ⬜ pending |
| Plan-04 Task-2 | 04 | 2 | USR-02/03 | — | Briefing time stored as UTC; unknown timezone returns 422 | unit | `pytest tests/test_users_router.py::test_update_preferences tests/test_users_router.py::test_invalid_timezone -x -q` | ❌ W0 | ⬜ pending |
| Plan-05 Task-3 | 05 | 3 | AASA-01 | — | AASA paths list includes /oauth/success | unit | `pytest tests/test_aasa.py -x -q` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_integrations_router.py` — stubs for INT-01 through INT-07 (Google/Microsoft/Slack connect, callback, invalid state)
- [ ] `tests/test_users_router.py` — stubs for USR-01 through USR-03 (integration status, preferences update, invalid timezone)
- [ ] Extend `tests/test_aasa.py` — add assertion for `/oauth/success` in AASA paths response
- [ ] `tests/conftest.py` — shared fixtures (test user, mock Redis, mock DB session)

*Note: Plan 01 (Alembic migration) is verified via `alembic current` + psql column check documented in the plan — no pytest row needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OAuth redirect lands on correct provider consent screen | D-04 | Requires live OAuth provider interaction | Test with real Google/Microsoft/Slack OAuth in dev environment |
| Universal Link deep-link back to iOS app after callback | D-03 | Requires physical device + AASA file + app install | Install app on device, complete OAuth flow, verify Universal Link intercept |
| Briefing fires at user's scheduled local time | D-15 | Requires waiting for scheduled cron | Set briefing_time to +2 min from now, verify cron fires and briefing is generated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
