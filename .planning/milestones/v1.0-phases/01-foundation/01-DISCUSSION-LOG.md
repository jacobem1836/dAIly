# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-05
**Phase:** 01-foundation
**Mode:** discuss
**Areas discussed:** OAuth connection flow, Integration scope, Schema philosophy, Read adapter depth

## Gray Areas Presented

| Area | Options Presented |
|------|-------------------|
| OAuth connection flow | CLI + local redirect, Device Authorization Grant, Token injection via .env |
| Integration scope | All 4 now, Google stack first, Google + Slack first |
| Schema philosophy | Minimal core, Balanced (Phase 1 + Phase 2 metadata), Forward-looking skeleton |
| Read adapter depth | Typed models + pagination, Thin connectivity proof, Full production adapters |

## Decisions Made

### OAuth Connection Flow
- **Decision:** CLI + local redirect
- **Rationale:** Validates the same OAuth mechanism production will use. Redirect URL is the only thing that changes when moving to production. Not wasted work.
- **Confirmed by:** User accepted recommended option after PoC vs production framing discussion.

### Integration Scope
- **Decision:** All 4 integrations (Gmail, GCal, Outlook, Slack) in Phase 1
- **Implementation order:** Google → Slack → Microsoft Graph
- **Rationale:** Roadmap scope; Google covers 2 adapters in 1 OAuth flow. Microsoft Graph is most complex — last.
- **Confirmed by:** User accepted recommended option.

### Schema Philosophy
- **Decision:** Minimal — users + integration_tokens only. No raw_body column exists structurally.
- **Rationale:** PoC backend. Production schema will evolve. Nail the two critical constraints, nothing else.
- **Confirmed by:** User accepted recommended option.

### Read Adapter Depth
- **Decision:** Typed Pydantic models + pagination. No rate-limit or retry logic.
- **Rationale:** Clean contract for Phase 2 to consume. Rate limits are Phase 2's problem at pipeline scale.
- **Confirmed by:** User accepted recommended option.

## Clarification Exchange

User asked: "considering this is just the backend phase for proof of concept, which is the best approach considering daily-prompt.txt and the future production implementation"

Claude reframed recommendations in PoC vs production context:
- OAuth: local redirect validates the real flow, not a throwaway
- Schema: minimal is correct for PoC; production will diverge from any pre-stub
- Adapters: typed models is the PoC/production sweet spot

All 4 recommendations accepted together.

## Corrections Made

No corrections — all recommendations confirmed.
