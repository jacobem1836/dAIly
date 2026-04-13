---
phase: 05-voice-interface
plan: 03
subsystem: voice
tags: [barge-in, asyncio, tts, stt, echo-suppression, concurrency]
dependency_graph:
  requires: [05-01, 05-02]
  provides: [VoiceTurnManager, barge-in coordination]
  affects: [05-04]
tech_stack:
  added: []
  patterns: [asyncio task coordination, shared Event flag, echo suppression, TDD]
key_files:
  created:
    - src/daily/voice/barge_in.py
    - tests/test_voice_barge_in.py
  modified:
    - src/daily/voice/__init__.py
decisions:
  - "Echo suppression via tts_active flag prevents TTS audio from self-triggering barge-in (Pitfall 6)"
  - "speak() uses CancelledError catch + stop_event.is_set() check to detect both cancellation and stop paths"
  - "stop_event.clear() in finally block ensures each speak() call starts clean"
  - "start_stt() mutates _stt._on_speech_started directly to wire callback without STTPipeline constructor changes"
metrics:
  duration_minutes: 18
  completed_date: "2026-04-13T10:31:00Z"
  tasks_completed: 1
  files_changed: 3
---

# Phase 05 Plan 03: Barge-In Coordination Layer Summary

VoiceTurnManager coordinating TTS/STT concurrency via shared asyncio.Event with echo suppression during TTS playback.

## What Was Built

`src/daily/voice/barge_in.py` — `VoiceTurnManager` class that:

- Wraps `TTSPipeline` and `STTPipeline` with a shared `asyncio.Event` stop flag
- `speak(text)` — plays TTS with barge-in support: sets `tts_active=True`, clears `stop_event`, creates TTS task, awaits it, handles `CancelledError`, returns `True` on completion or `False` on interruption. Always clears `stop_event` and `tts_active` in `finally`.
- `_on_speech_started()` — Deepgram SpeechStarted callback. Suppresses `stop_event.set()` when `tts_active=True` (echo suppression, T-05-08). Sets `stop_event` when TTS is idle (real barge-in).
- `wait_for_utterance()` — proxies `stt.utterance_queue.get()` for the turn loop
- `start_stt(listen_stop)` — wires `_on_speech_started` callback into STT pipeline, starts `start_listening` as background task
- `stop()` — cancels in-flight TTS task and STT listener task cleanly

## Tests (11 passing)

- `test_speak_completes_normally` — returns True on normal completion
- `test_tts_active_false_after_normal_completion` — cleanup verified
- `test_barge_in_cancels_tts` — returns False when stop_event set during playback
- `test_tts_active_false_after_barge_in` — cleanup after interruption
- `test_echo_suppression_during_tts` — stop_event NOT set when tts_active=True
- `test_real_barge_in_when_tts_inactive` — stop_event IS set when tts_active=False
- `test_stop_event_cleared_after_speak_normal` — stop_event cleared after normal completion
- `test_stop_event_cleared_after_speak_barge_in` — stop_event cleared after barge-in
- `test_wait_for_utterance_returns_text` — queue proxy works
- `test_start_stt_wires_speech_started_callback` — callback wired and functional
- `test_stop_cancels_tts_task` — stop() cancels in-flight TTS

## Regression

All 39 voice tests pass (`test_voice_tts.py`, `test_voice_stt.py`, `test_voice_barge_in.py`).

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Echo suppression via `tts_active` bool | Pitfall 6 from RESEARCH.md: Cartesia TTS audio output is picked up by mic and triggers Deepgram SpeechStarted. tts_active flag breaks the echo loop. |
| `stop_event.clear()` in finally block | Ensures each speak() call is independent — previous barge-in state doesn't bleed into next turn. |
| `start_stt()` mutates `_stt._on_speech_started` directly | STTPipeline was designed to accept callback at construction time. Direct mutation avoids reconstruction overhead and aligns with the callback injection pattern documented in Plan 02. |
| `speak()` checks both `CancelledError` and `stop_event.is_set()` | The TTS fake in tests sets `stop_event` without raising `CancelledError` (it just exits). The real TTSPipeline breaks the audio loop on `stop_event.is_set()` and returns normally. Both paths must resolve to `False`. |

## Deviations from Plan

**1. [Rule 1 - Bug] Test assertion too strict for bound method identity**
- **Found during:** RED phase — `test_start_stt_wires_speech_started_callback`
- **Issue:** `fake_stt._on_speech_started is manager._on_speech_started` failed because Python bound methods create new objects on each attribute access. `is` identity check fails even for the same underlying function.
- **Fix:** Replaced identity check with callable check + behavioral test (calling the wired callback with `tts_active=False` verifies `stop_event` is set).
- **Files modified:** `tests/test_voice_barge_in.py`
- **Commit:** b9aa6f6

## Known Stubs

None — all methods are fully implemented.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. T-05-08 (echo suppression DoS) is mitigated by `tts_active` flag as planned.

## Self-Check: PASSED

- `src/daily/voice/barge_in.py` — FOUND
- `tests/test_voice_barge_in.py` — FOUND
- `src/daily/voice/__init__.py` — FOUND (updated)
- Commit b9aa6f6 — FOUND
- `uv run pytest tests/test_voice_barge_in.py -x -q` — 11 passed
- `uv run pytest tests/test_voice_tts.py tests/test_voice_stt.py tests/test_voice_barge_in.py -x -q` — 39 passed
- `from daily.voice import VoiceTurnManager` — import succeeds
