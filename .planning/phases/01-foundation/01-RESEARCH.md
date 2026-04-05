# Phase 1: Foundation - Research

**Researched:** 2026-04-05
**Domain:** OAuth 2.0 integration layer, encrypted token vault, async PostgreSQL schema, read adapters, CLI tooling
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** CLI command pattern — `daily connect gmail`, `daily connect outlook`, etc. Command opens the user's browser and spins up a temporary FastAPI server on localhost to capture the OAuth callback. Same redirect flow production will use; redirect URL moves from `localhost:8080/callback` to the real app — not wasted work.
- **D-02:** Each provider gets its own connect command. Tokens are written to the encrypted vault immediately after the callback — never held in plaintext beyond the in-memory exchange.
- **D-03:** All 4 integrations in Phase 1: Gmail, Google Calendar, Microsoft Outlook (via Microsoft Graph), and Slack. These represent 3 distinct OAuth flows — Google (shared for Gmail + GCal), Slack, and Microsoft Graph.
- **D-04:** Implementation order within Phase 1: Google OAuth flow first (covers Gmail + GCal in one flow), then Slack, then Microsoft Graph (most complex). This is the natural risk-ordered sequence.
- **D-05:** Minimal schema only. Two core tables: `users` and `integration_tokens` (encrypted). No pre-stubbing of columns or tables for future phases. Phase 2 adds its own migrations.
- **D-06:** "No raw body storage" constraint is structural — the schema has no `raw_body` column. There is no column to store it in. Only `summary` and metadata columns exist for email/message data. Enforcement is architectural, not conventional.
- **D-07:** Adapters return typed Pydantic models with pagination support. No rate-limit handling, no retry logic, no exponential backoff — that is Phase 2's responsibility when the pipeline runs adapters at scale.
- **D-08:** Adapter interface contract: `list_emails(since: datetime, page_token: str | None) -> EmailPage`, `list_events(since: datetime, until: datetime) -> list[CalendarEvent]`, `list_messages(channels: list[str], since: datetime) -> MessagePage`.

### Claude's Discretion

- Exact Pydantic model field names for email/event/message types
- Internal module structure within the integration package
- How token decryption is handled at adapter instantiation (inject vs. lazy load)
- CLI framework choice (Typer vs Click — Typer recommended given FastAPI ecosystem)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-01 | User can connect a Gmail account via OAuth 2.0 with minimum required scopes (read email, draft/send replies) | Google OAuth flow with `google-auth-oauthlib` + `google-api-python-client`; minimum scopes section below |
| INTG-02 | User can connect a Google Calendar account via OAuth 2.0 (read events, create/update events) | Shared Google flow with INTG-01 — single OAuth authorization covers both Gmail and Calendar scopes |
| INTG-03 | User can connect a Microsoft Outlook account via OAuth 2.0 / Microsoft Graph (read email, draft/send replies, read/write Exchange calendar) | `msal` + `msgraph-sdk`; MSAL device code or auth code flow; Graph scopes documented below |
| INTG-04 | User can connect a Slack workspace via OAuth 2.0 (≥50 req/min rate limit tier) | `slack-sdk` WebClient; Slack OAuth V2 flow; internal app required for ≥50 req/min |
| INTG-05 | OAuth access tokens refreshed proactively before briefing jobs run, not inline | Background refresh function: load tokens nearing expiry, call provider refresh endpoint, re-encrypt, write back to DB; run as APScheduler job in Phase 2 but token refresh logic lives in Phase 1 vault module |
| SEC-01 | OAuth tokens encrypted at rest (AES-256) — never exposed to frontend, logs, or LLM | `cryptography` library AES-256-GCM; encrypt before DB write, decrypt in-memory only at call time |
| SEC-03 | Each integration requests only minimum OAuth scopes required | Minimum scope tables documented below |
| SEC-04 | Raw email and message bodies not stored long-term — only summaries and metadata persisted | Schema has no raw_body column (D-06); read adapters return typed Pydantic models with metadata only |
</phase_requirements>

---

## Summary

Phase 1 establishes the integration foundation: an encrypted OAuth token vault, three distinct OAuth authorization flows (Google, Slack, Microsoft Graph), typed read adapters for each data source, and a minimal PostgreSQL schema. The entire surface area is a data-access layer — no LLM, no voice, no briefing pipeline.

The core complexity sits in two places: (1) AES-256-GCM token encryption/decryption lifecycle — tokens must never touch a log or the LLM context in plaintext, and (2) Microsoft Graph OAuth, which uses MSAL with a device code or auth code flow that differs meaningfully from Google's flow. The Google and Slack flows are comparatively straightforward.

This is a greenfield codebase. Phase 1 establishes the patterns (adapter interface, token vault, async SQLAlchemy, Alembic migrations) that every subsequent phase inherits. Getting these right structurally matters more than feature completeness.

**Primary recommendation:** Build the token vault module first (encryption/decryption + DB write/read), then layer each OAuth flow on top. All adapter tests should mock the token vault and the external API calls — no live API calls in tests.

---

## Project Constraints (from CLAUDE.md)

These directives are non-negotiable and override any conflicting recommendation in this document:

| Constraint | Directive |
|------------|-----------|
| Architecture | LLM must not directly access APIs or hold credentials — backend mediates everything |
| Privacy | Raw email/message bodies must not be stored long-term — only summaries and metadata |
| Security | OAuth tokens encrypted at rest (AES-256), stored in secure vault (never frontend) |
| Autonomy | All external-facing actions require user approval in M1 — auto-actions are M2+ |
| Forbidden library | Do NOT use `python-jose` — near-abandoned, flagged by FastAPI maintainers (use `authlib`) |
| Forbidden pattern | Do NOT use `LangChain` chains (use `LangGraph`) |
| Forbidden | Do NOT use Flask (use FastAPI) |
| Forbidden | Do NOT use Chroma/Pinecone as standalone vector DB (use pgvector on Postgres) |
| Package manager | Use `uv` — replaces pip + virtualenv |
| ORM | SQLAlchemy 2.0 async engine with `asyncpg` driver — no sync engine |

---

## Standard Stack

### Core (Phase 1 specific)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Primary language | Required by FastAPI 0.130+; async-native |
| FastAPI | 0.135.3 | Temporary OAuth callback server + future API | localhost callback server uses FastAPI; same pattern production will use |
| Pydantic | 2.12.5 | Typed models for adapter return types + settings | Required by FastAPI; v2 is 50x faster than v1 |
| SQLAlchemy | 2.0.49 | Async ORM for token vault persistence | 2.0 rewrites async properly — `create_async_engine` + `asyncpg` |
| asyncpg | 0.31.0 | PostgreSQL async driver | Required backend for SQLAlchemy async engine |
| Alembic | 1.18.4 | Database migrations | Pairs with SQLAlchemy 2.0; manages schema evolution |
| cryptography | 46.0.6 | AES-256-GCM token encryption | Industry standard; SEC-01 requirement |
| python-dotenv | 1.2.2 | Load secrets from .env | Keep credentials out of code |
| Typer | 0.24.1 | CLI framework (`daily connect gmail`) | FastAPI-ecosystem CLI tool; uses Click underneath |

[VERIFIED: npm/PyPI registry - all versions confirmed 2026-04-05]

### Integrations (Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| google-auth-oauthlib | 1.3.1 | Google OAuth 2.0 flow | Official Google library; handles token refresh, scope management |
| google-api-python-client | 2.193.0 | Gmail + Google Calendar API calls | Official Google client; required since March 2025 OAuth mandate |
| slack-sdk | 3.41.0 | Slack OAuth + API calls | Official Slack Python SDK |
| msgraph-sdk | 1.55.0 | Microsoft Graph API calls | Official Microsoft Graph Python SDK |
| msal | 1.35.1 | Microsoft OAuth 2.0 token acquisition | Microsoft Authentication Library — required for Graph API scopes |

[VERIFIED: PyPI registry - all versions confirmed 2026-04-05]

### Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| uv | 0.11.2 | Package/venv management (already installed) |
| pytest | latest | Test runner |
| pytest-asyncio | 1.3.0 | Async test support |
| httpx | 0.28.1 | Async HTTP client for tests |
| docker compose | v5.0.2 | Local Postgres + Redis (already installed) |

[VERIFIED: PyPI registry + local environment check 2026-04-05]

### Installation

```bash
# Initialise project
uv init daily
cd daily

# Core infrastructure
uv add fastapi pydantic sqlalchemy asyncpg alembic python-dotenv typer

# Security / encryption
uv add cryptography

# Google integrations
uv add google-auth-oauthlib google-api-python-client

# Slack integration
uv add slack-sdk

# Microsoft integration
uv add msal msgraph-sdk

# Dev dependencies
uv add --dev pytest pytest-asyncio httpx
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Typer | Click directly | Typer wraps Click and adds type-hint ergonomics; no reason to use raw Click |
| FastAPI callback server | http.server stdlib | FastAPI is reusable for the production API; stdlib is throwaway code |
| cryptography (AES-256-GCM) | authlib encryption | cryptography is lower-level and gives full control; authlib is better for JWT handling in future phases |
| msal + msgraph-sdk | azure-identity + requests | msal + msgraph-sdk is the current Microsoft-recommended pattern for Python |

---

## Architecture Patterns

### Recommended Project Structure

```
daily/
├── pyproject.toml
├── .env                          # secrets (gitignored)
├── docker-compose.yml            # local Postgres + Redis
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── src/
│   └── daily/
│       ├── __init__.py
│       ├── main.py               # FastAPI app entrypoint
│       ├── cli.py                # Typer CLI entrypoint (daily connect ...)
│       ├── config.py             # Settings via pydantic-settings
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py         # create_async_engine + session factory
│       │   └── models.py         # SQLAlchemy ORM models (User, IntegrationToken)
│       ├── vault/
│       │   ├── __init__.py
│       │   └── crypto.py         # AES-256-GCM encrypt/decrypt
│       └── integrations/
│           ├── __init__.py
│           ├── base.py           # Abstract adapter interface
│           ├── models.py         # Pydantic output models (EmailPage, CalendarEvent, MessagePage)
│           ├── google/
│           │   ├── __init__.py
│           │   ├── auth.py       # OAuth flow + token storage
│           │   └── adapter.py    # GmailAdapter + GoogleCalendarAdapter
│           ├── slack/
│           │   ├── __init__.py
│           │   ├── auth.py
│           │   └── adapter.py    # SlackAdapter
│           └── microsoft/
│               ├── __init__.py
│               ├── auth.py       # MSAL auth code flow + token storage
│               └── adapter.py    # OutlookAdapter
└── tests/
    ├── conftest.py               # pytest fixtures, async session setup
    ├── test_vault.py             # crypto unit tests
    ├── test_google_adapter.py    # adapter unit tests (mocked API calls)
    ├── test_slack_adapter.py
    └── test_microsoft_adapter.py
```

### Pattern 1: Token Vault — Encrypt Before Write

The vault module is the single point of encryption/decryption. Nothing outside `vault/crypto.py` handles plaintext token data.

```python
# src/daily/vault/crypto.py
# Source: cryptography library docs — https://cryptography.io/en/latest/hazmat/primitives/aead/
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, base64

def encrypt_token(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt a token string. Returns base64-encoded ciphertext+nonce."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Store nonce prepended to ciphertext, base64-encoded
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt_token(encrypted: str, key: bytes) -> str:
    """Decrypt a vault-stored token. Returns plaintext string."""
    data = base64.b64decode(encrypted.encode())
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

[CITED: https://cryptography.io/en/latest/hazmat/primitives/aead/]

### Pattern 2: Async SQLAlchemy Engine Setup

```python
# src/daily/db/engine.py
# Source: SQLAlchemy 2.0 async docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

def make_engine(database_url: str):
    # URL must use postgresql+asyncpg:// scheme
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)

def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

[CITED: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]

### Pattern 3: OAuth Callback Server (localhost)

```python
# src/daily/integrations/google/auth.py  (sketch)
# FastAPI app spun up temporarily; same mechanism production uses
import uvicorn, webbrowser
from fastapi import FastAPI

def run_google_oauth_flow(client_id: str, client_secret: str, scopes: list[str]) -> dict:
    app = FastAPI()
    auth_code_holder = {}

    @app.get("/callback")
    async def callback(code: str, state: str):
        auth_code_holder["code"] = code
        # exchange code for tokens via google-auth-oauthlib
        ...

    # Open browser to Google auth URL
    webbrowser.open(build_google_auth_url(client_id, scopes, redirect_uri="http://localhost:8080/callback"))
    uvicorn.run(app, host="127.0.0.1", port=8080)
    # Server shuts down after callback received
    return auth_code_holder["tokens"]
```

[ASSUMED] - Pattern is standard but exact shutdown mechanism (using asyncio events or threading) needs validation.

### Pattern 4: Adapter Interface Contract

```python
# src/daily/integrations/base.py
from abc import ABC, abstractmethod
from datetime import datetime
from daily.integrations.models import EmailPage, CalendarEvent, MessagePage

class EmailAdapter(ABC):
    @abstractmethod
    async def list_emails(self, since: datetime, page_token: str | None = None) -> EmailPage:
        ...

class CalendarAdapter(ABC):
    @abstractmethod
    async def list_events(self, since: datetime, until: datetime) -> list[CalendarEvent]:
        ...

class MessageAdapter(ABC):
    @abstractmethod
    async def list_messages(self, channels: list[str], since: datetime) -> MessagePage:
        ...
```

### Anti-Patterns to Avoid

- **Storing plaintext tokens at any point:** Even in a temporary variable that gets logged. Encrypt immediately after the OAuth callback — never assign to a named variable that could be logged or serialised.
- **Broad OAuth scopes:** Requesting `https://mail.google.com/` (full mail access) instead of `https://www.googleapis.com/auth/gmail.readonly`. Use the narrowest scope that satisfies the use case.
- **Sync SQLAlchemy engine with asyncpg:** `create_engine("postgresql+asyncpg://...")` will fail. Must use `create_async_engine`.
- **Re-using the same nonce for AES-GCM:** Never re-use a nonce with the same key. Generate `os.urandom(12)` fresh for every encryption call.
- **Token refresh inline in the adapter:** Adapters should receive a valid (already decrypted) token at instantiation. Token refresh is the vault's responsibility, not the adapter's.
- **Raw HTTP calls instead of SDK:** Do not call `https://gmail.googleapis.com/gmail/v1/users/me/messages` directly. Use `google-api-python-client` service objects.

---

## Minimum OAuth Scopes

### Google (Gmail + Calendar)

| Scope | Purpose | Required By |
|-------|---------|-------------|
| `https://www.googleapis.com/auth/gmail.readonly` | Read email (Phase 1 read adapter) | INTG-01 |
| `https://www.googleapis.com/auth/gmail.compose` | Draft replies (Phase 4 action layer) | INTG-01 (future) |
| `https://www.googleapis.com/auth/calendar.readonly` | Read events (Phase 1 read adapter) | INTG-02 |
| `https://www.googleapis.com/auth/calendar.events` | Create/update events (Phase 4) | INTG-02 (future) |

**Phase 1 minimum (read-only):** Request `gmail.readonly` + `calendar.readonly` only. Do not request compose or events scopes until Phase 4. Scope incrementalism is supported by Google OAuth — add scopes in a later authorization step.

[CITED: https://developers.google.com/gmail/api/auth/scopes + https://developers.google.com/calendar/api/auth]

### Slack

| Scope | Purpose | Required By |
|-------|---------|-------------|
| `channels:read` | List public channels | INTG-04 |
| `channels:history` | Read messages from public channels | INTG-04 |
| `im:read` | Read direct message metadata | INTG-04 |
| `im:history` | Read DM content | INTG-04 |
| `users:read` | Resolve user IDs to names | INTG-04 |

**Rate limit note:** The ≥50 req/min tier requires an **internal Slack app** (not a public distributed app). The OAuth app type must be set to "internal" in the Slack App configuration. Distributed public apps default to Tier 1 (1 req/min for some endpoints).

[CITED: https://api.slack.com/docs/rate-limits + https://api.slack.com/authentication/oauth-v2]

### Microsoft Graph (Outlook + Exchange Calendar)

| Scope | Purpose | Required By |
|-------|---------|-------------|
| `Mail.Read` | Read email | INTG-03 |
| `Mail.ReadWrite` | Draft replies (Phase 4) | INTG-03 (future) |
| `Calendars.Read` | Read calendar events | INTG-03 |
| `Calendars.ReadWrite` | Create/update events (Phase 4) | INTG-03 (future) |
| `offline_access` | Refresh token (long-lived session) | INTG-05 |
| `User.Read` | Basic profile (required for Graph auth) | INTG-03 |

**Phase 1 minimum:** `Mail.Read`, `Calendars.Read`, `offline_access`, `User.Read`.

[CITED: https://learn.microsoft.com/en-us/graph/permissions-reference]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AES-256 encryption | Custom cipher | `cryptography` AESGCM | Nonce management, padding, and authenticated encryption are subtle — one mistake breaks security silently |
| OAuth 2.0 flow | Custom PKCE/auth code exchange | `google-auth-oauthlib`, `msal`, `slack-sdk` | Token exchange, refresh, revocation, and PKCE are complex; each provider has quirks |
| Google API pagination | Custom next_page cursor | `google-api-python-client` list() with `pageToken` | The API wraps all list methods; do not build raw HTTP pagination |
| Token refresh scheduling | Custom background loop | Token refresh function called by APScheduler (Phase 2) | Phase 2 owns the scheduler; Phase 1 just provides the refresh function |
| Microsoft Graph pagination | Custom `@odata.nextLink` traversal | `msgraph-sdk` PageIterator | MS Graph uses OData pagination; the SDK PageIterator handles multi-page responses |
| Slack channel listing | Custom cursor pagination | `slack-sdk` WebClient with `cursor` parameter | Slack uses cursor-based pagination across all list methods |

**Key insight:** Every OAuth provider has shipped Python SDKs that handle the most dangerous edge cases (token expiry races, refresh races, scope escalation). Using raw HTTP calls for any of these flows means re-implementing those edge cases incorrectly.

---

## Common Pitfalls

### Pitfall 1: Google OAuth Refresh Token Only Issued Once

**What goes wrong:** Google only issues a `refresh_token` on the first authorization. If the access token expires and you don't have the refresh token stored, the user must re-authorize from scratch.

**Why it happens:** By default, Google does not re-issue a refresh token if the user has already authorized the app. The `access_type=offline` parameter must be set AND the flow must be treated as a fresh grant (or `prompt=consent` forced).

**How to avoid:** Always request `access_type=offline` in the initial auth URL. Store the `refresh_token` in the vault immediately on first callback — never discard it. If testing and the refresh token is missing, revoke app access at https://myaccount.google.com/permissions and re-authorize.

**Warning signs:** `refresh_token` is `None` in the credentials object after the callback.

[CITED: https://developers.google.com/identity/protocols/oauth2/web-server#offline]

### Pitfall 2: SQLAlchemy Async Session Lifecycle

**What goes wrong:** `Session is already closed` or `MissingGreenlet` errors in async context. SQLAlchemy 2.0 async sessions are not thread-safe and must not be used outside their `async with` block.

**Why it happens:** Accessing lazy-loaded ORM attributes outside the session context, or sharing a session across tasks.

**How to avoid:** Use `async_sessionmaker` with `expire_on_commit=False`. Never pass a session across task boundaries. Each request/operation gets its own session via dependency injection or context manager.

[CITED: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession]

### Pitfall 3: Microsoft Graph MSAL Auth Code Flow vs Device Code Flow

**What goes wrong:** MSAL's `PublicClientApplication.acquire_token_interactive()` opens a browser but requires a redirect URI registered in Azure AD. If the redirect URI doesn't match exactly (including trailing slashes), Azure rejects the request with `AADSTS50011`.

**Why it happens:** Azure AD validates the redirect URI against the registered list. `http://localhost:8080/callback` and `http://localhost:8080/callback/` are different URIs.

**How to avoid:** Register `http://localhost:8080/callback` (no trailing slash) in the Azure AD app registration. Use the exact same string in code. For CLI flows, the device code flow (`acquire_token_by_device_flow`) avoids redirect URI issues entirely and may be simpler for Phase 1.

[ASSUMED] — Azure AD URI matching behavior is well-documented but exact CLI recommendation needs testing.

### Pitfall 4: AES-GCM Nonce Reuse

**What goes wrong:** If the same nonce is used with the same key twice, AES-GCM authentication is completely broken and plaintext can be recovered.

**Why it happens:** Developers store the nonce as a constant or derive it deterministically from the token content.

**How to avoid:** Always generate nonce with `os.urandom(12)` per encryption call. Prepend the nonce to the ciphertext before base64-encoding (standard pattern). The same key can be reused safely as long as nonces are random and non-repeating.

[CITED: https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM]

### Pitfall 5: Slack Internal App vs. Distributed App Rate Limits

**What goes wrong:** Slack app is registered as a distributed app and hits Tier 1 rate limits (1 req/min for some endpoints) instead of the ≥50 req/min tier required by INTG-04.

**Why it happens:** New Slack apps default to "distributed" mode. The rate limit tier is determined by app type, not by OAuth scopes.

**How to avoid:** When creating the Slack app at https://api.slack.com/apps, configure it as an internal app (toggle off "Distribute App"). Internal apps get Tier 2+ rate limits. The OAuth flow is the same — only the app configuration differs.

[CITED: https://api.slack.com/docs/rate-limits]

### Pitfall 6: Token Decryption Key Not Available at Startup

**What goes wrong:** The AES-256 key is loaded from `.env` at startup. If the key is missing or wrong length (must be 32 bytes for AES-256), decryption fails silently or raises a cryptic error.

**Why it happens:** Developers generate the key as a hex string, store it in `.env`, but forget to decode it from hex before passing to AESGCM (which expects raw bytes).

**How to avoid:** Generate the key as: `python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`. Store as base64 in `.env`. Decode at startup: `key = base64.b64decode(os.environ["VAULT_KEY"])`. Validate length at startup: `assert len(key) == 32`.

[ASSUMED] — Standard pattern; exact env var handling is implementation detail.

---

## Code Examples

### SQLAlchemy ORM Models for Phase 1 Schema

```python
# src/daily/db/models.py
# Source: SQLAlchemy 2.0 docs — https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class IntegrationToken(Base):
    __tablename__ = "integration_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    provider: Mapped[str] = mapped_column(String(50))   # "gmail", "google_calendar", "slack", "outlook"
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str] = mapped_column(Text)           # space-separated scope list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # NOTE: No raw_body, no message_content — enforces SEC-04 architecturally (D-06)
```

[CITED: https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#orm-declarative-mapped-column]

### Pydantic Adapter Output Models

```python
# src/daily/integrations/models.py
from pydantic import BaseModel
from datetime import datetime

class EmailMetadata(BaseModel):
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    is_unread: bool
    labels: list[str]
    # No body field — raw body never returned from adapters (SEC-04 / D-06)

class EmailPage(BaseModel):
    emails: list[EmailMetadata]
    next_page_token: str | None

class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    location: str | None
    is_all_day: bool

class MessageMetadata(BaseModel):
    message_id: str
    channel_id: str
    sender_id: str
    timestamp: datetime
    is_mention: bool
    is_dm: bool
    # No text field — raw message content not returned from adapters (SEC-04 / D-06)

class MessagePage(BaseModel):
    messages: list[MessageMetadata]
    next_cursor: str | None
```

### Google Auth Flow (outline)

```python
# src/daily/integrations/google/auth.py
# Source: google-auth-oauthlib InstalledAppFlow docs
from google_auth_oauthlib.flow import Flow

GMAIL_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

def build_google_flow(client_secrets_file: str, redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(
        client_secrets_file,
        scopes=GMAIL_READONLY_SCOPES,
        redirect_uri=redirect_uri,
    )
```

[CITED: https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `google-auth-httplib2` | `google-auth-oauthlib` | ~2020 | httplib2 backend deprecated; oauthlib is the current standard |
| `python-jose` for JWT | `authlib` | 2024–2025 | python-jose near-abandoned; FastAPI maintainers explicitly flag it |
| LangChain chains | LangGraph | 2024 | Chains lack state persistence and human-in-the-loop; LangGraph is the current pattern |
| SQLAlchemy 1.4 legacy async | SQLAlchemy 2.0 `create_async_engine` | 2023 | 2.0 is the stable async API; 1.4 async was experimental |
| ADAL for Microsoft auth | MSAL | 2020 | ADAL is deprecated; MSAL is the replacement |

**Deprecated/outdated:**

- `python-jose`: Do not use — near-abandoned, security library with no active maintenance
- `google.oauth2.credentials.Credentials` stored as JSON: Acceptable for local prototyping but never for production; use encrypted vault
- `InstalledAppFlow.run_local_server()` from google-auth-oauthlib: This is the standard CLI pattern but spins up a generic HTTP server — replacing it with a FastAPI server gives the production redirect path (D-01)

---

## Runtime State Inventory

This is a greenfield codebase — no renaming or migration in scope. Included for completeness:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — database doesn't exist yet | Create schema via Alembic migration |
| Live service config | None | Create Google Cloud project, Slack app, Azure AD app registration |
| OS-registered state | None | None |
| Secrets/env vars | None — .env doesn't exist yet | Create .env with VAULT_KEY, client IDs/secrets |
| Build artifacts | None — greenfield | None |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI localhost callback server can be shut down cleanly after receiving the OAuth code (via threading or asyncio event) | Architecture Patterns — Pattern 3 | Planner may need to specify exact shutdown mechanism; otherwise server stays alive |
| A2 | MSAL device code flow is simpler than auth code flow for CLI context | Common Pitfalls — Pitfall 3 | If device code flow has limitations for this use case, must use auth code flow with registered redirect URI |
| A3 | AES-256 key stored as base64 in .env is the intended vault key management pattern for M1 (not AWS Secrets Manager) | Standard Stack | If Jacob intends to use a proper secrets manager from day 1, vault implementation changes |

---

## Open Questions

1. **Google Cloud Project setup: is Jacob creating a new project or using an existing one?**
   - What we know: OAuth requires a Google Cloud Console project with Gmail API and Calendar API enabled
   - What's unclear: Whether test credentials already exist or need to be created as part of Phase 1
   - Recommendation: Include "create Google Cloud project + enable APIs" as a Wave 0 task

2. **Azure AD app registration: personal Microsoft account vs Entra ID tenant?**
   - What we know: Personal Microsoft accounts (outlook.com) can use a consumer-facing app registration; enterprise/Entra accounts require tenant-specific setup
   - What's unclear: Which Microsoft account type Jacob is testing with
   - Recommendation: Register app for "Accounts in any organizational directory and personal Microsoft accounts" to cover both cases

3. **Slack workspace: does a test workspace exist?**
   - What we know: Slack internal apps must be created in an actual Slack workspace
   - What's unclear: Whether Jacob has a dedicated test workspace or will use a personal workspace
   - Recommendation: Create a free Slack workspace for development if none exists

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All code | ✓ | 3.14.3 | — |
| uv | Package management | ✓ | 0.11.2 | — |
| Docker | Local Postgres + Redis | ✓ | 29.2.1 | — |
| Docker Compose | Local dev orchestration | ✓ | v5.0.2 | — |
| psql CLI | DB inspection/debugging | ✗ | — | Use `docker exec -it postgres psql` or DBeaver |
| redis-cli | Cache inspection | ✗ | — | Use `docker exec -it redis redis-cli` |
| pytest | Test runner | ✗ | — | Install via `uv add --dev pytest pytest-asyncio` in Wave 0 |
| Google Cloud project | INTG-01, INTG-02 | ✗ | — | Must be created; no fallback |
| Slack workspace + app | INTG-04 | ✗ | — | Must be created; no fallback |
| Azure AD app registration | INTG-03 | ✗ | — | Must be created; no fallback |

**Missing dependencies with no fallback:**
- Google Cloud project with Gmail API and Calendar API enabled (requires manual setup in Google Cloud Console)
- Slack app registered as internal app in a Slack workspace
- Azure AD app registration for Microsoft Graph

**Missing dependencies with fallback:**
- `psql` CLI: use `docker exec` to access Postgres shell inside the container
- `redis-cli`: use `docker exec` to access Redis shell inside the container
- `pytest`: install in Wave 0 setup task

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — see Wave 0 |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | Encrypted token stored in DB has no plaintext substring | unit | `pytest tests/test_vault.py::test_encrypted_token_is_not_plaintext -x` | ❌ Wave 0 |
| SEC-01 | Decrypt(encrypt(token)) == original token | unit | `pytest tests/test_vault.py::test_round_trip_encryption -x` | ❌ Wave 0 |
| SEC-03 | Google adapter is initialised with only `gmail.readonly` + `calendar.readonly` scopes | unit | `pytest tests/test_google_adapter.py::test_google_scopes_are_minimum -x` | ❌ Wave 0 |
| SEC-04 | EmailMetadata model has no `body` or `raw_body` field | unit | `pytest tests/test_models.py::test_email_model_has_no_body -x` | ❌ Wave 0 |
| INTG-01/02 | `list_emails` and `list_events` return correctly typed Pydantic models | unit | `pytest tests/test_google_adapter.py -x` | ❌ Wave 0 |
| INTG-04 | `list_messages` returns MessagePage with correct cursor structure | unit | `pytest tests/test_slack_adapter.py -x` | ❌ Wave 0 |
| INTG-03 | `list_emails` (Outlook) returns EmailPage from mocked Graph response | unit | `pytest tests/test_microsoft_adapter.py -x` | ❌ Wave 0 |
| INTG-05 | Token with near-expiry flag triggers refresh path | unit | `pytest tests/test_vault.py::test_refresh_required_detection -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/conftest.py` — async session fixtures, vault key fixture
- [ ] `tests/test_vault.py` — covers SEC-01, INTG-05
- [ ] `tests/test_models.py` — covers SEC-04
- [ ] `tests/test_google_adapter.py` — covers INTG-01, INTG-02, SEC-03
- [ ] `tests/test_slack_adapter.py` — covers INTG-04
- [ ] `tests/test_microsoft_adapter.py` — covers INTG-03
- [ ] Framework install: `uv add --dev pytest pytest-asyncio httpx`
- [ ] pytest config in `pyproject.toml`: `asyncio_mode = "auto"`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | OAuth delegated auth — user authenticates with provider, not with this app directly |
| V3 Session Management | Partial | Token expiry and refresh (INTG-05); no user session in Phase 1 (CLI only) |
| V4 Access Control | No | Single-user CLI in Phase 1; multi-user is Phase 3+ |
| V5 Input Validation | Yes | Pydantic models validate all API responses before use |
| V6 Cryptography | Yes | `cryptography` AESGCM — never hand-roll; AES-256-GCM with random nonce per call |
| V8 Data Protection | Yes | No raw body storage (SEC-04); token encryption at rest (SEC-01) |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Plaintext token in logs | Information Disclosure | Never log token values; mask in error output; encrypt before any persistence |
| Token stored in env var without encryption | Information Disclosure | Vault key in .env; encrypted token ciphertext in DB — plaintext never in DB |
| Nonce reuse in AES-GCM | Tampering | `os.urandom(12)` per encryption call — never reuse |
| Scope creep on OAuth consent | Elevation of Privilege | Request only minimum scopes (SEC-03); document each scope with its purpose |
| PKCE bypass on auth code flow | Spoofing | Use `code_verifier` / `code_challenge` if implementing custom flow; sdks handle this |
| Stale refresh token causes silent failure | Denial of Service | INTG-05: proactive refresh before expiry, not inline; log refresh failures clearly |

---

## Sources

### Primary (HIGH confidence)

- [PyPI registry] — all package versions verified 2026-04-05 via `pip3 index versions`
- [https://cryptography.io/en/latest/hazmat/primitives/aead/] — AES-GCM usage, nonce requirements
- [https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html] — async engine setup, session lifecycle
- [https://developers.google.com/identity/protocols/oauth2/web-server#offline] — refresh_token issuance requirements
- [https://developers.google.com/gmail/api/auth/scopes] — Gmail minimum scopes
- [https://developers.google.com/calendar/api/auth] — Calendar minimum scopes
- [https://api.slack.com/docs/rate-limits] — Slack rate limit tiers, internal vs distributed app
- [https://api.slack.com/authentication/oauth-v2] — Slack OAuth V2 flow
- [https://learn.microsoft.com/en-us/graph/permissions-reference] — Microsoft Graph scope reference
- [CLAUDE.md §Technology Stack] — stack decisions, version compatibility, forbidden patterns

### Secondary (MEDIUM confidence)

- [google-auth-oauthlib docs] — InstalledAppFlow and Flow class patterns
- [msgraph-sdk GitHub] — Python SDK patterns for Graph API pagination

### Tertiary (LOW confidence)

- FastAPI localhost shutdown mechanism for OAuth callback (A1 in assumptions log) — standard pattern but exact implementation unverified

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI registry
- OAuth scope minimums: HIGH — cited from official Google/Slack/Microsoft docs
- Architecture patterns: HIGH (vault, ORM) / MEDIUM (OAuth callback server shutdown mechanism)
- Pitfalls: HIGH (Google refresh token, AES nonce, Slack rate limits) / MEDIUM (MSAL CLI pattern)
- Test map: HIGH — maps directly to stated requirements

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (package versions stable; OAuth scope docs are stable)
