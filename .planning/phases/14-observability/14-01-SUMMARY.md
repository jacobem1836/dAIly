---
phase: 14-observability
plan: "01"
subsystem: observability
tags: [logging, structured-json, observability, stdlib]
dependency_graph:
  requires: []
  provides: [logging_config.JSONFormatter, logging_config.ContextAdapter, logging_config.configure_logging, logging_config.make_logger, Settings.log_level]
  affects: [src/daily/main.py, all modules using logging.getLogger]
tech_stack:
  added: []
  patterns: [JSONFormatter via stdlib logging.Formatter subclass, LoggerAdapter for ctx injection, configure_logging factory]
key_files:
  created:
    - src/daily/logging_config.py
    - tests/test_logging_config.py
  modified:
    - src/daily/config.py
    - src/daily/main.py
decisions:
  - "Use record.name (not record.module) for module field to get full dotted path (e.g. daily.briefing.pipeline)"
  - "Call root.handlers.clear() before adding JSON handler to prevent duplicate output"
  - "configure_logging called as first statement in lifespan startup before any logger.info() calls"
metrics:
  duration_minutes: 12
  completed_date: "2026-04-19"
  tasks_completed: 2
  files_changed: 4
---

# Phase 14 Plan 01: Structured Logging Infrastructure Summary

**One-liner:** stdlib JSONFormatter + ContextAdapter wired onto root logger at startup — all 17+ existing logger call sites emit structured JSON without modification.

## What Was Built

`src/daily/logging_config.py` with four exports:

- `JSONFormatter(logging.Formatter)` — formats log records as single-line JSON with `ts` (ISO-8601 UTC), `level`, `module` (record.name), `msg`, `ctx`, and optional `exc` fields
- `ContextAdapter(logging.LoggerAdapter)` — injects `ctx` dict (user_id, stage) into every log record via `process()`
- `configure_logging(log_level: str)` — clears root handlers, attaches JSON handler, sets level; called first in lifespan startup
- `make_logger(name, **ctx_fields)` — factory returning a ContextAdapter for modules that want ctx injection

`src/daily/config.py` now has `log_level: str = "INFO"` mapped from `LOG_LEVEL` env var via pydantic-settings.

`src/daily/main.py` lifespan now calls `configure_logging(settings.log_level)` as its first statement, before any `logger.info()` calls.

## Tests

7 tests in `tests/test_logging_config.py`, all passing:

| Test | Requirement |
|------|-------------|
| `test_json_formatter_emits_valid_json` | OBS-01 — required JSON fields present |
| `test_json_formatter_includes_exception` | OBS-01 — exc field on exception records |
| `test_context_adapter_injects_ctx` | OBS-01 — user_id and stage in ctx |
| `test_configure_logging_sets_json_handler` | OBS-01 — exactly one JSONFormatter handler on root |
| `test_log_level_debug_shows_debug` | OBS-02 — DEBUG verbosity |
| `test_log_level_warning_suppresses_info` | OBS-02 — WARNING suppresses INFO |
| `test_make_logger_returns_adapter` | OBS-01 — factory return type |

## Verification

- [x] OBS-01: JSONFormatter emits valid JSON with ts, level, module, msg, ctx fields
- [x] OBS-01: ContextAdapter injects user_id and stage into ctx
- [x] OBS-02: LOG_LEVEL=DEBUG enables debug output
- [x] OBS-02: LOG_LEVEL=WARNING suppresses info output

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | cdd4d4c | feat(14-01): add structured JSON logging infrastructure |
| Task 2 | 5bd2306 | test(14-01): add test suite for structured logging infrastructure |

## Deviations from Plan

None — plan executed exactly as written. JSONFormatter, ContextAdapter, configure_logging, and make_logger implemented per spec. RESEARCH.md patterns followed directly.

## Threat Surface Scan

No new network endpoints or auth paths introduced. `logging_config.py` emits only to stdout via StreamHandler. Security dispositions from threat model satisfied:

- T-14-01: `json.dumps` auto-escapes newlines and special characters (no raw string concatenation)
- T-14-02: `ctx` carries only `user_id` (int) and `stage` (str) — no tokens or email bodies

## Self-Check: PASSED

- `src/daily/logging_config.py` — exists, verified via import test
- `tests/test_logging_config.py` — exists, 7 tests, all green
- `cdd4d4c` — confirmed in git log
- `5bd2306` — confirmed in git log
