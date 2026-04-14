---
plan: "06-01"
phase: 6
status: complete
committed: true
---

# Summary: Wire load_profile into briefing pipeline and scheduler cron

## What was built

Closed the PERS-01 gap: user preferences (tone, briefing_length, category_order) stored in `UserProfile` are now loaded by the APScheduler cron job and applied to the precomputed morning briefing narrative.

## Changes made

**src/daily/briefing/narrator.py**
- Added explicit `from daily.profile.models import UserPreferences` import (previously deferred via `from __future__ import annotations`)

**src/daily/briefing/pipeline.py**
- Added `from daily.profile.models import UserPreferences` import
- Added `preferences: UserPreferences | None = None` as last parameter of `run_briefing_pipeline()`
- Forward `preferences` to `generate_narrative(context, openai_client, preferences=preferences)`

**src/daily/briefing/scheduler.py**
- Added `from daily.profile.service import load_profile` import
- Added `load_profile(user_id, session)` call in `_build_pipeline_kwargs` after VIP senders block
- Added `"preferences": preferences` to the returned dict

**tests/test_briefing_pipeline.py**
- `test_pipeline_forwards_preferences_to_narrator`: verifies formal/concise prefs appear in narrator LLM system prompt
- `test_pipeline_no_preferences_backward_compat`: verifies omitted preferences works, no preamble injected
- `test_build_pipeline_kwargs_includes_preferences`: mocks load_profile, asserts "preferences" key in returned dict

**pyproject.toml**
- Added `pythonpath = ["src"]` to `[tool.pytest.ini_options]` — fixes pytest discovery for src-layout project

## Verification

```
uv run python -m pytest tests/test_briefing_pipeline.py tests/test_narrator_preferences.py -v
24 passed in 0.48s
```

All 6 acceptance criteria from the plan passed.

## Wiring chain

```
APScheduler cron
  → _scheduled_pipeline_run(user_id)
  → _build_pipeline_kwargs(user_id, settings)
      → load_profile(user_id, session)  ← NEW
  → run_briefing_pipeline(..., preferences=prefs)  ← NEW param
  → generate_narrative(context, client, preferences=prefs)
  → build_narrator_system_prompt(prefs)
      → injects tone/briefing_length/category_order into LLM system prompt
```
