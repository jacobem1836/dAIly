# Milestones

## v1.2 Deployability Layer (Shipped: 2026-04-20)

**Phases:** 13–16 | **Plans:** 9 | **Timeline:** 2026-04-18 → 2026-04-20 (3 days)
**Files changed:** 62 (+7,604 / -118 lines) | **Requirements:** 10/10

**Key accomplishments:**

1. Adaptive ranker learns from `skip`, `re_request`, and `expand` signals — full signal closure with tanh-centred decay scoring
2. `BriefingItem` model + Redis item cache enables per-item signal attribution wired through pipeline and session state
3. Voice loop tracks item cursor and auto-captures implicit skip signals on silence/barge-in detection
4. stdlib JSON logging (`JSONFormatter` + `ContextAdapter`) routes all 17+ existing logger call sites to structured JSON without modification
5. Multi-stage Dockerfile with Alembic auto-migrations and health-checked docker-compose stack (app + Postgres + Redis)
6. All v1.2 tech debt closed — `make_logger` adopted in all hot-path modules, VALIDATION.md files compliant

**Archive:** `.planning/milestones/v1.2-ROADMAP.md`, `.planning/milestones/v1.2-REQUIREMENTS.md`

---

## v1.1 Intelligence Layer (Shipped: 2026-04-18)

**Phases:** 7–12 | **Plans:** 14 | **Timeline:** 2026-04-16 → 2026-04-18

**Key accomplishments:**

1. Adaptive ranking replaces heuristics — pgvector-backed signal decay with tanh scoring; sender multipliers personalise briefing order over time
2. Cross-session memory persists context across days — mem0 + pgvector HNSW-indexed 1536-dim embeddings; profile extraction on session end
3. Voice-driven memory audit and control — `list_all_memories`, `delete_memory_fact`, `clear_all_memories` helpers + `memory_node` with query/delete/clear/disable sub-paths wired into orchestrator graph
4. CLI autonomy configuration with validation gates — `suggest-only`, `approve-per-action`, `trusted-auto` levels; `BLOCKED_ACTION_TYPES` enforced at code level
5. Briefing supports natural mid-session interruption — sentence-level cursor tracking, resume after barge-in, tone compression adaptation
6. Tech debt closed: RFC 2822 address normalisation (WEIGHT_DIRECT path), Slack cursor-based pagination, real message ID extraction in summarise_thread_node

---

## v1.0 MVP (Shipped: 2026-04-14)

**Phases:** 1–6 | **Plans:** 22 | **Timeline:** 2026-04-05 → 2026-04-14 (10 days)
**Codebase:** 7,049 Python LOC across 447 files

**Key accomplishments:**

1. Multi-source OAuth integrations — Gmail, Google Calendar, Outlook/Teams (Microsoft Graph), and Slack connected via AES-256-GCM encrypted token vault; proactive background token refresh
2. Precomputed morning briefing pipeline — heuristic email ranking, redaction/summarisation layer, LLM narration (GPT-4.1), APScheduler cron, Redis cache for sub-1s delivery
3. Conversational LangGraph orchestrator — dual-model routing, session-stateful follow-ups, thread summarisation on demand, SEC-05 intent-only LLM outputs
4. Approval-gated action layer — email/Slack/calendar drafting via LLM, human-in-the-loop approval gate, append-only action log with full audit trail
5. Full voice session loop — Cartesia Sonic-3 TTS streaming + Deepgram Nova-3 STT + asyncio barge-in detection + AsyncPostgresSaver session persistence
6. User preferences wired end-to-end — tone/length/category_order stored in profile, loaded by scheduler at briefing time, injected into narrator system prompt for every scheduled run

**Requirements satisfied:** 31/31 v1 requirements

**Tech debt carried to v1.1:**

- `user_email=""` in scheduler — WEIGHT_DIRECT scoring path never fires for scheduled runs
- Slack pagination is single-page only (multi-workspace TODO in place)
- `message_id = last_content` stub in summarise_thread_node (approximate, functional)
- `known_channels=set()` in SlackExecutor — channel whitelist validation deferred

**Archive:** `.planning/milestones/v1.0-ROADMAP.md`, `.planning/milestones/v1.0-REQUIREMENTS.md`

---
