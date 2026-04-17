---
phase: 07-tech-debt-fixes
plan: "01"
subsystem: briefing-ranker
tags: [ranker, scheduler, rfc2822, email-normalization, user-profile, alembic]
dependency_graph:
  requires: []
  provides: [FIX-01-ranker-rfc2822, FIX-01-scheduler-user-email]
  affects: [briefing-pipeline, ranker, scheduler, user-profile]
tech_stack:
  added: [email.utils.parseaddr]
  patterns: [rfc2822-normalization, db-query-on-schedule]
key_files:
  created:
    - alembic/versions/006_add_user_profile_email.py
  modified:
    - src/daily/briefing/ranker.py
    - src/daily/briefing/scheduler.py
    - src/daily/profile/models.py
    - tests/test_briefing_ranker.py
    - tests/test_briefing_scheduler.py
decisions:
  - "Use email.utils.parseaddr (stdlib) for RFC 2822 normalization — no new dependency"
  - "Add UserProfile.email as nullable String(255) column — DB-authoritative source for user_email"
  - "UserProfile import moved to module level in scheduler.py — avoids circular import concern but OK here since profile.models has no scheduler dependency"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-17T13:12:49Z"
  tasks_completed: 2
  files_changed: 5
---

# Phase 07 Plan 01: FIX-01 RFC 2822 Ranker Normalization Summary

**One-liner:** RFC 2822 address normalization via `email.utils.parseaddr` in `_is_direct_recipient`, and `user_email` populated from `user_profile.email` DB column instead of hardcoded empty string.

## What Was Built

Two coordinated fixes that together ensure `WEIGHT_DIRECT` (10pts) fires correctly for emails sent directly to the user:

1. **Ranker fix** (`src/daily/briefing/ranker.py`): `_is_direct_recipient` now uses `email.utils.parseaddr` to normalize both sides before comparison. RFC 2822 formatted addresses like `"Alice <alice@example.com>"` are correctly parsed to bare `alice@example.com` before matching. Empty `user_email` short-circuits to `False`.

2. **Scheduler fix** (`src/daily/briefing/scheduler.py`): `_build_pipeline_kwargs` replaces the `user_email = ""` stub with a DB query on `UserProfile.email`. Returns empty string as fallback when no profile row exists or email column is NULL.

3. **Model change** (`src/daily/profile/models.py`): `UserProfile` gains a nullable `email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)` column.

4. **Migration** (`alembic/versions/006_add_user_profile_email.py`): Adds the `email` column to `user_profile` table (down_revision: 005).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 (email column + scheduler) | `0965e72` | feat(07-03): resolve message_id — included profile/scheduler changes |
| Task 2 (ranker normalization) | `59685ff` | feat(07-01): normalize RFC 2822 addresses in ranker _is_direct_recipient |

> Note: Task 1 changes were committed by the parallel 07-03 agent running in the same worktree. The file changes are identical to what this plan specifies.

## Test Results

All 18 tests pass:
- `tests/test_briefing_ranker.py`: 12 tests (6 new RFC 2822 tests, 6 existing)
- `tests/test_briefing_scheduler.py`: 6 tests (3 new user_email tests, 3 existing)

```
18 passed in 1.91s
```

## Decisions Made

1. **`email.utils.parseaddr` over custom regex**: stdlib, handles edge cases correctly, no new dependency.
2. **Nullable email column**: allows gradual population — existing users without email set get `""` fallback in scheduler.
3. **Module-level UserProfile import in scheduler**: safe since `daily.profile.models` has no scheduler dependency. Consistent with other module-level imports.

## Deviations from Plan

### Coordination Note

**Task 1 committed by parallel agent:** The parallel 07-03 worktree agent committed the Task 1 changes (profile model, migration, scheduler fix, scheduler tests) in commit `0965e72` while this agent was preparing to commit them. The changes are identical to the plan specification — verified by `git show`. This plan's agent committed Task 2 (ranker fix) independently at `59685ff`.

No functional deviations — plan executed exactly as written.

## Verification

- `src/daily/briefing/ranker.py` contains `from email.utils import parseaddr`: PASS
- `_is_direct_recipient` uses `parseaddr(user_email)` and `parseaddr(r`: PASS
- `user_email = ""` no longer exists in `scheduler.py`: PASS
- `scheduler.py` contains `select(UserProfile.email).where(UserProfile.user_id == user_id)`: PASS
- `UserProfile` has `email: Mapped[str | None]` column: PASS
- `alembic/versions/006_add_user_profile_email.py` has `op.add_column('user_profile'`: PASS
- `tests/test_briefing_ranker.py` contains RFC 2822 tests: PASS (6 new tests)
- `tests/test_briefing_scheduler.py` contains 3 new user_email tests: PASS
- All tests pass (18/18): PASS

## Known Stubs

None — all stubs from this plan have been resolved.

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced. Threat model analysis per plan:
- T-07-01: `parseaddr` handles malformed input gracefully (returns empty string) — empty user_email returns False, no false WEIGHT_DIRECT.
- T-07-02: `user_email` used only for scoring comparison, never logged or passed to LLM.

## Self-Check: PASSED

All files exist and commits are present in git history.
