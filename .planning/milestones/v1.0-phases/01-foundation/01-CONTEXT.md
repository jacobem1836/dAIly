# Phase 1: Foundation - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Encrypted OAuth token vault, read adapters for Gmail/GCal/Outlook/Slack, and PostgreSQL schema with correct data lifecycle. Users can connect their accounts and the system can securely read their data. No briefing pipeline, no LLM, no voice — data access layer only.

Requirements in scope: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05, SEC-01, SEC-03, SEC-04

</domain>

<decisions>
## Implementation Decisions

### OAuth Connection Flow
- **D-01:** CLI command pattern — `daily connect gmail`, `daily connect outlook`, etc. Command opens the user's browser and spins up a temporary FastAPI server on localhost to capture the OAuth callback. Same redirect flow production will use; redirect URL moves from `localhost:8080/callback` to the real app — not wasted work.
- **D-02:** Each provider gets its own connect command. Tokens are written to the encrypted vault immediately after the callback — never held in plaintext beyond the in-memory exchange.

### Integration Scope
- **D-03:** All 4 integrations in Phase 1: Gmail, Google Calendar, Microsoft Outlook (via Microsoft Graph), and Slack. These represent 3 distinct OAuth flows — Google (shared for Gmail + GCal), Slack, and Microsoft Graph.
- **D-04:** Implementation order within Phase 1: Google OAuth flow first (covers Gmail + GCal in one flow), then Slack, then Microsoft Graph (most complex). This is the natural risk-ordered sequence.

### Database Schema
- **D-05:** Minimal schema only. Two core tables: `users` and `integration_tokens` (encrypted). No pre-stubbing of columns or tables for future phases. Phase 2 adds its own migrations.
- **D-06:** "No raw body storage" constraint is structural — the schema has no `raw_body` column. There is no column to store it in. Only `summary` and metadata columns exist for email/message data. Enforcement is architectural, not conventional.

### Read Adapter Depth
- **D-07:** Adapters return typed Pydantic models with pagination support. No rate-limit handling, no retry logic, no exponential backoff — that is Phase 2's responsibility when the pipeline runs adapters at scale.
- **D-08:** The adapter interface is the contract Phase 2 consumes. Each adapter exposes: `list_emails(since: datetime, page_token: str | None) -> EmailPage`, `list_events(since: datetime, until: datetime) -> list[CalendarEvent]`, `list_messages(channels: list[str], since: datetime) -> MessagePage`. Exact model field names are Claude's discretion.

### Claude's Discretion
- Exact Pydantic model field names for email/event/message types
- Internal module structure within the integration package
- How token decryption is handled at adapter instantiation (inject vs. lazy load)
- CLI framework choice (Typer vs Click — Typer recommended given FastAPI ecosystem)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — INTG-01 through INTG-05 (OAuth flows, minimum scopes, token refresh) and SEC-01, SEC-03, SEC-04 (encryption, scope minimization, data lifecycle) — the authoritative acceptance criteria for this phase
- `.planning/ROADMAP.md` §Phase 1 — Success criteria (5 items) and phase dependencies

### Product & Architecture
- `CLAUDE.md` §Technology Stack — Full recommended stack with versions, compatibility notes, and "What NOT to Use" (especially: use `authlib`, not `python-jose`; use SQLAlchemy 2.0 async engine with `asyncpg`)
- `CLAUDE.md` §Constraints — Non-negotiable architectural constraints (LLM never holds credentials, AES-256 at rest, no raw body storage)
- `daily-prompt.txt` §Authentication & API Security — OAuth 2.0 flow description, token storage requirements, minimum scopes principle
- `daily-prompt.txt` §Technical Architecture — Integration layer design, separation of LLM from credentials

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield codebase. Phase 1 establishes all patterns.

### Established Patterns
- None yet. Phase 1 will establish: adapter interface pattern, token vault pattern, async SQLAlchemy usage. These become the baseline all subsequent phases inherit.

### Integration Points
- Phase 2 (Briefing Pipeline) consumes the read adapters directly. The typed Pydantic models returned by Phase 1 adapters are the data contract Phase 2 builds on.
- Phase 3 (Orchestrator) reads `users` and `integration_tokens` tables established here.
- The CLI connect commands are the only user-facing interface in M1 until Phase 5 voice layer.

</code_context>

<specifics>
## Specific Ideas

- This is a backend PoC, not a production system. Prioritise validating the pattern over polishing edge cases.
- The OAuth CLI + localhost redirect validates the exact same mechanism production will use — redirect URL is the only thing that changes. Don't shortcut with token injection.
- Implementation order within Phase 1: Google (Gmail + GCal) → Slack → Microsoft Graph. Google first because it covers two adapters in one OAuth flow and is the simplest to validate.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-05*
