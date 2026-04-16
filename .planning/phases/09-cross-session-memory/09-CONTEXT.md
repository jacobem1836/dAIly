# Phase 9: Cross-Session Memory — Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Persist durable user facts across days via LLM extraction and pgvector retrieval. Facts stated during voice sessions are extracted asynchronously at session end, embedded, and stored in a new `memory_facts` table. Each morning's briefing and each live session response injects the most relevant recalled facts into context. A user with `memory_enabled=False` has no facts extracted or injected.

**In scope:**
- New `memory_facts` table (text + VECTOR(1536) column) via Alembic migration
- Extraction task: fires at session end, async/non-blocking, extracts facts via LLM call
- Embedding: `text-embedding-3-small` (1536d) via OpenAI SDK, stored in pgvector column
- Deduplication: vector similarity check before insert (cosine distance < 0.1 threshold)
- `memory_enabled` boolean in `UserPreferences` — gating both extraction and injection
- Retrieval: cosine similarity query against `memory_facts` at briefing build time
- Injection into narrator system prompt (precomputed briefing) AND SessionState (live sessions)
- Unit tests for extraction, dedup, retrieval, and gating logic

**Out of scope:**
- Voice interface for inspecting/editing/deleting memories (Phase 10)
- Memory reset command (Phase 10)
- Per-topic/keyword memory (v2.0)
- langmem or mem0 library adoption

</domain>

<decisions>
## Implementation Decisions

### D-01 — Memory Library
Custom extraction pipeline, not mem0 or langmem. One OpenAI LLM call at session end extracts facts from conversation history. Embedding via `text-embedding-3-small` (1536d). Full schema control required for Phase 10 (MEM-01/02/03 need row-level access to delete and inspect individual facts).

### D-02 — Storage Schema
New `memory_facts` table:
- `id` (UUID, PK)
- `user_id` (FK → `users.id`)
- `fact_text` (TEXT — raw extracted statement)
- `embedding` (VECTOR(1536) — pgvector column)
- `source_session_id` (TEXT — session ID or timestamp at extraction, for dedup and Phase 10 provenance)
- `created_at` (TIMESTAMPTZ)

Add via new Alembic migration. Enable `pgvector` extension in the same migration if not already enabled.

### D-03 — Extraction Trigger
`asyncio.create_task()` in the `finally` block of `run_voice_session()` in `src/daily/voice/loop.py`. Fire-and-forget — does not block voice response path. Uses its own DB session opened inside the task (same pattern as `_capture_signal()` and `_log_action()` in `nodes.py`).

### D-04 — Hallucination Loop Prevention
Vector similarity dedup at insert time: before storing any extracted fact, query pgvector for existing facts with cosine distance < 0.1. Only insert if no near-duplicate found. This is more reliable than prompt exclusion lists and scales with growing fact volumes.

### D-05 — `memory_enabled` Flag
Boolean field with default `True` added to `UserPreferences` Pydantic model in `src/daily/profile/models.py`. Stored as JSONB in `UserProfile.preferences` — no schema migration needed. Checked in:
1. Extraction task — skip entirely if `False`
2. Briefing pipeline injection — skip retrieval and injection if `False`

### D-06 — Retrieval and Injection Points
Recalled memories injected at **two points**:
1. **Narrator system prompt** (`src/daily/briefing/narrator.py` → `build_narrator_system_prompt()`) — ensures precomputed morning briefing reflects memory. Pattern follows existing `PREFERENCE_PREAMBLE` injection.
2. **SessionState** (`src/daily/orchestrator/session.py` → `initialize_session_state()`) — ensures live session responses also have memory context via `respond_node`.

Retrieval: query `memory_facts` by cosine similarity (`<=>` operator) against a query embedding of the current date/briefing topic, top-K results (default K=10).

### D-07 — New Module
`src/daily/profile/memory.py` — exports:
- `extract_and_store_memories(user_id, session_history, session_id, db_session)` — async, called via create_task
- `retrieve_relevant_memories(user_id, query_text, db_session, top_k=10) -> list[str]` — used by briefing pipeline and session init

### Claude's Discretion
- Exact extraction prompt wording
- Number of facts extracted per session (suggested: cap at 10 per session)
- Index type for pgvector column (`hnsw` preferred for ANN search — lower latency than `ivfflat`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/PROJECT.md` §"Active (v1.1 targets)" — INTEL-02 requirement statement
- `.planning/ROADMAP.md` §"Phase 9: Cross-Session Memory" — success criteria and dependency chain

### Prior Phase Context
- `.planning/phases/08-adaptive-ranker/08-CONTEXT.md` — D-05: `db_session` pattern added to `run_briefing_pipeline()`, establishes how session is passed through pipeline

### Key Source Files
- `src/daily/voice/loop.py` — `run_voice_session()` finally block (extraction trigger point)
- `src/daily/orchestrator/session.py` — `initialize_session_state()` (SessionState injection point)
- `src/daily/briefing/narrator.py` — `build_narrator_system_prompt()` (narrator injection point)
- `src/daily/briefing/pipeline.py` — `run_briefing_pipeline()` (already accepts `db_session=None`)
- `src/daily/profile/models.py` — `UserPreferences` Pydantic model (add `memory_enabled`)
- `src/daily/db/models.py` — existing ORM models (pattern for new `MemoryFact` model)
- `src/daily/orchestrator/nodes.py` — `_capture_signal()` pattern for fire-and-forget tasks
- `src/daily/alembic/versions/` — existing migration chain to append to

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_capture_signal()` in `nodes.py` — direct template for the fire-and-forget extraction task pattern (asyncio.create_task + own DB session)
- `build_narrator_system_prompt()` in `narrator.py` — `PREFERENCE_PREAMBLE` injection shows exact pattern for adding memory context to narrator
- `initialize_session_state()` in `session.py` — returns the dict that becomes `SessionState`; add `user_memories: list[str]` field here
- `run_briefing_pipeline()` in `pipeline.py` — already accepts `db_session=None` (Phase 8 addition); no signature change needed

### Established Patterns
- All new intelligence features get a module in `src/daily/profile/` (Phase 8 established with `adaptive_ranker.py`)
- All async DB tasks open their own session inside the task (never share a session across tasks)
- All new profile-level preferences are JSONB fields on `UserPreferences`, not DB columns — no migration for flags
- Alembic migrations use sequential naming; the pgvector extension `CREATE EXTENSION IF NOT EXISTS vector` goes in the same migration as the new table

### Integration Points
- `run_voice_session()` finally block → `extract_and_store_memories()` via create_task
- `run_briefing_pipeline()` → `retrieve_relevant_memories()` → narrator injection
- `initialize_session_state()` → `retrieve_relevant_memories()` → SessionState
- `UserPreferences.memory_enabled` → gating in both paths above

</code_context>

<specifics>
## Specific Requirements

1. Extraction must never delay voice response — `asyncio.create_task` only, no `await`
2. `extract_and_store_memories()` must never raise — all errors caught and logged, task completes silently on failure
3. Dedup check must use `<=>` (cosine distance) operator on the pgvector column with threshold 0.1
4. `retrieve_relevant_memories()` returns plain `list[str]` (fact_text only) — no metadata exposed to LLM
5. `memory_enabled=False` must be a hard gate — no extraction and no injection, no opt-out bypass
6. pgvector `hnsw` index on `embedding` column for production query performance

</specifics>

<deferred>
## Deferred Ideas

- Voice interface for "what do you know about me?" — Phase 10 (MEM-01)
- Deleting specific facts by voice — Phase 10 (MEM-02)
- "Forget everything" reset — Phase 10 (MEM-03)
- Per-user configurable top-K retrieval count — v2.0
- Per-topic/keyword memory beyond user profile facts — v2.0
- Memory confidence scoring or source weighting — v2.0
- langmem or mem0 adoption — deferred; custom schema needed for Phase 10 row-level access
- Separate memory for CLI chat sessions vs voice sessions — v2.0 consideration

</deferred>

---

*Phase: 09-cross-session-memory*
*Context gathered: 2026-04-16*
