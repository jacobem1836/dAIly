---
phase: 1
slug: foundation
status: draft
nyquist_compliant: true
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
| 1-01-01 | 01 | 1 | SEC-01, SEC-04 | T-1-01, T-1-04 | Token encrypted before DB write; no raw_body column in schema | unit | `pytest tests/test_vault.py tests/test_schema.py -v` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | SEC-01 | T-1-02 | AES-256-GCM round-trip; nonce uniqueness; key validation | unit | `pytest tests/test_vault.py -v` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | SEC-04 | T-1-06 | Adapter models have no body/raw_body fields | unit | `pytest tests/test_models.py -v` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | INTG-01, INTG-02, SEC-03 | T-1-09, T-1-10, T-1-11 | Google OAuth stores encrypted token; Gmail/Calendar adapters return metadata only | unit | `pytest tests/test_google_oauth.py tests/test_google_adapter.py -v` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 3 | INTG-04, SEC-03 | T-1-12, T-1-13, T-1-14 | Slack OAuth stores encrypted token; Slack adapter returns message metadata only | unit | `pytest tests/test_slack_oauth.py tests/test_slack_adapter.py -v` | ❌ W0 | ⬜ pending |
| 1-05-01 | 05 | 4 | INTG-03, INTG-05, SEC-01, SEC-03 | T-1-16, T-1-17, T-1-18, T-1-19 | Microsoft OAuth flow; Outlook adapter returns metadata only; token refresh detects near-expiry | unit | `pytest tests/test_microsoft_oauth.py tests/test_microsoft_adapter.py tests/test_token_refresh.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (mock DB, mock OAuth tokens, vault key)
- [ ] `tests/test_vault.py` — stubs for SEC-01 token encryption (Plan 01, Task 2)
- [ ] `tests/test_schema.py` — stubs for SEC-04 schema privacy check (Plan 01, Task 2)
- [ ] `tests/test_models.py` — stubs for SEC-04 adapter model privacy check (Plan 02, Task 1)
- [ ] `tests/test_google_oauth.py` — stubs for INTG-01 Google OAuth flow (Plan 03, Task 2)
- [ ] `tests/test_google_adapter.py` — stubs for INTG-01/INTG-02 Gmail + Calendar adapters (Plan 03, Task 2)
- [ ] `tests/test_slack_oauth.py` — stubs for INTG-04 Slack OAuth flow (Plan 04, Task 2)
- [ ] `tests/test_slack_adapter.py` — stubs for INTG-04 Slack adapter (Plan 04, Task 2)
- [ ] `tests/test_microsoft_oauth.py` — stubs for INTG-03 Microsoft OAuth flow (Plan 05, Task 1)
- [ ] `tests/test_microsoft_adapter.py` — stubs for INTG-03 Outlook adapter (Plan 05, Task 1)
- [ ] `tests/test_token_refresh.py` — stubs for INTG-05 token refresh (Plan 05, Task 2)
- [ ] `pytest` + `pytest-asyncio` installed in dev dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OAuth redirect round-trip in browser | INTG-01, INTG-02 | Requires browser session and live OAuth provider | Manually run OAuth flow against Google Cloud test credentials |
| Slack workspace authorization | INTG-04 | Requires Slack workspace admin consent | Authorize app in Slack developer portal, verify token received |
| Azure AD authorization | INTG-03 | Requires Azure AD tenant and browser | Complete MSAL auth code flow manually against personal Microsoft account |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
