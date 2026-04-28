# Phase 18: LiveKit Infrastructure + Token Endpoint - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-28
**Phase:** 18-livekit-infrastructure
**Areas discussed:** Auth & session strategy, Deployment topology, Token endpoint design, Dev environment setup

---

## Auth & Session Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| API key in header | Shared secret in Authorization header — simple but no per-device control | |
| Device pairing + JWT | 6-digit code pairs device once, then JWT refresh flow handles sessions | ✓ |
| Email/password + JWT | Traditional login flow — more UI work for a voice-first product | |
| mTLS / client certificate | Device-level TLS cert auth — overkill for this use case | |

**User's choice:** Device pairing + JWT
**Notes:** User asked for deep explanation of all options and how they work on mobile. Confirmed that the goal is production-ready for public release / multiple testers — not a single-user prototype. API key rejected because it doesn't scale past single-user. mTLS rejected as overkill. Email/password rejected as unnecessary friction. Pairing code is the IoT/smart speaker pattern — production-grade without password UI.

---

## Deployment Topology

| Option | Description | Selected |
|--------|-------------|----------|
| Same VPS as backend | Self-hosted alongside FastAPI/Postgres/Redis. Fine for <50 concurrent | ✓ |
| LiveKit Cloud (hosted) | Managed cloud service. Zero infra management, vendor dependency | |
| Separate VPS for media | Dedicated machine. Better isolation, doubles infra cost | |

**User's choice:** Same VPS (self-hosted)
**Notes:** User asked for clarification on "<50 concurrent users" — explained that 50 concurrent covers ~600 users/hour for 5-minute briefings. User confirmed self-hosted with a note to document the scale-out path (split to dedicated VPS or migrate to LiveKit Cloud).

---

## Token Endpoint Design — Rooms

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral per-session | Unique room per session, auto-destroys on disconnect | ✓ |
| Persistent per-user | Fixed room per user, needs cleanup logic | |
| Single shared room | All sessions in one room — doesn't scale | |

**User's choice:** Ephemeral per-session
**Notes:** User asked for explanation of all options. Explained that ephemeral is the standard pattern for 1:1 voice AI (Vapi, PlayAI, etc.) and avoids zombie room cleanup.

## Token Endpoint Design — TTL

| Option | Description | Selected |
|--------|-------------|----------|
| 1 hour | Covers longest expected briefing + follow-up | ✓ |
| 15 minutes | More secure but requires refresh logic | |
| 24 hours | Very permissive, larger leak window | |

**User's choice:** 1 hour

---

## Dev Environment Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Docker Compose service | Add livekit-server to compose. One command starts everything | ✓ |
| LiveKit CLI binary | Install binary on macOS. Breaks single-compose workflow | |
| LiveKit Cloud dev project | Hosted cloud for dev. Requires internet for all testing | |

**User's choice:** Docker Compose service

## Dev Environment — TURN

| Option | Description | Selected |
|--------|-------------|----------|
| Skip for dev | TURN only needed for firewall traversal — localhost doesn't need it | ✓ |
| Include Coturn in compose | Full parity with production | |

**User's choice:** Skip for dev
**Notes:** User asked for explanation of TURN relay — explained STUN vs TURN, when direct connections fail (~20% of users behind corporate firewalls/symmetric NAT), and why TURN on TCP 443 solves it.

---

## Claude's Discretion

- Room naming convention
- LiveKit server config defaults
- JWT signing details
- Pairing code expiry and length
- FastAPI middleware pattern for JWT validation

## Deferred Ideas

None
