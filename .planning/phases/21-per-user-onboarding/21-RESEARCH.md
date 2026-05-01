# Phase 21: Per-User Onboarding - Research

**Researched:** 2026-05-01
**Domain:** Backend OAuth integration, mobile auth flow, per-user credential storage, briefing schedule API
**Confidence:** HIGH (all findings verified against live codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Backend-mediated OAuth flow. App opens ASWebAuthenticationSession → OAuth provider redirects to backend callback endpoint (`/integrations/{provider}/callback`) → backend stores encrypted tokens → backend issues a deep link (Universal Link) back to the iOS app signaling success.
- **D-02:** Tokens never pass through the iOS app — the backend callback handler is the sole recipient of the auth code and performs the exchange. Preserves the SEC-01 constraint.
- **D-03:** After backend callback stores tokens, the backend redirects to a Universal Link (e.g. `https://yourdomain.com/oauth/success?provider=google`). iOS intercepts it via Universal Links and resumes the onboarding flow. No polling required.
- **D-04:** New backend endpoints required per provider: `GET /integrations/{provider}/connect` (returns authorization URL) and `GET /integrations/{provider}/callback` (handles redirect, stores token, issues deep link). Providers: google, microsoft, slack.
- **D-05:** The existing `integrations/google/auth.py` localhost flow is CLI/dev tooling only — it is not touched. New mobile OAuth endpoints are added alongside it.
- **D-06:** Linear flow: Email (magic link pairing) → Integrations → Briefing Schedule → Voice experience. User completes steps in this order.
- **D-07:** At least one integration must be connected before the user can advance to schedule setup.
- **D-08:** Briefing schedule is configured in onboarding (not deferred to settings). It is the final step before the user reaches the voice experience for the first time.
- **D-09:** ASWebAuthenticationSession — Apple's purpose-built OAuth API.
- **D-10:** One screen per integration, sequentially: Google → Microsoft → Slack.
- **D-11:** After successful connection, Connect button is replaced by green checkmark and connected account email.
- **D-12:** User can skip individual integrations (except at least one must be connected before advancing).
- **D-13:** Onboarding shows a dedicated schedule screen with iOS native DatePicker. Default: 7:00 AM.
- **D-14:** Timezone auto-detected from `TimeZone.current` on iOS and sent to backend. No user-facing timezone picker in onboarding.
- **D-15:** Backend stores briefing schedule time and timezone on the user's preferences record (`BriefingConfig` model). APScheduler cron job reads this per-user.

### Claude's Discretion

- Visual design, colors, animation details on onboarding screens — keep consistent with the existing iOS app aesthetic (Phase 19).
- Exact wording on integration permission descriptions.
- Error handling for failed OAuth flows (generic retry screen is fine).
- Success/completion animation on final onboarding screen.

### Deferred Ideas (OUT OF SCOPE)

- Android onboarding — same pattern but Android OAuth uses Chrome Custom Tabs. Phase 20 follow-up.
- Reconnect / re-auth flow for expired integrations — settings screen, not onboarding.
- Adding integrations post-onboarding (e.g. adding Slack later) — settings screen.
- Incremental OAuth scope upgrades (e.g. requesting send permission later) — M2+ consideration.
</user_constraints>

---

## Summary

Phase 21 adds a self-service onboarding backend so new users can independently pair their email, connect OAuth integrations (Google, Microsoft, Slack), and configure their briefing schedule — all without developer CLI intervention. The current system is entirely single-user (hardcoded `user_id=1`) with a localhost-based OAuth flow that requires the developer to run `daily connect gmail` at a terminal. Phase 21 replaces this with backend-mediated OAuth endpoints that iOS can drive via ASWebAuthenticationSession.

The core auth primitives (magic-link pairing codes, JWT access tokens, encrypted refresh tokens, `IntegrationToken` DB model, AES-256-GCM vault) are already fully implemented and production-quality. Phase 21 builds on them — it is additive, not a rewrite. The five new backend capabilities are: (1) authenticated connect URL generation per provider, (2) OAuth callback handlers per provider that store tokens and redirect to Universal Links, (3) an `/oauth/success` Universal Link path added to the AASA, (4) a `GET /users/me/integrations` status endpoint for the iOS onboarding UI to show checkmarks, and (5) a `PUT /users/me/preferences` endpoint that stores briefing time + timezone.

The biggest architectural consideration is the OAuth `state` parameter CSRF validation. The backend generates `state`, stores it in Redis with a short TTL, and validates it on callback. This prevents cross-site request forgery on the callback endpoint. Redis is already in the stack and in use for briefing caching.

**Primary recommendation:** Build a new `integrations_router` in `src/daily/integrations/router.py` following the exact same pattern as `src/daily/livekit/router.py` — authenticated via `get_current_user` dependency, with provider-specific connect/callback pairs. Add two small endpoints to a new `users_router` for preferences and integration status.

---

## Project Constraints (from CLAUDE.md)

- Python 3.11+, FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.0 async
- AES-256-GCM token encryption via `daily.vault.crypto` — never store tokens in plaintext
- LLM must not access APIs or hold credentials — backend mediates everything
- Raw email/message bodies must not be stored — only summaries and metadata
- OAuth tokens encrypted at rest; never exposed to frontend, logs, or LLM
- `python-jose` is banned — use `authlib` (existing code uses PyJWT which is fine)
- Tests use pytest + pytest-asyncio; 80% coverage minimum
- Formatting: black + ruff; type annotations on all function signatures
- New endpoints follow `src/daily/livekit/router.py` pattern (router + `get_current_user` Depends)

---

## Existing Codebase Analysis

### Auth Primitives Already Implemented

**[VERIFIED: direct code read]**

| Component | File | What It Does | Status |
|-----------|------|-------------|--------|
| Magic-link pairing | `auth/router.py` | `POST /auth/pair/send-link` → sends OTP email; `POST /auth/pair/complete` → creates user by email, issues JWT + refresh token | Production-ready |
| JWT encode/decode | `auth/jwt.py` | HS256 access tokens (15 min TTL), opaque refresh tokens (90 days) | Production-ready |
| Bearer dep | `auth/deps.py` | `get_current_user` FastAPI dependency — validates JWT, returns `User` object | Production-ready |
| Token vault | `vault/crypto.py` | `encrypt_token` / `decrypt_token` — AES-256-GCM, nonce-prepended, base64-encoded | Production-ready |
| Resend email | `email/resend_client.py` | `send_magic_link(email, code)` — uses Resend HTTP API | Production-ready |

### Database Models Already Implemented

**[VERIFIED: direct code read — `src/daily/db/models.py`]**

| Model | Table | Key Columns | Notes |
|-------|-------|------------|-------|
| `User` | `users` | `id`, `email` (nullable, unique), `created_at` | Email is optional — set during magic-link flow |
| `IntegrationToken` | `integration_tokens` | `user_id`, `provider` (string), `encrypted_access_token`, `encrypted_refresh_token`, `token_expiry`, `scopes` | No unique constraint on (user_id, provider) — **gap: upsert needed** |
| `BriefingConfig` | `briefing_config` | `user_id` (unique FK), `schedule_hour`, `schedule_minute` | Stores UTC hour/minute only — **gap: no timezone column** |
| `PairingCode` | `pairing_codes` | `user_id` (nullable FK), `email` (nullable), `code`, `used`, `expires_at` | Email-based flow stores email, not user_id |
| `DeviceToken` | `device_tokens` | `user_id`, `encrypted_refresh_token`, `expires_at`, `revoked` | Opaque refresh token |
| `UserProfile` | `user_profile` | `user_id` (unique FK), `preferences` (JSONB) | Stores tone, briefing_length, category_order — **not briefing time/timezone** |

### What Needs to Change (Gap Analysis)

**[VERIFIED: code inspection]**

**Gap 1: `BriefingConfig` has no timezone column**
- D-15 says backend stores `briefing_time` and `timezone` on user preferences. `BriefingConfig` only has `schedule_hour`/`schedule_minute` (UTC). The timezone must be stored so the scheduler can convert user's local 7:00 AM to UTC.
- **Action:** Alembic migration adds `timezone` column (String, default `"UTC"`) to `briefing_config`.
- **Scheduler impact:** `main.py` lifespan and `scheduler.py` still use `schedule_hour/minute` directly (already UTC). The `PUT /users/me/preferences` endpoint must convert the user-supplied local time + timezone to UTC before writing `schedule_hour/minute`.

**Gap 2: `IntegrationToken` has no unique constraint on `(user_id, provider)`**
- The Google CLI flow uses a `DELETE ... WHERE user_id=X AND provider=Y` before insert (see `google/auth.py` line 176). This is the correct upsert pattern. The mobile callback handler must do the same.
- **Action:** Add a UniqueConstraint to `IntegrationToken` via Alembic migration, and use `ON CONFLICT DO UPDATE` in the callback handler. (Alternatively, keep the delete-then-insert pattern from existing CLI code — simpler and already working.)

**Gap 3: OAuth `state` storage for CSRF prevention**
- CONTEXT.md specifies: backend generates state, stores in Redis with TTL, validates on callback.
- Redis is already in the stack (`redis.asyncio`). State key pattern: `oauth_state:{state_value}` with TTL 600s (10 minutes — enough for user to complete provider consent screen).

**Gap 4: AASA needs `/oauth/success` path**
- The current AASA in `main.py` only lists `/pair` and `/pair/*` paths. The Universal Link callback from OAuth (`/oauth/success?provider=google`) needs to be added to the AASA paths array.
- **Action:** Add `"/oauth/success"` to the AASA `paths` list in `main.py`.

**Gap 5: No integration status endpoint**
- iOS onboarding needs to know which integrations are already connected (to show checkmarks). No such endpoint exists.
- **Action:** `GET /users/me/integrations` returns `{google: bool, microsoft: bool, slack: bool}` by querying `IntegrationToken` for the current user.

**Gap 6: No preferences update endpoint**
- Schedule setup screen calls `PUT /users/me/preferences` with `{briefing_time: "07:00", timezone: "Australia/Brisbane"}`. No such endpoint exists.
- **Action:** New endpoint on a `users_router`.

### CLI Single-User Pattern (What Gets Replaced)

**[VERIFIED: direct code read — `cli.py`]**

The CLI hardcodes `user_id=1` everywhere. The new mobile flow is multi-user: each user is identified by their JWT (which carries `sub=user_id`). The `get_current_user` dependency already handles this correctly — the new endpoints just use `current_user.id` instead of hardcoded `1`.

The CLI connect commands (`daily connect gmail`, etc.) call the localhost OAuth flow which opens a browser on the developer's machine. This stays as dev tooling (D-05). The new endpoints implement a different code path in `src/daily/integrations/router.py`.

---

## Standard Stack

### Core (already in project)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| FastAPI | 0.115+ | HTTP router for new endpoints | Follow `livekit/router.py` pattern |
| SQLAlchemy 2.0 | async | `IntegrationToken`, `BriefingConfig` writes | Use `async_session` from `db/engine.py` |
| `google-auth-oauthlib` | 1.x | Google OAuth flow | Already installed — `Flow.from_client_config` |
| `msal` | 1.x | Microsoft OAuth flow | Already installed — `PublicClientApplication` |
| `httpx` | async | Slack token exchange (POST to `oauth.v2.access`) | Already installed |
| `redis.asyncio` | 5.x | OAuth state CSRF storage | Already installed |
| `daily.vault.crypto` | — | `encrypt_token` before any `IntegrationToken` write | Required by SEC-01 |
| `daily.auth.deps` | — | `get_current_user` dependency | Required for all authenticated endpoints |
| `pytz` / `zoneinfo` | stdlib (3.9+) | Convert local time + IANA tz to UTC | `zoneinfo` is stdlib in Python 3.9+, no install needed |

**[VERIFIED: `uv.lock` / imports in existing code]**

### Installation

No new packages required. All dependencies are already present.

---

## Architecture Patterns

### Recommended Project Structure

```
src/daily/
├── integrations/
│   ├── router.py          # NEW: /integrations/{provider}/connect + callback
│   ├── google/auth.py     # UNCHANGED (CLI-only localhost flow)
│   ├── microsoft/auth.py  # UNCHANGED (CLI-only localhost flow)
│   └── slack/auth.py      # UNCHANGED (CLI-only localhost flow)
├── users/
│   └── router.py          # NEW: /users/me/integrations + /users/me/preferences
└── main.py                # ADD: include new routers, add /oauth/success to AASA
```

### Pattern 1: OAuth Connect Endpoint (Authenticated)

```python
# Source: mirrors livekit/router.py pattern + google/auth.py Flow usage
@router.get("/integrations/google/connect")
async def google_connect(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> ConnectResponse:
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", 600, str(current_user.id))
    
    flow = Flow.from_client_config(
        _google_client_config(settings),
        scopes=GOOGLE_ACTION_SCOPES,
        redirect_uri=f"{settings.magic_link_base_url}/integrations/google/callback",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return ConnectResponse(auth_url=auth_url)
```

**Key points:**
- Endpoint is authenticated — user must have completed magic-link pairing first
- State is stored in Redis with 600s TTL keyed by `oauth_state:{state}`
- Redis value is the `user_id` (int as string) — retrieved on callback to associate token
- `redirect_uri` must match the backend callback URL registered with provider

### Pattern 2: OAuth Callback Handler (Unauthenticated)

```python
# Source: mirrors google/auth.py store_google_tokens + livekit/router.py structure
@router.get("/integrations/google/callback")
async def google_callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
    redis: Redis = Depends(_get_redis),
) -> RedirectResponse:
    # 1. Validate state (CSRF prevention)
    raw = await redis.get(f"oauth_state:{state}")
    if raw is None:
        raise HTTPException(400, "Invalid or expired OAuth state")
    user_id = int(raw)
    await redis.delete(f"oauth_state:{state}")
    
    # 2. Exchange code for tokens
    flow = Flow.from_client_config(...)
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    # 3. Encrypt and upsert IntegrationToken
    vault_key = base64.b64decode(settings.vault_key)
    encrypted_access = encrypt_token(creds.token, vault_key)
    encrypted_refresh = encrypt_token(creds.refresh_token, vault_key) if creds.refresh_token else None
    
    await session.execute(
        delete(IntegrationToken).where(
            IntegrationToken.user_id == user_id,
            IntegrationToken.provider == "google",
        )
    )
    session.add(IntegrationToken(
        user_id=user_id, provider="google",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        token_expiry=creds.expiry,
        scopes=" ".join(creds.scopes or []),
    ))
    await session.commit()
    
    # 4. Redirect to Universal Link → iOS intercepts
    return RedirectResponse(
        f"{settings.magic_link_base_url}/oauth/success?provider=google",
        status_code=302,
    )
```

**Key points:**
- Callback is NOT authenticated (no JWT) — the user_id comes from Redis state lookup
- Provider is `"google"` for Google/Gmail, `"outlook"` for Microsoft (existing convention from CLI), `"slack"` for Slack
- Delete-then-insert (not upsert) follows existing `google/auth.py` pattern
- Redirect 302 to Universal Link — iOS app picks it up via Universal Links

### Pattern 3: Integration Status Endpoint

```python
@router.get("/users/me/integrations")
async def get_integration_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_db),
) -> IntegrationStatusResponse:
    result = await session.execute(
        select(IntegrationToken.provider).where(
            IntegrationToken.user_id == current_user.id
        )
    )
    connected = {row[0] for row in result.fetchall()}
    return IntegrationStatusResponse(
        google="google" in connected,
        microsoft="outlook" in connected,
        slack="slack" in connected,
    )
```

### Pattern 4: Briefing Schedule Update

```python
@router.put("/users/me/preferences")
async def update_preferences(
    body: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_db),
) -> None:
    # Convert local time + IANA timezone to UTC
    tz = ZoneInfo(body.timezone)
    local_dt = datetime.now(tz).replace(
        hour=int(body.briefing_time.split(":")[0]),
        minute=int(body.briefing_time.split(":")[1]),
    )
    utc_dt = local_dt.astimezone(timezone.utc)
    
    # Upsert BriefingConfig
    result = await session.execute(
        select(BriefingConfig).where(BriefingConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = BriefingConfig(user_id=current_user.id)
        session.add(config)
    config.schedule_hour = utc_dt.hour
    config.schedule_minute = utc_dt.minute
    config.timezone = body.timezone  # stored for display/recalculation
    await session.commit()
```

### Anti-Patterns to Avoid

- **Do not** generate the OAuth flow on the callback endpoint — the flow must be reconstructed with the same `redirect_uri` and scopes used in the connect step. Google and Microsoft validate this.
- **Do not** pass the OAuth state as a JWT claim or session cookie — Redis with TTL is the correct short-lived storage mechanism.
- **Do not** trust the `provider` path parameter alone to associate tokens — always validate state and retrieve `user_id` from Redis on the callback.
- **Do not** accept `error` query parameters silently in the callback — if the user cancels or denies, the provider sends `?error=access_denied`. The callback must detect and redirect accordingly (to a failure deep link, or return 400 for the session).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth state generation | Custom state machine | `secrets.token_urlsafe(32)` + Redis TTL | Cryptographically secure, atomic, TTL-managed |
| Google token exchange | Manual HTTP POST to token endpoint | `google_auth_oauthlib.flow.Flow.fetch_token()` | Handles PKCE, state validation, token refresh |
| Microsoft token exchange | Manual HTTP POST | `msal.PublicClientApplication.acquire_token_by_authorization_code()` | Handles MSAL internals, PKCE |
| Timezone conversion | Custom UTC math | `zoneinfo.ZoneInfo` (stdlib Python 3.9+) | DST-aware, IANA tz database |
| Token encryption | Custom cipher | `daily.vault.crypto.encrypt_token` | Already implemented, AES-256-GCM, tested |
| JWT auth guard | Manual header parsing | `daily.auth.deps.get_current_user` | Already implemented, tested |

---

## Common Pitfalls

### Pitfall 1: Flow Object Not Reconstructed on Callback
**What goes wrong:** The Google/Microsoft Flow object created in `/connect` is not accessible in `/callback` (stateless HTTP). The callback must reconstruct the Flow with identical parameters.
**Why it happens:** Developers assume the Flow persists between requests.
**How to avoid:** Always reconstruct `Flow.from_client_config(...)` in the callback handler with the same `redirect_uri` and `scopes`. Both endpoints share the same provider-specific constants.
**Warning signs:** `redirect_uri_mismatch` errors from Google.

### Pitfall 2: Microsoft Provider Key Is `"outlook"` Not `"microsoft"`
**What goes wrong:** Queries for `provider == "microsoft"` return no rows.
**Why it happens:** The existing CLI code (`microsoft/auth.py`) stores tokens with `provider="outlook"`. This naming is established in the existing `IntegrationToken` rows.
**How to avoid:** New mobile callback for Microsoft stores with `provider="outlook"` to match existing convention. Document this in the router code as a comment.

### Pitfall 3: Google Does Not Issue Refresh Token Without `prompt="consent"` + `access_type="offline"`
**What goes wrong:** `credentials.refresh_token` is `None` on second authorization.
**Why it happens:** Google only issues a refresh token on the first authorization unless `prompt="consent"` forces re-consent.
**How to avoid:** Always pass `access_type="offline"` and `prompt="consent"` in the authorization URL. This is already done in the CLI flow — replicate it in the mobile connect endpoint.

### Pitfall 4: OAuth State TTL vs User Latency
**What goes wrong:** User takes longer than TTL to complete provider consent screen → callback receives valid code but state has expired in Redis → 400 error.
**Why it happens:** Default TTL set too short.
**How to avoid:** 600s (10 minutes) TTL is appropriate. The typical OAuth consent screen takes < 30 seconds; 10 minutes covers slow networks and distracted users.

### Pitfall 5: AASA Cache — Apple CDNs Cache Aggressively
**What goes wrong:** Add `/oauth/success` to AASA paths but iOS doesn't pick it up as a Universal Link for days.
**Why it happens:** Apple's CDN caches the AASA file. On device, re-install the app to force re-fetch.
**How to avoid:** Test Universal Link handling with a fresh app install (or reinstall) after updating the AASA. During development, use `xcrun` diagnostics: `xcrun devicectl manage process launch --terminate-existing-process --device ... <bundle-id>`.

### Pitfall 6: `ZoneInfo` Key Error for Unknown Timezone
**What goes wrong:** iOS sends an unusual or malformed timezone string → `ZoneInfo(body.timezone)` raises `ZoneInfoNotFoundError`.
**Why it happens:** iOS `TimeZone.current.identifier` returns IANA identifiers (e.g., `"Australia/Brisbane"`) which are valid, but user could theoretically send anything via the API.
**How to avoid:** Catch `ZoneInfoNotFoundError` and return HTTP 422. Validate the timezone string before conversion.

### Pitfall 7: Scheduler Is Currently Hardcoded to `user_id=1`
**What goes wrong:** New users' briefing configs are stored but the APScheduler cron only fires for `user_id=1`.
**Why it happens:** `main.py` lifespan calls `setup_scheduler(hour, minute, user_id=1)` — single-user only.
**How to avoid:** Phase 21 scope is storing the per-user config and providing the API. The scheduler multi-user iteration (reading all users' `BriefingConfig` rows and scheduling each) is a follow-on task. Document this as a Phase 21 deliverable boundary: the API stores the preference; making the scheduler per-user requires a separate task to refactor the lifespan.

---

## Code Examples

### Redis Dependency (for connect/callback endpoints)

```python
# Source: pattern from existing briefing/scheduler.py Redis usage
from redis.asyncio import Redis
from daily.config import Settings

async def _get_redis() -> Redis:
    settings = Settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.aclose()
```

### Pydantic Request/Response Models

```python
# Source: mirrors auth/router.py Pydantic model pattern
class ConnectResponse(BaseModel):
    auth_url: str

class IntegrationStatusResponse(BaseModel):
    google: bool
    microsoft: bool
    slack: bool

class PreferencesUpdateRequest(BaseModel):
    briefing_time: str  # "HH:MM" format
    timezone: str       # IANA tz string e.g. "Australia/Brisbane"

    @field_validator("briefing_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("briefing_time must be HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid hour or minute")
        return v
```

### Timezone Conversion (stdlib zoneinfo)

```python
# Source: Python 3.9+ stdlib — no install needed
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, timezone

def local_to_utc(time_str: str, tz_name: str) -> tuple[int, int]:
    """Convert 'HH:MM' in IANA timezone to (utc_hour, utc_minute)."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown timezone: {tz_name}")
    h, m = map(int, time_str.split(":"))
    # Use today's date for DST accuracy
    today = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
    utc = today.astimezone(timezone.utc)
    return utc.hour, utc.minute
```

### Slack Token Exchange in Callback (httpx async)

```python
# Source: mirrors slack/auth.py httpx token exchange pattern, but async
import httpx

async def _exchange_slack_code(code: str, redirect_uri: str, settings: Settings) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(400, f"Slack error: {data.get('error')}")
    return data["access_token"]
```

Note: Google and Microsoft callbacks use synchronous SDK calls (`flow.fetch_token`, `msal.acquire_token_by_authorization_code`). These block the event loop briefly. For v1.4 scale this is acceptable; wrap in `asyncio.get_event_loop().run_in_executor(None, ...)` if needed.

---

## Schema Changes Required

### Migration 007: Add timezone to briefing_config

```python
# Alembic migration
def upgrade() -> None:
    op.add_column(
        "briefing_config",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )

def downgrade() -> None:
    op.drop_column("briefing_config", "timezone")
```

### SQLAlchemy Model Update

```python
class BriefingConfig(Base):
    __tablename__ = "briefing_config"
    # ... existing columns ...
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
```

No migration needed for `IntegrationToken` — the delete-then-insert upsert pattern from `google/auth.py` is sufficient without a unique constraint.

---

## Runtime State Inventory

> Phase 21 is not a rename/refactor — no runtime state inventory required.

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| PostgreSQL | `BriefingConfig` timezone column migration | ✓ | Running via Docker Compose |
| Redis | OAuth state CSRF storage | ✓ | Already used by briefing cache |
| `google-auth-oauthlib` | Google connect endpoint | ✓ | Already in `.venv` |
| `msal` | Microsoft connect endpoint | ✓ | Already in `.venv` |
| `httpx` | Slack async token exchange | ✓ | Already in `.venv` |
| `zoneinfo` | Timezone conversion | ✓ | Python 3.9+ stdlib |
| Resend API | Magic-link email (existing, unchanged) | ✓ | Configured via `RESEND_API_KEY` |

**No missing dependencies.** All required libraries are already installed.

---

## Validation Architecture

`nyquist_validation: true` in config.json — validation section required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest tests/test_integrations_router.py tests/test_users_router.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INT-01 | `GET /integrations/google/connect` returns `auth_url`, stores state in Redis | unit | `pytest tests/test_integrations_router.py::test_google_connect -x` | ❌ Wave 0 |
| INT-02 | `GET /integrations/google/callback` validates state, stores encrypted token, redirects | unit | `pytest tests/test_integrations_router.py::test_google_callback -x` | ❌ Wave 0 |
| INT-03 | `GET /integrations/microsoft/connect` returns `auth_url` | unit | `pytest tests/test_integrations_router.py::test_microsoft_connect -x` | ❌ Wave 0 |
| INT-04 | `GET /integrations/microsoft/callback` exchanges code, stores token with provider="outlook" | unit | `pytest tests/test_integrations_router.py::test_microsoft_callback -x` | ❌ Wave 0 |
| INT-05 | `GET /integrations/slack/connect` returns `auth_url` | unit | `pytest tests/test_integrations_router.py::test_slack_connect -x` | ❌ Wave 0 |
| INT-06 | `GET /integrations/slack/callback` exchanges code async, stores token | unit | `pytest tests/test_integrations_router.py::test_slack_callback -x` | ❌ Wave 0 |
| INT-07 | Expired/invalid OAuth state returns 400 | unit | `pytest tests/test_integrations_router.py::test_invalid_state -x` | ❌ Wave 0 |
| USR-01 | `GET /users/me/integrations` returns correct boolean per provider | unit | `pytest tests/test_users_router.py::test_integration_status -x` | ❌ Wave 0 |
| USR-02 | `PUT /users/me/preferences` stores briefing time as UTC in BriefingConfig | unit | `pytest tests/test_users_router.py::test_update_preferences -x` | ❌ Wave 0 |
| USR-03 | `PUT /users/me/preferences` with unknown timezone returns 422 | unit | `pytest tests/test_users_router.py::test_invalid_timezone -x` | ❌ Wave 0 |
| AASA-01 | AASA includes `/oauth/success` path | unit | `pytest tests/test_aasa.py -x` (extend existing) | ✅ exists |

### Sampling Rate

- **Per task commit:** `pytest tests/test_integrations_router.py tests/test_users_router.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_integrations_router.py` — covers INT-01 through INT-07
- [ ] `tests/test_users_router.py` — covers USR-01 through USR-03
- [ ] Extend `tests/test_aasa.py` — add assertion for `/oauth/success` path in AASA response

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | JWT Bearer via `get_current_user`; magic-link OTP for signup |
| V3 Session Management | yes | OAuth state in Redis with TTL; refresh token in `DeviceToken` |
| V4 Access Control | yes | All authenticated endpoints require valid JWT |
| V5 Input Validation | yes | Pydantic v2 models; `briefing_time` format validator; `ZoneInfo` key validation |
| V6 Cryptography | yes | AES-256-GCM via `encrypt_token`; never hand-roll |

### Known Threat Patterns for OAuth + FastAPI

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on OAuth callback | Spoofing | `state` parameter — Redis-backed, 600s TTL, single-use (delete after read) |
| OAuth code injection | Tampering | Validate state before exchanging code; code is tied to state in provider session |
| Token interception | Information Disclosure | Tokens never pass through iOS app; backend-only exchange (D-02) |
| Replay attack on callback | Elevation | Delete Redis state key immediately after reading — single-use |
| Email enumeration via send-link | Information Disclosure | Already handled — `POST /auth/pair/send-link` always returns 204 |
| Open redirect in callback | Spoofing | Deep link base URL comes from `settings.magic_link_base_url` (env var), not user input |

---

## Open Questions

1. **Scheduler multi-user iteration**
   - What we know: The scheduler currently runs only for `user_id=1`. `BriefingConfig` is per-user with a unique FK.
   - What's unclear: Is Phase 21's scope to make the scheduler iterate all users, or just to store the preference and defer scheduling to a follow-on task?
   - Recommendation: CONTEXT.md D-15 says "APScheduler cron job reads this per-user". This implies Phase 21 must update `main.py` to query all `BriefingConfig` rows and register a cron job per user. This is a non-trivial lifespan refactor. Planner should include this as a dedicated task (Wave 3).

2. **Google Flow reconstruction on callback — `client_config` source**
   - What we know: The connect endpoint constructs a `Flow` from `client_config`. The callback must reconstruct the same Flow.
   - What's unclear: Best approach for sharing the `client_config` helper between connect and callback without duplication.
   - Recommendation: Define `_google_client_config(settings)` as a module-level helper in `integrations/router.py` returning the config dict. Both endpoints call it.

3. **Slack `redirect_uri` registration**
   - What we know: Slack requires the redirect URI to be registered in the Slack app settings.
   - What's unclear: Whether the production URL is already configured in the Slack app settings, or if this is a deployment prerequisite.
   - Recommendation: Document as a deployment prerequisite in the plan. The callback URL will be `{magic_link_base_url}/integrations/slack/callback`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Google and Microsoft SDK token exchange calls are fast enough to not block the event loop noticeably at v1.4 scale | Code Examples | Could cause request latency; fix: wrap in `run_in_executor` |
| A2 | iOS Universal Link interception works without app reinstall after adding `/oauth/success` to AASA in dev | Pitfall 5 | Need to reinstall app; no code change required |
| A3 | `ZoneInfo` package (stdlib) is available — no `tzdata` install needed on the deployment OS | Environment | macOS has builtin tzdata; Linux may need `tzdata` system package |

---

## Sources

### Primary (HIGH confidence — direct code read)

- `src/daily/auth/router.py` — existing pairing endpoints, Pydantic model patterns
- `src/daily/auth/deps.py` — `get_current_user` dependency pattern
- `src/daily/auth/jwt.py` — JWT encode/decode
- `src/daily/vault/crypto.py` — `encrypt_token` / `decrypt_token`
- `src/daily/db/models.py` — all ORM models, confirmed schema
- `src/daily/integrations/google/auth.py` — existing token storage pattern (delete-then-insert)
- `src/daily/integrations/microsoft/auth.py` — provider="outlook" convention
- `src/daily/integrations/slack/auth.py` — async httpx pattern for token exchange
- `src/daily/main.py` — AASA paths, lifespan scheduler, single-user hardcoding
- `src/daily/briefing/scheduler.py` — per-user scheduling architecture
- `src/daily/livekit/router.py` — canonical authenticated router pattern to replicate
- `.planning/phases/21-per-user-onboarding/21-CONTEXT.md` — locked decisions
- `alembic/versions/005_add_pairing_codes_device_tokens.py` — migration convention

### Secondary (MEDIUM confidence)

- Python 3.9+ stdlib docs for `zoneinfo` module — DST-aware timezone conversion [ASSUMED from training; stdlib since 3.9]

---

## Metadata

**Confidence breakdown:**

- Existing auth system: HIGH — read all source files directly
- Gap analysis (BriefingConfig timezone, AASA paths, etc.): HIGH — verified against live code
- OAuth state/CSRF pattern: HIGH — verified against CONTEXT.md D-03 + confirmed Redis in stack
- Scheduler multi-user gap: HIGH — `main.py` hardcodes `user_id=1`, confirmed by inspection
- `zoneinfo` availability on Linux: MEDIUM — stdlib in Python 3.9+ but `tzdata` system package may be needed on some Linux distributions

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (stable stack, no fast-moving dependencies in scope)
