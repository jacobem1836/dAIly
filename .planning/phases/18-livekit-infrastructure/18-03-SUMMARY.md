---
phase: 18-livekit-infrastructure
plan: "03"
subsystem: livekit
tags: [livekit, auth, jwt, fastapi, tdd]
dependency_graph:
  requires: ["18-01", "18-02"]
  provides: ["POST /livekit/token", "INFRA-01", "INFRA-02"]
  affects: ["mobile client voice session initiation"]
tech_stack:
  added: []
  patterns: ["LiveKit AccessToken per-call minting", "ephemeral room name session-{user_id}-{ts}", "FastAPI Depends auth gate reuse"]
key_files:
  created:
    - src/daily/livekit/__init__.py
    - src/daily/livekit/tokens.py
    - src/daily/livekit/router.py
    - tests/test_livekit_tokens.py
    - tests/test_livekit_token.py
  modified:
    - src/daily/main.py
decisions:
  - "LiveKit JWT uses nbf (not before) not iat (issued at) — TTL assertion uses nbf for exp-nbf delta"
  - "Integration tests use SQLite in-memory DB matching 18-02 pattern — no Postgres required in CI"
  - "Fresh AccessToken constructed per create_livekit_token call (not module-level) per RESEARCH.md Pitfall 6 thread-safety note"
metrics:
  duration: "360 seconds (~6 minutes)"
  completed_date: "2026-04-29"
  tasks_completed: 2
  files_changed: 6
---

# Phase 18 Plan 03: LiveKit Token Endpoint Summary

POST /livekit/token endpoint: app JWT authentication gate via `get_current_user`, server-minted LiveKit JWT with ephemeral room name `session-{user_id}-{ts}`, 1-hour TTL, signed with `LIVEKIT_API_SECRET`.

## What Was Built

### LiveKit Token Module

| File | Purpose |
|------|---------|
| `src/daily/livekit/__init__.py` | Package marker |
| `src/daily/livekit/tokens.py` | `create_livekit_token(user_id, settings)` — mints LiveKit AccessToken JWT |
| `src/daily/livekit/router.py` | `POST /livekit/token` endpoint gated by `Depends(get_current_user)` |

### Endpoint Contract

**`POST /livekit/token`**

- Requires: `Authorization: Bearer <app-jwt>`
- Returns 200: `{ token: string, room: string, livekit_url: string }`
- Returns 401: missing / garbage / expired Bearer token
- Room name format: `session-{user_id}-{unix_timestamp}` (ephemeral, per D-08)
- LiveKit JWT: signed with `LIVEKIT_API_SECRET`, `sub=user_id`, `exp-nbf=3600s`, `room_join=True` grant

### Wiring

`src/daily/main.py` includes `livekit_router` after `auth_router`:
```python
from daily.livekit.router import router as livekit_router
app.include_router(livekit_router)
```

## Test Coverage

9 tests all passing:

**`tests/test_livekit_tokens.py` (4 unit tests)**
- `test_room_name_format` — regex `^session-42-\d+$`
- `test_token_decodes_with_secret` — LiveKit JWT decodes with `LIVEKIT_API_SECRET`, sub=42, TTL≈3600s
- `test_room_name_unique_across_seconds` — two calls >1s apart produce different room names
- `test_room_name_uses_session_prefix` — room starts with `session-`

**`tests/test_livekit_token.py` (5 integration tests)**
- `test_unauthorized` — no auth header → 401
- `test_unauthorized_invalid_token` — garbage Bearer → 401
- `test_unauthorized_expired_token` — expired app JWT → 401
- `test_valid_token` — valid app JWT → 200, room matches `session-100-\d+`, livekit_url matches settings
- `test_returned_token_signed_with_livekit_secret` — LiveKit JWT in response decodes with `LIVEKIT_API_SECRET`, sub=user_id

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] LiveKit JWT uses `nbf` claim, not `iat`**
- **Found during:** Task 1 GREEN phase — `test_token_decodes_with_secret` failed with `KeyError: 'iat'`
- **Issue:** Plan specified TTL check as `payload["exp"] - payload["iat"]`, but LiveKit's AccessToken SDK emits `nbf` (not before) instead of `iat` (issued at)
- **Fix:** Updated test assertion to `payload["exp"] - payload["nbf"]`
- **Files modified:** `tests/test_livekit_tokens.py`
- **Commit:** ca47e3a

## Known Stubs

None — endpoint is fully functional. LiveKit JWT is real, room name is server-derived, auth gate is enforced.

## Threat Flags

None — no new security surface beyond what is in the plan's `<threat_model>`. All STRIDE mitigations implemented:

| Threat | Status |
|--------|--------|
| T-18-14: Unauthenticated token request | Mitigated — `Depends(get_current_user)` raises 401; covered by `test_unauthorized*` |
| T-18-15: User obtains token for another user's room | Mitigated — room name derived from `current_user.id` (server), not request body |
| T-18-16: LiveKit API secret leaked in response | Mitigated — response contains only signed JWT + public URL |
| T-18-17: Long-lived token replay | Accepted — 1h TTL bounds exposure; full revocation deferred |
| T-18-18: DoS via room slot exhaustion | Accepted — LiveKit ephemeral rooms auto-destroy; rate limiting deferred to phase 19 |
| T-18-19: Attacker-chosen identity in token | Mitigated — identity sourced from `current_user.id`, not user-controllable |

## Open Items (Post-Phase)

- VPS smoke test: TURN connectivity validation is manual UAT per VALIDATION.md (requires running LiveKit dev container and issuing a real join)
- Rate limiting on `/livekit/token` deferred to phase 19 (alongside auth rate limits per T-18-18)

## Self-Check

Files exist:
- `src/daily/livekit/__init__.py` — FOUND
- `src/daily/livekit/tokens.py` — FOUND
- `src/daily/livekit/router.py` — FOUND
- `tests/test_livekit_tokens.py` — FOUND
- `tests/test_livekit_token.py` — FOUND

Commits:
- ca47e3a — feat(18-03): create_livekit_token with ephemeral room name, 1h TTL, and unit tests
- 7acba00 — feat(18-03): POST /livekit/token endpoint with auth gate, integration tests, and router wiring

## Self-Check: PASSED
