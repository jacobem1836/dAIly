# Phase 18: LiveKit Infrastructure + Token Endpoint - Research

**Researched:** 2026-04-28
**Domain:** LiveKit self-hosted server, WebRTC TURN infrastructure, JWT device-pairing auth, FastAPI token endpoint
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Device pairing + JWT auth flow. User pairs a device via a 6-digit code (generated server-side), which exchanges for a long-lived refresh token stored in iOS Keychain / Android Keystore. Subsequent API calls use short-lived JWTs issued from the refresh token.
- **D-02:** No email/password login — pairing code is the only auth mechanism for v1.4. Production-grade for multi-user/multi-tester deployment.
- **D-03:** The `/livekit/token` endpoint validates the JWT from D-01 and returns a LiveKit-specific JWT scoped to the user's room. Unauthenticated requests return 401.
- **D-04:** This auth pattern (pairing + JWT) becomes the standard for ALL future API endpoints, not just LiveKit.
- **D-05:** Self-hosted LiveKit server on the same VPS as FastAPI/Postgres/Redis. Single machine, single docker-compose deployment.
- **D-06:** Coturn (TURN relay) included in production deployment for firewall/NAT traversal (~20% of users need TURN fallback). Configured on TCP 443 + UDP 3478.
- **D-07:** Scale-out path documented: if concurrent sessions exceed ~50, split LiveKit + Coturn to a dedicated media VPS. LiveKit URL is a config variable — moving it is a one-line change.
- **D-08:** Ephemeral rooms — each voice session creates a unique room (e.g., `session-{user_id}-{timestamp}`). Room auto-destroys when all participants disconnect. No persistent room state.
- **D-09:** LiveKit token TTL of 1 hour.
- **D-10:** LiveKit server added as a Docker Compose service alongside Postgres + Redis.
- **D-11:** TURN relay (Coturn) skipped in dev compose — not needed for localhost development.

### Claude's Discretion

- Room naming convention (exact format of `session-{user_id}-{timestamp}`)
- LiveKit server configuration defaults (port, log level, etc.)
- JWT signing algorithm and key management details
- Pairing code expiry time and length
- FastAPI middleware implementation pattern for JWT validation

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | User can connect to a LiveKit room via self-hosted LiveKit server with TURN support | LiveKit Docker image v1.11.0; Coturn Docker image; embedded TURN config in livekit.yaml |
| INFRA-02 | User receives a short-lived JWT session token from `POST /livekit/token` authenticated against their existing session | livekit-api 1.1.0 AccessToken; PyJWT 2.12.1 for app JWT; FastAPI Depends pattern |
</phase_requirements>

---

## Summary

Phase 18 installs two independent systems that compose cleanly: a LiveKit server (with Coturn TURN relay in production) running as Docker services, and a pairing-code + JWT auth system that gates the `/livekit/token` endpoint.

The LiveKit piece is mechanical. The `livekit/livekit-server:v1.11.0` Docker image, a YAML config file, and four opened firewall ports are all that is required. In dev, the compose service is started with `--dev` defaults. In production, a `livekit.yaml` embeds TURN config and points at the Coturn container. The `livekit-api` Python package (1.1.0) generates LiveKit-specific JWTs from the `AccessToken` class with three lines of code.

The auth piece is the more nuanced part. The 6-digit pairing code pattern is essentially a simplified OAuth Device Authorization Grant (RFC 8628) without the browser redirect — a server generates a short-lived code, the mobile app submits it, the server issues a long-lived refresh token stored in the device's secure enclave, and subsequent requests carry short-lived JWTs derived from the refresh token. PyJWT 2.12.1 (already installed in the environment) handles both the app JWT layer and any custom signing. The vault module already exists for refresh token encryption at rest.

**Primary recommendation:** Stand up LiveKit + Coturn in Docker Compose, extend Pydantic Settings with LiveKit and JWT config vars, add two new DB tables (`device_tokens`, `pairing_codes`), implement four endpoints (`POST /auth/pair/initiate`, `POST /auth/pair/complete`, `POST /auth/token/refresh`, `POST /livekit/token`), then wire a FastAPI `Depends` guard reused across all future endpoints.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| livekit-api | 1.1.0 | LiveKit AccessToken generation (LiveKit-specific JWTs) | Official LiveKit Python server SDK; only package for server-side token signing |
| PyJWT | 2.12.1 | App-layer JWT encode/decode (access + refresh tokens) | Already installed; actively maintained; recommended over python-jose (abandoned) |
| cryptography | 45.0.2 | AES-256-GCM refresh token encryption at rest | Already used by vault module; project pattern established |
| livekit/livekit-server | v1.11.0 (Docker) | WebRTC room server | Official image; current stable release as of 2026-04-28 |
| coturn/coturn | 4.6.x (Docker) | TURN relay for NAT traversal | De facto standard TURN server; Docker Hub official image |

[VERIFIED: PyPI `pip index versions livekit-api` — 1.1.0 is latest]
[VERIFIED: Docker Hub `livekit/livekit-server` — v1.11.0 is current stable]
[VERIFIED: `pip show PyJWT` — 2.12.1 installed in dev environment]
[VERIFIED: `pip show cryptography` — 45.0.2 installed; vault module already uses it]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| secrets | stdlib | Cryptographically secure pairing code + token generation | Generating 6-digit codes and opaque refresh tokens — no install needed |
| httpx | 0.28.1 | Async test client for endpoint tests | Already in dev deps; used for endpoint integration tests |
| fakeredis | 2.x | Redis stub in tests | Already in dev deps; useful if any caching is added to auth layer |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT | authlib | authlib is heavier (full OAuth server); PyJWT is correct for signing/verifying JWTs only |
| coturn/coturn | LiveKit embedded TURN | LiveKit's embedded TURN requires TLS cert on the LiveKit host; separate Coturn is cleaner on a multi-service VPS |
| PyJWT | python-jose | Do NOT use python-jose — near-abandoned, flagged in FastAPI maintainer issues |

**Installation (new packages only):**
```bash
uv add livekit-api
```
PyJWT and cryptography are already installed. No other new runtime dependencies.

**Version verification:**
```bash
pip index versions livekit-api   # confirmed 1.1.0 current
pip show PyJWT                   # confirmed 2.12.1
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/daily/
├── auth/
│   ├── __init__.py
│   ├── deps.py          # FastAPI Depends: get_current_user() — reused by ALL future endpoints
│   ├── jwt.py           # encode/decode app-layer JWTs (access + refresh)
│   ├── pairing.py       # 6-digit code generation, validation, expiry
│   └── router.py        # POST /auth/pair/initiate, /auth/pair/complete, /auth/token/refresh
├── livekit/
│   ├── __init__.py
│   ├── router.py        # POST /livekit/token
│   └── tokens.py        # LiveKit AccessToken generation wrapper
├── db/
│   └── models.py        # +DeviceToken, +PairingCode models (existing file extended)
└── config.py            # +livekit_url, livekit_api_key, livekit_api_secret, jwt_secret, jwt_access_ttl_minutes, jwt_refresh_ttl_days
```

### Pattern 1: Auth Dependency (Reused by all endpoints)

**What:** FastAPI `Depends` function that extracts and validates the Bearer JWT, returns the authenticated `User`. Applied to any protected endpoint via `Depends(get_current_user)`.

**When to use:** Every protected endpoint — including `/livekit/token` and all future API routes.

```python
# Source: FastAPI official docs — https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
# Adapted for project pattern (no OAuth2PasswordBearer — Bearer token only)
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer()

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    token = creds.credentials
    payload = decode_access_token(token)  # raises 401 on invalid/expired
    user = await session.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user
```

### Pattern 2: LiveKit Token Generation

**What:** Wraps `livekit-api` `AccessToken` to produce a room-scoped JWT for the mobile client. Room name is ephemeral, derived from user ID and current timestamp.

**When to use:** Only in `POST /livekit/token` — called once per voice session initiation.

```python
# Source: https://docs.livekit.io/realtime/server/generating-tokens/
# Source: https://docs.livekit.io/reference/python/v1/livekit/api/access_token.html
import datetime
from livekit.api import AccessToken, VideoGrants

def create_livekit_token(
    user_id: int,
    livekit_api_key: str,
    livekit_api_secret: str,
) -> tuple[str, str]:
    room_name = f"session-{user_id}-{int(datetime.datetime.utcnow().timestamp())}"
    token = (
        AccessToken(livekit_api_key, livekit_api_secret)
        .with_identity(str(user_id))
        .with_name(f"user-{user_id}")
        .with_ttl(datetime.timedelta(hours=1))
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    return token, room_name
```

### Pattern 3: Pairing Code Flow

**What:** Server-side pairing code generation and exchange pattern. No browser involved — pure API.

**When to use:** `POST /auth/pair/initiate` (server generates code → returns to display) and `POST /auth/pair/complete` (mobile submits code → gets refresh token).

```
POST /auth/pair/initiate
  Body: { "user_id": 1 }  (or internal — server creates/gets user)
  Response: { "code": "482931", "expires_in": 300 }

POST /auth/pair/complete
  Body: { "code": "482931", "device_name": "Jacob's iPhone" }
  Response: { "refresh_token": "<opaque>", "access_token": "<jwt>", "expires_in": 900 }

POST /auth/token/refresh
  Body: { "refresh_token": "<opaque>" }
  Response: { "access_token": "<jwt>", "expires_in": 900 }
```

Code generation: `secrets.randbelow(900000) + 100000` → 6-digit numeric, cryptographically random.

Refresh token: `secrets.token_urlsafe(32)` → 43-char opaque string, stored AES-256-GCM encrypted via existing `vault.crypto.encrypt_token`.

### Pattern 4: Docker Compose Service (Dev)

**What:** Add LiveKit as a dev compose service using `--dev` flag which sets `devkey`/`secret` defaults and binds to all interfaces.

**When to use:** Local development — no TURN needed, no TLS needed.

```yaml
# Addition to docker-compose.yml (dev only)
livekit:
  image: livekit/livekit-server:v1.11.0
  command: --dev --bind 0.0.0.0
  ports:
    - "7880:7880"   # HTTP/WebSocket signal port
    - "7881:7881"   # WebRTC over TCP (fallback)
  environment:
    - LIVEKIT_API_KEY=devkey
    - LIVEKIT_API_SECRET=secret
```

### Pattern 5: Docker Compose Service (Production) with Coturn

**What:** Production compose adds `livekit.yaml` config file and Coturn TURN relay. Coturn uses `network_mode: host` for optimal UDP performance.

**When to use:** VPS / staging deployment only.

```yaml
# docker-compose.prod.yml additions
livekit:
  image: livekit/livekit-server:v1.11.0
  command: --config /etc/livekit.yaml
  network_mode: host   # required for WebRTC UDP on Linux
  volumes:
    - ./livekit.yaml:/etc/livekit.yaml:ro

coturn:
  image: coturn/coturn:latest
  network_mode: host   # recommended for TURN UDP relay
  volumes:
    - ./turnserver.conf:/etc/coturn/turnserver.conf:ro
```

```yaml
# livekit.yaml (production)
port: 7880
log_level: info
rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: true
keys:
  <LIVEKIT_API_KEY>: <LIVEKIT_API_SECRET>
turn:
  enabled: false   # Using external Coturn; set true only if using LiveKit embedded TURN
```

```conf
# turnserver.conf (Coturn)
listening-port=3478
tls-listening-port=5349
fingerprint
lt-cred-mech
use-auth-secret
static-auth-secret=<TURN_SECRET>
realm=<your-domain>
```

**Important:** `network_mode: host` is Linux-only. On macOS dev machines, use the dev compose (no TURN needed). Production runs on Linux VPS.

### Anti-Patterns to Avoid

- **Do not use `python-jose`** for JWT signing — near-abandoned, flagged by FastAPI maintainers. PyJWT is the correct library.
- **Do not store refresh tokens in plaintext** — encrypt with `vault.crypto.encrypt_token` before writing to DB.
- **Do not issue LiveKit tokens without auth guard** — the `/livekit/token` endpoint MUST go through `get_current_user` Depends.
- **Do not run LiveKit with `--dev` in production** — dev mode uses public default credentials.
- **Do not use `network_mode: host` in dev Docker Compose** — only needed in Linux production. On macOS it silently no-ops and causes port confusion.
- **Do not put TURN secret in LiveKit's livekit.yaml TURN block when using external Coturn** — Coturn manages its own credentials. The LiveKit TURN block is only for LiveKit's embedded TURN.
- **Do not use integer room IDs** — room name must be a string. Use `f"session-{user_id}-{timestamp}"` pattern.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LiveKit JWT signing | Custom HMAC/JWT code for LiveKit tokens | `livekit-api` AccessToken | LiveKit JWT has specific claim structure (video grants, identity) that the SDK handles correctly |
| WebRTC media server | Custom SFU/MCU | `livekit/livekit-server` Docker image | WebRTC is a 50k-line protocol stack; LiveKit implements ICE, DTLS, SRTP, SFU correctly |
| TURN server | Custom UDP relay | `coturn/coturn` Docker image | TURN protocol (RFC 5766) has specific packet framing and credential flows |
| Secure random codes | `random.randint` | `secrets.randbelow` | `random` is not cryptographically secure — pairing codes must be unpredictable |
| Token encryption | Manual AES implementation | `vault.crypto.encrypt_token` | Already implemented and tested in the project |

**Key insight:** LiveKit's value is the pre-built media infrastructure. Every piece of this stack (WebRTC, ICE, DTLS, SRTP, TURN, barge-in) would be months of work to build correctly. The token endpoint is ~30 lines; the infrastructure is the entire value.

---

## Common Pitfalls

### Pitfall 1: LiveKit `use_external_ip: true` Required on VPS

**What goes wrong:** LiveKit reports ICE candidates with the internal Docker network IP (e.g., 172.17.x.x) instead of the public VPS IP. Client cannot connect.

**Why it happens:** By default LiveKit uses the local NIC IP for ICE candidates. Inside Docker on a VPS, this is the container network IP.

**How to avoid:** Set `use_external_ip: true` in `livekit.yaml` `rtc:` block. LiveKit will query a STUN server to discover its public IP.

**Warning signs:** Client connects WebSocket signal but ICE negotiation hangs; Wireshark shows ICE candidates with RFC1918 addresses.

### Pitfall 2: `network_mode: host` Mac vs Linux Behavior

**What goes wrong:** `network_mode: host` is a no-op on Docker Desktop for Mac/Windows. UDP ports that appear to work locally silently fail when deployed to Linux VPS.

**Why it happens:** Docker Desktop on Mac uses a Linux VM with a NAT layer; host networking doesn't pass through to the Mac's actual network stack.

**How to avoid:** Dev compose explicitly uses port mappings (`ports: ["7880:7880"]`). Production compose uses `network_mode: host` only, with no `ports:` block (they conflict with host mode on Linux).

**Warning signs:** UDP media works on Mac dev but drops on VPS; ICE connectivity checks fail only in production.

### Pitfall 3: Refresh Token Must Be Stored Encrypted

**What goes wrong:** Refresh token stored in plaintext in Postgres. DB breach gives attackers permanent access to all user sessions.

**Why it happens:** Easy to forget the vault pattern applies to ALL long-lived secrets, not just OAuth tokens.

**How to avoid:** Always pass refresh token through `vault.crypto.encrypt_token(token, key)` before `INSERT`. Decrypt on `SELECT` before comparison. Store only the encrypted blob.

**Warning signs:** `device_tokens.refresh_token` column contains readable ASCII (not base64 blob).

### Pitfall 4: Pairing Code Race Window

**What goes wrong:** Two devices submit the same 6-digit code in the same second and both get issued refresh tokens for the same user.

**Why it happens:** No atomicity on code lookup + invalidation. Check-then-delete gap.

**How to avoid:** Use a DB `UPDATE pairing_codes SET used=true WHERE code=? AND used=false AND expires_at > now() RETURNING id` — atomic compare-and-swap via `RETURNING`. Only commit the refresh token insert if the UPDATE returned a row.

**Warning signs:** Multiple `device_tokens` rows created for the same pairing code in load tests.

### Pitfall 5: Coturn Needs Its Own Auth Secret — Not LiveKit's API Secret

**What goes wrong:** Reusing `LIVEKIT_API_SECRET` as the Coturn `static-auth-secret`. If LiveKit API secret is rotated or compromised, TURN credentials are also compromised.

**Why it happens:** Configuration copy-paste.

**How to avoid:** Generate a separate `TURN_SECRET` env var. Reference it only in `turnserver.conf` and never in LiveKit config.

**Warning signs:** `turnserver.conf` contains the string from `LIVEKIT_API_SECRET`.

### Pitfall 6: AccessToken `.to_jwt()` Is Synchronous

**What goes wrong:** Calling `.to_jwt()` inside an async FastAPI handler without `await` — this is fine (it's sync), but calling it in a thread that shares the `AccessToken` object is not thread-safe.

**Why it happens:** `AccessToken` uses a builder pattern with mutable internal state.

**How to avoid:** Always construct a fresh `AccessToken` per request. Never reuse an `AccessToken` instance across requests.

**Warning signs:** Intermittent wrong room names in tokens under concurrent load.

---

## Code Examples

### LiveKit Token Endpoint (Full)

```python
# Source: https://docs.livekit.io/realtime/server/generating-tokens/
# src/daily/livekit/router.py
import datetime
from fastapi import APIRouter, Depends
from livekit.api import AccessToken, VideoGrants
from daily.auth.deps import get_current_user
from daily.config import Settings
from daily.db.models import User

router = APIRouter(prefix="/livekit", tags=["livekit"])

@router.post("/token")
async def get_livekit_token(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(Settings),
) -> dict:
    room_name = (
        f"session-{current_user.id}-"
        f"{int(datetime.datetime.utcnow().timestamp())}"
    )
    token = (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(str(current_user.id))
        .with_name(f"user-{current_user.id}")
        .with_ttl(datetime.timedelta(hours=1))
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    return {"token": token, "room": room_name, "livekit_url": settings.livekit_url}
```

### Access Token Decode (JWT Guard)

```python
# Source: PyJWT docs — https://pyjwt.readthedocs.io/en/latest/usage.html
# src/daily/auth/jwt.py
import jwt
from datetime import datetime, timedelta, timezone
from daily.config import Settings

def encode_access_token(user_id: int, settings: Settings) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise  # caller converts to 401
    except jwt.InvalidTokenError:
        raise  # caller converts to 401
```

### Pairing Code Generation

```python
# Source: Python docs stdlib secrets — https://docs.python.org/3/library/secrets.html
# src/daily/auth/pairing.py
import secrets
from datetime import datetime, timedelta, timezone

PAIRING_CODE_TTL_SECONDS = 300  # 5 minutes

def generate_pairing_code() -> str:
    """Cryptographically secure 6-digit numeric code."""
    return str(secrets.randbelow(900000) + 100000)

def generate_refresh_token() -> str:
    """Opaque 43-char URL-safe refresh token."""
    return secrets.token_urlsafe(32)

def code_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)
```

### New DB Models

```python
# Source: SQLAlchemy 2.0 Mapped pattern — matches existing codebase style
# Addition to src/daily/db/models.py
class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String(6), index=True)
    used: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)  # AES-256-GCM via vault
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

### Config Extension

```python
# Addition to src/daily/config.py
class Settings(BaseSettings):
    # ... existing fields ...

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # App JWT
    jwt_secret: str = ""                    # min 32 bytes, generated at deploy
    jwt_access_ttl_minutes: int = 15        # short-lived access tokens
    jwt_refresh_ttl_days: int = 90          # long-lived refresh tokens (device-bound)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-jose for JWT | PyJWT 2.x | 2024 (FastAPI #9587) | python-jose unmaintained; PyJWT is the maintained replacement |
| LiveKit v1.4–v1.6 configs | LiveKit v1.11 config schema | 2025 | Minor schema differences; `use_external_ip` and `turn:` block format stable |
| TURN on dedicated port 3478 only | TURN on TCP 443 + UDP 3478 | 2023+ | TCP 443 fallback essential for corporate firewall penetration |
| Hand-rolled WebRTC SFU | LiveKit Docker image | 2021+ | WebRTC SFU is not a project deliverable; use the managed image |

**Deprecated/outdated:**
- `livekit-server-sdk-python` (old package name): replaced by `livekit-api` — the old name is a redirect, use `livekit-api` for explicit pinning.
- python-jose: do not use. Near-abandoned as of 2024; flagged in FastAPI issue tracker.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Coturn `coturn/coturn:latest` is a stable production image | Standard Stack | Could pull a broken image — pin to `4.6.2` if `latest` is unstable |
| A2 | LiveKit v1.11 `--dev` flag behaviour is unchanged (devkey/secret credentials, binds localhost) | Architecture Patterns | If `--dev` was removed or renamed, dev setup breaks — verify `docker run livekit/livekit-server:v1.11.0 --help` |
| A3 | JWT_SECRET of 32+ bytes is sufficient for HS256 per RFC 7518 | Code Examples | Correct per spec, but verify the project has a secret rotation plan before production |
| A4 | `jwt_refresh_ttl_days = 90` is appropriate for mobile device pairing | Config Extension | Business decision — 90 days is standard for mobile (see Google, Apple patterns), but Jacob may want shorter for early testers |

---

## Open Questions

1. **Who creates the `User` row on first pairing?**
   - What we know: `POST /auth/pair/initiate` must associate the code with a user, but there is no existing user registration flow (no email/password).
   - What's unclear: Does `initiate` create a new `User` row automatically, or does the user pre-exist (e.g., seeded by admin)?
   - Recommendation: For v1.4 multi-tester, `initiate` auto-creates a `User` row if none exists for the requesting context. Or have Jacob pre-seed users. Clarify before planning.

2. **Single user or multi-user for v1.4?**
   - What we know: `main.py` hardcodes `user_id=1` in the scheduler. The CONTEXT.md says "multi-user/multi-tester."
   - What's unclear: Does the token endpoint need to support multiple authenticated users, or is user_id always 1?
   - Recommendation: Design the auth tables for multi-user (correct) but keep the scheduler's `user_id=1` hardcode for now (Phase 19 concern).

3. **Pairing code display mechanism?**
   - What we know: The server generates the 6-digit code. The mobile app submits it.
   - What's unclear: Where does the human SEE the code to type into the mobile app? Backend CLI? A display page? A QR code?
   - Recommendation: For Phase 18, expose the code via a simple `GET /auth/pair/initiate` or via CLI. The mobile app display is Phase 20. Plan around this sequence.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | LiveKit + Coturn containers | Yes | 29.2.1 | — |
| Docker Compose | docker-compose.yml orchestration | Yes | v5.0.2 | — |
| PyJWT | App JWT encode/decode | Yes | 2.12.1 | — |
| cryptography | Vault AES-256-GCM | Yes | 45.0.2 | — |
| livekit-api | LiveKit token generation | No (not yet installed) | — | `uv add livekit-api` |
| Linux VPS | Production TURN relay (network_mode: host) | [ASSUMED] | — | Staging env must be Linux; macOS dev skips TURN |

**Missing dependencies with no fallback:**
- `livekit-api` — must be installed via `uv add livekit-api` in Wave 0.

**Missing dependencies with fallback:**
- Linux VPS for production TURN — dev runs without TURN on macOS. TURN validation deferred to staging deploy task.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_auth*.py tests/test_livekit*.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | LiveKit server reachable via WebSocket from a client | smoke | `pytest tests/test_livekit_connectivity.py -x` | No — Wave 0 |
| INFRA-01 | LiveKit server health endpoint responds | unit/integration | `pytest tests/test_livekit_health.py -x` | No — Wave 0 |
| INFRA-02 | `POST /livekit/token` returns 200 with `token` and `room` for authenticated user | integration | `pytest tests/test_livekit_token.py::test_token_endpoint_authenticated -x` | No — Wave 0 |
| INFRA-02 | `POST /livekit/token` returns 401 for unauthenticated request | integration | `pytest tests/test_livekit_token.py::test_token_endpoint_unauthenticated -x` | No — Wave 0 |
| INFRA-02 | Pairing code flow: initiate + complete issues valid JWT | integration | `pytest tests/test_auth_pairing.py::test_full_pairing_flow -x` | No — Wave 0 |
| INFRA-02 | Refresh token exchange issues new access token | integration | `pytest tests/test_auth_pairing.py::test_refresh_token_exchange -x` | No — Wave 0 |
| INFRA-02 | Expired/used pairing code returns 400 | unit | `pytest tests/test_auth_pairing.py::test_expired_code_rejected -x` | No — Wave 0 |
| INFRA-02 | Revoked refresh token returns 401 | unit | `pytest tests/test_auth_pairing.py::test_revoked_refresh_token -x` | No — Wave 0 |
| INFRA-02 | LiveKit token contains correct room name, identity, TTL=1h | unit | `pytest tests/test_livekit_tokens.py::test_token_claims -x` | No — Wave 0 |

### Success Criteria → Test Map (from Phase 18 definition)

| Success Criterion | Test Strategy |
|-------------------|--------------|
| User can connect LiveKit client to self-hosted server through TURN relay | Manual smoke test on VPS after production deploy; automated connectivity test via httpx WebSocket handshake on dev |
| User receives JWT from `POST /livekit/token` using existing auth session | `test_livekit_token.py::test_token_endpoint_authenticated` |
| Token endpoint rejects unauthenticated requests with 401 | `test_livekit_token.py::test_token_endpoint_unauthenticated` |
| LiveKit server reachable from outside localhost | Manual VPS deploy validation; document as `HUMAN-UAT` step |

### Sampling Rate

- **Per task commit:** `pytest tests/test_auth*.py tests/test_livekit*.py -x`
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green + manual VPS connectivity smoke test before `/gsd-verify-work`

### Wave 0 Gaps

All test files are new — none exist yet:
- [ ] `tests/test_auth_pairing.py` — covers pairing initiate, complete, refresh, expiry, revocation
- [ ] `tests/test_livekit_token.py` — covers 200 authenticated, 401 unauthenticated, token claims
- [ ] `tests/test_livekit_tokens.py` — unit tests for `livekit/tokens.py` (room name format, TTL)
- [ ] `tests/test_livekit_connectivity.py` — smoke test: HTTP GET to LiveKit health endpoint
- [ ] `tests/test_livekit_health.py` — integration: LiveKit container health check via Docker

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Pairing code (short-lived, numeric, single-use); refresh token (opaque, encrypted at rest) |
| V3 Session Management | Yes | Short-lived access JWT (15 min); long-lived refresh token (90 days, device-bound, revocable) |
| V4 Access Control | Yes | `get_current_user` Depends gates all protected endpoints; unauthenticated → 401 |
| V5 Input Validation | Yes | Pydantic request models on all endpoints; pairing code validated as 6-digit numeric |
| V6 Cryptography | Yes | PyJWT HS256 for app JWTs; AES-256-GCM (existing vault) for refresh token at rest |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Pairing code brute force | Elevation of Privilege | 6-digit = 900000 space; rate limit initiate + complete endpoints; code expires in 5 min |
| Refresh token theft from DB | Information Disclosure | AES-256-GCM encrypted at rest via vault; never logged |
| Expired access token reuse | Elevation of Privilege | PyJWT verifies `exp` claim on every decode |
| TURN relay open relay abuse | Tampering | Coturn `lt-cred-mech` with `static-auth-secret`; only LiveKit server has credentials |
| LiveKit API key exposure | Information Disclosure | Keys in env vars only; never in code or git; Pydantic Settings reads from `.env` |
| Replay of single-use pairing code | Elevation of Privilege | Atomic DB update marks code `used=true`; second submission finds no row |

---

## Sources

### Primary (HIGH confidence)
- [LiveKit Python SDK — livekit-api 1.1.0 PyPI](https://pypi.org/project/livekit-api/) — verified current version
- [LiveKit AccessToken API reference](https://docs.livekit.io/reference/python/v1/livekit/api/access_token.html) — AccessToken class, VideoGrants, with_ttl
- [LiveKit token generation docs](https://docs.livekit.io/realtime/server/generating-tokens/) — canonical Python code examples
- [PyJWT 2.12.1 documentation](https://pyjwt.readthedocs.io/en/stable/) — encode/decode API, HS256
- [LiveKit Docker Hub — livekit/livekit-server v1.11.0](https://hub.docker.com/r/livekit/livekit-server/tags) — verified current stable image
- [LiveKit self-hosting VM guide](https://docs.livekit.io/transport/self-hosting/vm/) — port requirements, production config
- [LiveKit config-sample.yaml](https://github.com/livekit/livekit/blob/master/config-sample.yaml) — full config schema
- `pip show PyJWT` — confirmed 2.12.1 installed locally
- `pip show cryptography` — confirmed 45.0.2 installed locally
- `docker --version` — confirmed Docker 29.2.1 available

### Secondary (MEDIUM confidence)
- [LiveKit self-hosted example docker-compose.yaml](https://github.com/anguzo/livekit-self-hosted/blob/main/docker-compose.yaml) — `network_mode: host` pattern for Linux
- [Coturn Docker Hub](https://hub.docker.com/r/coturn/coturn) — official coturn image
- [FastAPI JWT auth docs](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) — Depends pattern for auth guard
- [WebRTC.ventures TURN server setup guide 2025](https://webrtc.ventures/2025/01/how-to-set-up-self-hosted-stun-turn-servers-for-webrtc-applications/)

### Tertiary (LOW confidence — verify before executing)
- Coturn `static-auth-secret` configuration format — verify against official turnserver.conf docs before writing config
- LiveKit GitHub issue #3826 — external-ip detection problems with Docker; may require manual IP config on some VPS providers [CITED: github.com/livekit/livekit/issues/3826]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified via pip index, Docker Hub, and local environment
- Architecture patterns: HIGH — LiveKit docs are authoritative; FastAPI Depends pattern from official docs
- Auth flow: MEDIUM — pairing code pattern is well-understood but specific implementation details (user creation, multi-user) have open questions
- TURN/Coturn config: MEDIUM — LiveKit docs cover embedded TURN; external Coturn config draws from community examples

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 (LiveKit is actively developed; re-verify Docker image tag before deploy)
