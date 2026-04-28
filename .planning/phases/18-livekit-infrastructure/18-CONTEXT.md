# Phase 18: LiveKit Infrastructure + Token Endpoint - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Self-hosted LiveKit server with TURN support and a `POST /livekit/token` JWT endpoint authenticated against the existing user session. User can connect a LiveKit client and receive a valid session token — no separate login required. This is infrastructure only — the agent worker, mobile clients, and voice pipeline migration are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Auth & Session Strategy
- **D-01:** Device pairing + JWT auth flow. User pairs a device via a 6-digit code (generated server-side), which exchanges for a long-lived refresh token stored in iOS Keychain / Android Keystore. Subsequent API calls use short-lived JWTs issued from the refresh token.
- **D-02:** No email/password login — pairing code is the only auth mechanism for v1.4. Production-grade for multi-user/multi-tester deployment.
- **D-03:** The `/livekit/token` endpoint validates the JWT from D-01 and returns a LiveKit-specific JWT scoped to the user's room. Unauthenticated requests return 401.
- **D-04:** This auth pattern (pairing + JWT) becomes the standard for ALL future API endpoints, not just LiveKit.

### Deployment Topology
- **D-05:** Self-hosted LiveKit server on the same VPS as FastAPI/Postgres/Redis. Single machine, single docker-compose deployment.
- **D-06:** Coturn (TURN relay) included in production deployment for firewall/NAT traversal (~20% of users need TURN fallback). Configured on TCP 443 + UDP 3478.
- **D-07:** Scale-out path documented: if concurrent sessions exceed ~50, split LiveKit + Coturn to a dedicated media VPS. LiveKit URL is a config variable — moving it is a one-line change. Alternative: migrate to LiveKit Cloud managed service.

### Token Endpoint Design
- **D-08:** Ephemeral rooms — each voice session creates a unique room (e.g., `session-{user_id}-{timestamp}`). Room auto-destroys when all participants disconnect. No persistent room state.
- **D-09:** LiveKit token TTL of 1 hour. Covers longest expected briefing + follow-up. LiveKit handles reconnection within the TTL window.

### Dev Environment Setup
- **D-10:** LiveKit server added as a Docker Compose service alongside Postgres + Redis. One `docker compose up` starts everything.
- **D-11:** TURN relay (Coturn) skipped in dev compose — not needed for localhost development. TURN only in production compose/deployment config.

### Claude's Discretion
- Room naming convention (exact format of `session-{user_id}-{timestamp}`)
- LiveKit server configuration defaults (port, log level, etc.)
- JWT signing algorithm and key management details
- Pairing code expiry time and length
- FastAPI middleware implementation pattern for JWT validation

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Voice architecture
- `.planning/research/voice-strategy-decision.md` — Why LiveKit was chosen over OpenAI Realtime and current voice stack limitations
- `.planning/research/voice-architecture-research.md` — Full analysis of alternative voice architectures and barge-in problem

### Requirements
- `.planning/REQUIREMENTS.md` §Backend Infrastructure — INFRA-01 (LiveKit + TURN connectivity), INFRA-02 (token endpoint)
- `.planning/ROADMAP.md` §Phase 18 — Success criteria (4 items)

### Project context
- `.planning/PROJECT.md` §Constraints — LLM must not access APIs, OAuth tokens encrypted at rest, backend mediates everything
- `.planning/PROJECT.md` §Key Decisions — Native over cross-platform, LiveKit for transport, mobile-first voice architecture

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/vault/crypto.py`: AES-256 encrypt/decrypt — reuse for storing refresh tokens
- `src/daily/config.py`: Pydantic Settings pattern — extend with `livekit_url`, `livekit_api_key`, `livekit_api_secret`
- `src/daily/db/engine.py`: Async SQLAlchemy session factory — inject into auth middleware
- `src/daily/main.py`: FastAPI lifespan hook — extend for LiveKit health check on startup

### Established Patterns
- All config via environment variables (Pydantic Settings + `.env`)
- SQLAlchemy 2.0 async ORM with Mapped type hints for all models
- Token encryption before DB write (vault pattern)
- Single FastAPI app with lifespan context manager

### Integration Points
- `src/daily/main.py` — Add APIRouter for `/livekit/token` and `/auth/*` endpoints
- `src/daily/db/models.py` — Add User auth fields (or new DeviceToken model) for pairing + refresh tokens
- `docker-compose.yml` — Add livekit-server service
- `pyproject.toml` — Add `livekit` dependency
- `alembic/versions/` — Migration for auth/device tables

</code_context>

<specifics>
## Specific Ideas

- Auth must be production-grade from day one — v1.4 targets public release / multi-tester deployment, not a personal prototype
- Pairing code flow inspired by smart speaker / IoT device setup — no email/password UI needed
- TURN relay is essential for production (corporate firewalls, mobile carrier NAT) but unnecessary for local dev

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-livekit-infrastructure*
*Context gathered: 2026-04-28*
