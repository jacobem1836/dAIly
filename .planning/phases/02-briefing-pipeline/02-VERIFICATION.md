---
phase: 02-briefing-pipeline
verified: 2026-04-07T11:00:00Z
status: gaps_found
score: 5/6 must-haves verified
re_verification: false
gaps:
  - truth: "User can configure the precompute schedule time and the change persists across restarts"
    status: failed
    reason: "CLI saves schedule to briefing_config DB table, but main.py reads only Settings.briefing_schedule_time (env var / .env file) on startup — it never reads the DB value. The main.py docstring explicitly documents this as a 'future enhancement'. BRIEF-02 is partially satisfied: the CLI write path exists, the read-at-startup path does not."
    artifacts:
      - path: "src/daily/main.py"
        issue: "Reads Settings.briefing_schedule_time from env only; does not query BriefingConfig table on startup"
      - path: "src/daily/cli.py"
        issue: "config_set correctly writes to DB but the value is never read back by the scheduler on next start"
    missing:
      - "main.py lifespan must query BriefingConfig from DB for user_id=1 on startup and use schedule_hour/schedule_minute if a row exists, falling back to Settings.briefing_schedule_time otherwise"
---

# Phase 2: Briefing Pipeline Verification Report

**Phase Goal:** The system produces a ranked, LLM-generated briefing narrative on a precomputed schedule every morning
**Verified:** 2026-04-07
**Status:** gaps_found — 1 gap blocking full BRIEF-02 compliance
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Briefing is precomputed and cached in Redis overnight (default 05:00) — serving from cache takes under 1 second | VERIFIED | cache.py stores BriefingOutput with TTL=86400; test_briefing_pipeline.py::test_get_or_generate_cache_hit confirms <0.1s; scheduler.py sets up CronTrigger at configured hour/minute |
| 2 | User can configure the precompute schedule time and the change persists across restarts | FAILED | CLI writes to briefing_config DB table (schedule_hour/schedule_minute), but main.py reads only Settings.briefing_schedule_time (env var) at startup — DB config is never consulted. Explicitly deferred in main.py docstring. |
| 3 | Briefing correctly ranks emails by heuristic priority (sender weight, deadline keywords, thread activity recency) | VERIFIED | ranker.py implements all four scoring components; score_email(), rank_emails(), _is_direct_recipient() all present and tested with 6 passing tests including VIP override, recency decay, CC vs direct, and substring guard |
| 4 | Briefing includes today's and next 48h calendar events with conflict detection noted | VERIFIED | context_builder.py fetches events with since=now, until=now+48h; find_conflicts() does sorted sweep; CalendarContext.conflicts populated; to_prompt_string() includes "Conflicts detected:" line |
| 5 | Briefing includes Slack mentions and DMs from priority channels | VERIFIED | context_builder.py filters `is_mention or is_dm`; SlackContext populated; to_prompt_string() includes SLACK section |
| 6 | External data passes through a summarisation/redaction layer before reaching the LLM — no raw bodies in LLM context | VERIFIED | redactor.py runs GPT-4.1-mini per-item summarisation + credential strip; pipeline.py explicitly passes email_bodies and slack_texts (extracted from context.raw_bodies) to redact_emails/redact_messages before calling generate_narrative; context.raw_bodies.clear() called after redaction; BriefingContext.raw_bodies has Field(exclude=True) preventing serialisation |

**Score:** 5/6 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/daily/briefing/models.py` | Pipeline data models | VERIFIED | BriefingContext, RankedEmail, CalendarContext, SlackContext, BriefingOutput, RedactedItem all present; to_prompt_string() fully implemented; raw_bodies has Field(exclude=True) |
| `src/daily/integrations/base.py` | Extended adapter interfaces | VERIFIED | get_email_body abstract on EmailAdapter; get_message_text abstract on MessageAdapter |
| `src/daily/db/models.py` | DB models for briefing config and VIP senders | VERIFIED | BriefingConfig with schedule_hour/minute/email_top_n/slack_channels ARRAY; VipSender with explicit UniqueConstraint uq_vip_user_email |
| `alembic/versions/56a7489e1608_add_briefing_config_vip_senders.py` | Migration | VERIFIED | Creates briefing_config and vip_senders tables; uq_vip_user_email constraint present |
| `src/daily/briefing/ranker.py` | Heuristic email scoring | VERIFIED | score_email(), rank_emails(), _is_direct_recipient(); WEIGHT_VIP=40, DEADLINE_KEYWORDS; per-address split, not substring |
| `src/daily/briefing/context_builder.py` | Pipeline context assembly | VERIFIED | build_context(), find_conflicts(), _fetch_all_emails() with pagination; asyncio.gather for concurrent body fetches; try/except isolation per phase |
| `src/daily/briefing/redactor.py` | Per-item summarisation + credential stripping | VERIFIED | CREDENTIAL_PATTERN with bounded capture; strip_credentials(); summarise_and_redact() with Semaphore(3); redact_emails(); redact_messages() |
| `src/daily/briefing/narrator.py` | LLM narrative generation | VERIFIED | NARRATOR_SYSTEM_PROMPT enforces 300-word limit, no lists, three-source structure; generate_narrative() with response_format=json_object, max_tokens=650; narrative key validation; retry-once + fallback |
| `src/daily/briefing/cache.py` | Redis cache read/write | VERIFIED | cache_briefing() with TTL=86400; get_briefing(); UTC date cache keys |
| `src/daily/briefing/scheduler.py` | APScheduler integration | VERIFIED | AsyncIOScheduler; setup_scheduler(); _build_pipeline_kwargs(); _scheduled_pipeline_run(); update_schedule() via reschedule_job |
| `src/daily/briefing/pipeline.py` | End-to-end pipeline orchestrator | VERIFIED | run_briefing_pipeline() chains build_context -> redact_emails -> redact_messages -> generate_narrative -> cache_briefing; context.raw_bodies.clear() after redaction; get_or_generate_briefing() for cache miss fallback |
| `src/daily/cli.py` | Config and VIP CLI commands | VERIFIED | config set (briefing.schedule_time, briefing.email_top_n) via asyncio.run(); vip add/remove/list via asyncio.run() |
| `src/daily/main.py` | FastAPI lifespan with scheduler start | VERIFIED | lifespan context manager calls setup_scheduler then scheduler.start() on boot; scheduler.shutdown on exit; /health endpoint |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| pipeline.py | context_builder.py | calls build_context | WIRED | Line 78: `context = await build_context(...)` |
| pipeline.py | redactor.py | calls redact_emails(context.emails, context.raw_bodies) | WIRED | Lines 96-104: email_bodies extracted from context.raw_bodies; redact_emails called |
| pipeline.py | narrator.py | calls generate_narrative | WIRED | Line 121: `output = await generate_narrative(context, openai_client)` |
| pipeline.py | cache.py | calls cache_briefing | WIRED | Line 124: `await cache_briefing(redis, user_id, output)` |
| scheduler.py | pipeline.py | _scheduled_pipeline_run calls run_briefing_pipeline | WIRED | Line 134: `await run_briefing_pipeline(user_id=user_id, **kwargs)` |
| main.py | scheduler.py | FastAPI lifespan starts scheduler | WIRED | Lines 45-46: `setup_scheduler(...)`, `scheduler.start()` |
| context_builder.py | ranker.py | calls rank_emails | WIRED | Line 166: `ranked_emails = rank_emails(all_emails, vip_senders, user_email, top_n=top_n)` |
| redactor.py | openai AsyncOpenAI | GPT-4.1-mini for per-item summarisation | WIRED | Line 83: `model="gpt-4.1-mini"` in summarise_and_redact |
| narrator.py | openai AsyncOpenAI | GPT-4.1 for narrative generation | WIRED | Line 75: `model="gpt-4.1"` in generate_narrative |
| cli.py (config set) | briefing_config DB | writes schedule to DB | WIRED | _upsert_config() sets schedule_hour/schedule_minute |
| main.py | briefing_config DB | reads schedule on startup | NOT_WIRED | main.py reads Settings.briefing_schedule_time (env) only; never queries BriefingConfig table |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| pipeline.py | context | build_context() from adapters | Yes — adapters call real APIs; bodies fetched and stored in context.raw_bodies | FLOWING |
| pipeline.py | email_bodies | context.raw_bodies by message_id | Yes — populated in context_builder via get_email_body() calls | FLOWING |
| pipeline.py | context.slack.summaries | redact_messages() result | Yes — returns dict of summaries | FLOWING |
| cache.py | payload | BriefingOutput narrative | Yes — only stores narrative/generated_at/version, never raw bodies (SEC-02) | FLOWING |
| scheduler.py | user_email | hardcoded `""` in _build_pipeline_kwargs | No — user_email never populated from DB; ranker's WEIGHT_DIRECT path always fails silently | STATIC |

**Note on user_email gap:** `_build_pipeline_kwargs()` in scheduler.py sets `user_email = ""` and never queries the DB for the user's actual email address. This means the ranker always assigns WEIGHT_CC (2) to direct-to-user emails instead of WEIGHT_DIRECT (10) when called from the scheduler. VIP senders still get WEIGHT_VIP (40). This is a warning-level concern — ranking works but direct-recipient boost is always missed in scheduled runs.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 2 tests pass | `PYTHONPATH=src uv run --with pytest --with pytest-asyncio pytest tests/ -q` | 157 passed, 8 warnings | PASS |
| Briefing models importable | `uv run python -c "from daily.briefing.models import BriefingContext, BriefingOutput"` | Checked via test suite | PASS |
| BriefingContext.raw_bodies excluded from serialisation | `BriefingContext(...).model_dump()` not containing raw_bodies | Confirmed by test_briefing_models.py | PASS |
| Credential stripping regex works on JSON context | test_credential_strip_json_context | 15/15 redactor tests pass | PASS |
| Cache TTL set correctly | test_briefing_cache.py::test_cache_briefing | Confirms TTL=86400 | PASS |
| Scheduler reschedule works | test_briefing_scheduler.py::test_scheduler_reschedule | Passes | PASS |

**Note:** pytest-asyncio is in pyproject.toml dev deps (`pytest-asyncio>=1.3.0`) but the venv pytest binary appears to have a naming collision with another pytest installation on this machine (`pytest 2` vs `pytest`). All tests pass correctly when invoked via `uv run --with pytest --with pytest-asyncio pytest` or directly via the venv, confirming the test failures seen with bare `uv run --with pytest` were an env-level issue, not code failures.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BRIEF-01 | 02-04 | Precomputed morning briefing cached for instant delivery | SATISFIED | cache.py + pipeline.py; get_or_generate_briefing serves from cache; test confirms <0.1s cache hit |
| BRIEF-02 | 02-04 | User can configure precompute schedule time | PARTIAL | CLI writes schedule to DB; but main.py does NOT read DB schedule on startup — only reads env var. Config write path exists, read-at-restart path missing. |
| BRIEF-03 | 02-01, 02-02 | Email ranking by heuristic priority | SATISFIED | ranker.py: sender weight, deadline keywords, thread activity, recency; all tests pass |
| BRIEF-04 | 02-02 | Calendar events (today + 48h) with conflict detection | SATISFIED | context_builder.py fetches since=now, until=now+48h; find_conflicts() sweep; CalendarContext.conflicts |
| BRIEF-05 | 02-02 | Slack mentions, DMs, priority channels | SATISFIED | context_builder.py filters is_mention or is_dm; SlackContext populated |
| BRIEF-06 | 02-03 | LLM narrative from pre-ranked, pre-summarised context — no raw data to LLM | SATISFIED | redactor.py per-item summarisation; narrator.py receives BriefingContext with summaries, not raw bodies; context.raw_bodies.clear() after redaction |
| PERS-03 | 02-01, 02-02 | Heuristic defaults at cold start: sender importance, deadline keywords, thread activity | SATISFIED | ranker.py implements all three heuristic components as defaults |
| SEC-02 | 02-03 | Pre-filter/redaction layer sanitises external data before LLM | SATISFIED | redactor.py credential stripping + GPT-4.1-mini summarisation; pipeline passes email_bodies/slack_texts (extracted from raw_bodies) to redactor before narrator; raw_bodies cleared after; Field(exclude=True) on BriefingContext |
| SEC-05 | 02-03 | LLM tool-call outputs are intents only; LLM never holds credentials or calls APIs | SATISFIED | narrator.py: response_format=json_object; no tools= or function_call= parameters; narrative key validated; LLM receives only pre-summarised text |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/daily/briefing/scheduler.py | 83 | `user_email = ""` — hardcoded empty, never populated from DB | Warning | Ranker always assigns WEIGHT_CC to direct-to-user emails in scheduled runs; WEIGHT_DIRECT (10 pts) path never fires |
| src/daily/briefing/context_builder.py | 116 | `_fetch_all_messages` pagination bug — cursor tracked but never passed to next page call | Warning | Slack pagination effectively broken: multi-page results would loop infinitely (if cursor always returned) or silently miss later pages. Single-page scenarios unaffected for M1. |

Neither anti-pattern is classified as a Blocker because:
1. The `user_email` issue degrades ranking quality but does not prevent briefing generation.
2. The Slack pagination bug only affects multi-page Slack workspaces. M1 single-user with small Slack workspace is unaffected.

---

## Human Verification Required

### 1. DB Schedule Config Read-at-Startup

**Test:** Run `daily config set briefing.schedule_time 07:00`, then restart the server and check scheduler logs to confirm it starts at 07:00 instead of 05:00.
**Expected:** Scheduler should use the DB-stored schedule (07:00), not the env default (05:00).
**Why human:** Requires actually running the CLI, restarting the server, and observing scheduler startup logs. The code clearly shows this path does NOT exist today — main.py never reads briefing_config from the DB.

### 2. End-to-End Pipeline with Real Credentials

**Test:** With valid OPENAI_API_KEY, Google/Slack tokens connected, trigger `run_briefing_pipeline` manually and verify the cached BriefingOutput in Redis contains a coherent narrative.
**Expected:** Narrative is 225-300 words, covers emails, calendar, and Slack sections, no raw email content visible.
**Why human:** Requires real API keys and connected accounts; cannot verify LLM narrative quality programmatically.

---

## Gaps Summary

**1 gap blocking full goal achievement:**

**BRIEF-02 — Schedule persistence across restarts** is the critical gap. The `daily config set briefing.schedule_time` CLI command correctly writes the new schedule to the `briefing_config` database table (schedule_hour, schedule_minute). However, `src/daily/main.py` reads `Settings.briefing_schedule_time` from the environment/`.env` file at startup — it never queries `BriefingConfig` from the database. The main.py docstring explicitly acknowledges this: *"the cron job reads DB config at startup in a future enhancement"*.

**Root cause:** Missing DB read on startup in `main.py` lifespan function.

**Fix scope:** Small — add a DB query in the lifespan function after `Settings()` is initialised to look up `BriefingConfig` for user_id=1 and override the default schedule_hour/minute if a row exists.

**2 warnings (not blockers):**
- `_scheduled_pipeline_run` uses empty `user_email=""` — direct-recipient scoring never fires in scheduled runs.
- `_fetch_all_messages` Slack pagination bug — cursor tracked but never passed to next page call.

---

_Verified: 2026-04-07_
_Verifier: Claude (gsd-verifier)_
