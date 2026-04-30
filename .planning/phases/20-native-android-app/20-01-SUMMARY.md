---
phase: 20
plan: "01"
subsystem: backend
tags: [android, app-links, fastapi, settings, tdd]
dependency_graph:
  requires: []
  provides: [GET /.well-known/assetlinks.json, android_package_name Setting, android_sha256_fingerprint Setting]
  affects: [src/daily/main.py, src/daily/config.py]
tech_stack:
  added: []
  patterns: [env-driven Settings, JSONResponse endpoint, TDD]
key_files:
  created:
    - tests/test_assetlinks.py
  modified:
    - src/daily/config.py
    - src/daily/main.py
    - .env.example
decisions:
  - Top-level JSON array (not object) required by Android Digital Asset Links spec — matches Google documentation exactly
  - Comma-separated fingerprint splitting mirrors iOS pattern for supporting debug + release certs
  - include_in_schema=False mirrors AASA endpoint — keeps Swagger docs clean
metrics:
  duration: "3m"
  completed_date: "2026-04-30"
  tasks_completed: 1
  files_changed: 4
---

# Phase 20 Plan 01: Android assetlinks.json Endpoint Summary

**One-liner:** Added `GET /.well-known/assetlinks.json` endpoint serving Android App Links verification JSON, driven by two new env-configured Settings fields with comma-separated multi-fingerprint support.

## What Was Built

### Task 1: Add Settings fields + GET /.well-known/assetlinks.json endpoint with TDD

**Commit (RED):** `5527dd8` — test(20-01): add failing tests for assetlinks.json endpoint
**Commit (GREEN):** `e3c54de` — feat(20-01): add assetlinks.json endpoint and Settings fields for Android App Links

**Files changed:**
- `src/daily/config.py` — Added `android_package_name: str = "com.daily.android"` and `android_sha256_fingerprint: str = ""` fields adjacent to the existing Apple Universal Links fields
- `src/daily/main.py` — Added `GET /.well-known/assetlinks.json` route returning a JSON array per the Digital Asset Links specification, with comma-split fingerprint logic
- `tests/test_assetlinks.py` — 8 pytest tests covering all behaviors (status, content-type, array shape, relation, namespace, package_name, single fingerprint, multi-fingerprint)
- `.env.example` — Documented `ANDROID_PACKAGE_NAME` and `ANDROID_SHA256_FINGERPRINT` with placeholder values and comment about comma-separation

**Test results:** 8/8 passing; full suite 571 passed, 8 pre-existing failures (unrelated: test_action_draft.py, test_briefing_ranker 2.py, test_livekit_tokens 2.py, test_voice_barge_in.py)

## Decisions Made

1. **JSON array at top level** — Android Digital Asset Links spec requires a top-level JSON array, unlike Apple's AASA which uses a nested object. The implementation produces `[{...}]` not `{"applinks": {...}}`.
2. **Comma-separated fingerprint splitting** — `android_sha256_fingerprint` splits on commas to support debug + release certificate fingerprints in a single env var (same pattern philosophy as Apple multi-cert support).
3. **include_in_schema=False** — Keeps the endpoint out of auto-generated OpenAPI docs, consistent with the AASA endpoint.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — both Settings fields are env-driven and functional. The endpoint will return an empty `sha256_cert_fingerprints` array if `ANDROID_SHA256_FINGERPRINT` is not set, which is the correct fail-closed behavior (Android App Links won't verify, falling back to browser).

## Self-Check: PASSED

- `tests/test_assetlinks.py` — EXISTS
- `src/daily/config.py` contains `android_package_name` — CONFIRMED (line 49)
- `src/daily/main.py` contains `/.well-known/assetlinks.json` route — CONFIRMED (line 130)
- `.env.example` contains `ANDROID_PACKAGE_NAME` — CONFIRMED (line 30)
- Commit `5527dd8` — EXISTS
- Commit `e3c54de` — EXISTS
- All 8 assetlinks tests pass — CONFIRMED
- No regression introduced — CONFIRMED (pre-existing failures unchanged)
