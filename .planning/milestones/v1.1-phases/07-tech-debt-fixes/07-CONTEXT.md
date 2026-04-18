# Phase 7: Tech Debt Fixes — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Three broken paths are corrected so signals captured from this point forward are accurate and complete. No new features — only surgical fixes to existing, broken behaviour.

**In scope:**
- FIX-01: Normalize RFC 2822 recipient addresses in ranker so WEIGHT_DIRECT fires correctly for direct-to-user emails
- FIX-02: Paginate Slack `conversations_history` to retrieve all messages within the time window (not just page 1)
- FIX-03: Resolve `message_id` from `email_context` in `summarise_thread_node` instead of using `last_content` as a stub

**Out of scope (explicitly dropped):**
- Backfill validation script — no iCloud duplicate issue exists; signal data is sparse enough that historical corruption is not worth backfilling
- Any new features or integrations

**Phase is 3 plans, not 4.** Plan 07-04 (backfill + iCloud cleanup) has been dropped.

</domain>

<decisions>
## Implementation Decisions

### FIX-01: RFC 2822 Recipient Normalization

- **D-01:** Source of `user_email` — read from `user_profile` DB record (established pattern, used by Phase 8). Do not read from OAuth token or env var.
- **D-02:** Normalize both sides before comparison — extract bare email address from RFC 2822 format (e.g., `"Name <email@host>"` → `"email@host"`) in `_is_direct_recipient()` before matching against `user_email`.
- **D-03:** The fix lives in two places: `scheduler.py` (populate `user_email` from DB) and `ranker.py` (normalize both sides in `_is_direct_recipient()`).

### FIX-02: Slack Pagination

- **D-04:** Paginate with a **hard cap of 10 pages** (10 × 100 = 1,000 messages max per channel per run).
- **D-05:** If cap is hit, log a warning but continue with the messages already retrieved — do not fail the run.
- **D-06:** Pagination loop uses `response_metadata.next_cursor` / `has_more` from each Slack response as the cursor for the next call.

### FIX-03: Thread Summarisation — message_id Resolution

- **D-07:** Resolve `message_id` from `state.email_context` by matching user's request against available email metadata (subject, sender, snippet).
- **D-08:** If no match is found in `email_context` (empty or no matching email), respond to the user with a clear message: *"I can't find that email — try asking during or right after your briefing when I have context loaded."* No silent failure, no fuzzy search.
- **D-09:** The `last_content` stub (lines 235–238 of `nodes.py`) is replaced entirely. No fallback to using `last_content` as an ID.

### Claude's Discretion

- Exact matching strategy for FIX-03 (subject substring, sender prefix, etc.) — keep it simple
- RFC 2822 parsing implementation in FIX-01 (use stdlib `email.utils.parseaddr`)
- Unit test structure and fixture design for all three fixes

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### FIX-01 — Recipient normalization
- `src/daily/briefing/ranker.py` — contains `_is_direct_recipient()`, `WEIGHT_DIRECT`, `WEIGHT_CC`, `rank_emails()`
- `src/daily/briefing/scheduler.py` — lines 84, 118: `user_email = ""` stub that must be populated from DB

### FIX-02 — Slack pagination
- `src/daily/integrations/slack/adapter.py` — lines 58–68: single-page `conversations_history` call that needs pagination loop

### FIX-03 — Thread summarisation
- `src/daily/orchestrator/nodes.py` — lines 235–238: `message_id = last_content` stub in `summarise_thread_node()`
- `src/daily/orchestrator/state.py` — `SessionState` definition; verify `email_context` field is present and populated

### Phase 7 success criteria
- `.planning/ROADMAP.md` §Phase 7 — three success criteria define the acceptance bar for each fix

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `email.utils.parseaddr` (stdlib) — use for RFC 2822 parsing in FIX-01; already available, no new dependency
- `state.email_context` — populated during briefing session; available in `summarise_thread_node` for FIX-03

### Established Patterns
- `user_profile` DB record is the canonical source for user-specific settings (confirmed by Phase 8 usage)
- Graceful degradation pattern established in Phase 8: log warning, continue without feature — apply same pattern if Slack pagination cap is hit
- `nodes.py` uses `state.messages[-1].content` for user intent; `state.email_context` for email metadata — these are separate concerns, do not conflate

### Integration Points
- **FIX-01:** `scheduler.py` → DB session → `user_profile.email` → passed to `rank_emails()` in `ranker.py`
- **FIX-02:** `slack/adapter.py::list_messages()` — pagination is self-contained inside this method; callers don't need changes
- **FIX-03:** `summarise_thread_node()` in `nodes.py` — reads `state.email_context`, calls `adapters[0].get_email_body(message_id)`

</code_context>

<specifics>
## Specific Ideas

- FIX-03 user-facing error message: *"I can't find that email — try asking during or right after your briefing when I have context loaded."* — direct, explains why and what to do.
- Slack cap warning should name the channel: `"Slack pagination cap (10 pages) hit for channel {channel_id} — {N} messages fetched"`

</specifics>

<deferred>
## Deferred Ideas

- Plan 07-04 (backfill validation script + iCloud duplicate cleanup) — explicitly dropped. No iCloud duplicate issue; signal data cold-start fallback makes historical backfill unnecessary. Can revisit if signal quality concerns emerge in v1.2.
- Fuzzy search fallback for FIX-03 — could be added in Phase 12 (Conversational Flow) if out-of-briefing thread summarisation becomes a product requirement.

</deferred>

---

*Phase: 07-tech-debt-fixes*
*Context gathered: 2026-04-17*
