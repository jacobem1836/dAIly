---
status: testing
phase: 03-orchestrator
source: [03-01-SUMMARY.md, 03-01b-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md]
started: 2026-04-08T23:00:00Z
updated: 2026-04-08T23:00:00Z
---

## Current Test

number: 7
name: Daily Chat Command Launches
expected: |
  Run: PYTHONPATH=src uv run daily chat
  Expected: interactive prompt appears. If no OpenAI key / no email adapters, fails gracefully with a clear error — not a traceback.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: All Phase 03 module imports succeed and all 112+ Phase 03 tests pass with 0 failures.
result: pass

### 2. Profile Config Set — Tone
expected: |
  Run: PYTHONPATH=src uv run daily config set profile.tone casual
  Expected: prints confirmation like "tone set to casual". No errors.
result: issue
reported: "ForeignKeyViolationError: user_profile FK to users table fails — no user row with id=1 exists"
severity: major

### 3. Profile Config Set — Briefing Length
expected: |
  Run: PYTHONPATH=src uv run daily config set profile.briefing_length concise
  Expected: prints confirmation like "briefing_length set to concise". No errors.
result: skipped
reason: same FK issue as test 2

### 4. Profile Config Get
expected: |
  Run: PYTHONPATH=src uv run daily config get profile
  Expected: displays current preferences including tone=casual, briefing_length=concise (from tests 2-3), and category_order (default or previously set).
result: skipped
reason: depends on tests 2-3 passing first

### 5. Profile Config Set — Invalid Value Rejection
expected: |
  Run: PYTHONPATH=src uv run daily config set profile.tone aggressive
  Expected: error message rejecting "aggressive" and listing valid options (professional, casual, friendly). Does NOT write to database.
result: pass

### 6. Category Order Set
expected: |
  Run: PYTHONPATH=src uv run daily config set profile.category_order "calendar,email,tasks"
  Expected: prints confirmation. Then run config get profile — category_order shows calendar,email,tasks.
result: issue
reported: "ForeignKeyViolationError — same FK issue as test 2, no user row with id=1"
severity: major

### 7. Daily Chat Command Launches
expected: |
  Run: PYTHONPATH=src uv run daily chat
  Expected: an interactive prompt appears (e.g. "You: " or similar). If no OpenAI key / no email adapters configured, it should fail gracefully with a clear error — not crash with a traceback.
  Type "exit" or Ctrl+C to quit.
result: issue
reported: "Chat launches and shows 'You: ' prompt + no-adapters warning (graceful), but typing a message crashes with traceback: OpenAIError missing OPENAI_API_KEY — should catch and show clean error instead"
severity: minor

## Summary

total: 7
passed: 2
issues: 3
pending: 0
skipped: 2
blocked: 0

## Gaps

- truth: "daily config set profile.tone casual prints confirmation and writes to DB"
  status: failed
  reason: "User reported: ForeignKeyViolationError — user_profile FK to users table fails, no user row with id=1 exists"
  severity: major
  test: 2
  root_cause: "Hardcoded user_id=1 (T-03-11 accepted stub) but no seed user exists in the users table"
  artifacts:
    - path: "src/daily/cli.py"
      issue: "hardcoded user_id=1"
    - path: "src/daily/profile/service.py"
      issue: "upsert_preference assumes user exists"
  missing:
    - "Seed a default user row OR auto-create user in upsert_preference"
  debug_session: ".planning/debug/test2-profile-config-fk-violation.md"

- truth: "daily chat shows clean error when OPENAI_API_KEY is not set, not a traceback"
  status: failed
  reason: "User reported: chat launches and prompts but crashes with OpenAIError traceback when message sent — no graceful error handling for missing API key"
  severity: minor
  test: 7
  root_cause: "respond_node creates AsyncOpenAI() without catching OpenAIError — exception propagates up as unhandled traceback"
  artifacts:
    - path: "src/daily/orchestrator/nodes.py"
      issue: "respond_node: AsyncOpenAI() raises OpenAIError if no key, not caught"
    - path: "src/daily/cli.py"
      issue: "_run_chat_session: no top-level exception handler for OpenAIError"
  missing:
    - "Catch OpenAIError in _run_chat_session or respond_node and print friendly message"
