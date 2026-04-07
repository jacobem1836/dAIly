---
phase: 02-briefing-pipeline
plan: "03"
subsystem: briefing-pipeline
tags: [redactor, narrator, llm, security, credential-stripping, tdd]
dependency_graph:
  requires: [02-01]
  provides: [redactor, narrator]
  affects: [02-04-pipeline-assembly]
tech_stack:
  added: []
  patterns:
    - "Bounded regex credential stripping with JSON/HTML-aware delimiters"
    - "Asyncio semaphore for OpenAI rate-limit protection"
    - "TDD: failing tests first, then implementation"
    - "Retry-once + fallback pattern for LLM JSON parse failures"
key_files:
  created:
    - src/daily/briefing/redactor.py
    - src/daily/briefing/narrator.py
    - tests/test_briefing_redactor.py
    - tests/test_briefing_narrator.py
  modified: []
decisions:
  - "Regex uses optional closing-quote on keyword to handle JSON key context (e.g. '\"password\": \"value\"' not just 'password: value')"
  - "Narrator max_tokens=650 provides adequate headroom for 300-word narrative (~390 tokens at 1.3/word + overhead)"
  - "Retry-once pattern chosen over single-shot for transient LLM failures"
metrics:
  duration_minutes: 32
  completed_date: "2026-04-07"
  tasks_completed: 2
  files_created: 4
---

# Phase 02 Plan 03: Redactor and Narrator Summary

Two-layer LLM pipeline: GPT-4.1-mini per-item redactor with JSON/HTML-aware credential stripping (bounded regex), and GPT-4.1 narrator with JSON-mode output, key validation, and retry-once fallback.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Redactor — credential stripping and per-item summarisation | 3e56ed5 | src/daily/briefing/redactor.py, tests/test_briefing_redactor.py |
| 2 | Narrator — LLM narrative generation with structured JSON output | 67177f3 | src/daily/briefing/narrator.py, tests/test_briefing_narrator.py |

## What Was Built

### redactor.py

- `CREDENTIAL_PATTERN` — bounded regex (`{1,200}`) strips password/token/api_key/secret/auth/authorization/bearer/URL auth params. Two-branch value capture handles JSON (quoted values including surrounding quotes) and plain-text/HTML (stops at comma, semicolon, angle brackets) contexts.
- `strip_credentials(text)` — pure function, applies pattern substitution.
- `summarise_and_redact(raw_body, client)` — GPT-4.1-mini per-item summarisation with semaphore rate limiting; empty body short-circuits without LLM call.
- `redact_emails(emails, raw_bodies, client)` — concurrent batch via `asyncio.gather`.
- `redact_messages(messages, raw_texts, client)` — concurrent batch, returns `message_id → summary` dict.
- `_LLM_SEMAPHORE = asyncio.Semaphore(3)` — prevents OpenAI rate limit exhaustion.

### narrator.py

- `NARRATOR_SYSTEM_PROMPT` — enforces 300-word limit, no lists/bullets, three-paragraph structure (emails → calendar → Slack), "Nothing notable" sentences for empty sections.
- `FALLBACK_NARRATIVE` — returned on double LLM failure.
- `generate_narrative(context, client)` — GPT-4.1 in `response_format=json_object` mode, `max_tokens=650`. Validates `"narrative"` key present. Retry-once on `JSONDecodeError` or `ValueError` (wrong key). Fallback on second failure. No `tools=` or `function_call=` — SEC-05.

## Test Results

15 tests pass, 0 fail. No real OpenAI API calls — all tests use `unittest.mock.AsyncMock`.

**Redactor (8 tests):** credential strip (plain), credential strip JSON context, credential strip HTML context, summarise_and_redact, email batch, slack batch, empty body, concurrent semaphore.

**Narrator (7 tests):** output structure, JSON intent mode, word count soft gate, system prompt constraints, empty context, key validation, JSON parse failure fallback.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] JSON key quoting broke credential regex**
- **Found during:** Task 1 (test_credential_strip_json_context)
- **Issue:** In JSON, the credential keyword itself appears inside quotes: `"password": "secret123"`. The original regex used `\s*[:=]\s*` which expects the colon directly after the keyword, but in JSON there's a `"` between the keyword and the colon. The regex never matched JSON-formatted credentials.
- **Fix:** Added optional closing-quote `"?` after the keyword group so `password"` or `password` both match before the `:`. Changed the value branch to match `"value"` (including surrounding quotes) for JSON context, stopping at the closing `"`.
- **Files modified:** src/daily/briefing/redactor.py
- **Commit:** 3e56ed5

## Known Stubs

None. Both modules are fully wired. `redactor.py` calls real OpenAI API (mocked in tests). `narrator.py` calls real OpenAI API (mocked in tests). No placeholder text or hardcoded empty values in the data path.

## Threat Flags

No new threat surface introduced beyond what was already modelled in the plan's threat register. The regex boundary fix reduces T-02-07 attack surface further (JSON-context credentials now stripped correctly).

## Self-Check: PASSED

- [x] src/daily/briefing/redactor.py exists
- [x] src/daily/briefing/narrator.py exists
- [x] tests/test_briefing_redactor.py exists
- [x] tests/test_briefing_narrator.py exists
- [x] Commit 3e56ed5 exists (Task 1)
- [x] Commit 67177f3 exists (Task 2)
- [x] 15/15 tests pass
