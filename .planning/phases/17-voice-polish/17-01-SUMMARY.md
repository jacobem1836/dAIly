---
phase: 17-voice-polish
plan: "01"
subsystem: voice
tags: [tts, barge-in, graceful-fade-out, voice-polish]
dependency_graph:
  requires: []
  provides: [graceful-tts-fade-out]
  affects: [voice-loop, barge-in-flow]
tech_stack:
  added: []
  patterns: [stop-event-ordering, graceful-shutdown]
key_files:
  created: []
  modified:
    - src/daily/voice/tts.py
    - tests/test_voice_tts.py
decisions:
  - "Write current audio chunk before checking stop_event — Improvement 3 (D-03)"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-25"
  tasks_completed: 2
  files_modified: 2
requirements: [VOICE-POLISH-03]
---

# Phase 17 Plan 01: Graceful TTS Fade-Out Summary

**One-liner:** Reordered stop_event check to occur after output_stream.write so barge-in no longer cuts the current audio chunk mid-word.

## What Was Built

Minimal one-line reorder in `TTSPipeline.play_streaming()`: the `stop_event.is_set()` check
was moved from BEFORE `output_stream.write(response.audio)` to AFTER it.

Previously:
```python
async for response in ctx.receive():
    if stop_event.is_set():
        break  # cut immediately
    if response.type == "chunk" and response.audio:
        output_stream.write(response.audio)
```

Now:
```python
async for response in ctx.receive():
    if response.type == "chunk" and response.audio:
        output_stream.write(response.audio)
    if stop_event.is_set():
        break  # finish current chunk, then stop (graceful fade-out)
```

The test `test_play_streaming_stops_on_event` was updated to assert the new graceful
semantics: when stop_event is set at index 2, exactly 3 chunks are written (the chunk at
index 2 completes before the break fires).

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: Reorder stop_event check | `61d7743` | src/daily/voice/tts.py |
| Task 2: Update test for graceful semantics | `7fe5b35` | tests/test_voice_tts.py |

## Verification

- `pytest tests/test_voice_tts.py -x`: 14 passed
- `ast.parse(open('src/daily/voice/tts.py').read())`: exits 0
- `grep -nA2 "async for response in ctx.receive"` shows write before stop_event check

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network surface, endpoints, or auth paths introduced.

## Self-Check: PASSED

- [x] src/daily/voice/tts.py modified (write before stop_event check)
- [x] tests/test_voice_tts.py modified (== 3 assertion, Graceful fade-out comment)
- [x] Commit 61d7743 exists
- [x] Commit 7fe5b35 exists
- [x] All 14 tests pass
