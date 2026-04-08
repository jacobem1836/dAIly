---
status: resolved
trigger: "UAT Tests 2, 3, 4, 6 fail with ForeignKeyViolationError — user_id=1 hardcoded but no users row"
created: 2026-04-08
updated: 2026-04-08
---

## Current Focus

hypothesis: confirmed — upsert_preference FK violation fixed by auto-creating default user
test: ran pytest tests/test_profile_service.py — 15/15 pass
next_action: archived

## Symptoms

expected: `daily config set profile.tone casual` prints confirmation and writes to DB
actual: ForeignKeyViolationError — user_profile FK to users table fails, no user row with id=1 exists
errors: `ForeignKeyViolationError: insert or update on table "user_profile" violates foreign key constraint "user_profile_user_id_fkey" — Key (user_id)=(1) is not present in table "users".`
reproduction: Run `PYTHONPATH=src uv run daily config set profile.tone casual`
started: Since Phase 03 implementation — hardcoded user_id=1 was an accepted stub

## Eliminated

- hypothesis: FK constraint missing or wrong
  evidence: migration 003 correctly defines FK from user_profile.user_id → users.id
  timestamp: 2026-04-08

## Evidence

- timestamp: 2026-04-08
  checked: src/daily/cli.py
  found: all profile/config/vip commands hardcode user_id=1
  implication: any FK-constrained table touched before users row exists will fail

- timestamp: 2026-04-08
  checked: src/daily/db/models.py User model
  found: users table only requires id (created_at has server default, no email column)
  implication: INSERT INTO users (id=1) is sufficient to satisfy FK

- timestamp: 2026-04-08
  checked: sqlalchemy.dialects.postgresql.insert vs generic sqlalchemy.insert
  found: on_conflict_do_nothing only available on PostgreSQL dialect insert
  implication: must use pg_insert from sqlalchemy.dialects.postgresql

## Resolution

root_cause: upsert_preference called without a parent users row. The user_profile table has a FK to users.id. cli.py hardcodes user_id=1 (T-03-11 stub) but no seed data creates that row.
fix: Added `_ensure_default_user(user_id, session)` to `src/daily/profile/service.py` using `pg_insert(User).values(id=user_id).on_conflict_do_nothing()`. Called at the top of `upsert_preference()` before any profile write. Added test `test_ensure_default_user_executes_insert` and updated `test_upsert_preference_creates_row_when_none_exists` to assert execute is called twice.
verification: pytest tests/test_profile_service.py — 15/15 passed
files_changed:
  - src/daily/profile/service.py
  - tests/test_profile_service.py
