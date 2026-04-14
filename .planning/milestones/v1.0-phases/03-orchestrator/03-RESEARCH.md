# Phase 3: Orchestrator - Research

**Researched:** 2026-04-07
**Domain:** LangGraph stateful agent graph, user profile persistence, interaction signal capture
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** LangGraph 1.0+ (`langgraph>=1.0.3`) as orchestration backbone. Stateful graph execution with per-user session state via `thread_id` + `AsyncPostgresSaver` checkpointer (Postgres-backed).
- **D-02:** Dual-model routing via per-node instantiation: GPT-4.1 for reasoning/briefing nodes, GPT-4.1 mini for follow-up responses. Static per node type — no dynamic router in Phase 3.
- **D-03:** LLM outputs are structured intent JSON only (SEC-05 enforcement). Orchestrator graph validates output schema at each node boundary. LLM never holds credentials or calls external APIs.
- **D-04:** `user_profile` SQLAlchemy table with JSONB `preferences` column. Initial keys: `tone`, `briefing_length`, `category_order`. JSONB allows schema evolution without migrations.
- **D-05:** Preferences set via CLI: `daily config set profile.tone casual`. Loaded at briefing generation time and injected as system instruction context to the narrator LLM.
- **D-06:** Skip mem0 for Phase 3. Preferences are explicitly set, not conversation-emergent.
- **D-07:** Append-only `signal_log` table: `(id, user_id, signal_type, target_id, metadata_json, created_at)`. Signal types are a Python enum: `skip`, `correction`, `re_request`, `follow_up`, `expand`.
- **D-08:** Signals stored for future ranking personalisation. NOT consumed by Phase 3 ranking logic.
- **D-09:** Session state is a Pydantic model managed by LangGraph StateGraph, persisted via `AsyncPostgresSaver`. Contains: current briefing, Q&A history, expanded thread metadata, active section pointer.
- **D-10:** Thread summarisation on-demand: user asks → orchestrator fetches full thread via `get_email_body()` adapter → redactor → GPT-4.1 mini → intent JSON with narrative text.
- **D-11:** Orchestrator reads Redis-cached briefing (`briefing:{user_id}:{date}`) on session start. Does NOT re-run pipeline. Session context wraps cached `BriefingOutput`.

### Claude's Discretion

- Exact LangGraph graph topology (node names, edge routing logic)
- Internal module structure for orchestrator package
- Pydantic model field names for session state and signal log
- How preference injection is formatted in the narrator system prompt
- Checkpointer configuration details (connection pooling, TTL)

### Deferred Ideas (OUT OF SCOPE)

- mem0 for interaction-driven preferences
- Pre-fetching thread bodies during pipeline
- Adaptive model routing (complexity-aware router node)
- Signal-based ranking personalisation (consumer of PERS-02 data, future iteration)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRIEF-07 | User can request thread summarisation on demand during briefing ("summarise that email chain") | LangGraph node fetches thread via `get_email_body()` adapter → existing `summarise_and_redact()` pattern → GPT-4.1 mini intent JSON response |
| PERS-01 | System maintains user profile storing preferences: tone, briefing length, category order, notification preferences | `user_profile` SQLAlchemy table + JSONB `preferences` column + CLI `config set profile.*` commands + narrator system prompt injection |
| PERS-02 | System captures implicit interaction signals: skips, corrections, re-requests, follow-up patterns — stored for future ranking use | Append-only `signal_log` table; fire-and-forget async inserts during orchestrator session |
</phase_requirements>

---

## Summary

Phase 3 introduces the conversational layer that wraps the Phase 2 briefing output. The core infrastructure is a LangGraph 1.x `StateGraph` compiled with an `AsyncPostgresSaver` checkpointer. Per-user session state is keyed by `thread_id`, giving each user a persistent conversation context that survives app restarts. The graph dispatches to two OpenAI models via `langchain-openai`: GPT-4.1 for reasoning nodes (thread summarisation, context-heavy replies) and GPT-4.1 mini for lightweight follow-ups.

Three new database artifacts are required: a `user_profile` table (JSONB preferences), a `signal_log` table (append-only interaction signals), and the LangGraph checkpointer tables (created via `await checkpointer.setup()` at app startup). No additional services are needed beyond what Phase 1/2 already provision (Postgres + Redis).

The Phase 2 `narrator.py` system prompt is extended by prepending a user-preferences preamble sourced from the `user_profile` table. Thread summarisation reuses `summarise_and_redact()` exactly — triggered on-demand rather than at pipeline precompute time. Signal capture is fire-and-forget (non-blocking) to avoid stalling the conversation loop.

**Primary recommendation:** Build the LangGraph graph skeleton first (graph definition, state model, checkpointer wiring), then layer in the three features (preferences injection, thread summarisation, signal logging) as separate tasks.

---

## Standard Stack

### Core (new additions for Phase 3)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.6 | Stateful agent graph with persistent session state | Decision D-01 — locked. Latest stable 1.x release. [VERIFIED: pip index versions] |
| langgraph-checkpoint-postgres | 3.0.5 | AsyncPostgresSaver — Postgres-backed checkpointer | Required for D-01 `AsyncPostgresSaver`. Latest 3.x release. [VERIFIED: pip index versions] |
| langchain-openai | 1.1.12 | ChatOpenAI wrapper with streaming for LangGraph nodes | Standard LangGraph + OpenAI integration. 1.x aligns with project's openai>=2.0.0. [VERIFIED: pip index versions] |
| langchain-core | latest compatible | LangGraph dependency (messages, base models) | Only install langchain-core — not full langchain. See CLAUDE.md version compat table. [CITED: CLAUDE.md] |
| psycopg | 3.3.3 | Psycopg3 async driver for AsyncPostgresSaver | Required by langgraph-checkpoint-postgres. [VERIFIED: pip index versions] |
| psycopg-pool | 3.3.0 | Connection pool for AsyncPostgresSaver | Required by langgraph-checkpoint-postgres for async pooled connections. [VERIFIED: pip index versions] |

### Already in pyproject.toml (no new install needed)

| Library | Version | Purpose |
|---------|---------|---------|
| openai | >=2.0.0,<3.0.0 | Direct AsyncOpenAI client already used in narrator.py |
| sqlalchemy | >=2.0.49 | `user_profile` and `signal_log` tables |
| asyncpg | >=0.29.0 | Existing Postgres async driver (SQLAlchemy engine) |
| redis | >=7.0.0 | Briefing cache read on session start |

**Note on driver coexistence:** The project uses `asyncpg` as the SQLAlchemy engine driver. `langgraph-checkpoint-postgres` uses `psycopg` (Psycopg3) directly for its own connections. These are independent — both can coexist in the same process without conflict. [ASSUMED — no official statement found, but architecturally independent connection pools]

### Installation

```bash
uv add "langgraph>=1.1.6" "langgraph-checkpoint-postgres>=3.0.5" "langchain-openai>=1.1.12" "psycopg[binary]>=3.3.3" "psycopg-pool>=3.3.0"
```

**Note:** Use `psycopg[binary]` variant unless building from source — avoids C compiler requirement. [CITED: psycopg docs]

---

## Architecture Patterns

### Recommended Project Structure

```
src/daily/
├── orchestrator/
│   ├── __init__.py
│   ├── graph.py          # StateGraph definition, node functions, graph.compile()
│   ├── state.py          # SessionState Pydantic model
│   ├── models.py         # Intent JSON response models (Pydantic)
│   └── session.py        # Session entry point (wraps graph.astream())
├── profile/
│   ├── __init__.py
│   ├── models.py         # UserProfile, UserPreferences Pydantic + ORM models
│   ├── service.py        # load_profile(), upsert_preference()
│   └── signals.py        # SignalLog ORM model + append_signal()
```

The `orchestrator/` package owns the LangGraph graph. The `profile/` package owns DB models and services for preferences and signals. The CLI is extended in the existing `cli.py` with a `profile_app` sub-typer.

### Pattern 1: AsyncPostgresSaver Initialization

The checkpointer is created once at app startup and held as application state. The `setup()` call creates LangGraph's checkpoint tables (idempotent — safe to call on every startup).

```python
# Source: langgraph-checkpoint-postgres PyPI README, langgraph GitHub
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# In FastAPI lifespan or app startup:
async def startup():
    checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url_psycopg)
    await checkpointer.setup()  # creates checkpoint tables, idempotent
    app.state.checkpointer = checkpointer
```

**Critical:** `AsyncPostgresSaver.from_conn_string()` requires a `psycopg`-format connection string (not `postgresql+asyncpg://`). The project already has `asyncpg`-format strings in `Settings`. A second `database_url_psycopg` settings field is needed:

```python
# settings addition
database_url_psycopg: str = "postgresql://daily:daily_dev@localhost:5432/daily"
```

[VERIFIED: langgraph-checkpoint-postgres README — `autocommit=True` and `row_factory=dict_row` required when passing manual connections. `from_conn_string()` handles these automatically.]

### Pattern 2: StateGraph Definition with Pydantic State

```python
# Source: StateGraph reference docs (reference.langchain.com)
from typing import Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel

class SessionState(BaseModel):
    messages: Annotated[list, add_messages]  # Q&A history with auto-append
    briefing_narrative: str = ""             # loaded from Redis cache on start
    active_user_id: int = 0
    preferences: dict = {}                   # loaded from user_profile table

builder = StateGraph(SessionState)
builder.add_node("respond", respond_node)
builder.add_node("summarise_thread", summarise_thread_node)
builder.add_edge(START, "respond")
graph = builder.compile(checkpointer=app.state.checkpointer)
```

### Pattern 3: Thread ID per User Session

Each user session gets a `thread_id`. The same `thread_id` across multiple `ainvoke`/`astream` calls resumes the same conversation (checkpointer loads previous state).

```python
# Source: StateGraph reference docs
config = {"configurable": {"thread_id": f"user-{user_id}-{date}"}}
async for chunk in graph.astream({"messages": [user_input]}, config=config):
    # yields state updates as they happen
    yield chunk
```

**Recommendation:** Use `f"user-{user_id}-{date}"` as `thread_id` so each day's briefing session has a fresh state. The `date` component prevents stale context from previous days bleeding into a new morning session.

### Pattern 4: Structured Intent JSON at Node Boundary (SEC-05)

Every LLM-calling node validates the response schema before returning. LLM never calls tools or holds credentials.

```python
# Pattern established in narrator.py — extend to orchestrator nodes
from pydantic import BaseModel

class OrchestratorIntent(BaseModel):
    action: str       # "answer" | "summarise_thread" | "skip"
    narrative: str    # text to return to user
    target_id: str | None = None  # email/thread id if action == "summarise_thread"

async def respond_node(state: SessionState) -> dict:
    raw = await llm.ainvoke(messages)
    intent = OrchestratorIntent.model_validate_json(raw.content)  # validates schema
    return {"messages": [AIMessage(content=intent.narrative)]}
```

### Pattern 5: Fire-and-Forget Signal Logging

Signals must not block the conversation turn. Use `asyncio.create_task()` to write without awaiting.

```python
# PERS-02 signal capture pattern
import asyncio

async def respond_node(state: SessionState, *, db_session) -> dict:
    # ... generate response ...
    # Non-blocking signal write:
    asyncio.create_task(
        append_signal(user_id=state.active_user_id, signal_type=SignalType.follow_up, ...)
    )
    return {"messages": [...]}
```

### Pattern 6: User Preferences Injected into Narrator System Prompt

Preferences are loaded at session start and stored in `SessionState.preferences`. The narrator node prepends a preamble derived from them.

```python
# PERS-01 preference injection
PREAMBLE_TEMPLATE = (
    "User preferences: tone={tone}, briefing_length={length}, "
    "category_order={order}.\n\n"
)

def build_narrator_system_prompt(preferences: dict) -> str:
    preamble = PREAMBLE_TEMPLATE.format(
        tone=preferences.get("tone", "conversational"),
        length=preferences.get("briefing_length", "standard"),
        order=", ".join(preferences.get("category_order", ["emails", "calendar", "slack"])),
    )
    return preamble + NARRATOR_SYSTEM_PROMPT  # existing Phase 2 prompt appended
```

### Anti-Patterns to Avoid

- **Using `invoke()` with an async checkpointer:** LangGraph hangs if you call `graph.invoke()` (sync) when the checkpointer is `AsyncPostgresSaver`. Always use `graph.ainvoke()` or `graph.astream()` in async contexts. [CITED: LangGraph GitHub issue #1800]
- **Sharing one checkpointer connection without pooling:** The `AsyncPostgresSaver` should use a connection pool (`psycopg-pool`) for concurrent sessions. Single connection will serialize all I/O.
- **Storing raw email bodies in SessionState:** Session state is persisted to Postgres by the checkpointer. Raw bodies must NOT enter `SessionState` — only summaries. This is SEC-04 enforcement at the LangGraph layer.
- **Re-running the briefing pipeline on every follow-up:** The orchestrator reads from Redis cache (D-11). Never re-trigger `pipeline.run()` during a session.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session state persistence across restarts | Custom Redis/Postgres state serialisation | `AsyncPostgresSaver` from `langgraph-checkpoint-postgres` | LangGraph owns serialisation, versioning, and conflict resolution for state |
| Message history management | Manual list append in session dict | `add_messages` annotation in `StateGraph` | LangGraph's `add_messages` handles de-dup, ordering, and type coercion automatically |
| Conversation routing logic | Custom if/else dispatcher | `add_conditional_edges()` in StateGraph | Built-in graph routing, debuggable via LangSmith/LangGraph Studio |
| JSON output validation from LLM | Ad-hoc `json.loads()` + key check | `Pydantic.model_validate_json()` | Type-safe, produces structured errors, consistent with existing narrator.py pattern |
| Async LLM calls | Direct `AsyncOpenAI` in LangGraph nodes | `ChatOpenAI` from `langchain-openai` | Natively compatible with LangGraph's `ainvoke`; streaming works via `astream_events` |

**Key insight:** LangGraph's checkpointer + StateGraph replaces an entire custom session management layer. The "don't hand-roll" rule applies most strongly here — session state serialisation has subtle edge cases (concurrent writes, schema migration) that LangGraph handles.

---

## Common Pitfalls

### Pitfall 1: asyncpg vs psycopg Connection String Mismatch

**What goes wrong:** `AsyncPostgresSaver.from_conn_string()` requires a `psycopg3` connection string (e.g. `postgresql://user:pass@host/db`). The project's existing `Settings.database_url` uses the SQLAlchemy asyncpg format (`postgresql+asyncpg://...`). Passing `+asyncpg` URL to the checkpointer causes `psycopg` to fail with an unrecognised scheme error.

**Why it happens:** Two different drivers with different DSN formats.

**How to avoid:** Add a second `Settings` field `database_url_psycopg: str` that uses plain `postgresql://` format.

**Warning signs:** `psycopg.errors.OperationalError: unknown/unsupported connection URL scheme`

### Pitfall 2: Calling graph.invoke() with AsyncPostgresSaver

**What goes wrong:** The application hangs silently when `graph.invoke()` (synchronous) is called on a compiled graph that has an async checkpointer. No error is raised — it just never returns.

**Why it happens:** Sync `invoke()` calls `asyncio.run()` internally but the async checkpointer already expects to be inside a running event loop.

**How to avoid:** Always use `graph.ainvoke()` or `graph.astream()` in async FastAPI/asyncio contexts.

**Warning signs:** Request hangs indefinitely, no exception, no log output. [CITED: LangGraph GitHub issue #1800]

### Pitfall 3: Pickle Deserialization Latency for Long Sessions

**What goes wrong:** LangGraph serialises state blobs via Python `pickle` into `checkpoint_blobs` (BYTEA in Postgres). Long conversation histories with large message lists can take several seconds to deserialise.

**Why it happens:** Pickle is opaque and requires full deserialization even for partial reads.

**How to avoid:** Keep `SessionState.messages` bounded. Consider capping history at N messages and summarising older turns (out of scope for Phase 3, but design the state model to support it). For Phase 3 with short briefing sessions, this is not a concern.

**Warning signs:** Increasing latency on returning sessions. [CITED: blog.lordpatil.com/posts/langgraph-postgres-checkpointer]

### Pitfall 4: Checkpointer Tables Not Created on First Run

**What goes wrong:** `AsyncPostgresSaver` raises table-not-found errors on first use if `.setup()` was not called.

**Why it happens:** LangGraph doesn't auto-create its tables.

**How to avoid:** Call `await checkpointer.setup()` in the FastAPI lifespan startup, not lazily. This is idempotent — safe to run every startup.

**Warning signs:** `asyncpg.exceptions.UndefinedTableError: relation "checkpoints" does not exist`

### Pitfall 5: Raw Email Bodies in LangGraph State

**What goes wrong:** If a `get_email_body()` response is placed directly into `SessionState` before redaction, the raw body is serialised to Postgres by the checkpointer — violating SEC-02/SEC-04.

**Why it happens:** LangGraph automatically persists everything in state.

**How to avoid:** The thread summarisation flow must pass through `summarise_and_redact()` before any summary enters `SessionState`. Only summaries (never raw bodies) go into state.

**Warning signs:** Email body content appearing in `checkpoint_blobs` Postgres rows.

---

## Code Examples

### Verified Pattern: Graph Compilation with AsyncPostgresSaver

```python
# Source: langgraph-checkpoint-postgres README (pypi.org/project/langgraph-checkpoint-postgres)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END

# 1. Create checkpointer (once, at startup)
checkpointer = AsyncPostgresSaver.from_conn_string(
    "postgresql://daily:daily_dev@localhost:5432/daily"
)
await checkpointer.setup()  # idempotent — creates LangGraph tables

# 2. Build graph
builder = StateGraph(SessionState)
builder.add_node("respond", respond_node)
builder.add_edge(START, "respond")
builder.add_edge("respond", END)
graph = builder.compile(checkpointer=checkpointer)

# 3. Invoke with thread_id
config = {"configurable": {"thread_id": "user-1-2026-04-07"}}
result = await graph.ainvoke({"messages": [HumanMessage(content="What emails do I have?")]}, config)
```

### Verified Pattern: Conditional Routing for On-Demand Thread Summarisation

```python
# Source: StateGraph reference docs (reference.langchain.com/python/langgraph/graph/state/StateGraph)
from langgraph.graph import StateGraph, START, END

def route_intent(state: SessionState) -> str:
    """Route to thread summarisation if last message requests it."""
    last_msg = state.messages[-1].content.lower()
    if "summarise" in last_msg or "summarize" in last_msg or "summary" in last_msg:
        return "summarise_thread"
    return "respond"

builder.add_conditional_edges(START, route_intent, {
    "respond": "respond",
    "summarise_thread": "summarise_thread",
})
```

### Verified Pattern: SQLAlchemy JSONB Column

```python
# Source: SQLAlchemy 2.0 docs + existing db/models.py patterns
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

class UserProfile(Base):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangGraph 0.2.x graph patterns | LangGraph 1.x (`StateGraph` with typed state, `context_schema`) | 2024 Q4 / 2025 | Breaking API changes — 1.x StateGraph constructor is `StateGraph(state_schema)`, not `StateGraph(state)` |
| `langgraph-checkpoint-postgres` 2.x | 3.x (current, aligns with langgraph 1.x) | 2025 Q1 | Pin `>=3.0.5` with `langgraph>=1.1.6` |
| `langchain-openai` 0.3.x | 1.x (current) | 2025 Q1 | Required for langgraph 1.x + openai>=2.0.0 compatibility |
| Per-session InMemorySaver | AsyncPostgresSaver | Ongoing | InMemorySaver is dev-only — sessions lost on restart. AsyncPostgresSaver is production-grade |

**Deprecated/outdated:**
- `langgraph.checkpoint.aiosqlite` — SQLite-backed async saver. Not suitable for production (single-writer). Use Postgres.
- Full `langchain` package install — Only `langchain-core` + `langchain-openai` needed. Full install causes dependency conflicts with the project's `openai>=2.0.0` pin. [CITED: CLAUDE.md version compat table]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | asyncpg (SQLAlchemy driver) and psycopg (LangGraph checkpointer) can coexist in the same process without conflict | Standard Stack | Low — they are independent connection pools, but if psycopg's `asyncio` event loop handling clashes with asyncpg's, a workaround (separate thread or process) may be needed |
| A2 | `langchain-openai 1.x` is compatible with `openai>=2.0.0,<3.0.0` pinned in pyproject.toml | Standard Stack | Medium — if langchain-openai pins an older openai version, `uv` will reject the resolution. Test: `uv add langchain-openai` and check solver output |
| A3 | `AsyncPostgresSaver.from_conn_string()` accepts a standard libpq DSN without additional pool configuration sufficient for Phase 3 load (single user, single session) | Architecture Patterns | Low risk for Phase 3. Production (multi-user) would require explicit pool size tuning |

---

## Open Questions (RESOLVED)

1. **langchain-openai compatibility with openai>=2.0.0**
   - What we know: `langchain-openai 1.1.12` is the latest. `openai>=2.0.0,<3.0.0` is pinned in the project.
   - What's unclear: Whether `langchain-openai 1.x` pins `openai<2.0` internally or supports 2.x.
   - Recommendation: Run `uv add "langchain-openai>=1.1.12"` during Wave 0 as a dependency resolution check. If it conflicts, fall back to using `AsyncOpenAI` directly in LangGraph nodes (the existing Phase 2 pattern from `narrator.py`) — this is a viable alternative since the project already uses `AsyncOpenAI` directly.

2. **thread_id TTL / cleanup strategy**
   - What we know: LangGraph checkpointer tables have no built-in TTL/cleanup.
   - What's unclear: Whether stale checkpoints (e.g. 30-day-old sessions) will accumulate unboundedly.
   - Recommendation: Out of scope for Phase 3 (single dev user). Flag for Phase 5+ as a maintenance concern. A nightly `DELETE FROM checkpoints WHERE created_at < NOW() - INTERVAL '7 days'` is sufficient.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | AsyncPostgresSaver, user_profile, signal_log | Assumed ✓ (Phase 1/2 running) | 15+ | — |
| Redis | Session start briefing cache read | Assumed ✓ (Phase 2 running) | 7.x | — |
| psycopg | AsyncPostgresSaver driver | Not yet installed | — | No fallback — required |
| psycopg-pool | AsyncPostgresSaver pooling | Not yet installed | — | No fallback — required |
| langgraph | Core orchestration | Not yet installed | — | No fallback — required |
| langgraph-checkpoint-postgres | Postgres checkpointer | Not yet installed | — | No fallback — required |
| langchain-openai | LangGraph OpenAI nodes | Not yet installed | — | Fallback: use `AsyncOpenAI` directly (already in project) |

**Missing dependencies with no fallback:**
- `psycopg`, `psycopg-pool`, `langgraph`, `langgraph-checkpoint-postgres` — must be installed in Wave 0

**Missing dependencies with fallback:**
- `langchain-openai` — if dependency conflicts arise, nodes can use `AsyncOpenAI` directly (same pattern as `narrator.py`). This would require more boilerplate per node.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `pytest tests/test_orchestrator*.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRIEF-07 | Thread summarisation on demand returns coherent narrative | unit (mock LLM + mock adapter) | `pytest tests/test_orchestrator_thread.py -x` | Wave 0 |
| PERS-01 | Preferences saved, loaded, and injected into narrator system prompt | unit | `pytest tests/test_profile_service.py -x` | Wave 0 |
| PERS-01 | CLI `daily config set profile.tone X` updates DB record | integration | `pytest tests/test_profile_cli.py -x` | Wave 0 |
| PERS-02 | Signals written to `signal_log` table with correct type and target | unit (fakeredis + in-memory DB) | `pytest tests/test_signal_log.py -x` | Wave 0 |
| D-03/SEC-05 | Orchestrator graph rejects LLM responses missing intent schema | unit | `pytest tests/test_orchestrator_graph.py::test_intent_validation -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_orchestrator*.py tests/test_profile*.py tests/test_signal*.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_orchestrator_graph.py` — covers D-03/SEC-05 intent validation and graph routing
- [ ] `tests/test_orchestrator_thread.py` — covers BRIEF-07 on-demand thread summarisation
- [ ] `tests/test_profile_service.py` — covers PERS-01 preference CRUD
- [ ] `tests/test_profile_cli.py` — covers PERS-01 CLI commands
- [ ] `tests/test_signal_log.py` — covers PERS-02 signal append

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Out of scope Phase 3 |
| V3 Session Management | yes | LangGraph `thread_id` keyed per user — do not allow cross-user `thread_id` access |
| V4 Access Control | no | Single-user Phase 3 |
| V5 Input Validation | yes | Pydantic `model_validate_json()` at every LLM node boundary (SEC-05) |
| V6 Cryptography | no | No new crypto — tokens already encrypted in Phase 1 |

### Known Threat Patterns for LangGraph + OpenAI Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via email content | Tampering | `summarise_and_redact()` runs before any email content enters LLM context — existing Phase 2 pattern |
| LLM-generated tool calls invoking APIs | Elevation of Privilege | SEC-05: no `tools=` parameter on any LLM call; `response_format=json_object` constrains output; Pydantic validation rejects unexpected keys |
| Session state leaking between users | Information Disclosure | `thread_id` scoped to `user-{user_id}-{date}` — never allow user-supplied `thread_id` |
| Raw email bodies persisted to checkpointer | Information Disclosure | Only summaries enter `SessionState`; redactor must run before state update |

---

## Sources

### Primary (HIGH confidence)
- `pypi.org/project/langgraph-checkpoint-postgres` — latest version (3.0.5), installation, AsyncPostgresSaver import paths, connection requirements [VERIFIED: PyPI]
- `pip index versions langgraph` — confirmed current version 1.1.6 [VERIFIED: pip registry]
- `pip index versions langchain-openai` — confirmed current version 1.1.12 [VERIFIED: pip registry]
- `pip index versions psycopg` — confirmed 3.3.3 [VERIFIED: pip registry]
- `reference.langchain.com/python/langgraph/graph/state/StateGraph` — StateGraph constructor, add_node, add_edge, compile, thread_id pattern [CITED]
- Existing codebase: `narrator.py`, `models.py`, `db/models.py`, `cli.py`, `config.py` — established patterns directly observed [VERIFIED: codebase read]
- `CLAUDE.md` §Technology Stack, §Version Compatibility — stack decisions and pinning constraints [CITED]

### Secondary (MEDIUM confidence)
- `blog.lordpatil.com/posts/langgraph-postgres-checkpointer` — AsyncPostgresSaver table schema, pickle blob performance characteristics [CITED]
- LangGraph GitHub issue #1800 — confirmed sync `invoke()` hangs with async checkpointer [CITED]

### Tertiary (LOW confidence)
- None — all critical claims verified or cited

---

## Metadata

**Confidence breakdown:**
- Standard stack versions: HIGH — all verified via pip index
- AsyncPostgresSaver API: HIGH — verified via PyPI README and reference docs
- LangGraph StateGraph API: HIGH — verified via reference docs
- asyncpg/psycopg coexistence: ASSUMED (A1) — architecturally sound but not explicitly documented
- langchain-openai + openai>=2.0.0 compatibility: ASSUMED (A2) — needs verification at install time

**Research date:** 2026-04-07
**Valid until:** 2026-05-07 (LangGraph releases frequently — recheck version pins before install)
