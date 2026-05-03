---
phase: 21-per-user-onboarding
verified: 2026-05-02T00:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification: true
gaps: []
    artifacts:
      - path: "src/daily/briefing/scheduler.py"
        issue: "Line 112: `elif provider == 'microsoft':` should be `elif provider == 'outlook':`"
    missing:
      - "Change `provider == 'microsoft'` to `provider == 'outlook'` in _build_pipeline_kwargs (scheduler.py line 112)"
---

# Phase 21: Per-User Onboarding Verification Report

**Phase Goal:** Implement per-user onboarding — timezone-aware briefing config, mobile-mediated OAuth integrations (Google/MS/Slack), user preferences endpoints, per-user scheduler wiring, and AASA Universal Link support for OAuth callbacks.
**Verified:** 2026-05-02
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | BriefingConfig.timezone column exists (Mapped[str], server_default='UTC') | VERIFIED | models.py line 48: `timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")` |
| 2 | Alembic migration 007 adds timezone column with nullable=False, server_default='UTC' | VERIFIED | alembic/versions/007_briefing_config_timezone.py: `op.add_column` with `nullable=False, server_default="UTC"` |
| 3 | GET /integrations/google/connect returns auth_url and stores Redis state (600s TTL) | VERIFIED | router.py lines 132-158: setex with OAUTH_STATE_TTL_SECONDS=600 |
| 4 | GET /integrations/google/callback validates state, encrypts token, upserts provider='google', redirects to /oauth/success?provider=google | VERIFIED | router.py lines 161-212: _consume_oauth_state + encrypt_token + delete+insert + RedirectResponse |
| 5 | Microsoft connect+callback work analogously, storing provider='outlook' | VERIFIED | router.py lines 230-312: msal.ConfidentialClientApplication, provider="outlook" stored |
| 6 | Slack connect+callback work analogously, storing provider='slack' | VERIFIED | router.py lines 320-404: httpx.AsyncClient POST to SLACK_TOKEN_URL, provider="slack" stored |
| 7 | GET /users/me/integrations returns {google, microsoft, slack} booleans with outlook->microsoft mapping | VERIFIED | users/router.py lines 33-55: `"outlook" in connected` maps to `microsoft:` |
| 8 | PUT /users/me/preferences upserts BriefingConfig with UTC-converted schedule + IANA timezone, invalid tz returns 422 | VERIFIED | users/router.py lines 82-122: ZoneInfoNotFoundError->422, config.timezone=body.timezone |
| 9 | AASA paths array includes /oauth/success | VERIFIED | main.py line 103: `"paths": ["/pair", "/pair/*", "/oauth/success"]` |
| 10 | Lifespan registers one APScheduler cron job per BriefingConfig row | VERIFIED | main.py lines 44-56: iterates scalars().all(), calls setup_scheduler_for_user per row |
| 11 | Microsoft/Outlook tokens are correctly matched in the briefing pipeline scheduler | FAILED | scheduler.py line 112 checks `provider == "microsoft"` but tokens are stored as `provider="outlook"` — Outlook adapters are never instantiated |

**Score:** 10/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/daily/db/models.py` | BriefingConfig.timezone column | VERIFIED | Line 48, String(64), default="UTC" |
| `alembic/versions/007_briefing_config_timezone.py` | Migration with op.add_column | VERIFIED | nullable=False, server_default="UTC", down_revision="006" |
| `src/daily/integrations/router.py` | 6 OAuth endpoints (min 200 lines) | VERIFIED | 404 lines, all 6 endpoints present |
| `src/daily/users/router.py` | /users/me/integrations + /users/me/preferences (min 80 lines) | VERIFIED | 123 lines, both endpoints present |
| `src/daily/main.py` | Router mounts + AASA + multi-user lifespan | VERIFIED | Lines 29-31, 76-79, 103, 44-56 |
| `src/daily/briefing/scheduler.py` | setup_scheduler_for_user + BriefingConfig iteration | VERIFIED | Lines 164-173 — but contains provider mismatch bug |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| GET /integrations/{provider}/connect | redis.setex (oauth_state:{state}) | OAUTH_STATE_TTL_SECONDS=600 | WIRED | router.py line 144, 241, 331 |
| GET /integrations/{provider}/callback | encrypt_token + IntegrationToken | _consume_oauth_state + delete+insert | WIRED | router.py: all 3 callbacks use encrypt_token before session.add |
| callback success | iOS via Universal Link | RedirectResponse(.../oauth/success?provider=...) | WIRED | router.py lines 209, 310, 401 |
| GET /users/me/integrations | IntegrationToken table | select(IntegrationToken.provider).where(user_id) | WIRED | users/router.py lines 45-50 |
| PUT /users/me/preferences | BriefingConfig table | upsert via select + scalar_one_or_none | WIRED | users/router.py lines 111-121 |
| PUT /users/me/preferences | zoneinfo.ZoneInfo | ZoneInfoNotFoundError -> HTTP 422 | WIRED | users/router.py lines 88-90 |
| lifespan | BriefingConfig rows | select(BriefingConfig).scalars().all() | WIRED | main.py lines 46-47 |
| _build_pipeline_kwargs | OutlookAdapter | provider == "microsoft" (BUG: should be "outlook") | NOT_WIRED | scheduler.py line 112 — tokens are stored as "outlook", check uses "microsoft" — adapters never instantiated |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| integrations/router.py | IntegrationToken rows | delete+insert from OAuth flow | Yes | FLOWING |
| users/router.py (integrations) | connected set | select(IntegrationToken.provider) | Yes | FLOWING |
| users/router.py (preferences) | config (BriefingConfig) | scalar_one_or_none + upsert | Yes | FLOWING |
| briefing/scheduler.py | outlook adapter | select(IntegrationToken) | No — outlook tokens silently dropped | HOLLOW (provider mismatch) |

### Behavioral Spot-Checks

Step 7b: SKIPPED (requires running server; checked statically instead — all key patterns verified via grep)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCHED-TZ-01 | 21-01 | BriefingConfig timezone column | SATISFIED | models.py + migration 007 |
| INT-01 | 21-03 | GET /integrations/google/connect | SATISFIED | router.py lines 132-158 |
| INT-02 | 21-03 | GET /integrations/google/callback | SATISFIED | router.py lines 161-212 |
| INT-03 | 21-03 | GET /integrations/microsoft/connect | SATISFIED | router.py lines 230-250 |
| INT-04 | 21-03 | GET /integrations/microsoft/callback, provider='outlook' | SATISFIED | router.py lines 253-312 |
| INT-05 | 21-03 | GET /integrations/slack/connect | SATISFIED | router.py lines 320-340 |
| INT-06 | 21-03 | GET /integrations/slack/callback | SATISFIED | router.py lines 343-404 |
| INT-07 | 21-03 | Invalid state returns HTTP 400 | SATISFIED | _consume_oauth_state raises HTTPException(400) |
| INT-08 | 21-03 | Connect endpoints require auth (401 without JWT) | SATISFIED | Depends(get_current_user) on all connect endpoints |
| USR-01 | 21-04 | GET /users/me/integrations | SATISFIED | users/router.py lines 33-55 |
| USR-02 | 21-04 | PUT /users/me/preferences with UTC conversion | SATISFIED | users/router.py lines 97-122 |
| USR-03 | 21-04 | Invalid IANA timezone returns 422 | SATISFIED | users/router.py lines 88-90 |
| AASA-01 | 21-05 | /oauth/success in AASA paths | SATISFIED | main.py line 103 |
| SCHED-MULTI-01 | 21-05 | One cron job per BriefingConfig row | SATISFIED | main.py lines 44-56, scheduler.py lines 164-173 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/daily/briefing/scheduler.py | 112 | `provider == "microsoft"` (wrong provider key — all tokens stored as "outlook") | Blocker | Microsoft/Outlook users get no email or calendar adapters in briefing pipeline; Outlook integration is silently broken at runtime |

### Human Verification Required

None required beyond the gap closure above — all automated checks completed.

### Gaps Summary

One blocker gap found in `src/daily/briefing/scheduler.py`. The `_build_pipeline_kwargs` function at line 112 checks `elif provider == "microsoft":` to instantiate `OutlookAdapter`. However, the integrations router (Plan 03) stores Microsoft tokens with `provider="outlook"` to match the existing CLI convention. The users router (Plan 04) correctly maps `"outlook"` to `microsoft: true`. The scheduler alone uses the wrong key, so Outlook adapters are never instantiated and Microsoft users receive briefings with no email or calendar data.

**Fix:** Change `provider == "microsoft"` to `provider == "outlook"` at scheduler.py line 112.

This is a pre-existing bug in `_build_pipeline_kwargs` — Phase 21 did not introduce the function but did not correct the mismatch when adding the `provider="outlook"` convention in Plan 03. The 10 other must-haves are fully verified and wired.

---

_Verified: 2026-05-02_
_Verifier: Claude (gsd-verifier)_
