---
phase: 18-livekit-infrastructure
plan: "02"
subsystem: auth
tags: [auth, jwt, pairing, device-tokens, encryption, fastapi]
dependency_graph:
  requires: ["18-01"]
  provides: ["auth-system", "get_current_user-dep", "INFRA-02"]
  affects: ["all future protected endpoints", "18-03 LiveKit token endpoint"]
tech_stack:
  added: ["PyJWT (HS256)", "aiosqlite (test driver)"]
  patterns: ["device-pairing auth flow", "AES-256-GCM token encryption at rest", "atomic CAS pairing code consumption"]
key_files:
  created:
    - src/daily/auth/__init__.py
    - src/daily/auth/jwt.py
    - src/daily/auth/pairing.py
    - src/daily/auth/deps.py
    - src/daily/auth/router.py
    - alembic/versions/005_add_pairing_codes_device_tokens.py
    - tests/test_auth_jwt.py
    - tests/test_auth_pairing.py
  modified:
    - src/daily/config.py
    - src/daily/db/models.py
    - src/daily/main.py
    - pyproject.toml
decisions:
  - "Migration 005 chains from 004 (not 56a7489e1608) to maintain linear Alembic history"
  - "Integration tests use SQLite in-memory DB (selective table creation) to avoid Postgres dependency in CI"
  - "aiosqlite added as dev dependency for async SQLite test driver"
  - "VAULT_KEY env in tests uses 32-byte string (not base64) matching encrypt_token's 32-byte key requirement"
metrics:
  duration: "293 seconds (~5 minutes)"
  completed_date: "2026-04-29"
  tasks_completed: 3
  files_changed: 12
---

# Phase 18 Plan 02: Device-Pairing JWT Auth System Summary

JWT + device-pairing auth with AES-256-GCM encrypted refresh tokens at rest, atomic single-use code consumption, and a reusable `get_current_user` FastAPI Depends gating all future protected endpoints.

## What Was Built

### Three Auth Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/pair/initiate` | POST | Returns 6-digit pairing code (5-min TTL); auto-creates user if missing |
| `/auth/pair/complete` | POST | Atomically consumes code; returns access JWT + encrypted refresh token |
| `/auth/token/refresh` | POST | Exchanges valid refresh token for new access JWT |

### Auth Module Architecture

- **`src/daily/auth/jwt.py`** — `encode_access_token` / `decode_access_token` using PyJWT HS256
- **`src/daily/auth/pairing.py`** — `generate_pairing_code()` (6-digit, `secrets.randbelow`), `generate_refresh_token()` (43-char URL-safe), `code_expiry()`
- **`src/daily/auth/deps.py`** — `get_current_user` FastAPI Depends; raises 401 on missing/expired/invalid Bearer tokens
- **`src/daily/auth/router.py`** — Three endpoints wired to DB with atomic CAS logic

### Database Changes

- **`PairingCode`** model + table: `pairing_codes` (user_id, code String(6), used Boolean, expires_at tz-aware)
- **`DeviceToken`** model + table: `device_tokens` (user_id, encrypted_refresh_token Text, expires_at tz-aware, revoked Boolean, last_used_at)
- **Migration 005**: Chains from `004` (maintaining linear history); creates both tables with proper indexes

### Security Implementation

All STRIDE mitigations from the plan's threat model implemented:

| Threat | Mitigation |
|--------|------------|
| T-18-07: Refresh token theft from DB | AES-256-GCM via `vault.crypto.encrypt_token`; verified by `test_refresh_token_stored_encrypted` |
| T-18-08: Expired access token reuse | PyJWT `exp` claim verified on every `decode_access_token` call |
| T-18-09: Forged JWT | HS256 with server-only `JWT_SECRET`; wrong-secret test passes |
| T-18-10: Race condition on pairing code | Atomic `UPDATE...WHERE used=false...RETURNING` — second submission finds no row |
| T-18-11: JWT_SECRET leak | Pydantic Settings from env only; `encode_access_token` raises `RuntimeError` if unset |

## Test Coverage

14 tests all passing:

**`test_auth_jwt.py` (8 tests)**
- Settings JWT fields present and correct defaults
- PairingCode and DeviceToken model columns present
- JWT round-trip: encode → decode → sub/type claim verification
- Expired JWT raises `ExpiredSignatureError`
- Wrong-secret JWT raises `InvalidTokenError`
- `generate_pairing_code()` returns 6-digit numeric string (100000–999999)
- `generate_refresh_token()` returns 43+ char string

**`test_auth_pairing.py` (6 tests)**
- Full pairing flow: initiate → complete → access+refresh tokens returned
- Invalid code rejected (400)
- Used code rejected on second submission (400) — atomic single-use
- Refresh token exchange returns new access token
- Invalid refresh token rejected (401)
- Refresh token stored encrypted (plaintext NOT in DB column)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Alembic migration chain used wrong down_revision**
- **Found during:** Task 1 implementation
- **Issue:** Plan specified `down_revision = "56a7489e1608"` but the actual latest head in the main chain was `004` (56a7489e1608 → 003 → 004). Using 56a7489e1608 created a branch point in the migration tree.
- **Fix:** Set `down_revision = "004"` for migration 005, resulting in a clean linear chain.
- **Files modified:** `alembic/versions/005_add_pairing_codes_device_tokens.py`
- **Commit:** b20132f

**2. [Rule 3 - Blocking] SQLite ARRAY type incompatibility in integration tests**
- **Found during:** Task 3 test execution
- **Issue:** `Base.metadata.create_all` fails on SQLite because `BriefingConfig.slack_channels` uses PostgreSQL `ARRAY(String)` type, which SQLite doesn't support.
- **Fix:** Used selective table creation (`tables=[User.__table__, PairingCode.__table__, DeviceToken.__table__]`) in the test fixture. Also added `aiosqlite` as dev dependency.
- **Files modified:** `tests/test_auth_pairing.py`, `pyproject.toml`
- **Commit:** 8f2b4e0

**3. [Rule 3 - Blocking] Test fixture refactored to inject SQLite session**
- **Found during:** Task 3 test execution
- **Issue:** Original test design from plan used real Postgres session from `async_session`; fails when Postgres not running. Other integration tests in this project use `unittest.mock` instead.
- **Fix:** Rewrote `client` fixture to monkeypatch `async_session` in `daily.auth.router` and `daily.auth.deps` with an SQLite-backed `async_sessionmaker`. Tests run fully in-memory without Postgres.
- **Files modified:** `tests/test_auth_pairing.py`
- **Commit:** 8f2b4e0

## Known Stubs

None — all endpoints fully functional with real DB operations.

## Threat Flags

None — no new security surface beyond what is documented in the plan's `<threat_model>`.

## Self-Check

Files exist check:
- `src/daily/auth/__init__.py` — FOUND
- `src/daily/auth/jwt.py` — FOUND
- `src/daily/auth/pairing.py` — FOUND
- `src/daily/auth/deps.py` — FOUND
- `src/daily/auth/router.py` — FOUND
- `alembic/versions/005_add_pairing_codes_device_tokens.py` — FOUND
- `tests/test_auth_jwt.py` — FOUND
- `tests/test_auth_pairing.py` — FOUND

Commits check:
- b20132f — feat(18-02): add JWT settings, PairingCode/DeviceToken models, migration 005
- 0c51719 — feat(18-02): build auth modules (jwt, pairing, deps) + extend JWT tests
- 8f2b4e0 — feat(18-02): auth router (3 endpoints), wire into main app, SQLite integration tests

## Self-Check: PASSED
