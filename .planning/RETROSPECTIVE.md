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

## Milestone: v1.2 — Deployability Layer

**Shipped:** 2026-04-20
**Phases:** 4 | **Plans:** 9 | **Timeline:** 3 days (2026-04-18 → 2026-04-20)
**Files changed:** 62 (+7,604 / -118 lines)

### What Was Built

1. Full signal closure — `skip_node` and `re_request_node` wired into orchestrator graph; voice loop item cursor tracks position and auto-fires implicit skip on silence/barge-in
2. `BriefingItem` model + Redis item cache — per-item sender attribution for signal capture; `SessionState.briefing_items` tracks current item index
3. stdlib JSON logging — `JSONFormatter` + `ContextAdapter` on root logger; all 17+ existing `getLogger` call sites emit structured JSON without modification
4. `/health` + `/metrics` endpoints — DB, Redis, APScheduler state checks inline; briefing latency, signal counts, memory size queryable without code changes
5. Multi-stage Dockerfile + docker-compose — `uv`-based build, Alembic auto-migrations in entrypoint, health-checked app + postgres + redis services
6. Tech debt closeout — `make_logger` adopted in `adaptive_ranker.py`, `nodes.py`, `voice/loop.py`; all VALIDATION.md files marked compliant

### What Worked

- **Phase 16 as explicit debt-close phase** — naming a milestone-closeout phase and planning it explicitly (not ad-hoc) worked well. The audit-driven phase had a clear scope and finished in 8 minutes.
- **`task fire-and-forget` for signal capture** — the same `asyncio.create_task` pattern from memory extraction applied cleanly to signal writes. Consistent pattern across the codebase.
- **stdlib over structlog** — using `logging.Formatter` subclass required zero new dependencies and intercepted all existing `getLogger` call sites transparently. The "no new deps" constraint paid off.
- **multi-stage Dockerfile with uv** — separating the uv binary (upstream image) from the Python runtime (slim) gave stable build caching. Layer order (deps before src) worked correctly.
- **Audit status `tech_debt` (not `gaps_found`)** — the v1.2 audit found no requirement gaps; only implementation polish items. This meant milestone close could proceed immediately after closeout phase.

### What Was Inefficient

- **SUMMARY.md one-liner tool extraction still broken** — gsd-tools couldn't parse the structured `one_liner:` field from YAML frontmatter in SUMMARY.md files for the third consecutive milestone. MILESTONES.md entries required manual writing every time.
- **Phase 13 plan checkboxes showed `[ ]` in ROADMAP.md mid-milestone** — Phases 14 and 15 had the same issue. The ROADMAP.md progress table drifted from actual state during execution.
- **Tech debt found by audit required a separate phase** — three modules still used bare `logging.getLogger` after Phase 14 was "complete." A linting rule or grep hook on commit would have caught this inline.

### Patterns Established

- **Close debt before archiving** — Phase 16 as a named milestone-closeout phase is a pattern worth keeping. It gives the debt a home instead of letting it slip into quick tasks.
- **stdlib-first for infrastructure concerns** — JSON logging, health checks, and metrics were all implemented with stdlib + FastAPI primitives. No new library dependencies added in v1.2.
- **`env_file` not `environment:` in compose** — using `env_file: .env` in docker-compose prevents config baking into the image and aligns with twelve-factor principles.

### Key Lessons

- **Add a grep-based lint for bare `logging.getLogger` after introducing `make_logger`** — three files slipped through. A `rg "logging.getLogger" src/` check in the phase verification step would catch this.
- **Phase UAT should verify signal attribution end-to-end** — Phase 13 was verified in isolation but the audit revealed the `ctx={}` issue in hot-path modules. Integration-level signal verification at UAT close would catch this.
- **Item cursor is the right primitive for voice UX** — tracking which briefing item the user is on (by sentence boundaries) turned out to be clean and enables a whole class of signal-aware behaviours. Worth keeping as a first-class concept.

### Tech Debt Inventory

| Item | Severity | Phase | Fix in |
|------|----------|-------|--------|
| `known_channels=set()` in SlackExecutor — no channel whitelist | Low | 04 | v2.0 |
| Hallucination-loop guard is a binary flag — embedding dedup at injection is stronger | Low | 09 | v2.0 |
| `* 2.md` duplicate artifacts in phase directories (worktree artifacts) | Low | — | /gsd-cleanup |
| SUMMARY.md one-liner tool extraction broken — manual milestone summary always needed | Medium | — | Fix gsd-tools |

---

## Cross-Milestone Trends

| Metric | v1.0 | v1.1 | v1.2 |
|--------|------|------|------|
| Phases | 6 | 6 | 4 |
| Plans | 22 | 14 | 9 |
| Days | 10 | 13 | 3 |
| LOC (Python) | 7,049 | ~9,000+ | ~9,500+ |
| Plans/day | 2.2 | 1.1 | 3.0 |
| Tests failed at UAT | 0 | 0 | 0 |
| Gaps found in audit | 1 | 0 | 0 |
| Tech debt items at close | 4 | 4 | 1 (carry-forward) |
| Quick tasks post-milestone | 2 | 0 | 1 |
