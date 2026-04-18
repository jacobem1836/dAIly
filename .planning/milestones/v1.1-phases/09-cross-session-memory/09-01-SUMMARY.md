---
phase: 09-cross-session-memory
plan: "01"
subsystem: memory
tags: [pgvector, orm, migration, preferences, test-scaffold]
dependency_graph:
  requires: []
  provides:
    - pgvector Python package installed
    - MemoryFact ORM model (daily.db.models)
    - Alembic migration 005 (memory_facts table + HNSW index)
    - UserPreferences.memory_enabled flag
    - tests/test_memory.py scaffold (Wave 0 passing + stubs)
    - async_db_session fixture in tests/conftest.py
  affects:
    - src/daily/db/models.py
    - src/daily/profile/models.py
    - alembic/versions/
    - tests/
tech_stack:
  added:
    - pgvector>=0.3.0 (Python package for SQLAlchemy VECTOR type)
  patterns:
    - HNSW index created via raw DDL in Alembic (not in __table_args__)
    - UUID primary key via Python-side default lambda: str(uuid.uuid4())
    - Pydantic bool field with default True for safe JSONB round-trip
key_files:
  created:
    - alembic/versions/005_add_memory_facts.py
    - tests/test_memory.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/daily/db/models.py
    - src/daily/profile/models.py
    - tests/conftest.py
decisions:
  - HNSW index placed in Alembic migration DDL, not ORM __table_args__, per RESEARCH.md Pattern 2 — enables pgvector-specific syntax (m=16, ef_construction=64) unavailable via SQLAlchemy Index abstraction
  - Vector dimension 1536 matches text-embedding-3-small (OpenAI); consistent with Plan 02 extraction layer expectation
  - memory_enabled defaults to True (opt-out, not opt-in) per D-05 — safe for existing users on JSONB round-trip
  - downgrade does NOT drop pgvector extension — future phases may depend on it
metrics:
  duration: "~12 minutes"
  completed: "2026-04-17"
  tasks: 3
  files_changed: 6
---

# Phase 09 Plan 01: Cross-Session Memory Foundation Summary

**One-liner:** pgvector installed, MemoryFact ORM defined with Vector(1536) HNSW-indexed embedding, migration 005 chained from 004, memory_enabled gate added to UserPreferences, test scaffold with 3 passing Wave 0 tests and 8 skipped stubs for Plans 02-04.

## What Was Built

### Task 1 — pgvector dependency + MemoryFact ORM model

Added `pgvector>=0.3.0` to `pyproject.toml` and ran `uv sync` to install and lock the package. Added `from pgvector.sqlalchemy import Vector` and `import uuid` to `src/daily/db/models.py`, then defined:

```
class MemoryFact(Base):
    __tablename__ = "memory_facts"
    id: Mapped[str]          # UUID text PK, Python-side default
    user_id: Mapped[int]     # FK -> users.id
    fact_text: Mapped[str]
    embedding: Mapped[list[float]]  # Vector(1536)
    source_session_id: Mapped[str]
    created_at: Mapped[datetime]    # server_default now()
```

### Task 2 — Alembic migration 005

Confirmed `uv run alembic heads` returned `004` before creating the migration.

Created `alembic/versions/005_add_memory_facts.py`:
- `CREATE EXTENSION IF NOT EXISTS vector` (idempotent)
- `op.create_table("memory_facts", ...)` with all six columns
- `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`
- `down_revision = "004"` — correct chain
- Downgrade drops table only, leaves extension in place

Note: `uv run alembic upgrade head` was NOT applied — no running Postgres available in this execution context. Migration will apply in CI or when the developer runs it locally.

### Task 3 — memory_enabled flag + test scaffold

Added `memory_enabled: bool = True` field to `UserPreferences` with Phase 9 docstring section explaining the D-05 hard gate semantics.

Created `tests/test_memory.py` with 11 test functions:
- 3 Wave 0 tests (run now, no DB): `test_memory_enabled_defaults_to_true`, `test_memory_enabled_round_trips_false`, `test_memory_enabled_missing_key_defaults_to_true`
- 4 Wave 1 stubs (Plan 02 extraction): `test_extract_facts_stores_embedding`, `test_extraction_skipped_when_disabled`, `test_dedup_prevents_duplicate_insert`, `test_extraction_swallows_errors`
- 3 Wave 1 stubs (Plan 03 retrieval): `test_retrieve_relevant_facts`, `test_retrieval_skipped_when_disabled`, `test_session_state_includes_memories`
- 1 Wave 2 stub (Plan 04 wiring): `test_no_hallucination_loop`

Added `async_db_session` fixture to `tests/conftest.py` — skips automatically when `DATABASE_URL` is not set.

## Verification Results

```
uv run pytest tests/test_memory.py -q
...ssssssss
3 passed, 8 skipped in 0.18s

from daily.db.models import MemoryFact
MemoryFact.__tablename__ == "memory_facts"  # OK
MemoryFact.__table__.columns["embedding"].type.dim == 1536  # OK

from daily.profile.models import UserPreferences
UserPreferences().memory_enabled is True  # OK
```

## Alembic Migration Status

- **Confirmed head before migration:** `004 (head)`
- **`uv run alembic upgrade head` applied locally:** NO — no Postgres available during execution. Migration file is complete and verified via module import test. Apply on next `docker compose up` + `uv run alembic upgrade head`.
- **pgvector version pinned by `uv sync`:** 0.3.6 (latest compatible with `>=0.3.0`)

## Commits

| Hash | Task | Description |
|------|------|-------------|
| fff9cff | Task 1 | feat(09-01): add pgvector dependency and MemoryFact ORM model |
| 702319d | Task 2 | feat(09-01): create Alembic migration 005 for memory_facts table and HNSW index |
| 504fcf5 | Task 3 | feat(09-01): add memory_enabled to UserPreferences; scaffold test_memory.py |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

All Wave 1/2 test stubs are explicitly marked `@pytest.mark.skip(reason="pending Plan 02/03/04 implementation")`. They collect without failure. Plans 02, 03, and 04 are responsible for replacing the `raise NotImplementedError` bodies with real assertions and removing the skip markers.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundary crossings introduced. The `memory_facts` table includes the required FK `user_id -> users.id` (T-09-02 mitigation) enforced at schema level. Pydantic bool field with `default=True` resolves T-09-01 (malformed JSONB rows default safely).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/daily/db/models.py | FOUND |
| src/daily/profile/models.py | FOUND |
| alembic/versions/005_add_memory_facts.py | FOUND |
| tests/test_memory.py | FOUND |
| Commit fff9cff | FOUND |
| Commit 702319d | FOUND |
| Commit 504fcf5 | FOUND |
