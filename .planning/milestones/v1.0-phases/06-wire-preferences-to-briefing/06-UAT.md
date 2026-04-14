---
status: complete
phase: 06-wire-preferences-to-briefing
source: [06-01-SUMMARY.md]
started: 2026-04-14T00:00:00Z
updated: 2026-04-14T00:00:00Z
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Preferences flow into the LLM system prompt
expected: Run the test suite: `uv run python -m pytest tests/test_briefing_pipeline.py tests/test_narrator_preferences.py -v` — all 24 tests pass. Specifically, test_pipeline_forwards_preferences_to_narrator confirms that when a user has formal tone + concise briefing_length preferences set, those values appear in the system prompt passed to the LLM narrator — not just in pipeline kwargs, but actually injected into the prompt text.
result: pass

### 2. No-preferences backward compatibility
expected: test_pipeline_no_preferences_backward_compat passes — when preferences=None (no profile set), the briefing pipeline still runs successfully and no tone/length preamble is injected into the narrator system prompt. Old code paths continue to work.
result: pass

### 3. Scheduler loads preferences from user profile
expected: test_build_pipeline_kwargs_includes_preferences passes — the APScheduler cron job calls load_profile(user_id, session) and the returned dict contains a "preferences" key. This confirms the wiring from scheduler → pipeline is complete, not just pipeline → narrator.
result: pass

### 4. End-to-end wiring chain is intact
expected: Manually trace the wiring: `_scheduled_pipeline_run` → `_build_pipeline_kwargs` (loads profile) → `run_briefing_pipeline(..., preferences=prefs)` → `generate_narrative(context, client, preferences=prefs)` → `build_narrator_system_prompt(prefs)`. You can verify by reading scheduler.py and confirming load_profile is called and "preferences" key is returned in the kwargs dict.
result: pass

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
