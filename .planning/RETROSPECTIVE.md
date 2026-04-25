# Retrospective

---

## Milestone: v1.0 — MVP

**Shipped:** 2026-04-14
**Phases:** 6 | **Plans:** 22 | **Timeline:** 10 days (2026-04-05 → 2026-04-14)

### What Was Built

1. Multi-source OAuth integrations — Gmail, Google Calendar, Outlook/Teams, Slack with AES-256-GCM encrypted token vault
2. Precomputed morning briefing pipeline — heuristic ranking → redaction → LLM narration → Redis cache (sub-1s delivery)
3. Conversational LangGraph orchestrator — dual-model routing, session context, thread summarisation, intent-only LLM outputs
4. Approval-gated action layer — LLM drafting + human-in-the-loop gate + append-only action audit log
5. Full voice session loop — Cartesia TTS + Deepgram STT + asyncio barge-in + PostgreSQL session persistence
6. User preferences wired end-to-end — profile → scheduler → pipeline → narrator system prompt

### What Worked

- **Dependency-ordered phasing** — building Foundation before Briefing Pipeline before Orchestrator eliminated integration surprises. Each phase stood on tested ground.
- **Precomputed briefing strategy** — caching the briefing in Redis before the user wakes was the right call architecturally. The voice loop is simple because it just reads from cache.
- **LangGraph for approval flow** — human-in-the-loop interrupts were the right abstraction for the approval gate. Would have been painful to implement with a custom state machine.
- **Phase 6 gap closure** — the audit-discovered PERS-01 wiring gap was small (2 files, ~10 lines) but would have silently made the whole preferences feature invisible. The audit caught it before shipping.

### What Was Inefficient

- **SUMMARY.md one-liner fields missing** — gsd-tools couldn't extract structured one-liners from any SUMMARY.md file. They were written in narrative format without the structured `one_liner:` field the tool looks for. Cost: manual accomplishment extraction at milestone close.
- **Phase 6 could have been caught at Phase 3** — the PERS-01 wiring gap (scheduler never loading preferences) was introduced in Phase 3 and not caught until the milestone audit. A cross-phase integration check at Phase 3 close would have caught it immediately.
- **ROADMAP.md plan checkboxes not updated** — Phase 1, 3, 4, 5, 6 plan checkboxes were never marked `[x]` in ROADMAP.md as plans completed. Phase 2 was the only one maintained. Adds noise to any progress reads mid-milestone.
- **Quick tasks as phase fixes** — two quick tasks (260411-vlh, 260412-gak) addressed bugs that should have been caught in their respective phase UATs. Suggests UAT coverage could be tighter for action layer flows.

### Patterns Established

- **Audit before shipping** — `/gsd-audit-milestone` before `/gsd-complete-milestone` is mandatory. Found a real gap that would have shipped broken.
- **Phase ordering follows dependency graph** — data access → pipeline → orchestrator → actions → voice → preferences. This order should be the template for v1.1.
- **LLM as intent-only** — the SEC-05 constraint (LLM never calls external APIs) held throughout and was cleanly enforced by the orchestrator dispatch pattern. Keep this in v1.1.
- **Voice latency target works with precompute** — the combination of Redis cache + sentence-by-sentence TTS streaming + Deepgram interim STT results achieved the <1.5s target without hardware-level optimisation.

### Key Lessons

- **Write SUMMARY.md one-liners in structured format** — add `one_liner: "[what was delivered in one sentence]"` at the top of every SUMMARY.md. The milestone tooling depends on it.
- **Run cross-phase integration check at phase close** — after each phase, verify that the new code is actually called by the phases that depend on it, not just that the code exists.
- **Mark plan checkboxes `[x]` in ROADMAP.md on execution** — gsd-execute should mark the plan as complete in ROADMAP.md, not just create SUMMARY.md.
- **APScheduler `user_email` gap** — the scheduler was built with a placeholder `user_email=""` that means direct-to-user emails are always misclassified. This needs a proper fix in v1.1 before multi-user or real-user testing.

### Tech Debt Inventory

| Item | Severity | Phase | Fix in |
|------|----------|-------|--------|
| `user_email=""` in scheduler — WEIGHT_DIRECT never fires | Medium | 02 | v1.1 |
| Slack pagination single-page — cursor TODO | Low | 02 | v1.1 |
| `message_id = last_content` stub in thread summarisation | Low | 03 | v1.1 |
| `known_channels=set()` in SlackExecutor — no channel whitelist | Low | 04 | v1.1 |

---

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 6 |
| Plans | 22 |
| Days | 10 |
| LOC (Python) | 7,049 |
| Plans/day | 2.2 |
| Tests failed at UAT | 0 |
| Gaps found in audit | 1 |
| Tech debt items | 4 |
