# Phase 7: Tech Debt Fixes - Context

**Gathered:** 2026-04-28 (no discussion — scope fully defined by known bugs)
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix three documented bugs that degrade briefing quality and data completeness. No new features — strictly correctness fixes to existing pipeline code.

</domain>

<decisions>
## Implementation Decisions

### Bug A: user_email="" stub (WEIGHT_DIRECT broken)
- **D-01:** Extract user's email from their connected Google/Microsoft integration token after decryption, store in briefing context
- **D-02:** Fall back gracefully if no email integration is connected (skip WEIGHT_DIRECT rather than crash)
- **Evidence:** `src/daily/briefing/scheduler.py:84` hardcodes `user_email = ""`, passed at line 132. Ranker's `_is_direct_recipient()` at `src/daily/briefing/ranker.py:91-92` always fails

### Bug B: Slack single-page pagination
- **D-03:** Implement cursor-based pagination loop in Slack adapter — follow `next_cursor` until exhausted
- **D-04:** Also wire cursor support through `context_builder.py:114-118` which has a matching TODO for multi-page fetching
- **Evidence:** `src/daily/integrations/slack/adapter.py:54-88` fetches cursor but never follows it. `context_builder.py:114` explicitly documents single-page limitation

### Bug C: message_id = last_content stub
- **D-05:** Replace raw content passthrough with LLM-assisted extraction — parse user intent to identify which briefing item they're referring to, then look up the real message ID from briefing context
- **D-06:** Wire briefing item metadata (message IDs, subjects) through orchestrator state so thread-summarise node has proper references
- **Evidence:** `src/daily/orchestrator/nodes.py:227` sets `message_id = last_content` — brittle, expects user to type exact subject/ID

### Claude's Discretion
- Implementation order (though A is highest priority since it silently degrades every briefing)
- Whether to batch the context_builder pagination fix with Bug B or keep them as separate commits
- Error handling granularity for pagination edge cases

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Briefing pipeline
- `src/daily/briefing/scheduler.py` — Briefing precompute pipeline, user_email stub at line 84
- `src/daily/briefing/ranker.py` — Priority ranker, WEIGHT_DIRECT logic at line 91-92
- `src/daily/briefing/context_builder.py` — Data aggregation, pagination TODO at line 114

### Integrations
- `src/daily/integrations/slack/adapter.py` — Slack message fetching, cursor handling at lines 54-88
- `src/daily/integrations/google/adapter.py` — Google adapter (reference for how email address might be extracted)

### Orchestrator
- `src/daily/orchestrator/nodes.py` — Thread summarise node, message_id stub at line 227

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `IntegrationToken` model already stores provider-specific data — email address may be extractable from token metadata or a lightweight API call
- `MessagePage` dataclass already has `next_cursor` field — pagination plumbing exists, just not followed
- Ranker's `_is_direct_recipient()` is already implemented — just needs a real email to compare against

### Established Patterns
- Async adapter pattern: all integrations follow `list_messages() -> MessagePage` interface
- Context builder aggregates across adapters with `for adapter in adapters` loop
- Orchestrator state passed as LangGraph `State` dict — can add fields without breaking existing nodes

### Integration Points
- `scheduler.py` line 132 is the single injection point for user_email into briefing context
- `context_builder.py` is the single aggregation point for all message adapters
- `nodes.py` thread-summarise node is the only consumer of message_id

</code_context>

<specifics>
## Specific Ideas

No specific requirements — straightforward bug fixes with clear root causes.

</specifics>

<deferred>
## Deferred Ideas

- `user_id=1` hardcoded stub in `profile/service.py` — belongs to auth/multi-user phase
- Write scopes for Google/Microsoft/Slack — already scoped for Phase 4 action layer (done)
- Email adapter doesn't support cursor param in `list_messages()` — may surface when Google/Microsoft message volumes grow, but not blocking now

</deferred>

---

*Phase: 07-tech-debt-fixes*
*Context gathered: 2026-04-28*
