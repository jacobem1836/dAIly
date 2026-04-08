# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## test2-profile-config-fk-violation — ForeignKeyViolationError on user_profile upsert with hardcoded user_id
- **Date:** 2026-04-08
- **Error patterns:** ForeignKeyViolationError, user_profile, user_id_fkey, users, insert, upsert_preference
- **Root cause:** upsert_preference() wrote to user_profile (FK → users.id) with hardcoded user_id=1, but no users row existed in the database
- **Fix:** Added _ensure_default_user() to service.py using pg_insert(User).values(id=user_id).on_conflict_do_nothing() called at the top of upsert_preference(). Uses sqlalchemy.dialects.postgresql.insert (not generic sqlalchemy.insert) since on_conflict_do_nothing is PostgreSQL-dialect-only.
- **Files changed:** src/daily/profile/service.py, tests/test_profile_service.py
---

