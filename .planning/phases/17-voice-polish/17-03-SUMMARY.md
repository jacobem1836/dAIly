---
phase: 17-voice-polish
plan: "03"
subsystem: voice
tags: [voice, barge-in, backchannel, safety-window, acknowledgement, asyncio]
dependency_graph:
  requires: [mic-mute-echo-suppression, graceful-tts-fade-out]
  provides: [barge-in-safety-window, backchannel-detection, agent-acknowledgements]
  affects: [voice-loop, barge-in]
tech_stack:
  added: []
  patterns: [asyncio-deferred-timer, capture-flag-at-onset, frozenset-phrase-matching]
key_files:
  created:
    - src/daily/voice/utils.py
    - tests/test_voice_utils.py
  modified:
    - src/daily/voice/barge_in.py
    - tests/test_voice_barge_in.py
    - src/daily/voice/loop.py
decisions:
  - "_was_tts_active_at_speech_start captured in _on_speech_started not at filter time — fixes timing race with UtteranceEnd arriving 1000ms after speech onset"
  - "filter_utterance() returns bool (False=swallow); loop.py uses continue to skip backchannel turns"
  - "Acknowledgement speak is non-fatal — exception is caught and logged, real response still plays"
  - "exit/quit break fires before acknowledgement — no need for normalized not-in guard (already excluded by control flow)"
metrics:
  duration_minutes: 18
  completed_date: "2026-04-25"
  tasks_completed: 3
  files_modified: 5
requirements: [VOICE-POLISH-01, VOICE-POLISH-02, VOICE-POLISH-04]
---

# Phase 17 Plan 03: Adaptive Barge-In + Backchannel Detection + Acknowledgements Summary

**One-liner:** 600ms asyncio timer replaces unconditional stop_event.set(); backchannel frozenset in utils.py suppresses "yeah"/"ok" from barge-in; random acknowledgement phrase speaks before run_session on non-first turns.

## What Was Built

### Task 1 — voice/utils.py with _is_backchannel

New module `src/daily/voice/utils.py` with:
- `_BACKCHANNEL_PHRASES: frozenset[str]` — 23 phrases covering the common listening tokens
- `_is_backchannel(text: str) -> bool` — normalizes (strip, lower, rstrip punctuation), rejects >3 words, checks membership

8 unit tests in `tests/test_voice_utils.py` covering: case-insensitive match, punctuation stripping, hyphenated phrases, multi-word, word-count guard, empty string, whitespace-only.

### Task 2 — barge_in.py: 600ms timer + backchannel-aware filter

Three new fields on `VoiceTurnManager.__init__`:
- `_pending_barge_in_cancelled: bool = False`
- `_barge_in_timer_task: asyncio.Task | None = None`
- `_was_tts_active_at_speech_start: bool = False`

`_on_speech_started` rewritten to:
1. Capture `_was_tts_active_at_speech_start = self._tts_active` (at onset time — before UtteranceEnd)
2. Cancel any prior barge-in timer
3. Schedule `_commit_barge_in_after_window()` via `asyncio.create_task`

New coroutine `_commit_barge_in_after_window`: waits 600ms, then sets `stop_event` unless `_pending_barge_in_cancelled` is True. On `CancelledError`, returns immediately.

New method `filter_utterance(text)`: checks `_was_tts_active_at_speech_start and _is_backchannel(text)`. If True: sets `_pending_barge_in_cancelled = True`, cancels timer, returns False. Otherwise returns True.

`speak()` updated:
- At top: cancel any in-flight barge-in timer, reset all three new fields before `stop_event.clear()`
- In `finally`: clear `_was_tts_active_at_speech_start`

`stop()` updated: cancel barge-in timer and set `_pending_barge_in_cancelled = True` before other cleanup.

Import added: `from daily.voice.utils import _is_backchannel`.

Tests rewritten:
- `test_echo_suppression_during_tts` → replaced with `test_backchannel_does_not_set_stop_event_during_tts` (Case A) and `test_real_barge_in_non_backchannel_during_tts` (Case B)
- `test_real_barge_in_when_tts_inactive` → rewritten to use 700ms sleep and assert `stop_event.is_set()` (timer-based)
- Total: 12 barge-in tests + 8 utils tests = 20 passing

### Task 3 — loop.py: backchannel filter + acknowledgement phrases

Changes to `src/daily/voice/loop.py`:
- `import random` added (alphabetised with existing stdlib imports)
- Module constant: `_ACKNOWLEDGEMENTS: list[str] = ["Got it.", "One sec.", "Sure.", "On it.", "Mmhm."]`
- After `wait_for_utterance`: `if not turn_manager.filter_utterance(user_input): continue` (backchannels skip the turn)
- `normalized = user_input.lower().strip()` extracted variable (cleaner exit/quit check)
- Before `run_session`: `if not first_turn: await turn_manager.speak(random.choice(_ACKNOWLEDGEMENTS))` with non-fatal exception handling

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: voice/utils.py + unit tests | `b66ea76` | src/daily/voice/utils.py, tests/test_voice_utils.py |
| Task 2: barge-in timer + backchannel filter | `7ee91b9` | src/daily/voice/barge_in.py, tests/test_voice_barge_in.py |
| Task 3: loop.py filter + acknowledgements | `93e4286` | src/daily/voice/loop.py |

## Verification

- `pytest tests/test_voice_utils.py`: 8 passed
- `pytest tests/test_voice_barge_in.py`: 12 passed
- `pytest tests/test_voice_utils.py tests/test_voice_barge_in.py`: 20 passed
- `grep -n "self._stop_event.set()" src/daily/voice/barge_in.py`: appears only in `_commit_barge_in_after_window` (line 114) and `stop()` (line 233) — NOT in `_on_speech_started`
- `python -c "import ast; ast.parse(open('src/daily/voice/barge_in.py').read())"`: exits 0
- `python -c "import ast; ast.parse(open('src/daily/voice/loop.py').read())"`: exits 0
- `tests/test_voice_loop.py`: pre-existing failure (Pydantic Settings validation error unrelated to this plan — confirmed failing before Plan 17-03 changes)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] exit/quit guard already handled by break**

The plan spec included `normalized not in ("exit", "quit")` in the acknowledgement guard. After reading the actual loop structure, the exit/quit path already uses `break` before reaching the ack — so the guard was simplified to just `if not first_turn`. This is functionally equivalent (exit/quit turns never reach the ack) and cleaner.

**2. [Pre-existing] test_voice_loop.py failures**

All 5 tests in `tests/test_voice_loop.py` were failing before Plan 17-03 changes due to a Pydantic `Settings` validation error (`log_level: Extra inputs are not permitted`). Confirmed by running tests against the 59214be base commit. Out of scope for this plan — deferred.

## Known Stubs

None. All three changes are fully wired:
- `_is_backchannel` is called by `filter_utterance` which is called by `loop.py`
- `_commit_barge_in_after_window` is scheduled by `_on_speech_started` and cancelled by `speak()`/`stop()`/`filter_utterance()`
- `random.choice(_ACKNOWLEDGEMENTS)` is awaited by `turn_manager.speak()` in the main loop

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes. Backchannel matching operates on Deepgram-provided transcript text, which already passes through the existing STT pipeline input boundary.

## Self-Check: PASSED

- [x] `src/daily/voice/utils.py` exists and contains `_BACKCHANNEL_PHRASES` frozenset with "yeah"
- [x] `tests/test_voice_utils.py` exists with 8 tests
- [x] `src/daily/voice/barge_in.py` contains `_commit_barge_in_after_window`, `asyncio.sleep(0.6)`, `filter_utterance`, `_was_tts_active_at_speech_start`, `from daily.voice.utils import _is_backchannel`
- [x] `tests/test_voice_barge_in.py` updated — 12 tests including 3 new timer-based tests
- [x] `src/daily/voice/loop.py` contains `import random`, `_ACKNOWLEDGEMENTS`, `filter_utterance`, `random.choice(_ACKNOWLEDGEMENTS)`
- [x] Commit b66ea76 exists (Task 1)
- [x] Commit 7ee91b9 exists (Task 2)
- [x] Commit 93e4286 exists (Task 3)
- [x] 20 tests pass (8 utils + 12 barge-in)
