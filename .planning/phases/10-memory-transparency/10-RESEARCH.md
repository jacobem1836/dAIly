# Phase 10: Memory Transparency - Research

**Researched:** 2026-04-18
**Domain:** LangGraph orchestrator extension + pgvector memory operations
**Confidence:** HIGH

## Summary

Phase 10 adds three voice-triggered operations on top of the Phase 9 memory system: query, delete, and disable. All operations are local database changes with no external API calls and no approval gate. The implementation is a single new orchestrator node (`memory_node`) with three sub-paths, wired into `route_intent()` via new keyword sets, plus two new helper functions in `memory.py`.

The codebase is extremely well-prepared for this phase. Every building block already exists: `retrieve_relevant_memories()` for the query path, `MemoryFact` ORM with cosine-distance support for deletion, `upsert_preference()` for the disable path, and established node/routing patterns in `graph.py` / `nodes.py`. The only net-new code is the node function, two memory module helpers, keyword routing additions, and matching tests.

**Primary recommendation:** Implement in two plans — Plan 01: `memory.py` helpers + `memory_node` + routing wiring (no external dependencies); Plan 02: tests covering all four MEM requirements plus error paths.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Intent Routing**
Add memory-specific keywords to `route_intent()` in `src/daily/orchestrator/graph.py`:
- **memory_query_keywords**: "what do you know", "what do you remember", "tell me what you know", "what have you learned"
- **memory_delete_keywords**: "forget that", "delete that", "remove that fact", "forget everything", "clear my memory", "reset my memory"
- **memory_disable_keywords**: "disable memory", "stop learning", "turn off memory", "don't remember"

Routes matched intents to a new `memory_node` (single node handling all three operations based on sub-intent).

**D-02: Memory Introspection**
New `memory_node` sub-path for query intent: calls `retrieve_relevant_memories()` with a broad synthetic query ("user profile personal facts preferences"), returns top-10 facts. Response formatted as spoken list — no LLM re-summarisation. Falls back to "I don't know anything about you yet" when no facts stored.

**D-03: Fact Deletion**
"Forget that / delete that fact" path:
- Embed the user's spoken description using text-embedding-3-small (same as extraction)
- Query `memory_facts` by cosine similarity — find closest match below threshold
- DELETE that specific row
- Confirm verbally: "Done, I've forgotten that."
- Deletion threshold: cosine_distance < 0.2 (looser than 0.1 dedup threshold)

**D-04: Bulk Clear**
"Forget everything" path: `DELETE FROM memory_facts WHERE user_id = :user_id`. Confirm with count: "Done, I've cleared all 12 things I knew about you."

**D-05: Disable Memory Learning**
"Disable memory" path: call `upsert_preference(user_id, "memory_enabled", False, db_session)`. No migration needed. Confirm verbally: "Memory learning disabled. I'll stop extracting new facts." Extraction and retrieval gates already check this flag.

**D-06: No Approval Gate**
Memory transparency commands are user-initiated and local-only. No `approval_node` interrupt. Direct DB operations execute immediately and confirm verbally.

### Claude's Discretion
- Exact wording of voice confirmations (keep concise, natural)
- Whether bulk clear prompts for confirmation ("Are you sure?") or executes immediately — lean toward immediate
- Cosine threshold fine-tuning (start at 0.2, adjust if needed)
- Node naming (`memory_node` vs `memory_transparency_node`)

### Deferred Ideas (OUT OF SCOPE)
- "Re-enable memory learning" as a voice command
- Confirmation prompt before bulk clear
- Max facts per user policy / storage limit
- Memory fact summarisation via LLM prose
- Web dashboard for memory management (DASH-01)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | "What do you know about me?" returns verbal summary of up to 10 stored facts | `retrieve_relevant_memories()` already returns `list[str]` top-K facts; format as numbered spoken list in `memory_node` |
| MEM-02 | User can delete a specific stored fact by stating it; subsequent briefings no longer reflect that fact | New `delete_memory_fact()` in `memory.py` using cosine similarity DELETE; embeddings already indexed via HNSW on `memory_facts.embedding` |
| MEM-03 | User can say "forget everything" and all stored memories are cleared; user can disable memory learning | `clear_all_memories()` via bulk DELETE; disable via `upsert_preference(user_id, "memory_enabled", False, db_session)` |
</phase_requirements>

## Standard Stack

### Core (already installed — no new packages needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pgvector | 0.3.0+ (installed) | Cosine distance DELETE query | Already drives Phase 9 HNSW index on `memory_facts.embedding` |
| SQLAlchemy 2.0 | 2.0.49+ (installed) | Async ORM DELETE | `MemoryFact.embedding.cosine_distance()` operator already used in `_store_fact()` |
| openai | 2.x (installed) | text-embedding-3-small for delete match | Same `_embed()` helper already in `memory.py` |
| LangGraph | 1.1.6+ (installed) | New node + routing wiring | Established node pattern in `nodes.py` |

[VERIFIED: codebase grep, pyproject.toml]

No new packages required for this phase.

## Architecture Patterns

### Recommended Project Structure (additions only)

```
src/daily/
├── orchestrator/
│   ├── graph.py         # EDIT: add memory keywords + "memory" edge
│   └── nodes.py         # EDIT: add memory_node()
└── profile/
    └── memory.py        # EDIT: add delete_memory_fact(), clear_all_memories()

tests/
└── test_memory.py       # EDIT: add Phase 10 test cases
```

No new files required. All changes are additive edits to existing modules.

### Pattern 1: route_intent() keyword extension

The existing `route_intent()` function uses a simple keyword whitelist with priority ordering. The new memory keywords must be checked BEFORE summarise and draft keywords to avoid false routing — e.g., "forget everything about that thread" should go to `memory_node`, not `summarise_thread`.

```python
# Source: src/daily/orchestrator/graph.py (verified)
def route_intent(state: SessionState) -> str:
    last_msg = state.messages[-1].content.lower() if state.messages else ""

    # Memory keywords — checked FIRST (most specific; overlaps with summarise/draft terms)
    memory_query_keywords = ["what do you know", "what do you remember",
                             "tell me what you know", "what have you learned"]
    memory_delete_keywords = ["forget that", "delete that", "remove that fact",
                              "forget everything", "clear my memory", "reset my memory"]
    memory_disable_keywords = ["disable memory", "stop learning",
                               "turn off memory", "don't remember"]

    all_memory_keywords = memory_query_keywords + memory_delete_keywords + memory_disable_keywords
    if any(kw in last_msg for kw in all_memory_keywords):
        return "memory"

    # Existing summarise check ...
    # Existing draft check ...
    return "respond"
```

[VERIFIED: codebase — graph.py lines 47-71]

### Pattern 2: memory_node() sub-intent dispatch

The node receives `db_session` via `config["configurable"]["db_session"]` — the same pattern used by `summarise_thread_node`. Sub-intent is determined by re-examining the last message with the same keyword sets used in routing.

```python
# Source: src/daily/orchestrator/nodes.py pattern (verified)
async def memory_node(state: SessionState, config: RunnableConfig) -> dict:
    db_session = config["configurable"]["db_session"]
    user_id = state.active_user_id
    last_msg = state.messages[-1].content.lower() if state.messages else ""

    try:
        if any(kw in last_msg for kw in memory_query_keywords):
            narrative = await _handle_memory_query(user_id, db_session)
        elif any(kw in last_msg for kw in memory_delete_all_keywords):
            narrative = await _handle_memory_clear(user_id, db_session)
        elif any(kw in last_msg for kw in memory_delete_fact_keywords):
            narrative = await _handle_memory_delete(user_id, last_msg, db_session)
        elif any(kw in last_msg for kw in memory_disable_keywords):
            narrative = await _handle_memory_disable(user_id, db_session)
        else:
            narrative = "I'm not sure what memory operation you meant. Try 'what do you know about me?'"
    except Exception as exc:
        logger.warning("memory_node: unexpected failure: %s", exc)
        narrative = "I couldn't complete that right now."

    return {"messages": [AIMessage(content=narrative)]}
```

[ASSUMED: exact sub-intent dispatch split between "forget that" (single fact) vs "forget everything" (bulk) — both delete_keywords in CONTEXT.md; planner should split them carefully]

### Pattern 3: delete_memory_fact() in memory.py

The function reuses the existing `_embed()` helper. The cosine_distance query pattern is identical to `_store_fact()`'s dedup check, just with a different threshold and a DELETE instead of a guard.

```python
# Source: src/daily/profile/memory.py _store_fact() pattern (verified, lines 100-127)
async def delete_memory_fact(
    user_id: int,
    description: str,
    db_session: AsyncSession,
    threshold: float = 0.2,
) -> str | None:
    """Find and delete the memory fact closest to description.
    Returns deleted fact_text or None if no match found."""
    client = _get_openai_client()
    query_embedding = await _embed(description, client)

    stmt = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id)
        .where(MemoryFact.embedding.cosine_distance(query_embedding) < threshold)
        .order_by(MemoryFact.embedding.cosine_distance(query_embedding))
        .limit(1)
    )
    row = (await db_session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    await db_session.delete(row)
    await db_session.commit()
    return row.fact_text
```

[VERIFIED: pgvector SQLAlchemy operator pattern from codebase — memory.py lines 100-127]

### Pattern 4: clear_all_memories() in memory.py

```python
# Source: adapted from MemoryFact ORM model (verified, db/models.py lines 72-89)
async def clear_all_memories(user_id: int, db_session: AsyncSession) -> int:
    """Delete all memory facts for user. Returns count of deleted rows."""
    from sqlalchemy import delete, func, select
    count_result = await db_session.execute(
        select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == user_id)
    )
    count = count_result.scalar_one()
    await db_session.execute(
        delete(MemoryFact).where(MemoryFact.user_id == user_id)
    )
    await db_session.commit()
    return count
```

[VERIFIED: SQLAlchemy 2.0 async delete pattern — established in codebase]

### Pattern 5: upsert_preference() for disable path

The existing `upsert_preference(user_id, key, value, session)` signature takes `value: str`. The test suite uses `upsert_preference(2, "memory_enabled", "false", db_session)` with string `"false"` — see `test_memory.py` line 113. However, calling code in `memory_node` will pass the Python bool `False`. The current implementation stores the raw value, and `UserPreferences.model_validate()` reads it back — Pydantic v2 coerces `"false"` string to `False` bool via `model_validate`. Passing `False` (bool) directly also works.

**Critical finding:** The current `upsert_preference` signature is `value: str`. For `memory_enabled`, the node needs to pass `False` (bool). Either: (a) pass the string `"false"` and rely on Pydantic coercion (consistent with existing test patterns), or (b) pass `False` and note the type annotation mismatch. Option (a) is safer and consistent with existing tests.

[VERIFIED: service.py line 37-71, test_memory.py line 113 — confirmed "false" string is the existing pattern]

### Anti-Patterns to Avoid

- **Do NOT use `memory_enabled` gate in `delete_memory_fact()` or `clear_all_memories()`**: These are transparency operations — the user should be able to delete facts or clear everything even if learning is currently enabled. The gate only applies to extraction and retrieval.
- **Do NOT wrap `interrupt()` in try/except**: Phase 4's `approval_node` shows this clearly (nodes.py line 593-615). Not applicable here since memory_node has no interrupt, but the pattern is documented.
- **Do NOT call LLM for the query response**: D-02 explicitly prohibits LLM re-summarisation for the query path to avoid latency. Format the fact list directly in Python.
- **Do NOT read `memory_enabled` before deleting**: A user who has disabled learning still has existing facts. The delete and clear operations must work regardless of the flag.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cosine similarity DELETE | Custom SQL string | `MemoryFact.embedding.cosine_distance()` ORM operator | Already working in `_store_fact()` dedup; HNSW index makes it fast |
| Fact list formatting | LLM summarisation | Direct Python string formatting | D-02: avoid LLM latency for introspection read-back |
| Memory flag toggle | Custom DB update | `upsert_preference()` | Already handles profile JSONB update + commit |
| Embedding generation | Custom OpenAI call | `_embed()` helper in `memory.py` | Already exists, already tested |

## Common Pitfalls

### Pitfall 1: Sub-intent ordering (delete-single vs delete-all)

**What goes wrong:** "forget everything" matches both `memory_delete_keywords` and could match "forget" in a longer phrase. The node must check bulk-clear keywords (`"forget everything"`, `"clear my memory"`, `"reset my memory"`) BEFORE single-fact deletion keywords (`"forget that"`, `"delete that"`).

**Why it happens:** "forget everything" contains "forget" which is a substring match risk if the single-fact check runs first with loose matching.

**How to avoid:** Define two separate keyword lists — `memory_clear_keywords` and `memory_delete_keywords` — and check clear first. Both are locked in D-01; the split should be explicit in implementation.

**Warning signs:** Test case "forget everything" routing to single-fact delete instead of bulk clear.

### Pitfall 2: upsert_preference type mismatch for memory_enabled

**What goes wrong:** Passing Python `False` (bool) to `upsert_preference(user_id, "memory_enabled", False, db_session)` where the signature is `value: str`. Mypy will flag this.

**Why it happens:** The service was designed for string values from CLI input. The memory node passes programmatic booleans.

**How to avoid:** Pass `"false"` (string) consistent with existing test_memory.py line 113. Document this as the established pattern. Alternatively, extend `upsert_preference` to accept `str | bool` — but only if the planner decides it's in scope.

**Warning signs:** mypy type error on the `upsert_preference` call in `memory_node`.

### Pitfall 3: Querying with memory_enabled=False gate in retrieval

**What goes wrong:** `retrieve_relevant_memories()` returns `[]` when `memory_enabled=False` (lines 269-275 of memory.py). If the user calls "what do you know about me?" after disabling memory, the function returns an empty list, but they may still have existing facts.

**Why it happens:** The `memory_enabled` gate in `retrieve_relevant_memories()` was designed for the injection use case, not the introspection use case.

**How to avoid:** The query path in `memory_node` should NOT call `retrieve_relevant_memories()` with the gating behaviour. Instead it should query `memory_facts` directly (bypassing the gate), or call the function but then check if the empty result is due to the flag. The simpler fix: implement a separate `list_all_memories()` helper that does NOT check `memory_enabled`, so transparency always works.

**Warning signs:** "what do you know about me?" returns "I don't know anything about you" immediately after "disable memory" even though facts still exist in the DB.

### Pitfall 4: DB session not available in graph node

**What goes wrong:** `memory_node` needs a DB session but forgets to extract it from `config["configurable"]["db_session"]`.

**Why it happens:** `respond_node` doesn't need a DB session (uses `create_task` for signals), so it's easy to forget the pattern.

**How to avoid:** Follow `summarise_thread_node` pattern — it does NOT use DB directly but `memory_node` will. Use the `config["configurable"]["db_session"]` access pattern established and documented in CONTEXT.md.

[VERIFIED: nodes.py full read; CONTEXT.md code_context section]

### Pitfall 5: No edge wired in build_graph()

**What goes wrong:** `memory_node` function added to nodes.py but `build_graph()` not updated — node is unreachable.

**Why it happens:** Two separate files must be edited in sync.

**How to avoid:** The plan should explicitly list both changes: (a) add node to `builder.add_node("memory", memory_node)`, (b) add `"memory": "memory"` to the `add_conditional_edges` mapping, (c) add `builder.add_edge("memory", END)`.

[VERIFIED: graph.py lines 113-162]

## Code Examples

### Query path response formatting

```python
# Source: CONTEXT.md D-02 + specifics #1
async def _handle_memory_query(user_id: int, db_session: AsyncSession) -> str:
    # Direct DB query bypassing memory_enabled gate — transparency always works
    from sqlalchemy import select
    from daily.db.models import MemoryFact

    stmt = (
        select(MemoryFact.fact_text)
        .where(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.created_at.desc())
        .limit(10)
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    if not rows:
        return "I don't know anything about you yet."
    items = "\n".join(f"{i+1}. {fact}" for i, fact in enumerate(rows))
    return f"Here's what I know about you:\n{items}"
```

Note: this uses `created_at.desc()` ordering (most recent first) for the list-all case, not cosine similarity — since there's no query text to compare against. If the planner wants cosine ordering, a synthetic query string must be embedded first (as per D-02: "user profile personal facts preferences"). Both approaches are valid; the planner should pick one.

[ASSUMED: exact ordering strategy for the query path — CONTEXT.md says "broad synthetic query" but direct DB read also satisfies the requirement]

### Graph wiring additions

```python
# Source: graph.py build_graph() verified pattern (lines 113-162)

# In build_graph():
from daily.orchestrator.nodes import memory_node  # add to imports

builder.add_node("memory", memory_node)

# In add_conditional_edges:
builder.add_conditional_edges(
    START,
    route_intent,
    {
        "respond": "respond",
        "summarise_thread": "summarise_thread",
        "draft": "draft",
        "memory": "memory",   # new
    },
)

builder.add_edge("memory", END)   # new
```

[VERIFIED: graph.py structure]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No memory transparency | Voice-driven query/delete/disable | Phase 10 | Users can audit and control what the system knows |

No deprecated patterns introduced. This phase is purely additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `memory_node` should bypass `memory_enabled` gate for query/delete/clear operations | Pitfall 3 + Code Examples | If wrong: users lose transparency after disabling memory — can't see or delete their stored facts |
| A2 | "forget everything" keywords checked BEFORE "forget that" keywords within the delete sub-intent to prevent bulk-clear routing to single-fact delete | Pitfall 1 | If wrong: "forget everything" silently only deletes one fact |
| A3 | Exact ordering strategy for the query path (synthetic embedding query vs `created_at.desc()`) | Code Examples | Low risk — either approach satisfies MEM-01 |
| A4 | `upsert_preference` called with string `"false"` not Python `False` for `memory_enabled` toggle | Pitfall 2 + Pattern 5 | Type error if `False` is passed; minor — easy fix |

## Open Questions

1. **`retrieve_relevant_memories()` gate bypass for introspection**
   - What we know: The function hard-gates on `memory_enabled=False` and returns `[]`
   - What's unclear: Whether the planner should add a bypass parameter to the existing function or implement a new `list_all_memories()` that skips the gate
   - Recommendation: Add a new `list_all_memories(user_id, db_session, limit=10)` function that does NOT check `memory_enabled`. Keeps the existing function's semantics unchanged. 3 lines of new code.

2. **`upsert_preference` type signature for bool values**
   - What we know: Current signature is `value: str`; existing tests pass `"false"` as string
   - What's unclear: Whether to keep string convention or broaden the type
   - Recommendation: Pass `"false"` (string) from `memory_node` — consistent with existing test_memory.py patterns. No signature change needed.

## Environment Availability

Step 2.6: SKIPPED — Phase 10 is purely code changes within the existing service. No external dependencies beyond what Phase 9 already requires (PostgreSQL + pgvector are running if Phase 9 is complete).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — asyncio_mode = "auto" |
| Quick run command | `pytest tests/test_memory.py tests/test_orchestrator_graph.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | "what do you know about me?" returns up to 10 facts | unit (async) | `pytest tests/test_memory.py -k "query" -x` | Wave 0 gap |
| MEM-01 | Returns "I don't know anything about you yet" when no facts | unit (async) | `pytest tests/test_memory.py -k "query_empty" -x` | Wave 0 gap |
| MEM-02 | Delete a specific fact by cosine match; fact no longer returned | unit (async) | `pytest tests/test_memory.py -k "delete_fact" -x` | Wave 0 gap |
| MEM-02 | No match found returns appropriate message | unit (async) | `pytest tests/test_memory.py -k "delete_no_match" -x` | Wave 0 gap |
| MEM-03 | "forget everything" clears all facts; confirms count | unit (async) | `pytest tests/test_memory.py -k "clear_all" -x` | Wave 0 gap |
| MEM-03 | Disable memory sets memory_enabled=False; extraction no longer fires | unit (async) | existing `test_extraction_skipped_when_disabled` | EXISTING |
| MEM-01/02/03 | memory_node routes to correct sub-path per keyword | unit (sync) | `pytest tests/test_orchestrator_graph.py -k "memory" -x` | Wave 0 gap |
| All | Fail-silent: DB unavailable returns graceful message | unit (async) | `pytest tests/test_memory.py -k "fail_silent" -x` | Wave 0 gap |

### Sampling Rate

- **Per task commit:** `pytest tests/test_memory.py tests/test_orchestrator_graph.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_memory.py` — add Phase 10 test cases (file exists; extend it)
- [ ] `tests/test_orchestrator_graph.py` — add `memory` routing tests (file exists; extend it)

*(No new test files needed — all gaps are extensions to existing test files)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | user_id from existing session state |
| V3 Session Management | no | no new session handling |
| V4 Access Control | yes | `WHERE user_id = :user_id` on all memory queries (T-09-11 already enforced by `retrieve_relevant_memories`; apply same to new functions) |
| V5 Input Validation | yes | spoken description used for embedding only — never executed as SQL; cosine threshold bounds the match |
| V6 Cryptography | no | no new crypto; embeddings are not sensitive data |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-user memory access | Information Disclosure | `WHERE user_id = :user_id` on every query — never accept user_id from message content |
| Embedding oracle (repeated probing to infer stored facts) | Information Disclosure | Threshold 0.2 + single-match return limits enumeration; low-severity for M1 local-only deployment |
| Bulk delete denial of service | Tampering | Voice-only, single-user M1 deployment; no rate limiting needed for M1 |

**Critical (from T-09-11 pattern):** `delete_memory_fact()` and `clear_all_memories()` MUST include `WHERE user_id = :user_id` — no cross-user deletion is possible through these functions.

## Sources

### Primary (HIGH confidence)
- `src/daily/profile/memory.py` — VERIFIED full read: `_embed()`, `_store_fact()`, `retrieve_relevant_memories()`, `extract_and_store_memories()`
- `src/daily/orchestrator/graph.py` — VERIFIED full read: `route_intent()`, `build_graph()`
- `src/daily/orchestrator/nodes.py` — VERIFIED full read: all node patterns, DB session access via `config["configurable"]["db_session"]`
- `src/daily/orchestrator/state.py` — VERIFIED full read: `SessionState` fields
- `src/daily/profile/service.py` — VERIFIED full read: `upsert_preference()` signature and behaviour
- `src/daily/profile/models.py` — VERIFIED full read: `UserPreferences.memory_enabled` field
- `src/daily/db/models.py` — VERIFIED full read: `MemoryFact` ORM model
- `tests/test_memory.py` — VERIFIED full read: test patterns and upsert_preference "false" string convention
- `.planning/phases/10-memory-transparency/10-CONTEXT.md` — VERIFIED full read
- `pyproject.toml` — VERIFIED: pytest config, installed packages

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` — VERIFIED: phase dependencies and completion status

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed and verified in pyproject.toml
- Architecture: HIGH — all patterns verified from existing codebase; no new patterns required
- Pitfalls: HIGH — all pitfalls identified from direct code inspection, not training data assumptions

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable codebase, no fast-moving external dependencies)
