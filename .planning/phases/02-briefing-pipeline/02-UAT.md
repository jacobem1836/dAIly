---
status: testing
phase: 02-briefing-pipeline
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md
started: 2026-04-07T10:30:00Z
updated: 2026-04-07T10:30:00Z
---

## Current Test

number: 6
name: FastAPI Lifespan Startup
expected: |
  PYTHONPATH=src uv run uvicorn daily.main:app --port 8001
  Then: curl http://localhost:8001/health
  Expected: server starts, /health returns 200, scheduler logs visible.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill any running server. Run from scratch:
    PYTHONPATH=src uv run python -c "from daily.main import app; print('app imports OK')"
    PYTHONPATH=src uv run python -c "from daily.cli import app; print('cli imports OK')"
    PYTHONPATH=src uv run --with pytest --with pytest-asyncio pytest tests/ -q
  Expected: all imports succeed, 160+ tests pass with 0 failures.
result: pass

### 2. Database Migration
expected: |
  Run: uv run alembic upgrade head
  Expected: completes without error. Check postgres — tables briefing_config and vip_senders exist with correct schema (ARRAY slack_channels column, unique constraint on user_id+email for vip_senders).
result: pass

### 3. Email Ranking
expected: |
  PYTHONPATH=src uv run python -c "from daily.briefing.ranker import rank_emails; from daily.briefing.models import RankedEmail; print('OK')"
  Expected: imports cleanly, prints OK.
result: pass

### 4. Credential Redaction
expected: |
  PYTHONPATH=src uv run python -c "from daily.briefing.redactor import strip_credentials; print(strip_credentials('password=abc123 api_key=sk-test-xyz'))"
  Expected: output contains [REDACTED] — no raw values visible.
result: pass

### 5. Redis Cache TTL
expected: |
  Cache and retrieve a BriefingOutput via Redis. Expected: hit: True.
result: skipped
reason: verbose to test manually — covered by unit tests

### 6. FastAPI Lifespan Startup
expected: |
  Run: PYTHONPATH=src uv run uvicorn daily.main:app --port 8001 &
  Then: curl http://localhost:8001/health
  Expected: server starts, /health returns 200. Scheduler starts in background (visible in logs). Ctrl+C shuts down cleanly.
result: [pending]

### 7. CLI Config Commands
expected: |
  Run:
    PYTHONPATH=src uv run daily config set briefing.schedule_time 07:30
    PYTHONPATH=src uv run daily config get briefing.schedule_time
  Expected: first command confirms "schedule time set to 07:30". Second command returns "07:30". Value persists in database.
result: [pending]

### 8. CLI VIP Sender Management
expected: |
  Run:
    PYTHONPATH=src uv run daily vip add test@example.com
    PYTHONPATH=src uv run daily vip list
    PYTHONPATH=src uv run daily vip remove test@example.com
  Expected: add prints confirmation, list shows test@example.com, remove confirms deletion and list no longer shows it.
result: [pending]

### 9. Schedule Persistence Across Restarts
expected: |
  1. Run: PYTHONPATH=src uv run daily config set briefing.schedule_time 07:30
  2. Start server, check logs show "Briefing schedule loaded from database: 07:30 UTC"
  3. Stop server, restart it
  4. Logs should again show "Briefing schedule loaded from database: 07:30 UTC" — not the env default
  Expected: schedule persists across restarts, not reset to env default.
result: [pending]

### 10. Graceful DB Fallback on Startup
expected: |
  With Postgres NOT running (or with DATABASE_URL pointing at a non-existent DB):
    PYTHONPATH=src uv run uvicorn daily.main:app --port 8002
  Expected: server starts anyway (does not crash). Logs show warning about failed BriefingConfig lookup and confirm using env default schedule. /health returns 200.
result: [pending]

## Summary

total: 10
passed: 4
issues: 0
pending: 5
skipped: 1
blocked: 0

## Gaps

[none yet]
