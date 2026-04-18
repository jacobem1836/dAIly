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

## Milestone: v1.1 — Intelligence Layer

**Shipped:** 2026-04-18
**Phases:** 6 | **Plans:** 14 | **Timeline:** 13 days (2026-04-05 → 2026-04-18)

### What Was Built

1. Three tech debt fixes — RFC 2822 address normalization, Slack cursor pagination, message ID resolution from briefing metadata
2. Adaptive sender ranking — 14-day exponential decay scoring with sigmoid normalization (neutral=1.25), cold-start guard, graceful degradation
3. pgvector cross-session memory — LLM-driven fact extraction, cosine dedup (threshold=0.1), narrator injection, fire-and-forget session-end trigger
4. Memory transparency — voice-driven query/delete/clear/disable sub-paths via `memory_node`, keyword-first routing in orchestrator
5. Trusted actions — `BLOCKED_ACTION_TYPES` frozenset, per-action-type autonomy levels (suggest/approve/auto), CLI `profile.autonomy.*` config commands
6. Conversational flow — sentence-level briefing segmentation, cursor-tracked `resume_briefing` route, tone compression via keyword and implicit signal detection

### What Worked

- **Dependency-ordering again held** — Phase 7 (tech debt) before Phase 8 (adaptive ranker) meant the ranking bugs were fixed before the learning layer was added. Correct call.
- **pgvector in same Postgres instance** — no additional infra, HNSW cosine dedup worked cleanly at M1 scale. The "don't add a separate vector DB" constraint from CLAUDE.md was validated.
- **Sentence-level briefing segmentation** — the implementation was cleaner than expected. Splitting on `.` at delivery time gave cursor tracking for free. CONV-01 was the hardest success criterion and turned out to be the simplest to verify.
- **BLOCKED_ACTION_TYPES as a code-level constant** — making it a frozenset at import time (not a config value) was the right call. T-11-01 security constraint enforced without any runtime check.
- **Fire-and-forget memory extraction** — `asyncio.create_task` with a dedicated `async_session` inside the detached task solved the "don't block voice loop shutdown" requirement cleanly.

### What Was Inefficient

- **SUMMARY.md structured one-liners still inconsistent** — v1.1 SUMMARY.md files still didn't use the `one_liner:` structured field reliably. The milestone tooling extracted garbled output again. Same lesson as v1.0, not yet fixed in practice.
- **Phase 7 completion state missing from ROADMAP.md mid-milestone** — Phase 7 showed "Not started" in the progress table even though it was complete. This was a tooling issue (milestone complete ran before Phase 7's completion was reflected).
- **Phase 8 took 4 plans vs. expected 2** — the adaptive ranker required more wiring than anticipated (signal model → sender metadata capture → pipeline wire → session wiring were each non-trivial). Pre-phase planning underestimated integration depth.
- **Redundant `* 2.md` files in phase dirs** — artifact files (`08-01-PLAN 2.md`, `08-CONTEXT 2.md`, etc.) accumulated across all phase directories. These appear to be duplicate artifacts from worktree operations and add noise.

### Patterns Established

- **Cold-start guard is mandatory for any learned model** — ship the learning system with an explicit "< N samples → heuristic fallback" path from day one. Don't assume signal volume.
- **Transparency before trust** — Memory Transparency (Phase 10) before Trusted Actions (Phase 11) was the right order. User visibility into what the system knows should precede any increased autonomy.
- **Implicit signal detection as a tone path** — detecting time pressure from conversational patterns (not just keywords) is the right architecture for adaptive behaviour. Keeps the signal detection extensible.
- **Security constraints as code, not config** — high-impact action types that must never be auto-executed belong in a frozenset constant, not in a config file that a future code path might bypass.

### Key Lessons

- **Fix the SUMMARY.md one-liner format** — this is the third time manual extraction was needed. The solution is to add a SUMMARY.md template check to the execution hook, not to keep noting it.
- **Run `gsd-health` before milestone close** — caught the W009 VALIDATION.md gap for Phase 8 before archiving. This should be a standard pre-completion step.
- **Verify plan checkbox sync in ROADMAP.md at phase close** — the Phase 7 progress table discrepancy persisted because there was no automated sync between execution and the ROADMAP.md status column.
- **`skip` and `re_request` signals are still uncaptured** — the Phase 8 decision to defer adding new signal capture points means the adaptive ranker only learns from `expand` signals today. This limits ranking quality until a future phase adds capture for those signal types.

### Tech Debt Inventory

| Item | Severity | Phase | Fix in |
|------|----------|-------|--------|
| `known_channels=set()` in SlackExecutor — no channel whitelist | Low | 04 | v2.0 |
| `skip` and `re_request` signals uncaptured — ranker learns from `expand` only | Medium | 08 | v2.0 |
| Hallucination-loop guard is a binary flag — embedding dedup at injection is stronger | Low | 09 | v2.0 |
| `* 2.md` duplicate artifacts in phase directories (worktree artifacts) | Low | — | /gsd-cleanup |

---

## Cross-Milestone Trends

| Metric | v1.0 | v1.1 |
|--------|------|------|
| Phases | 6 | 6 |
| Plans | 22 | 14 |
| Days | 10 | 13 |
| LOC (Python) | 7,049 | ~9,000+ |
| Plans/day | 2.2 | 1.1 |
| Tests failed at UAT | 0 | 0 |
| Gaps found in audit | 1 | 0 (no audit run) |
| Tech debt items | 4 | 4 |
