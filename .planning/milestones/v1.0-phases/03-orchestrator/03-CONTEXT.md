# Phase 3: Orchestrator - Context

**Gathered:** 2026-04-07 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

LLM gateway with dual-model routing, LangGraph agent loop, in-session context, user profile, signal capture. Users can ask follow-up questions during the briefing and receive contextually-aware answers; the system knows their preferences. No voice interface (Phase 5), no action execution (Phase 4) — conversational intelligence and preference management only.

Requirements in scope: BRIEF-07, PERS-01, PERS-02

</domain>

<decisions>
## Implementation Decisions

### LLM Orchestration Framework
- **D-01:** Use LangGraph 1.0+ (pin `langgraph>=1.0.3`) as the orchestration backbone. Stateful graph execution with per-user session state managed via `thread_id` + `AsyncPostgresSaver` checkpointer (Postgres-backed, no additional infra).
- **D-02:** Dual-model routing via per-node model instantiation: GPT-4.1 for reasoning/briefing-related nodes, GPT-4.1 mini for quick follow-up responses. No separate router node needed in Phase 3 — model assignment is static per node type.
- **D-03:** LLM outputs are structured intent JSON only (SEC-05 enforcement). The orchestrator graph validates output schema at each node boundary. LLM never holds credentials or calls external APIs directly.

### User Profile & Preferences (PERS-01)
- **D-04:** Dedicated `user_profile` SQLAlchemy table with JSONB `preferences` column. Initial preference keys: `tone` (formal/casual/conversational), `briefing_length` (concise/standard/detailed), `category_order` (list of section names). JSONB allows schema evolution without migrations.
- **D-05:** Preferences set via CLI: `daily config set profile.tone casual`, `daily config set profile.briefing_length detailed`, etc. Preferences loaded at briefing generation time and injected as system instruction context to the narrator LLM.
- **D-06:** Skip mem0 for Phase 3. Preferences are explicitly set, not conversation-emergent. mem0 deferred to a future phase if interaction-driven preference extraction becomes valuable.

### Interaction Signal Capture (PERS-02)
- **D-07:** Append-only `signal_log` table: `(id, user_id, signal_type, target_id, metadata_json, created_at)`. Signal types are a Python enum: `skip`, `correction`, `re_request`, `follow_up`, `expand`. Target_id references the briefing item (email_id, event_id, etc.).
- **D-08:** Signals are captured during the orchestrator session as the user interacts with the briefing. They are stored for future ranking personalisation (Phase 2+ iteration) — not consumed by Phase 3 ranking logic.

### In-Session Context & Thread Summarisation (BRIEF-07)
- **D-09:** Session state is a Pydantic model managed by LangGraph's state graph, persisted via AsyncPostgresSaver checkpointer. Contains: current briefing (from Redis cache), Q&A history, expanded thread metadata, active section pointer.
- **D-10:** Thread summarisation (BRIEF-07) is on-demand: user asks "summarise that email chain" → orchestrator fetches full thread via `get_email_body()` adapter → passes through redactor (existing pattern) → summarised by GPT-4.1 mini → returned as intent JSON with narrative text.
- **D-11:** Orchestrator reads the Redis-cached briefing (`briefing:{user_id}:{date}`) on session start. It does NOT re-run the briefing pipeline. Session context wraps the cached `BriefingOutput` with session-specific state.

### Claude's Discretion
- Exact LangGraph graph topology (node names, edge routing logic)
- Internal module structure for orchestrator package
- Pydantic model field names for session state and signal log
- How preference injection is formatted in the narrator system prompt
- Checkpointer configuration details (connection pooling, TTL)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — BRIEF-07 (thread summarisation on demand), PERS-01 (user profile with preferences), PERS-02 (interaction signal capture)
- `.planning/ROADMAP.md` §Phase 3 — Success criteria (4 items) and phase dependencies

### Product & Architecture
- `CLAUDE.md` §Technology Stack — LangGraph 0.2+ (now 1.0+), OpenAI Python SDK 1.x, GPT-4.1 / GPT-4.1 mini routing, mem0 (deferred)
- `CLAUDE.md` §Constraints — LLM never holds credentials, orchestrator dispatches all actions, SEC-05 enforcement
- `CLAUDE.md` §Stack Patterns — "Conversational Follow-Up" variant: Deepgram STT → LangGraph agent → GPT-4.1 mini → response

### Phase 1 — Foundation (upstream)
- `src/daily/integrations/base.py` — EmailAdapter, CalendarAdapter, MessageAdapter abstract classes (orchestrator uses these for on-demand thread fetching)
- `src/daily/integrations/models.py` — EmailMetadata, CalendarEvent, MessageMetadata types (session context references these)
- `src/daily/db/models.py` — users and integration_tokens tables
- `src/daily/db/engine.py` — Async SQLAlchemy engine (reused for user_profile and signal_log tables)

### Phase 2 — Briefing Pipeline (upstream)
- `src/daily/briefing/models.py` — BriefingOutput, RankedEmail, CalendarContext, SlackContext (orchestrator consumes these from cache)
- `src/daily/briefing/cache.py` — Redis cache read/write, key schema `briefing:{user_id}:{date}`
- `src/daily/briefing/redactor.py` — Summarise-and-redact pattern (reused for on-demand thread summarisation)
- `src/daily/briefing/narrator.py` — LLM narrative generation (Phase 3 injects user preferences into narrator prompt)
- `src/daily/config.py` — BriefingConfig (extend for profile preferences)
- `src/daily/cli.py` — Typer CLI commands (extend for profile config)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/briefing/cache.py` — Redis cache read. Orchestrator reads cached briefing on session start.
- `src/daily/briefing/redactor.py` — `summarise_and_redact()` pattern. Reuse for on-demand thread summarisation in BRIEF-07.
- `src/daily/briefing/narrator.py` — LLM narrative generation. Phase 3 extends this to accept user preference context.
- `src/daily/briefing/models.py` — All briefing output types. Session context wraps these without modification.
- `src/daily/integrations/base.py` — `get_email_body()` adapter method added in Phase 2. Used for on-demand thread fetching.
- `src/daily/db/engine.py` — Async SQLAlchemy engine. Reused for new tables.
- `src/daily/cli.py` — Typer CLI framework. Extend with `daily config set profile.*` commands.

### Established Patterns
- Async-first throughout. LangGraph's `astream()`/`ainvoke()` integrate natively with FastAPI.
- Pydantic models at all data boundaries. Session state, signal log entries, and user profile are all typed models.
- LLM outputs as structured intent JSON (SEC-05). Established in Phase 2 narrator; Phase 3 enforces at graph level.
- Append-only logging. Phase 2 doesn't have an action log, but the pattern is established in the architecture for Phase 4. Signal log follows the same pattern.

### Integration Points
- Phase 3 reads from: Redis cache (briefing), PostgreSQL (user profile, integration tokens), adapters (on-demand thread fetch)
- Phase 3 writes to: PostgreSQL (user profile, signal log), LangGraph checkpointer (session state)
- Phase 4 (Action Layer) builds on: LangGraph graph (adds approval gate nodes), signal log (action signals), orchestrator session context
- Phase 5 (Voice Interface) connects to: orchestrator as the conversational backend (STT → orchestrator → TTS)

</code_context>

<specifics>
## Specific Ideas

- LangGraph checkpointer on Postgres means session state survives app restarts — important for long-running briefing sessions
- Thread summarisation reuses the exact same redactor pattern from Phase 2, just triggered on-demand instead of during pipeline precompute
- Signal capture should be lightweight — fire-and-forget writes, don't block the conversation flow
- User preferences applied to narrator prompt as system instruction preamble, not as user message content

</specifics>

<deferred>
## Deferred Ideas

- **mem0 for interaction-driven preferences** — Auto-extracting preferences from conversation (e.g. "I prefer shorter briefings") rather than explicit CLI config. Deferred until preference evolution from conversations becomes a validated need.
- **Pre-fetching thread bodies during pipeline** — Fetching top-N email thread bodies at briefing precompute time for instant thread summaries. Trades precompute latency for query-time speed. Evaluate if on-demand fetch latency becomes a problem.
- **Adaptive model routing** — Complexity-aware router node that dynamically selects GPT-4.1 vs mini per query. Not needed in Phase 3 where routing is static per node type.
- **Signal-based ranking personalisation** — Using captured signals to adjust heuristic weights in the ranker. This is the *consumer* of PERS-02 data, belonging to a future Phase 2 iteration or Phase 3+ enhancement.

</deferred>

---

*Phase: 03-orchestrator*
*Context gathered: 2026-04-07*
