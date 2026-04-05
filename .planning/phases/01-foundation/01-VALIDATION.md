---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` or `pyproject.toml` (Wave 0 installs) |
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
| 1-01-01 | 01 | 0 | SEC-01 | T-1-01 | Token encrypted before DB write | unit | `pytest tests/test_vault.py -v` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | INTG-01 | T-1-02 | OAuth callback stores token, redirects | integration | `pytest tests/test_google_oauth.py -v` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | INTG-02 | — | Gmail read returns email metadata only | unit | `pytest tests/test_gmail_reader.py -v` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | INTG-03 | — | Calendar read returns event metadata only | unit | `pytest tests/test_calendar_reader.py -v` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 2 | INTG-04 | — | Slack read returns message metadata only | unit | `pytest tests/test_slack_reader.py -v` | ❌ W0 | ⬜ pending |
| 1-05-01 | 05 | 2 | INTG-05 | — | Outlook read returns email metadata only | unit | `pytest tests/test_outlook_reader.py -v` | ❌ W0 | ⬜ pending |
| 1-06-01 | 06 | 2 | SEC-03 | T-1-03 | Token refresh runs without user interaction | integration | `pytest tests/test_token_refresh.py -v` | ❌ W0 | ⬜ pending |
| 1-07-01 | 07 | 3 | SEC-04 | T-1-04 | No raw bodies in DB schema | unit | `pytest tests/test_schema.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (mock DB, mock OAuth tokens)
- [ ] `tests/test_vault.py` — stubs for SEC-01 token encryption
- [ ] `tests/test_google_oauth.py` — stubs for INTG-01 Google OAuth flow
- [ ] `tests/test_gmail_reader.py` — stubs for INTG-02 Gmail reading
- [ ] `tests/test_calendar_reader.py` — stubs for INTG-03 Calendar reading
- [ ] `tests/test_slack_reader.py` — stubs for INTG-04 Slack reading
- [ ] `tests/test_outlook_reader.py` — stubs for INTG-05 Outlook reading
- [ ] `tests/test_token_refresh.py` — stubs for SEC-03 token refresh
- [ ] `tests/test_schema.py` — stubs for SEC-04 schema privacy check
- [ ] `pytest` + `pytest-asyncio` installed in dev dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OAuth redirect round-trip in browser | INTG-01, INTG-02 | Requires browser session and live OAuth provider | Manually run OAuth flow against Google Cloud test credentials |
| Slack workspace authorization | INTG-04 | Requires Slack workspace admin consent | Authorize app in Slack developer portal, verify token received |
| Azure AD authorization | INTG-05 | Requires Azure AD tenant and browser | Complete MSAL device code flow or auth code flow manually |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
