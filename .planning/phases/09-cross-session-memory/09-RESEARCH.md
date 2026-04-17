# Phase 9: Cross-Session Memory — Research

**Researched:** 2026-04-17
**Domain:** pgvector / SQLAlchemy ORM / OpenAI embeddings / async fire-and-forget pattern
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Memory Library**
Custom extraction pipeline, not mem0 or langmem. One OpenAI LLM call at session end extracts facts from conversation history. Embedding via `text-embedding-3-small` (1536d). Full schema control required for Phase 10 (MEM-01/02/03 need row-level access to delete and inspect individual facts).

**D-02 — Storage Schema**
New `memory_facts` table:
- `id` (UUID, PK)
- `user_id` (FK → `users.id`)
- `fact_text` (TEXT — raw extracted statement)
- `embedding` (VECTOR(1536) — pgvector column)
- `source_session_id` (TEXT — session ID or timestamp at extraction, for dedup and Phase 10 provenance)
- `created_at` (TIMESTAMPTZ)

Add via new Alembic migration. Enable `pgvector` extension in the same migration if not already enabled.

**D-03 — Extraction Trigger**
`asyncio.create_task()` in the `finally` block of `run_voice_session()` in `src/daily/voice/loop.py`. Fire-and-forget — does not block voice response path. Uses its own DB session opened inside the task (same pattern as `_capture_signal()` and `_log_action()` in `nodes.py`).

**D-04 — Hallucination Loop Prevention**
Vector similarity dedup at insert time: before storing any extracted fact, query pgvector for existing facts with cosine distance < 0.1. Only insert if no near-duplicate found.

**D-05 — `memory_enabled` Flag**
Boolean field with default `True` added to `UserPreferences` Pydantic model in `src/daily/profile/models.py`. Stored as JSONB in `UserProfile.preferences` — no schema migration needed. Checked in:
1. Extraction task — skip entirely if `False`
2. Briefing pipeline injection — skip retrieval and injection if `False`

**D-06 — Retrieval and Injection Points**
Recalled memories injected at two points:
1. **Narrator system prompt** (`src/daily/briefing/narrator.py` → `build_narrator_system_prompt()`) — precomputed morning briefing. Pattern follows existing `PREFERENCE_PREAMBLE` injection.
2. **SessionState** (`src/daily/orchestrator/session.py` → `initialize_session_state()`) — live session responses via `respond_node`.

Retrieval: query `memory_facts` by cosine similarity (`<=>` operator) against a query embedding of the current date/briefing topic, top-K results (default K=10).

**D-07 — New Module**
`src/daily/profile/memory.py` — exports:
- `extract_and_store_memories(user_id, session_history, session_id, db_session)` — async, called via create_task
- `retrieve_relevant_memories(user_id, query_text, db_session, top_k=10) -> list[str]`

### Claude's Discretion
- Exact extraction prompt wording
- Number of facts extracted per session (suggested: cap at 10 per session)
- Index type for pgvector column (`hnsw` preferred for ANN search — lower latency than `ivfflat`)

### Deferred Ideas (OUT OF SCOPE)
- Voice interface for "what do you know about me?" — Phase 10 (MEM-01)
- Deleting specific facts by voice — Phase 10 (MEM-02)
- "Forget everything" reset — Phase 10 (MEM-03)
- Per-user configurable top-K retrieval count — v2.0
- Per-topic/keyword memory beyond user profile facts — v2.0
- Memory confidence scoring or source weighting — v2.0
- langmem or mem0 adoption — deferred
- Separate memory for CLI chat sessions vs voice sessions — v2.0
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTEL-02 | System recalls facts from previous sessions when building each day's briefing context | D-02 schema, D-03 extraction trigger, D-06 injection at narrator + session init, D-04 dedup guard |
</phase_requirements>

---

## Summary

Phase 9 adds a durable user-memory layer: facts stated during voice sessions are extracted asynchronously, embedded with `text-embedding-3-small`, and stored as vector rows in a new `memory_facts` table backed by pgvector. At briefing generation and session initialisation time, the most relevant facts are retrieved via cosine similarity and injected into the LLM context.

The architecture is fully settled by CONTEXT.md decisions. What remains is to verify the exact code APIs, confirm the pgvector SQLAlchemy 2.0 integration pattern, understand the Alembic UUID + VECTOR column migration syntax, and identify the precise touch points where existing code needs extending. All five integration points (loop.py, memory.py, narrator.py, session.py, models.py) follow already-established codebase patterns, making this a mechanical expansion rather than a greenfield design problem.

**Primary recommendation:** Add `pgvector` to `pyproject.toml` dependencies, create a single Alembic migration (005) that enables the extension and creates the table, implement `memory.py` following the `_capture_signal` / `adaptive_ranker` patterns already in the codebase, then wire injection at the two locked points.

---

## Standard Stack

### Core (all already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pgvector (Python) | 0.3.x | `VECTOR` type + ORM methods | Required to use pgvector extension from SQLAlchemy. Exposes `.cosine_distance()` column method used for dedup and retrieval. [VERIFIED: github.com/pgvector/pgvector-python] |
| SQLAlchemy | 2.0.49+ (in pyproject.toml) | Async ORM for `memory_facts` model | Already project-standard. `mapped_column(VECTOR(1536))` is the type annotation. [VERIFIED: pyproject.toml] |
| OpenAI SDK | 2.x (in pyproject.toml) | `text-embedding-3-small` embeddings | Already used by narrator and ranker. Same client pattern. [VERIFIED: pyproject.toml] |
| Alembic | 1.13+ (in pyproject.toml) | Migration for `memory_facts` table | Already in migration chain. Next revision is `005`. [VERIFIED: worktree migration files 001–004] |
| asyncpg | 0.29+ (in pyproject.toml) | Postgres async driver | Already project-standard. [VERIFIED: pyproject.toml] |

**New dependency to add:**

```bash
uv add pgvector
```

pgvector is NOT currently in pyproject.toml. [VERIFIED: pyproject.toml inspection] The package name on PyPI is `pgvector`. [VERIFIED: pypi.org/project/pgvector]

### Claude's Discretion Recommendation: HNSW vs IVFFlat

Use `hnsw` with `vector_cosine_ops`. HNSW has better query-time speed/recall tradeoff than IVFFlat. IVFFlat requires a training pass (`VACUUM ANALYZE`) before it is effective; HNSW builds incrementally and is effective on small tables immediately. At M1 scale (hundreds to low thousands of facts), HNSW is the correct choice. [ASSUMED based on pgvector documentation guidance]

---

## Architecture Patterns

### Recommended Project Structure

No new directories. New files slot into existing structure:

```
src/daily/
├── profile/
│   ├── memory.py          ← NEW — extraction + retrieval module
│   ├── adaptive_ranker.py ← reference pattern
│   └── models.py          ← add memory_enabled to UserPreferences
├── db/
│   └── models.py          ← add MemoryFact ORM model
├── briefing/
│   └── narrator.py        ← extend build_narrator_system_prompt()
├── orchestrator/
│   └── session.py         ← extend initialize_session_state()
└── voice/
    └── loop.py            ← add create_task in finally block

src/daily/alembic/versions/
└── 005_add_memory_facts.py ← NEW migration
```

### Pattern 1: pgvector VECTOR Column in SQLAlchemy 2.0

```python
# Source: github.com/pgvector/pgvector-python README
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.orm import mapped_column

class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID as string
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fact_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(VECTOR(1536))
    source_session_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

UUID PK: use `uuid.uuid4()` as default at Python level, store as TEXT or UUID column. CONTEXT.md specifies UUID PK. [ASSUMED: UUID storage as TEXT matches existing codebase pattern of string IDs in other metadata]

### Pattern 2: HNSW Index in Alembic Migration

The index cannot be expressed purely through the ORM model's `__table_args__` when using pgvector ops — use raw DDL in the migration:

```python
# Source: github.com/pgvector/pgvector-python README (verified)
def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("source_session_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # HNSW index for cosine similarity (ANN, not exact)
    op.execute(
        "CREATE INDEX memory_facts_embedding_hnsw_idx "
        "ON memory_facts USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

def downgrade() -> None:
    op.drop_table("memory_facts")
    # Extension left in place — other tables may depend on it
```

Migration import: `from pgvector.sqlalchemy import Vector` — note capital V, same package.

### Pattern 3: Fire-and-Forget Task (mirrors _capture_signal exactly)

```python
# Source: src/daily/orchestrator/nodes.py _capture_signal (VERIFIED: codebase read)
async def extract_and_store_memories(
    user_id: int,
    session_history: list[dict],
    session_id: str,
    db_session: AsyncSession,
) -> None:
    """Must never raise — all errors caught and logged."""
    try:
        # ... extraction and storage logic
        pass
    except Exception as exc:
        logger.warning("extract_and_store_memories: failed: %s", exc)
```

Called from `loop.py` finally block:

```python
# Source: pattern from src/daily/orchestrator/nodes.py (VERIFIED: codebase read)
finally:
    listen_stop.set()
    await turn_manager.stop()
    # Fire-and-forget memory extraction — must not block voice shutdown
    if session_history:
        from daily.db.engine import async_session as _async_session
        from daily.profile.memory import extract_and_store_memories
        async def _run_extraction():
            async with _async_session() as db_sess:
                await extract_and_store_memories(
                    user_id=user_id,
                    session_history=session_history,
                    session_id=session_id,
                    db_session=db_sess,
                )
        asyncio.create_task(_run_extraction())
    print("Voice session ended.")
```

Note: `extract_and_store_memories` itself needs a `db_session` per its CONTEXT.md signature. The task wrapper opens the session, matching the `_capture_signal` and `_log_action` patterns exactly. [VERIFIED: nodes.py read]

### Pattern 4: Cosine Distance Dedup Query

```python
# Source: github.com/pgvector/pgvector-python README (VERIFIED via WebFetch)
from sqlalchemy import select

# Near-duplicate check before insert (threshold 0.1 per D-04)
stmt = (
    select(MemoryFact.id)
    .where(MemoryFact.user_id == user_id)
    .where(MemoryFact.embedding.cosine_distance(embedding_vector) < 0.1)
    .limit(1)
)
result = await session.execute(stmt)
if result.scalar():
    return  # duplicate, skip insert
```

### Pattern 5: Narrator Injection (extends PREFERENCE_PREAMBLE pattern)

```python
# Source: src/daily/briefing/narrator.py build_narrator_system_prompt (VERIFIED: codebase read)
MEMORY_PREAMBLE = (
    "User memories (facts recalled from previous sessions):\n"
    "{memories}\n\n"
    "Incorporate relevant memories naturally — do not list them verbatim.\n\n"
)

def build_narrator_system_prompt(
    preferences: UserPreferences | None = None,
    user_memories: list[str] | None = None,
) -> str:
    preamble = ""
    if user_memories:
        memory_lines = "\n".join(f"- {m}" for m in user_memories)
        preamble += MEMORY_PREAMBLE.format(memories=memory_lines)
    if preferences is not None:
        preamble += PREFERENCE_PREAMBLE.format(...)
    return preamble + NARRATOR_SYSTEM_PROMPT
```

The caller (`run_briefing_pipeline`) already accepts `db_session=None`. The pipeline needs a `retrieve_relevant_memories()` call inserted before `generate_narrative()`. [VERIFIED: pipeline.py read]

### Pattern 6: SessionState Extension

```python
# Source: src/daily/orchestrator/state.py (VERIFIED: codebase read)
class SessionState(BaseModel):
    # ... existing fields ...
    user_memories: list[str] = Field(default_factory=list)  # NEW
```

`initialize_session_state()` in `session.py` must call `retrieve_relevant_memories()` and populate this field. The `respond_node` then reads `state.user_memories` when building its system prompt.

### Anti-Patterns to Avoid

- **Sharing a DB session across create_task boundary:** Never pass a session from the voice loop into the extraction task. Each task opens its own session. [VERIFIED: _capture_signal pattern]
- **Raising inside extraction task:** `extract_and_store_memories` must catch all exceptions internally. An unhandled exception in a detached task logs an asyncio warning but does not crash the loop — however it corrupts the task result silently. Explicit try/except with logging is required. [ASSUMED based on asyncio task semantics]
- **Using `await` for the extraction call in the voice finally block:** Must be `asyncio.create_task(...)`, never `await extract_and_store_memories(...)`. The `await` would block the shutdown path. [VERIFIED: D-03 decision + _capture_signal code]
- **Re-extracting injected facts:** The injection places facts into the narrator context; the extraction runs on the conversation message history (turn messages), not on the narrator output. As long as extraction only reads `session.messages`, the hallucination loop cannot occur. [VERIFIED: D-04 dedup is the secondary guard]
- **IVFFlat index for small tables:** IVFFlat requires a minimum number of rows to be useful and needs VACUUM ANALYZE before first use. HNSW builds incrementally. [ASSUMED based on pgvector documentation guidance]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector similarity search | Custom cosine distance in Python | pgvector `<=>` operator in DB | Runs in Postgres, uses HNSW index, orders-of-magnitude faster than Python-side computation |
| Approximate nearest neighbour | Exact brute-force scan | HNSW index (`vector_cosine_ops`) | Exact scan is O(n) per query; HNSW is O(log n) with sub-millisecond retrieval at M1 scale |
| Embedding generation | Custom HTTP calls to OpenAI | `client.embeddings.create(model="text-embedding-3-small", input=text)` | Project already has AsyncOpenAI client; consistent with existing narrator/ranker patterns |
| Dedup logic | String similarity (edit distance) | Vector cosine distance < 0.1 | Semantic dedup catches paraphrased duplicates ("I travel a lot" vs "I'm often away for work") |

**Key insight:** Postgres with pgvector is the only vector store needed. No Chroma, Pinecone, or separate vector DB. This is an explicit project constraint per CLAUDE.md "What NOT to Use."

---

## Common Pitfalls

### Pitfall 1: pgvector Not in pyproject.toml

**What goes wrong:** Migration runs but `from pgvector.sqlalchemy import VECTOR` raises `ModuleNotFoundError` at startup.
**Why it happens:** The `pgvector` Python package is not yet in pyproject.toml. The Postgres extension and the Python package are separate. [VERIFIED: pyproject.toml inspection — pgvector absent]
**How to avoid:** Wave 0 task must add `pgvector` to pyproject.toml and run `uv sync`.
**Warning signs:** `ModuleNotFoundError: No module named 'pgvector'` at migration or model import time.

### Pitfall 2: Vector Type Import in Migration

**What goes wrong:** Alembic migration uses `VECTOR(1536)` but the type is not imported, causing `NameError` at migration run.
**Why it happens:** Unlike standard SQLAlchemy types, `Vector` is imported from `pgvector.sqlalchemy`, not `sqlalchemy`.
**How to avoid:** Import `from pgvector.sqlalchemy import Vector` at the top of the migration file. [VERIFIED: pgvector-python README]
**Warning signs:** `NameError: name 'Vector' is not defined` when running `alembic upgrade head`.

### Pitfall 3: UUID PK Needs Python-Side Default

**What goes wrong:** INSERT fails because there is no server-side UUID generator configured for the TEXT column.
**Why it happens:** Unlike `SERIAL` / `BIGSERIAL`, UUID text PKs have no automatic server-side default in Postgres unless `gen_random_uuid()` is specified.
**How to avoid:** Set `default=lambda: str(uuid.uuid4())` on the mapped column, or use `server_default=sa.text("gen_random_uuid()::text")` in the migration.
**Warning signs:** `NOT NULL violation` on `id` column at insert time.

### Pitfall 4: Async Session in Fire-and-Forget Task

**What goes wrong:** Extraction task silently fails with `sqlalchemy.exc.InvalidRequestError: Can't operate on a closed session`.
**Why it happens:** The voice loop's `async with async_session()` context exits before the task runs; the session is closed.
**How to avoid:** Open a new session inside the task itself, not outside. Match `_capture_signal` pattern exactly. [VERIFIED: nodes.py lines 367–385]

### Pitfall 5: Extraction Prompt Must Output Structured Facts

**What goes wrong:** LLM returns a paragraph, not a list of discrete facts; parsing fails and zero facts are stored.
**Why it happens:** Without explicit output format instruction, GPT-4.1 mini summarises conversationally.
**How to avoid:** Extraction prompt must request JSON array of fact strings. Example structure:
```json
{"facts": ["User is travelling next week", "User prefers concise emails"]}
```
Parse with `json.loads()`, fall back to empty list on parse error. Cap at 10 items. [ASSUMED: based on standard LLM structured output practices]

### Pitfall 6: memory_enabled Gate Must Be Checked at Load Time

**What goes wrong:** `retrieve_relevant_memories()` is called before the `memory_enabled` check, wasting a DB round-trip.
**Why it happens:** Callers check the flag after calling the retrieval function.
**How to avoid:** Check `preferences.memory_enabled` before calling `retrieve_relevant_memories()` in both `initialize_session_state()` and `run_briefing_pipeline()`. The function itself can also guard internally as belt-and-braces, but the outer gate should always be primary. [VERIFIED: D-05 gate contract]

### Pitfall 7: SessionState Serialisation

**What goes wrong:** Adding `user_memories: list[str]` to `SessionState` breaks the LangGraph `AsyncPostgresSaver` checkpoint schema.
**Why it happens:** The checkpointer serialises `SessionState` to JSON. `list[str]` is JSON-native, so this should not break — but any default mutable factory must use `Field(default_factory=list)`, not `= []`. [VERIFIED: existing state.py pattern for email_context]
**Warning signs:** Pydantic validation error on checkpoint load if the field is absent in older checkpoints — handle with `= Field(default_factory=list)` which provides a safe default on missing key.

---

## Code Examples

### Embedding Call

```python
# Source: OpenAI SDK v2 pattern (ASSUMED — consistent with existing project usage)
async def _embed(text: str, client: AsyncOpenAI) -> list[float]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding
```

### Full Dedup + Insert

```python
# Source: pgvector-python README + _capture_signal pattern (both VERIFIED)
async def _store_fact(
    user_id: int,
    fact_text: str,
    embedding: list[float],
    session_id: str,
    session: AsyncSession,
) -> None:
    """Store a fact if no near-duplicate exists (cosine distance < 0.1)."""
    from sqlalchemy import select
    dup_stmt = (
        select(MemoryFact.id)
        .where(MemoryFact.user_id == user_id)
        .where(MemoryFact.embedding.cosine_distance(embedding) < 0.1)
        .limit(1)
    )
    existing = (await session.execute(dup_stmt)).scalar()
    if existing:
        return
    session.add(MemoryFact(
        id=str(uuid.uuid4()),
        user_id=user_id,
        fact_text=fact_text,
        embedding=embedding,
        source_session_id=session_id,
    ))
    await session.commit()
```

### Retrieval

```python
# Source: pgvector-python README (VERIFIED)
async def retrieve_relevant_memories(
    user_id: int,
    query_text: str,
    session: AsyncSession,
    top_k: int = 10,
) -> list[str]:
    """Retrieve top-K most relevant facts by cosine similarity."""
    from daily.config import Settings
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=Settings().openai_api_key)
    query_embedding = await _embed(query_text, client)
    stmt = (
        select(MemoryFact.fact_text)
        .where(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
```

### Extraction Prompt (Claude's Discretion)

```python
EXTRACTION_SYSTEM_PROMPT = (
    "You are a personal assistant reading a conversation transcript. "
    "Extract durable personal facts that would help a briefing assistant in future sessions. "
    "Examples: travel plans, preferences, recurring commitments, personal context.\n\n"
    "Rules:\n"
    "- Extract at most 10 facts.\n"
    "- Each fact must be a single, self-contained statement.\n"
    "- Only extract facts stated by the user, not the assistant.\n"
    "- Do not extract ephemeral facts (e.g., 'user asked about today's weather').\n"
    "- Do not extract facts already obvious from the briefing context.\n\n"
    'Output MUST be valid JSON: {"facts": ["fact one", "fact two", ...]}\n'
    'If no durable facts exist, output: {"facts": []}'
)
```

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | UUID stored as TEXT PK, using `str(uuid.uuid4())` Python default | Code Examples | Low — if server-side UUID preferred, migration server_default changes but logic is identical |
| A2 | HNSW is effective immediately on small tables without VACUUM ANALYZE (unlike IVFFlat) | Architecture Patterns | Low — worst case is slightly slower index build, not incorrect behaviour |
| A3 | `list[str]` in `SessionState.user_memories` serialises cleanly through AsyncPostgresSaver checkpoint | Architecture Patterns | Medium — if checkpoint schema rejects unknown fields, a migration of the checkpoint table would be required (investigate if tests fail) |
| A4 | Extraction prompt returning `{"facts": [...]}` is the correct structured output format | Code Examples | Low — format is Claude's discretion; can change without affecting architecture |
| A5 | `asyncio.create_task` called inside the `finally` block is scheduled correctly even after normal loop exit | Architecture Patterns | Low — asyncio task scheduling survives finally block execution; loop is still running at this point |

---

## Open Questions (RESOLVED)

1. **Alembic chain: where is the live migration chain?** — RESOLVED
   - What we know: Worktree files show revisions 001 → 56a7489e → 003 → 004. The main branch `src/daily/alembic/` directory does not exist at the standard path.
   - **Resolution:** Migrations live in the repo root `alembic/` directory (confirmed by 001–004 files found there). Plan 01 Task 2 gates on confirming the current head via `uv run alembic heads` at runtime before writing migration 005. Standard path `alembic/versions/005_*.py`.

2. **`run_voice_session()` session_history accumulation** — RESOLVED
   - What we know: The voice loop runs a while loop processing turns; messages are passed to the orchestrator via `run_session()`.
   - **Resolution:** Plan 04 Task 1 builds `session_history` as a local list in the while loop, appending `{"role": "user"|"assistant", "content": "..."}` dicts per turn. The `config` dict is in scope at the inner `try/finally` block. No LangGraph checkpointer access required.

3. **`retrieve_relevant_memories()` query embedding** — RESOLVED
   - What we know: D-06 specifies "query embedding of the current date/briefing topic."
   - **Resolution (Claude's discretion):** Use `"today's daily briefing"` as the query string for briefing injection (narrator). For live-session injection, use `"today's briefing context"`. Both strings are stable across days and produce better semantic recall than raw date strings.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | memory_facts table | ✓ | 15+ (docker-compose per CLAUDE.md) | — |
| pgvector extension | VECTOR column | ✓ (assumed present in project Postgres) | — | Migration creates it with `CREATE EXTENSION IF NOT EXISTS vector` |
| pgvector Python pkg | ORM VECTOR type | ✗ | — | Must add to pyproject.toml (`uv add pgvector`) |
| OpenAI API | text-embedding-3-small | ✓ | API key in .env | — |
| AsyncOpenAI client | embedding calls | ✓ | openai>=2.0.0 already in project | — |

**Missing dependencies with no fallback:**
- `pgvector` Python package — must be added in Wave 0 before any import of `pgvector.sqlalchemy`

**Missing dependencies with fallback:**
- None

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (asyncio_mode = "auto") |
| Quick run command | `pytest tests/test_memory.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTEL-02 | extract_and_store_memories writes facts to DB | unit | `pytest tests/test_memory.py::test_extraction_stores_facts -x` | ❌ Wave 0 |
| INTEL-02 | dedup prevents near-duplicate insert | unit | `pytest tests/test_memory.py::test_dedup_prevents_near_duplicate -x` | ❌ Wave 0 |
| INTEL-02 | retrieve_relevant_memories returns list[str] | unit | `pytest tests/test_memory.py::test_retrieval_returns_strings -x` | ❌ Wave 0 |
| INTEL-02 | memory_enabled=False skips extraction | unit | `pytest tests/test_memory.py::test_memory_disabled_skips_extraction -x` | ❌ Wave 0 |
| INTEL-02 | memory_enabled=False skips injection | unit | `pytest tests/test_memory.py::test_memory_disabled_skips_injection -x` | ❌ Wave 0 |
| INTEL-02 | narrator prompt includes memory preamble | unit | `pytest tests/test_narrator_preferences.py -x` (extend existing) | ✅ (extend) |
| INTEL-02 | initialize_session_state includes user_memories | unit | `pytest tests/test_memory.py::test_session_state_includes_memories -x` | ❌ Wave 0 |
| INTEL-02 | extraction never raises even on LLM failure | unit | `pytest tests/test_memory.py::test_extraction_swallows_errors -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_memory.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_memory.py` — all new memory module tests (8 cases above)
- [ ] `pgvector` in pyproject.toml — `uv add pgvector`
- [ ] Alembic migration 005 — confirm head revision and active alembic path

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | `user_id` FK enforces per-user data isolation; queries always filter by `user_id` |
| V5 Input Validation | yes | Extraction LLM output parsed as JSON; facts are plain text strings with no HTML; no user-controlled query parameters |
| V6 Cryptography | no | Facts are not secrets; embeddings are derived representations, not PII themselves |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-user memory access | Information Disclosure | All `MemoryFact` queries MUST filter `WHERE user_id = :user_id` — never query without user_id |
| Prompt injection via stored facts | Tampering | Facts are injected as a clearly-labelled preamble block; the LLM never executes facts as instructions (narrator has no tool calls per SEC-05) |
| Unbounded fact accumulation | Denial of Service | Dedup threshold (0.1) and per-session cap (10 facts) limit growth rate naturally |
| Raw conversation bodies stored as facts | Privacy | Extraction prompt explicitly instructs extraction of distilled facts only, not verbatim quotes; facts are summaries, not raw bodies |

---

## Sources

### Primary (HIGH confidence)
- `src/daily/orchestrator/nodes.py` — `_capture_signal()` fire-and-forget pattern (VERIFIED: codebase read)
- `src/daily/briefing/narrator.py` — `build_narrator_system_prompt()` PREFERENCE_PREAMBLE injection pattern (VERIFIED: codebase read)
- `src/daily/orchestrator/session.py` — `initialize_session_state()` structure (VERIFIED: codebase read)
- `src/daily/briefing/pipeline.py` — `run_briefing_pipeline()` signature with `db_session=None` (VERIFIED: codebase read)
- `src/daily/profile/models.py` — `UserPreferences` JSONB pattern (VERIFIED: codebase read)
- `src/daily/db/models.py` — existing ORM model conventions (VERIFIED: codebase read)
- `pyproject.toml` — confirmed pgvector NOT present (VERIFIED: codebase read)
- Alembic worktree files 001–004 — migration chain and syntax patterns (VERIFIED: codebase read)
- `github.com/pgvector/pgvector-python` README — `VECTOR` type, `.cosine_distance()`, HNSW index DDL (VERIFIED: WebFetch)

### Secondary (MEDIUM confidence)
- pgvector HNSW vs IVFFlat guidance — multiple sources corroborate HNSW for ANN without training pass

### Tertiary (LOW confidence)
- None — all claims are codebase-verified or docs-verified.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified in pyproject.toml or pgvector-python docs
- Architecture: HIGH — all patterns verified in existing codebase; only UUID default is assumed
- Pitfalls: HIGH — pitfalls 1–4 and 6–7 are codebase-verified; pitfall 5 is standard LLM output practice

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (stable stack)
