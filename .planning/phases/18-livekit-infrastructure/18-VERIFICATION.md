---
phase: 18-livekit-infrastructure
verified: 2026-04-29T12:00:00Z
status: human_needed
score: 11/11 must-haves verified
human_verification:
  - test: "Run `docker compose up` then POST /auth/pair/initiate → POST /auth/pair/complete → POST /livekit/token and play the returned LiveKit JWT into a LiveKit room join"
    expected: "Device pairs, receives access JWT, exchanges for LiveKit JWT, and successfully joins an ephemeral room on the running LiveKit server"
    why_human: "Full end-to-end WebRTC/TURN connectivity cannot be verified without a running LiveKit dev container and real room join — automated tests use mocked sessions and never exercise the LiveKit server itself"
  - test: "Run `docker compose -f docker-compose.prod.yml up` on a Linux VPS with real domain/TURN_SECRET and verify TURN relay works"
    expected: "ICE negotiation completes via Coturn TURN relay (not STUN only); media flows through the relay for clients behind symmetric NAT"
    why_human: "TURN relay behaviour requires real network conditions (NAT traversal, external IP binding) — cannot be tested locally or in CI"
---

# Phase 18: LiveKit Infrastructure + Token Endpoint — Verification Report

**Phase Goal:** Stand up LiveKit server in Docker dev stack, implement device-pairing + JWT auth system, and expose a `POST /livekit/token` endpoint that returns a LiveKit room token for authenticated clients.
**Verified:** 2026-04-29T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LiveKit server runs in Docker dev stack | ✓ VERIFIED | `docker-compose.yml` contains `livekit/livekit-server:v1.11.0` service on ports 7880/7881; `livekit-api>=1.1.0` in `pyproject.toml` |
| 2 | Production manifest + Coturn TURN relay config exists | ✓ VERIFIED | `docker-compose.prod.yml`, `livekit.yaml` (use_external_ip: true), `turnserver.conf` (static-auth-secret=REPLACE_TURN_SECRET) all exist |
| 3 | Settings expose livekit_url, livekit_api_key, livekit_api_secret | ✓ VERIFIED | `src/daily/config.py` lines 27–29 confirm all three fields with dev defaults |
| 4 | POST /auth/pair/initiate returns 6-digit code + expiry | ✓ VERIFIED | `src/daily/auth/router.py` implements endpoint; `test_full_pairing_flow` passes |
| 5 | POST /auth/pair/complete returns access JWT + refresh token; codes are single-use and expiry-enforced | ✓ VERIFIED | Atomic `UPDATE...WHERE used=false...RETURNING` CAS in `router.py`; `test_used_code_rejected` and `test_invalid_code_rejected` pass |
| 6 | POST /auth/token/refresh exchanges refresh token for new access JWT; revoked/invalid tokens rejected with 401 | ✓ VERIFIED | `token_refresh` endpoint scans + decrypts device tokens; `test_refresh_token_exchange` and `test_invalid_refresh_token_rejected` pass |
| 7 | Refresh tokens stored AES-256-GCM encrypted at rest | ✓ VERIFIED | `router.py` calls `encrypt_token(refresh, key)` before inserting into `device_tokens`; `test_refresh_token_stored_encrypted` asserts ciphertext != plaintext |
| 8 | get_current_user FastAPI Depends raises 401 on missing/invalid/expired Bearer | ✓ VERIFIED | `src/daily/auth/deps.py` raises HTTP 401 for all three failure modes; verified by `test_unauthorized*` tests |
| 9 | POST /livekit/token returns 200 + {token, room, livekit_url} for authenticated user | ✓ VERIFIED | `src/daily/livekit/router.py` endpoint; `test_valid_token` passes (200, room matches `session-{user_id}-\d+`, livekit_url matches settings) |
| 10 | POST /livekit/token returns 401 for unauthenticated requests | ✓ VERIFIED | Three 401 tests pass: no auth, garbage JWT, expired JWT |
| 11 | LiveKit JWT contains user identity, ephemeral room `session-{user_id}-{ts}`, 1-hour TTL, signed with LIVEKIT_API_SECRET | ✓ VERIFIED | `tokens.py` constructs per D-08/D-09; `test_token_decodes_with_secret` verifies sub=user_id and exp-nbf≈3600s; `test_returned_token_signed_with_livekit_secret` verifies signing |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/daily/auth/jwt.py` | encode_access_token, decode_access_token (HS256) | ✓ VERIFIED | Both functions present and wired via `deps.py` |
| `src/daily/auth/pairing.py` | generate_pairing_code, generate_refresh_token, code_expiry | ✓ VERIFIED | All three functions present; uses `secrets.randbelow` and `secrets.token_urlsafe` |
| `src/daily/auth/deps.py` | get_current_user Depends | ✓ VERIFIED | Present; imported and used in `livekit/router.py` |
| `src/daily/auth/router.py` | POST /auth/pair/initiate, /pair/complete, /token/refresh | ✓ VERIFIED | All three routes present; router registered in `main.py` |
| `src/daily/db/models.py` | PairingCode, DeviceToken ORM models | ✓ VERIFIED | Both classes present; column sets verified by unit tests |
| `alembic/versions/005_add_pairing_codes_device_tokens.py` | Migration creating pairing_codes + device_tokens | ✓ VERIFIED | `create_table` calls for both tables; `down_revision = "004"` |
| `src/daily/livekit/tokens.py` | create_livekit_token wrapper | ✓ VERIFIED | Function present; uses `AccessToken(api_key, api_secret).with_grants(VideoGrants(...))` |
| `src/daily/livekit/router.py` | POST /livekit/token gated by get_current_user | ✓ VERIFIED | Endpoint uses `Depends(get_current_user)`; router registered in `main.py` |
| `src/daily/livekit/__init__.py` | Package marker | ✓ VERIFIED | File exists |
| `src/daily/auth/__init__.py` | Package marker | ✓ VERIFIED | File exists |
| `docker-compose.yml` | LiveKit service | ✓ VERIFIED | `livekit/livekit-server:v1.11.0` present |
| `docker-compose.prod.yml` | Production LiveKit + Coturn | ✓ VERIFIED | File exists |
| `livekit.yaml` | LiveKit production config | ✓ VERIFIED | `use_external_ip: true` confirmed |
| `turnserver.conf` | Coturn TURN config | ✓ VERIFIED | `static-auth-secret=REPLACE_TURN_SECRET` placeholder present |
| `tests/test_auth_jwt.py` | Unit tests (8 tests) | ✓ VERIFIED | 8 tests, all passing |
| `tests/test_auth_pairing.py` | Integration tests (6 tests) | ✓ VERIFIED | 6 tests, all passing |
| `tests/test_livekit_tokens.py` | Unit tests (4 tests) | ✓ VERIFIED | 4 tests, all passing |
| `tests/test_livekit_token.py` | Integration tests (5 tests) | ✓ VERIFIED | 5 tests, all passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/daily/auth/router.py` | `src/daily/vault/crypto.py` | `encrypt_token` before insert | ✓ WIRED | Line 108: `encrypted = encrypt_token(refresh, key)` |
| `src/daily/auth/deps.py` | `src/daily/auth/jwt.py` | `decode_access_token` | ✓ WIRED | Line 36: `payload = decode_access_token(creds.credentials, settings)` |
| `src/daily/main.py` | `src/daily/auth/router.py` | `app.include_router` | ✓ WIRED | Line 95: `app.include_router(auth_router)` |
| `src/daily/livekit/router.py` | `src/daily/auth/deps.py` | `Depends(get_current_user)` | ✓ WIRED | Line 25: `current_user: User = Depends(get_current_user)` |
| `src/daily/livekit/tokens.py` | `livekit.api.AccessToken` | `AccessToken(...).with_grants(VideoGrants(...))` | ✓ WIRED | Lines 22–29 in `tokens.py` |
| `src/daily/main.py` | `src/daily/livekit/router.py` | `app.include_router` | ✓ WIRED | Line 96: `app.include_router(livekit_router)` |

---

### Data-Flow Trace (Level 4)

`/livekit/token` endpoint does not render stored dynamic data — it mints a token on demand from live settings and the authenticated user identity. No persistent data source to trace beyond what the auth gate already verifies.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `livekit/router.py` | `current_user.id` | `get_current_user` Depends → DB `users` table | Yes — DB lookup in `deps.py` line 60 | ✓ FLOWING |
| `livekit/tokens.py` | `settings.livekit_api_key`, `settings.livekit_api_secret` | Pydantic Settings from env | Yes — env-loaded values; test fixture injects real strings | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 23 phase tests pass | `uv run pytest tests/test_auth_jwt.py tests/test_auth_pairing.py tests/test_livekit_tokens.py tests/test_livekit_token.py` | 23 passed, 0 failed, 8 warnings (key-length advisory only) | ✓ PASS |
| auth router wired into app | `grep -n "include_router(auth_router)" src/daily/main.py` | Line 95 match | ✓ PASS |
| livekit router wired into app | `grep -n "include_router(livekit_router)" src/daily/main.py` | Line 96 match | ✓ PASS |
| `get_current_user` applied to /livekit/token | `grep -n "Depends(get_current_user)" src/daily/livekit/router.py` | Line 25 match | ✓ PASS |

---

### Requirements Coverage

INFRA-01 and INFRA-02 are defined in the PLAN frontmatter. No separate REQUIREMENTS.md file was found in `.planning/` — requirements are embedded in the roadmap and plan files.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INFRA-01 | 18-01, 18-03 | LiveKit server in Docker dev stack + production manifests with Coturn | ✓ SATISFIED | `docker-compose.yml` LiveKit service; `docker-compose.prod.yml`; `livekit.yaml`; `turnserver.conf`; smoke test in `test_livekit_connectivity.py` |
| INFRA-02 | 18-02, 18-03 | Device-pairing + JWT auth system; `POST /livekit/token` returning LiveKit room JWT to authenticated clients | ✓ SATISFIED | Full auth flow + 23 passing tests; `/livekit/token` returns `{token, room, livekit_url}` for Bearer-authenticated callers |

---

### Anti-Patterns Found

No blockers or warnings found. All implementation files are substantive with real logic. No TODOs, FIXMEs, placeholder returns, or hardcoded empty values were detected in phase-produced files.

Note: test fixtures in `test_livekit_tokens.py` use a 29-byte LIVEKIT_API_SECRET (`"test-secret-32-bytes-padded-x"`) which triggers PyJWT's `InsecureKeyLengthWarning`. This is a test-only advisory — production deployments must supply a 32+ byte secret. Not a blocker.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None detected | — | — |

---

### Human Verification Required

#### 1. LiveKit Dev Container End-to-End Join

**Test:** Run `docker compose up`, complete the full auth flow (POST /auth/pair/initiate → /auth/pair/complete → /livekit/token), then use the returned LiveKit JWT to join a room via the LiveKit web playground or SDK client.
**Expected:** Room join succeeds; LiveKit server acknowledges the participant; media transport is established.
**Why human:** Automated integration tests use SQLite-backed sessions with monkeypatched `async_session` and never call the running LiveKit server. No automated test exercises actual WebRTC signalling or room creation on the dev container.

#### 2. TURN Relay on VPS

**Test:** Deploy `docker-compose.prod.yml` on a Linux VPS with real `REPLACE_API_KEY`, `REPLACE_TURN_SECRET`, and `REPLACE_DOMAIN` values substituted in `livekit.yaml` and `turnserver.conf`. Test with a client behind symmetric NAT.
**Expected:** ICE negotiation completes via Coturn TURN relay (relay candidates win); media flows without direct IP connectivity.
**Why human:** TURN relay behaviour requires real network topology and a public IP VPS — not testable locally or in CI.

---

### Gaps Summary

No gaps. All 11 observable truths are verified, all artifacts are substantive and wired, all 23 automated tests pass. The two human verification items are the expected post-phase validation steps for WebRTC/TURN infrastructure — they do not represent missing implementation, only unverifiable-programmatically runtime behaviour.

---

_Verified: 2026-04-29T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
