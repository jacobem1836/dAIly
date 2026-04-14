# Phase 7: Tech Debt Fixes - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Correct three broken paths in the v1.0 codebase so signals captured from this point forward are accurate and complete. Scope: FIX-01 (direct recipient scoring), FIX-02 (Slack pagination), FIX-03 (thread summarisation message ID resolution). Not a refactor — surgical fixes only, plus regression tests and signal backfill.

</domain>

<decisions>
## Implementation Decisions

### FIX-01 — Direct recipient scoring
- **D-01:** Direct = exact match of `user_email` in the `To` field only. CC/BCC → `WEIGHT_CC` (2). VIP override continues to take precedence over both.
- **D-02:** The fix lives in `src/daily/briefing/ranker.py` — correct `_is_direct_recipient()` so a direct-to-user email scores `WEIGHT_DIRECT` (10).

### FIX-02 — Slack pagination
- **D-03:** Loop `conversations_history` per channel, following `next_cursor` until messages fall outside the briefing time window (last 24h). Stop paginating once `ts` of oldest message in page is older than the window.
- **D-04:** No hard page cap — the time window is the stopping condition. Edge case: if a channel returns zero in-window messages on first page, stop immediately.

### FIX-03 — Thread summarisation message ID
- **D-05:** Real message IDs are surfaced by the briefing pipeline into session state (ranked items already carry the ID internally — expose it in the cached briefing metadata).
- **D-06:** `summarise_thread_node` reads the message_id from session state (keyed by subject/sender or index) rather than using `last_content` as a stub. Update `src/daily/orchestrator/nodes.py:224` accordingly.

### Testing & backfill
- **D-07:** Each fix ships with a targeted unit test: ranker direct-vs-cc scoring (To/CC/BCC cases), Slack pagination loop termination on time window, thread ID resolution from session state.
- **D-08:** After fixes land, backfill existing `signal_log` entries by re-running the corrected ranker logic over stored email metadata. Reason: Phase 8 adaptive ranker must not train on signals scored with the buggy weight.

### File hygiene (roadmap-adjacent, user-approved in scope)
- **D-09:** Remove iCloud-duplicated files (` 2.py`, ` 3.py`, ` 4.py` suffixes, `*2.md`, etc.) from `src/` and `.planning/`. These are sync artifacts polluting the repo. Use git to remove; keep the canonical (unsuffixed) file only.

### Claude's Discretion
- Exact signature for surfacing message_id through session state (dict key choice)
- Whether to add a structured log line when pagination stops on time-window boundary
- Backfill migration: one-off script vs Alembic data migration

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bug locations
- `src/daily/briefing/ranker.py` §`_is_direct_recipient` and §`score_email` (lines ~85–95) — FIX-01
- `src/daily/integrations/slack/adapter.py` §`fetch_messages` (lines ~30–90) — FIX-02
- `src/daily/orchestrator/nodes.py` §`summarise_thread_node` (line ~220–230) — FIX-03

### Related models
- `src/daily/briefing/models.py` — EmailMetadata, MessagePage shape
- `src/daily/orchestrator/models.py` — AgentState / session state shape
- `src/daily/signals/` (if present) — signal_log schema for backfill

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — FIX-01, FIX-02, FIX-03 acceptance criteria
- `.planning/ROADMAP.md` §Phase 7 — goal and success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ranker.py` scoring pipeline is otherwise correct — VIP override, keyword weight, recency decay, thread activity all working. Only the direct/cc branch is broken.
- Slack adapter already handles `response_metadata.next_cursor` — fix is tightening the loop condition, not rewriting pagination.
- Session state (`AgentState`) already flows through the LangGraph orchestrator — adding a message_id map is additive, not structural.

### Established Patterns
- Async-first throughout (`asyncio.to_thread` for sync SDK calls)
- Pydantic models for all cross-module data shapes
- Unit tests live alongside modules (pytest + pytest-asyncio)

### Integration Points
- Ranker output → briefing cache (Redis) → narrator → voice output
- Signal log is written by orchestrator after briefing delivery — backfill script needs to read + rewrite this table
- Slack adapter is called from the briefing pipeline's ingestion stage

</code_context>

<specifics>
## Specific Ideas

- "Signals captured from this point forward are accurate" — the backfill is explicitly to give Phase 8's adaptive ranker clean training data.
- Duplicate ` 2.py` files are iCloud sync artifacts, not intentional branches. Safe to delete.

</specifics>

<deferred>
## Deferred Ideas

- Broader `.gitignore` / iCloud-sync hardening to prevent future duplicates — note for backlog.
- Structured pagination metrics (pages fetched per channel, latency) — observability concern, future phase.

</deferred>

---

*Phase: 07-tech-debt-fixes*
*Context gathered: 2026-04-15*
