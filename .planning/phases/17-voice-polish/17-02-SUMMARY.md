---
phase: 17-voice-polish
plan: "02"
subsystem: voice
tags: [voice, stt, barge-in, echo-suppression, mic-mute]
dependency_graph:
  requires: []
  provides: [mic-mute-echo-suppression]
  affects: [voice-loop, barge-in]
tech_stack:
  added: []
  patterns: [silent-chunk-substitution, delayed-unmute-task]
key_files:
  created: []
  modified:
    - src/daily/voice/stt.py
    - src/daily/voice/barge_in.py
    - tests/test_voice_stt.py
decisions:
  - Send _SILENT_CHUNK to Deepgram when muted (not skip sending) to keep WebSocket stream alive
  - 500ms unmute delay matches barge-in safety window so genuine interrupts still work
  - _select_chunk in _sd_callback (not in send loop) so silencing happens at capture time
metrics:
  duration_minutes: 12
  completed: "2026-04-25"
  tasks_completed: 2
  files_modified: 3
---

# Phase 17 Plan 02: Mic-Mute Echo Cancellation Summary

**One-liner:** Silent-chunk substitution in STTPipeline._sd_callback eliminates TTS-echo false barge-ins, with 500ms delayed unmute in VoiceTurnManager.speak() so genuine interrupts remain possible.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Honour self.muted in STTPipeline._sd_callback | 139b1ec | src/daily/voice/stt.py, tests/test_voice_stt.py |
| 2 | Drive mic mute from VoiceTurnManager.speak() | 768a694 | src/daily/voice/barge_in.py |

## What Was Built

### Task 1 — STTPipeline._select_chunk helper

Added `_SILENT_CHUNK = bytes(_BLOCKSIZE * 2)` module-level constant (2048 zero bytes — one PCM block of silence at 16kHz/int16).

Added `_select_chunk(indata_bytes: bytes) -> bytes` method: returns `_SILENT_CHUNK if self.muted else indata_bytes`. Called from `_sd_callback` so that when the mic is muted, Deepgram still receives a continuous audio stream (no stream gaps) but only hears silence instead of TTS playback audio.

Updated the audio-send loop in `start_listening` to always call `socket.send_media(chunk)` — the muting is handled at enqueue time by `_select_chunk`, not at send time.

Added unit test `TestSelectChunk::test_sd_callback_sends_silent_chunk_when_muted` exercising both muted=True and muted=False paths directly on the helper.

### Task 2 — VoiceTurnManager 500ms delayed unmute

Added `self._unmute_task: asyncio.Task | None = None` field to `__init__`.

Added `_unmute_after_delay()` coroutine: waits 500ms then sets `self._stt.muted = False`. On `CancelledError` (TTS finished early), forces unmute immediately before re-raising so the mic is never left muted.

Updated `speak()`:
- After `self._stt.muted = True`: schedules `_unmute_after_delay` as an asyncio task
- In `finally`: cancels the unmute task if still pending, resets `_unmute_task = None`, force-sets `self._stt.muted = False` as belt-and-braces on every exit path

Updated `stop()`: cancels the unmute task and force-unmutes before cancelling the TTS task.

## Deviations from Plan

None — plan executed exactly as written.

The existing barge_in.py already had `self._stt.muted = True/False` assignments from prior work, but lacked the `_unmute_task` / 500ms delay pattern specified in this plan. The plan's changes were applied cleanly on top.

## Known Stubs

None. Both changes are fully wired: `_select_chunk` is called in `_sd_callback`, and `_unmute_after_delay` is scheduled by `speak()`.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes introduced.

## Self-Check: PASSED

- `src/daily/voice/stt.py` exists and contains `_select_chunk` and `_SILENT_CHUNK`
- `src/daily/voice/barge_in.py` exists and contains `_unmute_after_delay` and `_unmute_task`
- `tests/test_voice_stt.py` exists and contains `TestSelectChunk`
- Commit 139b1ec: feat(17-02): add _select_chunk helper for mic-mute echo suppression in STTPipeline
- Commit 768a694: feat(17-02): drive mic mute from VoiceTurnManager.speak() with 500ms unmute delay
- `pytest tests/test_voice_stt.py` — 15 passed
- `pytest tests/test_voice_barge_in.py -k "not test_echo_suppression_during_tts and not test_real_barge_in_when_tts_inactive"` — 9 passed
