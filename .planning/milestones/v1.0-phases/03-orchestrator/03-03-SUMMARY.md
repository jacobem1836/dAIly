---
phase: 03-orchestrator
plan: 03
subsystem: cli, briefing
tags: [typer, preferences, narrator, user-profile, personalization, cli]

# Dependency graph
requires:
  - phase: 03-orchestrator
    plan: 01
    provides: UserPreferences Pydantic model, load_profile(), upsert_preference()
  - phase: 02-briefing-pipeline
    provides: NARRATOR_SYSTEM_PROMPT, generate_narrative, BriefingContext

provides:
  - _upsert_profile() async CLI helper with input validation (T-03-09)
  - _get_profile() async CLI helper for displaying preferences
  - daily config set profile.* routing in config_set command
  - daily config get profile command
  - build_narrator_system_prompt(preferences) function (D-05)
  - PREFERENCE_PREAMBLE constant with tone/length/order formatting
  - generate_narrative extended with optional preferences parameter
  - Adaptive max_tokens: concise=350, standard=650, detailed=900

affects: [phase-04, briefing-pipeline, voice-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Profile routing: key.startswith('profile.') check in config_set before existing briefing.* dispatch"
    - "Preference validation in CLI helper: Literal values checked before DB write (T-03-09)"
    - "build_narrator_system_prompt: preamble prepended to base prompt — preferences=None returns base unchanged"
    - "from __future__ import annotations: enables UserPreferences | None annotation without circular import"

key-files:
  created:
    - tests/test_profile_cli.py
    - tests/test_narrator_preferences.py
  modified:
    - src/daily/cli.py
    - src/daily/briefing/narrator.py

key-decisions:
  - "CLI validation rejects invalid tone/briefing_length values before DB write — satisfies T-03-09 without needing DB-level constraints"
  - "build_narrator_system_prompt accepts None for backward compatibility — existing callers require no changes"
  - "from __future__ import annotations used in narrator.py to avoid circular import with profile.models"
  - "max_tokens adjusted by briefing_length preference: concise=350, standard=650, detailed=900 — proportional to word count targets"

requirements-completed: [PERS-01]

# Metrics
duration: 12min
completed: 2026-04-07
---

# Phase 03 Plan 03: Profile CLI and Preference-Aware Narrator Summary

**CLI profile config commands wired to upsert_preference() service, and narrator system prompt extended with user preference preamble for personalised briefing tone and length**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-07T13:42:51Z
- **Completed:** 2026-04-07T13:54:00Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Tests:** 28 total (12 CLI + 16 narrator)
- **Files modified:** 4

## Accomplishments

- `_upsert_profile()` async CLI helper validates tone and briefing_length Literal values before writing to DB (T-03-09 mitigation)
- `_get_profile()` async CLI helper loads and formats current preferences for display
- `daily config set profile.*` routing: profile.* keys intercepted before existing briefing.* dispatch — fully backward compatible
- `daily config get profile` command displays current tone, briefing_length, and category_order
- `build_narrator_system_prompt(preferences)` function builds system prompt with optional preference preamble (D-05)
- `PREFERENCE_PREAMBLE` constant with {tone}, {length}, {order} placeholders including per-length word count targets
- `generate_narrative` signature extended with `preferences: UserPreferences | None = None` — all 7 existing narrator tests still pass
- Adaptive max_tokens: concise=350 (100-150 word target), standard=650 (225-300 word target), detailed=900 (350-450 word target)

## Task Commits

1. **Task 1 RED: Failing tests for profile CLI commands** - `d623e99` (test)
2. **Task 1 GREEN: CLI profile config commands** - `3ac9304` (feat)
3. **Task 2 RED: Failing tests for narrator preferences** - `9202ea8` (test)
4. **Task 2 GREEN: Narrator preference-aware system prompt** - `d3db46e` (feat)

## Files Created/Modified

- `src/daily/cli.py` — `_upsert_profile()`, `_get_profile()`, profile.* routing in config_set, config_get command
- `src/daily/briefing/narrator.py` — `PREFERENCE_PREAMBLE`, `build_narrator_system_prompt()`, extended `generate_narrative` signature
- `tests/test_profile_cli.py` — 12 tests: tone/briefing_length/category_order set, unknown key error, get profile, routing
- `tests/test_narrator_preferences.py` — 16 tests: build_narrator_system_prompt variants, backward compat, preference injection, max_tokens

## Decisions Made

- CLI validates preference values before DB write (T-03-09) — rejects invalid tone/briefing_length with error message including valid options
- `build_narrator_system_prompt(None)` returns unmodified `NARRATOR_SYSTEM_PROMPT` — no behavior change for existing callers
- `from __future__ import annotations` in narrator.py avoids circular import: narrator imports from briefing.models, profile.models imports independently
- max_tokens tuned proportionally to word count targets: 350/650/900 give ~2.3x range from concise to detailed

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — all preference values flow from DB to system prompt. `build_narrator_system_prompt` is fully wired; `generate_narrative` passes preferences through to system prompt construction.

## Threat Flags

No new threat surface. T-03-09 (CLI tone validation), T-03-10 (category_order injection, accepted), and T-03-11 (hardcoded user_id=1, accepted) all addressed as documented in plan threat model.

## Self-Check: PASSED

- FOUND: src/daily/cli.py contains `async def _upsert_profile(`
- FOUND: src/daily/cli.py contains `async def _get_profile(`
- FOUND: src/daily/cli.py contains `if key.startswith("profile."):`
- FOUND: src/daily/cli.py contains `"tone"` and `"briefing_length"` and `"category_order"` as valid keys
- FOUND: src/daily/cli.py contains `@config_app.command("get")`
- FOUND: src/daily/briefing/narrator.py contains `def build_narrator_system_prompt(preferences: UserPreferences | None = None) -> str:`
- FOUND: src/daily/briefing/narrator.py contains `PREFERENCE_PREAMBLE =`
- FOUND: src/daily/briefing/narrator.py contains `preferences: UserPreferences | None = None` in generate_narrative
- FOUND: src/daily/briefing/narrator.py contains `system_prompt = build_narrator_system_prompt(preferences)`
- FOUND: tests/test_profile_cli.py (12 tests pass)
- FOUND: tests/test_narrator_preferences.py (16 tests pass)
- FOUND commit d623e99 (Task 1 RED)
- FOUND commit 3ac9304 (Task 1 GREEN)
- FOUND commit 9202ea8 (Task 2 RED)
- FOUND commit d3db46e (Task 2 GREEN)
- All 28 new tests pass + all 7 existing narrator tests pass

---
*Phase: 03-orchestrator*
*Completed: 2026-04-07*
