# Phase 7: Tech Debt Fixes — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-17
**Phase:** 07-tech-debt-fixes
**Mode:** discuss
**Areas analyzed:** Plan 07-04 scope, FIX-03 no-match fallback, FIX-02 safety cap

## Codebase Analysis Summary

Three broken paths identified via codebase exploration:

| Issue | File | Lines | Broken Code |
|-------|------|-------|-------------|
| FIX-01 | `scheduler.py` | 84, 118 | `user_email = ""` (never populated) |
| FIX-02 | `slack/adapter.py` | 58–68 | Single-page `conversations_history`, ignores `has_more` |
| FIX-03 | `orchestrator/nodes.py` | 235–238 | `message_id = last_content` stub |

FIX-01/02/03 core approaches were treated as decided (clear from codebase). Three gray areas presented for user input.

## Gray Areas Discussed

### Plan 07-04 Scope

**Question:** What should "backfill validation script + iCloud duplicate cleanup" deliver?

Options presented:
- Signal integrity check only (verify mis-scored WEIGHT_DIRECT signals)
- iCloud dedup + signal check (if real duplicate bug exists)
- Drop 07-04 entirely

**User decision:** Drop 07-04. No iCloud duplicate issue. Signal data is sparse (cold-start fallback means historical corruption has minimal impact).

**Reason:** The three core fixes are the complete scope. Backfill script adds overhead without clear value. Noted for backlog if signal quality concerns emerge.

---

### FIX-03 No-Match Fallback

**Question:** When `summarise_thread_node` can't resolve a `message_id` from `email_context`, what happens?

Options presented:
- Tell the user clearly (recommended)
- Fuzzy search the Gmail adapter
- Silent skip + log

**User decision:** Tell the user clearly. Message: *"I can't find that email — try asking during or right after your briefing when I have context loaded."*

---

### FIX-02 Pagination Cap

**Question:** Should Slack pagination have a hard max-page limit?

Options presented:
- Cap at 10 pages (recommended)
- No cap, paginate fully
- Cap at 5 pages

**User decision:** Cap at 10 pages (1,000 messages max per channel per run). Log warning if cap hit, continue with retrieved messages.

## No Corrections

Core approaches for FIX-01/02/03 were accepted as analyzed. Only gray areas above required user input.
