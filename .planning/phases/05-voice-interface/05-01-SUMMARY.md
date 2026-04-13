---
phase: 05-voice-interface
plan: "01"
subsystem: voice/tts
tags: [tts, cartesia, sounddevice, voice, sentence-splitter]
dependency_graph:
  requires: []
  provides: [TTSPipeline, split_sentences, voice-package-scaffold]
  affects: [05-02, 05-03, 05-04]
tech_stack:
  added: [deepgram-sdk>=6.1.1, cartesia[websockets]>=3.0.2, sounddevice>=0.5.5]
  patterns: [async-context-manager, try-finally-cleanup, asyncio-event-barge-in, sentence-by-sentence-streaming]
key_files:
  created:
    - src/daily/voice/__init__.py
    - src/daily/voice/tts.py
    - tests/test_voice_tts.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/daily/config.py
decisions:
  - "MIN_CHARS=6 chosen for sentence merger threshold — balances Pitfall 7 (very short Cartesia pushes add latency) against natural sentence granularity; only single-word fragments like 'Good.' merge, multi-word sentences stay separate"
  - "TTSPipeline uses try/finally around sd.RawOutputStream to guarantee cleanup on CancelledError (D-04 barge-in path)"
  - "stop_event checked inside ctx.receive() loop between every chunk, not at sentence boundaries, for sub-chunk interrupt latency"
metrics:
  duration_seconds: 415
  completed_date: "2026-04-13"
  tasks_completed: 2
  files_created: 3
  files_modified: 3
---

# Phase 5 Plan 01: TTS Pipeline Summary

**One-liner:** Cartesia Sonic-3 WebSocket TTS pipeline with regex sentence splitter, sentence-by-sentence streaming, per-chunk barge-in via asyncio.Event, and sounddevice PCM playback with guaranteed cleanup.

## What Was Built

### `src/daily/voice/tts.py`

- `split_sentences(text)` — regex-based sentence splitter using `(?<=[.!?])\s+` boundary detection with abbreviation protection (Mr., Mrs., Dr., Prof., etc. via negative-lookbehind pattern). Short segments (< MIN_CHARS=6) are merged into the following segment to avoid Cartesia per-segment latency stuttering (Pitfall 7 from RESEARCH.md).
- `CARTESIA_SAMPLE_RATE = 44100`, `CARTESIA_OUTPUT_FORMAT`, `DEFAULT_VOICE_ID` constants.
- `TTSPipeline` class with `play_streaming(text, stop_event)` async method — opens `AsyncCartesia` WebSocket, pushes sentences via `ctx.push()`, plays PCM chunks via `sd.RawOutputStream`, checks `stop_event.is_set()` between every chunk (D-04), and wraps output stream in try/finally for cleanup on cancellation (Pitfall 5).

### `src/daily/voice/__init__.py`

Package scaffold with `TTSPipeline` and `split_sentences` re-exported as public API.

### `tests/test_voice_tts.py`

14 tests total:
- 10 unit tests for `split_sentences`: normal splits, short-segment merging, abbreviation protection (Dr., Mr.), empty input, single sentence, punctuation variety, and non-merging of long segments.
- 4 integration-style tests for `TTSPipeline.play_streaming`: stop_event halts playback early, all chunks written when not stopped, stream closed on CancelledError, non-chunk responses skipped.

All tests mock `AsyncCartesia` and `sd.RawOutputStream` so no audio hardware or API key is required in CI.

### Config additions (`src/daily/config.py`)

Added `deepgram_api_key: str = ""` and `cartesia_api_key: str = ""` fields to `Settings`, following the existing `openai_api_key` pattern.

## Decisions Made

1. **MIN_CHARS=6** chosen for the merge threshold. The plan specified MIN_CHARS=30 in prose but the test fixtures revealed the intended behavior: only fragment-level segments (e.g. "Good." = 5 chars) should merge, not full short sentences (e.g. "Hello world." = 12 chars). MIN_CHARS=6 satisfies all 14 tests.

2. **try/finally pattern** used for sounddevice stream rather than a context manager to allow the `async for response in ctx.receive()` loop to live inside the protected block while still guaranteeing `stop()` and `close()` on any exception path including `CancelledError`.

3. **Abbreviation protection** implemented via substitution placeholder (`\x00ABBREV\x00`) rather than a complex lookbehind — more readable and avoids regex engine limitations with variable-length lookbehinds.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MIN_CHARS value adjusted from plan prose to match test fixtures**
- **Found during:** Task 1 GREEN phase
- **Issue:** Plan prose stated MIN_CHARS=30 but the test `test_normal_multi_sentence_splits_correctly` expected "Hello world." (12 chars) to remain a separate segment, which is impossible with a 30-char threshold
- **Fix:** Set MIN_CHARS=6, which correctly merges only fragment-level segments ("Good." = 5 chars) while preserving natural sentence boundaries
- **Files modified:** src/daily/voice/tts.py
- **Commit:** d5e7a55

## Known Stubs

None. `TTSPipeline` is fully wired to `AsyncCartesia` and `sd.RawOutputStream`. The `voice_id` and `api_key` require real values at runtime but are not hardcoded stubs in the code.

## Threat Flags

None. No new network endpoints introduced. The `cartesia_api_key` is loaded from `.env` via pydantic-settings (T-05-01 mitigated — key is never logged, never passed to LLM layer).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/daily/voice/__init__.py | FOUND |
| src/daily/voice/tts.py | FOUND |
| tests/test_voice_tts.py | FOUND |
| Commit d5e7a55 (Task 1) | FOUND |
| Commit e53e524 (Task 2) | FOUND |
