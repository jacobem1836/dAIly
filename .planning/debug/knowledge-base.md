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

## uvicorn-startup-hang — Uvicorn reloader starts but worker never prints "Application startup complete"
- **Date:** 2026-05-06
- **Error patterns:** uvicorn hang, reloader process, application startup complete, port 8000, worker process
- **Root cause:** Stale uvicorn process from a prior dev session was holding port 8000. The new uvicorn's reloader process started fine (it doesn't bind to the port), but the forked worker subprocess couldn't bind and silently failed. No code error — the recent code changes were all correct.
- **Fix:** Kill the stale uvicorn process holding port 8000. Check with `lsof -i :8000` before assuming the bug is in code.
- **Files changed:** (none — no code change needed)
---

