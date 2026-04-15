# Architecture: v1.1 Intelligence Layer Integration

**Domain:** Voice-first AI personal assistant — intelligence layer additions to existing backend
**Researched:** 2026-04-15
**Overall confidence:** HIGH (based on direct codebase inspection)

---

## Existing Architecture — Baseline

```
[Voice/CLI] → [Orchestrator (LangGraph)] → [Context Builder] → [LLM] → [Action Engine] → [Integrations]
```

**Pipeline (briefing):**
```
APScheduler cron
  → _build_pipeline_kwargs (resolves adapters from DB)
    → build_context (fetch + rank_emails heuristic)
      → redact_emails / redact_messages
        → generate_narrative (GPT-4.1)
          → cache_briefing (Redis, 24h TTL)
```

**Orchestrator (session):**
```
LangGraph StateGraph (SessionState)
  START → route_intent → [respond_node | summarise_thread_node | draft_node]
  draft_node → approval_node (interrupt()) → route_after_approval → [execute_node | draft_node]
```

**Storage layout:**
```
PostgreSQL tables: users, integration_tokens, briefing_config, vip_senders, user_profile, signal_log
  user_profile.preferences — JSONB blob (UserPreferences Pydantic model)
  signal_log — append-only interaction signals (skip, correction, re_request, follow_up, expand)
pgvector extension: present in stack but no vector tables exist yet
Redis: briefing cache (key: briefing:{user_id}:{YYYY-MM-DD}, TTL 24h)
```

---

## Feature Integration Map

### INTEL-01: Adaptive Prioritisation

**What it does:** Replace `rank_emails()` heuristic with a learned scoring layer that uses
accumulated `signal_log` data to personalise email priority over time.

**New component:** `src/daily/briefing/adaptive_ranker.py`
- Queries `signal_log` for the user (recent re_request, expand, skip signals against target_id)
- Derives per-sender and per-keyword weight adjustments from signal history
- Wraps (does not replace) the existing `rank_emails()` heuristic: heuristic score + learned delta
- Returns same `list[RankedEmail]` interface so `context_builder.py` needs zero changes at the
  return boundary

**Modified component:** `src/daily/briefing/context_builder.py`
- Single change: replace `from daily.briefing.ranker import rank_emails` callsite with
  `adaptive_ranker.rank_emails_adaptive(emails, vip_senders, user_email, user_id, session, top_n)`
- `build_context()` must acquire a DB session to pass to the adaptive ranker
- `user_id` is already a parameter of `build_context()`, no signature change needed there

**DB schema:** No new tables needed. Reads from existing `signal_log`. Consider adding a
`learned_weights` table (JSONB per user) as a materialised cache of derived weights if cold-path
signal aggregation is too slow. Not required for MVP.

**Integration point in pipeline:** `build_context` call site in `pipeline.py` is unchanged.
The adaptive ranker is a drop-in at the `rank_emails` callsite inside `context_builder.py`.

---

### INTEL-02: Cross-Session Memory

**What it does:** Extract durable facts about the user from conversations, store as pgvector
embeddings, and inject the most relevant memories at briefing generation time.

**New component:** `src/daily/memory/extractor.py`
- Called at end of each voice session (fire-and-forget via `asyncio.create_task`)
- Reads last N conversation messages from `SessionState.messages`
- Calls GPT-4.1 mini with extraction prompt → list of fact strings
- Embeds each fact via OpenAI `text-embedding-3-small` → `list[float]` (1536 dims)
- Upserts into new `user_memories` table (see schema below)

**New component:** `src/daily/memory/retriever.py`
- Called during `_build_pipeline_kwargs` in `scheduler.py` before narrator
- Takes briefing context summary as query, embeds it, runs pgvector cosine search
- Returns top-K memory facts as a formatted string

**New DB table:** `user_memories`
```sql
id          SERIAL PRIMARY KEY
user_id     INTEGER REFERENCES users(id)
content     TEXT
embedding   VECTOR(1536)
source      VARCHAR(50)   -- 'conversation' | 'briefing_feedback'
created_at  TIMESTAMPTZ DEFAULT now()
updated_at  TIMESTAMPTZ DEFAULT now()
is_active   BOOLEAN DEFAULT true  -- soft-delete flag for MEM-02/MEM-03
```
Index: `CREATE INDEX ON user_memories USING ivfflat (embedding vector_cosine_ops)`

**Modified component:** `src/daily/briefing/narrator.py`
- `generate_narrative()` gains optional `memory_context: str | None = None` parameter
- When provided, appended to system prompt before NARRATOR_SYSTEM_PROMPT as "USER MEMORY:\n{memory}"
- Backward compatible: default `None` means existing behaviour unchanged

**Modified component:** `src/daily/briefing/scheduler.py`
- `_build_pipeline_kwargs()` calls `memory_retriever.retrieve(user_id, context_summary)`
- Passes `memory_context` into `run_briefing_pipeline` which forwards to `generate_narrative`
- `pipeline.py` function signature gains optional `memory_context: str | None = None`

**Integration point in pipeline:**
```
build_context() → [NEW: retrieve_memories(user_id, context)] → generate_narrative(context, memory_context=...)
```

---

### MEM-01 / MEM-02 / MEM-03: Memory Transparency API

**What it does:** REST endpoints for the user to inspect, edit, delete, and reset memory entries.

**New component:** `src/daily/memory/router.py` (FastAPI router)
```
GET    /memory           → list all active user_memories for user
PATCH  /memory/{id}      → update content field of a specific memory
DELETE /memory/{id}      → soft-delete (set is_active=False)
DELETE /memory           → reset all (bulk soft-delete per user)
POST   /memory/disable   → set memory_enabled=False on user preferences
```

**New component:** `src/daily/memory/models.py`
- SQLAlchemy ORM model for `user_memories` table (schema defined above under INTEL-02)
- Pydantic schemas for request/response: `MemoryEntry`, `MemoryUpdateRequest`

**Modified component:** `src/daily/main.py`
- Register the new router via `app.include_router(memory_router, prefix="/memory")`

**Modified component:** `src/daily/profile/models.py`
- `UserPreferences` gains `memory_enabled: bool = True` field
- Checked in `extractor.py` before any extraction runs — if `False`, skip entirely

**Dependency constraint:** The `user_memories` table (INTEL-02 schema) must exist before the
transparency API can query it. The Alembic migration must run before either INTEL-02 or
MEM-01/02/03 code is active.

---

### ACT-07: Trusted Actions

**What it does:** User-configurable autonomy level. Three levels:
- `suggest` — LLM drafts but presents as suggestion only; no interrupt, no execution
- `approve` — current behaviour: always interrupts for explicit user approval
- `auto` — for pre-approved action types, bypasses interrupt and executes directly

**Modified component:** `src/daily/profile/models.py`
- `UserPreferences` gains:
  - `autonomy_level: Literal["suggest", "approve", "auto"] = "approve"`
  - `trusted_action_types: list[str] = []` (scopes `auto` to specific action types)

**Modified component:** `src/daily/orchestrator/nodes.py`
- `draft_node()`: read `state.preferences.get("autonomy_level", "approve")`
  - If `"suggest"`: return draft content as narrative text only; do not set `pending_action`;
    graph reaches `END` via respond path — no interrupt fires
  - If `"auto"` AND `action_type.value` in `trusted_action_types`: call `execute_node`
    logic inline (build executor, validate, execute, log) without triggering interrupt
  - If `"approve"` (default): current behaviour unchanged, `pending_action` set, approval fires

**Modified component:** `src/daily/orchestrator/graph.py`
- No graph topology changes required. The suggest/auto logic is entirely inside `draft_node`.
  Keeping it inside the node avoids adding conditional edges and keeps the topology debuggable.

**Security constraint:** The `auto` path must only fire when:
1. `autonomy_level == "auto"` is stored in user preferences (explicit opt-in required)
2. The specific `action_type` appears in `trusted_action_types`
Both conditions must be true. Never fall through to auto-execute by default.

---

### CONV-01 / CONV-02 / CONV-03: Conversational Flow

**What it does:**
- CONV-01: Mid-session interruption without breaking conversation state
- CONV-02: Fluid switching between briefing, discussion, and action modes
- CONV-03: Adaptive tone adjustment from context signals

**Modified component:** `src/daily/orchestrator/state.py`
- `SessionState` gains `mode: Literal["briefing", "chat", "action"] = "chat"`
- Nodes return `{"mode": "..."}` in state update dicts to signal mode transitions

**Modified component:** `src/daily/orchestrator/graph.py`
- Extend `route_intent()` to check `state.mode` in addition to message content
- Add `briefing_keywords` check ("play briefing", "start briefing", "back to briefing") that
  returns `"deliver_briefing"` route
- Add `"deliver_briefing"` node to graph

**Modified component:** `src/daily/orchestrator/nodes.py`
- Add `deliver_briefing_node`: reads `state.briefing_narrative`, streams it to TTS,
  sets `mode = "briefing"` in state update
- `respond_node()`: detect topic shift and transition `mode` to `"chat"` if previously `"briefing"`

**Modified component:** `src/daily/briefing/narrator.py`
- `generate_narrative()` gains `tone_signals: dict | None = None` parameter
- Tone signals derived from recent `signal_log`: skip count → speed up / shorten;
  re_request count → slow down / expand; correction → adjust formality
- Injected as additional preamble line in system prompt

**Modified component:** `src/daily/voice/loop.py`
- CONV-01 (barge-in) is already implemented via `barge_in.py` + `stop_event`
- Verify `stop_event` is checked during briefing TTS streaming (not just follow-up responses)
- Ensure barge-in mid-briefing transitions cleanly to STT listen mode without orphaned tasks

---

## Summary: New vs Modified Components

### New Files

| File | Purpose | Required By |
|------|---------|-------------|
| `src/daily/memory/__init__.py` | Package init | INTEL-02, MEM-01/02/03 |
| `src/daily/memory/models.py` | ORM + Pydantic for `user_memories` | INTEL-02, MEM-01/02/03 |
| `src/daily/memory/extractor.py` | Post-session memory extraction | INTEL-02 |
| `src/daily/memory/retriever.py` | Semantic memory retrieval at briefing time | INTEL-02 |
| `src/daily/memory/router.py` | FastAPI REST endpoints for memory transparency | MEM-01/02/03 |
| `src/daily/briefing/adaptive_ranker.py` | Signal-informed email scoring | INTEL-01 |

### Modified Files

| File | Change | Required By |
|------|--------|-------------|
| `src/daily/briefing/context_builder.py` | Swap `rank_emails` for `rank_emails_adaptive` | INTEL-01 |
| `src/daily/briefing/narrator.py` | Add `memory_context` + `tone_signals` optional params | INTEL-02, CONV-03 |
| `src/daily/briefing/pipeline.py` | Thread `memory_context` through to narrator | INTEL-02 |
| `src/daily/briefing/scheduler.py` | Call memory retriever; fix `user_email=""` bug | INTEL-02, FIX-01 |
| `src/daily/profile/models.py` | Add `autonomy_level`, `trusted_action_types`, `memory_enabled` | ACT-07, MEM-03 |
| `src/daily/orchestrator/state.py` | Add `mode` field | CONV-02 |
| `src/daily/orchestrator/graph.py` | Extend `route_intent`, add `deliver_briefing` node | CONV-01/02 |
| `src/daily/orchestrator/nodes.py` | Autonomy check in `draft_node`; add `deliver_briefing_node` | ACT-07, CONV-01/02 |
| `src/daily/main.py` | Register memory router | MEM-01/02/03 |
| `src/daily/integrations/slack/adapter.py` | Cursor-based pagination | FIX-02 |

### New DB Migrations

| Migration | Content | Dependency |
|-----------|---------|------------|
| `add_user_memories` | Create `user_memories` table with `VECTOR(1536)` column + ivfflat index | Must run before any memory code executes |

---

## Recommended Build Order

### Phase 1 — Tech Debt Fixes (unblock later phases)

Build FIX-01, FIX-02, FIX-03 first. These are self-contained and fix broken paths that would
corrupt signal data used by INTEL-01 and INTEL-02.

- **FIX-01** (`scheduler.py`): Fix `user_email=""` — ensures WEIGHT_DIRECT path fires correctly
  for scheduled runs. Signals captured after this fix will be accurate for INTEL-01.
- **FIX-02** (`slack/adapter.py`): Cursor-based pagination — memory extraction and signal capture
  see complete Slack history.
- **FIX-03** (`nodes.py`): Real message_id extraction in `summarise_thread_node` — expand signals
  reference correct target_ids.

Rationale: INTEL-01 scoring depends on signal accuracy. Running it on corrupt signals produces
garbage weights. Fix signals first, then build the scorer.

### Phase 2 — Memory Schema + INTEL-01 (can run in parallel)

These two share no code dependency and can proceed concurrently after Phase 1.

- **Memory schema migration** (`add_user_memories`): Alembic migration only. No code logic.
  Must complete before Phases 3 and 4 touch the `user_memories` table.

- **INTEL-01** (`adaptive_ranker.py` + one-line change in `context_builder.py`):
  Pure logic layer reading existing `signal_log`. No new schema required.
  Start here — it's the simplest intelligence feature and validates the signal pipeline end-to-end.

### Phase 3 — Cross-Session Memory (INTEL-02)

Depends on the `user_memories` table from Phase 2.

Build `extractor.py` → `retriever.py` → wire into `scheduler.py` and voice loop.
This is the highest-complexity phase: embedding pipeline, pgvector queries, prompt injection.

- `memory/extractor.py`: post-session extraction, embedding call, DB write
- `memory/retriever.py`: cosine similarity query, top-K fetch, format as string
- Modify `scheduler.py`: call retriever, pass `memory_context` to pipeline
- Modify `pipeline.py`: accept and forward `memory_context` param
- Modify `narrator.py`: inject `memory_context` into system prompt (backward compatible default=None)
- Modify `voice/loop.py`: trigger extraction via `asyncio.create_task` at session end

### Phase 4 — Memory Transparency API (MEM-01/02/03)

Depends on Phase 3 having populated `user_memories` with real data to inspect and edit.
Straightforward FastAPI CRUD over existing table.

- `memory/models.py` (Pydantic schemas — ORM model defined with migration in Phase 2)
- `memory/router.py` (CRUD endpoints)
- Add `memory_enabled` to `UserPreferences` and check it in `extractor.py`
- Register router in `main.py`

### Phase 5 — Trusted Actions (ACT-07)

No dependency on the memory phases. Can be sequenced after Phase 1 if separate capacity exists.

- Add `autonomy_level` + `trusted_action_types` to `UserPreferences`
- Modify `draft_node` to check preference before triggering interrupt
- Add CLI config commands for new preference fields
- Security test: verify `auto` path cannot fire without explicit user opt-in to both
  `autonomy_level="auto"` AND populating `trusted_action_types`

### Phase 6 — Conversational Flow (CONV-01/02/03)

Depends on ACT-07 (the `mode` concept interacts with action approval routing). Tone signals
(CONV-03) are richer with memory data from Phase 3 but can be implemented with `signal_log`
data alone — Phase 3 is a soft dependency.

- Add `mode` to `SessionState`
- Extend `route_intent` and add `deliver_briefing_node` in `graph.py`
- Verify barge-in during briefing TTS streaming in `voice/loop.py`
- Add `tone_signals` injection to `narrator.py`

---

## Data Flow Changes: v1.0 → v1.1

**Current (v1.0):**
```
signal_log ← append-only writes; never read by pipeline
user_profile.preferences → narrator prompt preamble only
rank_emails() → pure heuristic; no DB access
```

**After v1.1:**
```
signal_log ← writes (unchanged)
           → adaptive_ranker reads recent signals per user (INTEL-01)
           → narrator tone_signals aggregation (CONV-03)
           → memory extractor trigger (INTEL-02)

user_memories ← extractor writes after each session end
              → retriever reads at briefing time (cosine search)
              → narrator memory_context injection
              → REST API read/write (transparency endpoints)

user_profile.preferences → autonomy_level → draft_node bypass logic (ACT-07)
                         → memory_enabled → extractor gate (MEM-03)
                         → tone/length/order → narrator preamble (unchanged)
```

---

## Integration Points with Existing Pipeline

| Existing hook | v1.1 integration | Notes |
|---------------|-----------------|-------|
| `context_builder.build_context()` → `rank_emails()` | adaptive_ranker replaces callsite | Same `list[RankedEmail]` return type; zero change to caller |
| `narrator.generate_narrative()` in `pipeline.py` | Add `memory_context=`, `tone_signals=` kwargs | Both default to `None`; fully backward compatible |
| `_build_pipeline_kwargs()` in `scheduler.py` | Add async memory retrieval call | Adds ~100-200ms before LLM call; acceptable at precompute time |
| `SessionState` fields | Add `mode` field | LangGraph state merge is additive; existing checkpoints unaffected |
| `draft_node()` | Autonomy level short-circuit before interrupt | Approval gate path unchanged for `"approve"` (default) |
| `voice/loop.py` session cleanup | Trigger `extractor.py` via `asyncio.create_task` | Same fire-and-forget pattern as `append_signal`; never blocks voice path |
| `main.py` FastAPI app | Register `memory_router` | No conflict with existing routes |

---

## Architectural Constraints to Preserve

1. **SEC-05 (LLM = intent only):** Memory retriever returns a pre-formatted string injected into
   the prompt. It does not give the LLM direct DB access. The backend fetches memory before the LLM call.

2. **SEC-04 (no raw bodies in DB):** Memory extraction operates on `SessionState.messages`, which
   only contains redacted/summarised content. The raw body path in `summarise_thread_node` already
   clears `raw_body` before any state write. No new raw body storage introduced.

3. **T-04-02 (approval gate not bypassable):** The `auto` autonomy path only fires when
   `autonomy_level == "auto"` AND the specific `action_type` is in `trusted_action_types`.
   Both must be explicitly configured. Default level is `"approve"`. Graph topology's
   `draft → approval` edge remains the default path.

4. **D-01 (briefing always delivers):** Memory retrieval failure must be caught and treated as
   `memory_context=None`. Pipeline continues without memory context rather than aborting.
   Same resilience contract as the existing per-source try/except isolation in `build_context`.

5. **D-08 (fire-and-forget for non-critical writes):** Memory extraction follows the
   `asyncio.create_task()` pattern from `append_signal`. Never blocks the voice response path.

---

## Sources

- Direct inspection of codebase at `/Users/jacobmarriott/Documents/Personal/projects/dAIly/src/daily/`
- PROJECT.md requirements: v1.1 targets INTEL-01/02, MEM-01/02/03, ACT-07, CONV-01/02/03, FIX-01/02/03
- LangGraph interrupt() pattern: existing `approval_node` as implementation reference
- pgvector: already in stack per `CLAUDE.md`; `user_profile` JSONB pattern as schema evolution precedent
- mem0 library considered but not recommended: existing pgvector + SQLAlchemy 2.0 stack handles
  M1 memory scale adequately; mem0 adds opaque extraction layer over a system where prompt control
  is required by SEC-05 constraints
