# Phase 2: Briefing Pipeline - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Precomputed briefing cron, async context builder, Redis cache, heuristic priority ranking, LLM narrative generation. The system produces a ranked, LLM-generated briefing narrative on a precomputed schedule every morning. No voice delivery (Phase 5), no conversational follow-ups (Phase 3), no actions (Phase 4) — briefing generation and caching only.

Requirements in scope: BRIEF-01, BRIEF-02, BRIEF-03, BRIEF-04, BRIEF-05, BRIEF-06, PERS-03, SEC-02, SEC-05

</domain>

<decisions>
## Implementation Decisions

### Content Retrieval (Adapter Extension)
- **D-01:** Phase 1 adapters are extended with content-fetch methods: `get_email_body(message_id: str) -> str` on `EmailAdapter`, and `get_message_text(message_id: str, channel_id: str) -> str` on `MessageAdapter`. Calendars have no body to fetch (event metadata is sufficient).
- **D-02:** Pipeline flow: list all metadata (24h) → rank all by heuristic → fetch bodies for top-N only (user-configured). Body fetch is never done for un-ranked items — API quota is preserved.

### Email Priority Ranking
- **D-03:** Sender weight uses both heuristics AND an optional user-defined VIP list:
  - Heuristic signals (cold-start defaults): direct-to-user vs CC/BCC, reply frequency in thread metadata, subject-line keywords (urgent, action required, FYI, deadline, by EOD, due today), sender domain match to known contacts
  - VIP override: `daily vip add <email>` CLI command adds sender to a per-user VIP list stored in PostgreSQL. VIP senders always score maximum sender weight regardless of heuristics.
- **D-04:** Full ranking formula per email: `score = sender_weight + keyword_weight + recency_weight + thread_activity_weight`. Weights are heuristic constants at cold-start (no learned history in Phase 2). Exact weight values are Claude's discretion.
- **D-05:** Email scope: list ALL emails from the last 24h (metadata only, no body). Rank all of them. Fetch bodies for the top-N highest-scoring emails, where N is user-configured (default: 5, settable via `daily config set briefing.email_top_n <N>`).

### Briefing Narrative Structure
- **D-06:** Output format: flowing narrative — continuous spoken-English paragraphs written to be read aloud over TTS. No bullet points, no numbered lists. Sections in order: (1) critical emails, (2) calendar, (3) Slack. Each section is one paragraph.
- **D-07:** Target length: concise — 90–120 seconds of spoken content (approximately 225–300 words at average TTS pace). Pipeline instructs LLM to stay within this target.
- **D-08:** The briefing always covers all three data sources (email, calendar, Slack) regardless of volume. If a source has nothing to report, one sentence: "Nothing notable in [source] today."

### Pre-Filter / Redaction Layer (SEC-02)
- **D-09:** Before any email or message body reaches the main LLM: (1) pass through a lightweight "summarise to key actionable facts" prompt (cheap model — model routing is Claude's discretion), then (2) regex-strip obvious credential patterns (tokens, passwords, API keys, URLs containing auth params). LLM for briefing generation receives the summary, not the raw body.
- **D-10:** The redaction step runs per-item, not per-briefing. Each email body is independently summarised and redacted before being assembled into the context passed to the briefing LLM.
- **D-11:** LLM outputs are structured intent JSON only (SEC-05). Briefing generation output is `{ "narrative": "..." }` — the backend renders/caches it. LLM never calls adapters or holds credentials.

### Precompute Schedule and Caching
- **D-12:** APScheduler version: pin 3.10.x (`AsyncIOScheduler`) — 4.x is pre-release and flagged as a stability risk in STATE.md. Upgrade is a later concern.
- **D-13:** Default precompute schedule: 05:00 local time, configurable via `daily config set briefing.schedule_time HH:MM`. Schedule persists across restarts (stored in DB or config file — Claude's discretion).
- **D-14:** Redis cache: store briefing as `{ "narrative": "...", "generated_at": ISO-8601, "version": int }` with TTL = 24h. Key: `briefing:{user_id}:{date}`. Audio is NOT cached in Phase 2 (TTS is Phase 5).
- **D-15:** Cache miss on user request (user requests briefing before 5am precompute): generate on-demand synchronously and cache immediately. Latency is acceptable because this is a rare edge case; do not return "not ready" errors.

### User Configuration
- **D-16:** Configurable items in Phase 2: briefing schedule time, email top-N count, VIP sender list. All stored persistently. CLI entry points: `daily config set`, `daily vip add/remove/list`.

### Claude's Discretion
- Model routing for the pre-summarisation step (GPT-4.1 mini recommended)
- Exact heuristic weight constants for ranking formula
- Internal module structure for the pipeline (context builder, ranker, redactor, narrator)
- How briefing schedule is persisted (DB row vs config file)
- Exact Redis key schema and serialisation format beyond the shape defined in D-14

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — BRIEF-01 through BRIEF-06 (briefing pipeline), PERS-03 (cold-start ranking heuristics), SEC-02 (redaction layer), SEC-05 (LLM outputs as intents only)
- `.planning/ROADMAP.md` §Phase 2 — Success criteria (6 items) and phase dependencies

### Product & Architecture
- `CLAUDE.md` §Technology Stack — Full recommended stack: APScheduler 3.10.x (pin, not 4.x), Redis 7.x, GPT-4.1 / GPT-4.1 mini routing, OpenAI Python SDK 1.x
- `CLAUDE.md` §Constraints — LLM never holds credentials, no raw body to LLM, precomputed briefing is architectural default
- `CLAUDE.md` §Stack Patterns — "Briefing Pipeline" variant: cron at 05:30, ingestion → LLM summarisation → TTS render → Redis TTL=24h

### Phase 1 — Adapter Contracts (upstream dependency)
- `src/daily/integrations/base.py` — EmailAdapter, CalendarAdapter, MessageAdapter abstract classes (Phase 2 extends these with get_email_body / get_message_text)
- `src/daily/integrations/models.py` — EmailMetadata, EmailPage, CalendarEvent, MessageMetadata, MessagePage (Phase 2 pipeline consumes these types)
- `src/daily/db/models.py` — users and integration_tokens tables (Phase 2 reads tokens to instantiate adapters)
- `src/daily/vault/crypto.py` — Token decryption (Phase 2 pipeline uses this to load adapter credentials)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/integrations/base.py` — EmailAdapter, CalendarAdapter, MessageAdapter abstract classes. Phase 2 extends these (add body-fetch methods) — does not replace them.
- `src/daily/integrations/models.py` — All Phase 1 Pydantic models are the pipeline's input types. No new ingestion models needed.
- `src/daily/vault/crypto.py` — AES-256 token decryption. Pipeline calls this to instantiate adapters with decrypted credentials.
- `src/daily/db/engine.py` — Async SQLAlchemy engine. Pipeline uses the same engine for reading tokens and writing schedule config.
- `src/daily/config.py` — Config loading. Extend for briefing-specific config (schedule time, top-N, etc.).

### Established Patterns
- Async-first throughout Phase 1. Phase 2 pipeline must be async (asyncio/FastAPI compatible).
- Pydantic models for all data boundaries — the ranker, redactor, and narrator should all accept/return typed models.
- No raw body fields in stored models (SEC-04) — context builder constructs an in-memory `BriefingContext` that holds summaries, never persisted.

### Integration Points
- Phase 2 reads from: `integration_tokens` table (via vault decryption) → instantiate adapters → list_emails/list_events/list_messages
- Phase 2 extends: all three adapter base classes with body-fetch methods
- Phase 2 writes to: Redis (briefing cache), potentially PostgreSQL (schedule config, VIP list)
- Phase 3 (Orchestrator) consumes the Redis-cached briefing narrative directly — no re-generation needed

</code_context>

<specifics>
## Specific Ideas

- VIP sender list via `daily vip add/remove/list` CLI — important for cold-start sender weight when heuristics alone can't infer importance (e.g. new contact who never emailed before)
- Adaptive briefing length is deferred — MVP targets concise (90–120s). A future phase can add volume-adaptive length targeting.
- Cache miss → generate on-demand: do not return "not ready" errors. User experience: briefing always available, may just take a few seconds on cache miss.

</specifics>

<deferred>
## Deferred Ideas

- **Adaptive briefing length** — Short when quiet, longer when inbox is heavy. Deferred to a future phase. Currently hardcoded to 90–120s target. (Noted as todo.)
- **Full PII detection (presidio)** — Enterprise-grade PII classifier. Overkill for M1. Revisit in M2 if compliance requirements emerge.
- **Audio caching** — Caching TTS audio bytes in Redis alongside narrative text. Belongs in Phase 5 (Voice Interface) where TTS is implemented.
- BRIEF-07 (thread summarisation on demand) — Phase 3 (Orchestrator) scope.

</deferred>

---

*Phase: 02-briefing-pipeline*
*Context gathered: 2026-04-05*
