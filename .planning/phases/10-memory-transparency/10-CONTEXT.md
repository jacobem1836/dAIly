# Phase 10: Memory Transparency - Context

**Gathered:** 2026-04-18 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

User can inspect, delete, and disable the memory the system holds about them — entirely via voice. No UI required. Three operations: query ("what do you know about me?"), delete ("forget that" / "forget everything"), disable ("disable memory learning"). All operations are local (database only) — no external actions, no approval gate.

**In scope:**
- Voice-triggered memory introspection returning up to 10 stored facts as spoken summary
- Per-fact deletion via cosine similarity matching against spoken description
- Bulk clear ("forget everything") deleting all memory_facts for the user
- Disabling memory learning via memory_enabled preference flag
- New orchestrator node(s) for memory transparency commands
- New intent routing keywords in route_intent()

**Out of scope:**
- Web UI or dashboard for memory management (v2.0)
- Fine-grained memory categories or tags
- Memory export/download
- Re-enabling memory after disable (just set memory_enabled = True — same preference path)

</domain>

<decisions>
## Implementation Decisions

### D-01: Intent Routing
Add memory-specific keywords to the `route_intent()` whitelist in `src/daily/orchestrator/graph.py`. New keyword sets:
- **memory_query_keywords**: "what do you know", "what do you remember", "tell me what you know", "what have you learned"
- **memory_delete_keywords**: "forget that", "delete that", "remove that fact", "forget everything", "clear my memory", "reset my memory"
- **memory_disable_keywords**: "disable memory", "stop learning", "turn off memory", "don't remember"

Routes matched intents to a new `memory_node` (single node handling all three operations based on sub-intent).

### D-02: Memory Introspection
New `memory_node` sub-path for query intent: calls `list_all_memories(user_id, db_session, limit=10)` which queries `memory_facts` directly ordered by `created_at.desc()`, bypassing the `memory_enabled` gate in `retrieve_relevant_memories()`. This ensures transparency always works even when memory learning is disabled (per Research Pitfall 3 — `retrieve_relevant_memories()` hard-gates on `memory_enabled=False` and returns `[]`, which would hide existing facts from the user). Response formatted as spoken list — no LLM re-summarisation needed (avoids latency). Falls back to "I don't know anything about you yet" when no facts stored.

### D-03: Fact Deletion
"Forget that / delete that fact" path:
- Embed the user's spoken description using the same embedding model as extraction (OpenAI text-embedding-ada-002)
- Query `memory_facts` by cosine similarity — find closest match below threshold
- DELETE that specific row
- Confirm verbally: "Done, I've forgotten that."

Deletion threshold: use cosine_distance < 0.2 (slightly looser than the 0.1 dedup threshold, since users paraphrase when deleting).

### D-04: Bulk Clear
"Forget everything" path: `DELETE FROM memory_facts WHERE user_id = :user_id`. Confirm with count: "Done, I've cleared all 12 things I knew about you."

### D-05: Disable Memory Learning
"Disable memory" path: call `upsert_preference(user_id, "memory_enabled", "false", db_session)` — note: pass string `"false"` not Python bool `False`, consistent with `upsert_preference` signature (`value: str`) and existing test patterns (`test_memory.py` line 113). No migration needed — `memory_enabled` already exists in `UserPreferences` JSONB blob. Pydantic v2 `model_validate()` coerces `"false"` to `False` bool on read-back. Confirm verbally: "Memory learning disabled. I'll stop extracting new facts." Extraction and retrieval gates in `memory.py` already check this flag.

### D-06: No Approval Gate
Memory transparency commands are user-initiated and local-only. No `approval_node` interrupt. Direct DB operations execute immediately and confirm verbally.

### Claude's Discretion
- Exact wording of voice confirmations (keep concise, natural)
- Whether bulk clear prompts for confirmation ("Are you sure?") or executes immediately — lean toward immediate (user explicitly said "forget everything")
- Cosine threshold fine-tuning (start at 0.2, adjust if needed)
- Node naming (`memory_node` vs `memory_transparency_node`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Memory System (Phase 9)
- `src/daily/profile/memory.py` — Full memory module: extract_and_store_memories(), retrieve_relevant_memories(), _store_fact(), dedup logic, embedding calls
- `src/daily/db/models.py` — MemoryFact ORM model: Vector(1536) embedding, user_id FK, fact_text, source, created_at
- `alembic/versions/005_add_memory_facts.py` — migration 005 for memory_facts table + HNSW index

### Orchestrator (existing patterns)
- `src/daily/orchestrator/graph.py` — route_intent() function: how keywords route to nodes, graph edges
- `src/daily/orchestrator/nodes.py` — Node patterns: respond_node, summarise_thread_node, draft_node as implementation reference
- `src/daily/orchestrator/state.py` — SessionState: user_memories field, preferences field
- `src/daily/orchestrator/session.py` — initialize_session_state(): how session is set up, memory_enabled gate

### Preferences
- `src/daily/profile/models.py` — UserPreferences: memory_enabled field (line ~55), upsert_preference() pattern
- `src/daily/profile/signals.py` — SignalLog ORM (reference for DB pattern)

### Requirements
- `.planning/REQUIREMENTS.md` — MEM-01, MEM-02, MEM-03 definitions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `retrieve_relevant_memories(user_id, query_text, k, db_session)` — already returns `list[str]` facts; use with broad query for introspection
- `memory_enabled` gate in extraction and retrieval — already wired; disable path is just a preference update
- `upsert_preference()` pattern — used in tests; follow same pattern for memory_enabled toggle
- HNSW index on `memory_facts.embedding` — cosine similarity queries already performant

### Established Patterns
- **Node structure**: Each orchestrator node is an async function `async def node_name(state: SessionState, config: RunnableConfig) -> dict`. Returns dict of SessionState field updates.
- **Intent routing**: Keyword whitelist check in `route_intent()` → string return value → graph edge → node function
- **TTS response**: Nodes return narrative string; voice loop handles TTS. No node writes directly to audio.
- **DB session access**: Nodes receive `db_session` via `config["configurable"]["db_session"]` (established pattern from summarise_thread_node)

### Integration Points
- `graph.py:route_intent()` — add new keyword sets and return value ("memory")
- `graph.py` graph edges — wire "memory" return value to new `memory_node`
- `nodes.py` — add `memory_node` function
- `memory.py` — add `delete_memory_fact(user_id, query_text, db_session)` and `clear_all_memories(user_id, db_session)` functions
- `state.py` — may need no changes (user_memories already list[str])

</code_context>

<specifics>
## Specific Requirements

1. Response for "what do you know about me?" must be capped at 10 facts verbally — don't overwhelm the user
2. Deletion response must confirm verbally (don't silently succeed)
3. Bulk clear must state how many facts were removed
4. Memory disable confirmation should mention that past memories are preserved (just no new extraction)
5. All operations must be fail-silent (no crash if DB unavailable — say "I couldn't complete that right now")

</specifics>

<deferred>
## Deferred Ideas

- "Re-enable memory learning" as a voice command — same preference path, trivially addable later
- Confirmation prompt before bulk clear ("Are you sure?") — Claude's discretion; lean toward immediate
- Max facts per user policy / storage limit — defer to v2.0 when real usage data exists
- Memory fact summarisation via LLM prose (vs list read-back) — could be a Phase 12 conversational enhancement
- Web dashboard for memory management — v2.0 (DASH-01)

</deferred>

---

*Phase: 10-memory-transparency*
*Context gathered: 2026-04-18*
