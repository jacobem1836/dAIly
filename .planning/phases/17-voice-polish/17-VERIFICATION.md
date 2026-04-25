---
phase: 17-voice-polish
verified: 2026-04-25T10:00:00Z
status: human_needed
score: 11/12 must-haves verified
human_verification:
  - test: "Say a short word or sound ('yeah', cough) during TTS playback"
    expected: "TTS continues uninterrupted — backchannel is swallowed, stop_event never fires"
    why_human: "Requires live microphone, running TTS stream, and Deepgram STT — cannot simulate in unit tests"
  - test: "Ask a conversational question (e.g. 'what is the weather today?') and listen for first spoken word latency"
    expected: "First spoken word arrives noticeably sooner than with the old run_session full-response ainvoke path"
    why_human: "Perceptual latency comparison requires live Cartesia + OpenAI API keys and a running voice session"
---

# Phase 17: Voice Polish Verification Report

**Phase Goal:** Voice Polish — implement 4 improvements that make the voice loop more natural: graceful TTS fade-out, mic-mute echo suppression, barge-in safety window with backchannel detection, and streaming LLM→TTS for lower latency.
**Verified:** 2026-04-25T10:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | When stop_event is set mid-stream, the current audio chunk completes playback before TTS exits | ✓ VERIFIED | `tts.py` lines 197-199: `output_stream.write(response.audio)` before `if stop_event.is_set()` — confirmed in both `play_streaming` and `play_streaming_tokens` receive loops |
| 2  | TTS no longer cuts off mid-word on barge-in | ✓ VERIFIED | Follows directly from truth 1; test `test_play_streaming_stops_on_event` asserts `len(chunks_written) == 3` (graceful fade-out comment present at line 153) |
| 3  | When TTS is playing, the mic feeds silent audio chunks to Deepgram (echo suppressed) | ✓ VERIFIED | `stt.py` line 176: `_select_chunk` returns `_SILENT_CHUNK if self.muted else indata_bytes`; called at line 210 inside `_sd_callback` |
| 4  | Mic unmutes 500ms into TTS playback so genuine barge-in is still possible | ✓ VERIFIED | `barge_in.py` lines 62-79: `_unmute_after_delay()` coroutine with `asyncio.sleep(0.5)` scheduled by `speak()` at line 168 |
| 5  | Mic always unmutes when TTS completes or is interrupted | ✓ VERIFIED | `barge_in.py` has `self._stt.muted = False` at lines 76 (CancelledError path), 79 (CancelledError re-raise path), 187 (speak() finally), and 230 (stop()) |
| 6  | `_on_speech_started` no longer sets stop_event directly — it schedules a 600ms timer | ✓ VERIFIED | `barge_in.py` `_on_speech_started` (lines 86-105) contains NO `stop_event.set()` — schedules `_commit_barge_in_after_window` via `asyncio.create_task`; `stop_event.set()` only at lines 114 (timer) and 233 (stop()) |
| 7  | If the timer is cancelled within 600ms (backchannel detected), TTS continues | ✓ VERIFIED | `_commit_barge_in_after_window` (lines 107-115): `asyncio.sleep(0.6)` wrapped in try/except CancelledError; `filter_utterance` cancels the task and sets `_pending_barge_in_cancelled = True` |
| 8  | Backchannel utterances ('yeah', 'ok', etc.) detected by `_is_backchannel` are suppressed when TTS was active at speech start | ✓ VERIFIED | `utils.py` has `_BACKCHANNEL_PHRASES` frozenset + `_is_backchannel()`; `barge_in.py` `filter_utterance` checks `_was_tts_active_at_speech_start and _is_backchannel(text)`; `loop.py` uses `if not turn_manager.filter_utterance(user_input): continue` at line 205 |
| 9  | Backchannel utterances ('yeah', 'ok') are suppressed during TTS — confirmed by automated test | ? HUMAN | Unit tests (`test_backchannel_does_not_set_stop_event_during_tts`, `test_real_barge_in_non_backchannel_during_tts`) pass, but end-to-end behavior (real speech → Deepgram → filter → TTS continuation) needs live verification |
| 10 | After a user utterance is accepted, the agent speaks a random acknowledgement before run_session | ✓ VERIFIED | `loop.py` line 217: `await turn_manager.speak(random.choice(_ACKNOWLEDGEMENTS))` guarded by `if not first_turn` at line 215 |
| 11 | `astream_session` yields plain-text token deltas from OpenAI SDK stream=True for respond-intent turns | ✓ VERIFIED | `session.py` line 291: `stream=True`; no `response_format` inside `astream_session`; `_looks_like_respond_intent` confirmed working via import check |
| 12 | `TTSPipeline.play_streaming_tokens` accumulates tokens, splits on sentence boundaries, and pushes each completed sentence to Cartesia | ✓ VERIFIED | `tts.py` lines 44-46: `_SENTENCE_BOUNDARIES = (". ", "! ", "? ", "\n")`; `_split_at_boundary` helper at lines 51-78; `play_streaming_tokens` method at line 205 with producer/consumer structure |

**Score:** 11/12 truths verified (truth 9 is a subset of truth 8 — automated checks pass; live end-to-end needs human)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/daily/voice/tts.py` | `play_streaming` with write-before-stop ordering | ✓ VERIFIED | Lines 196-199 and 267-270 both show write before stop_event check |
| `src/daily/voice/tts.py` | `play_streaming_tokens` method + `_SENTENCE_BOUNDARIES` | ✓ VERIFIED | Line 205 (`async def play_streaming_tokens`), line 46 (`_SENTENCE_BOUNDARIES`), line 51 (`_split_at_boundary`) |
| `src/daily/voice/stt.py` | `_select_chunk` respects `self.muted` | ✓ VERIFIED | Lines 166 (def), 176 (`_SILENT_CHUNK if self.muted else indata_bytes`), 210 (call site) |
| `src/daily/voice/barge_in.py` | `speak()` mutes mic at TTS start, unmutes 500ms later + 600ms timer + `filter_utterance` | ✓ VERIFIED | Lines 62-79 (`_unmute_after_delay`), 107-115 (`_commit_barge_in_after_window`), 120 (`filter_utterance`), 167-168 (mute + schedule in `speak()`) |
| `src/daily/voice/utils.py` | `_is_backchannel()` and `_BACKCHANNEL_PHRASES` frozenset | ✓ VERIFIED | Lines 5 and 13-27; import check passed |
| `src/daily/voice/loop.py` | `_ACKNOWLEDGEMENTS` + ack speak + `filter_utterance` hook + streaming bridge | ✓ VERIFIED | Lines 43, 205, 217, 226-263 all confirmed |
| `src/daily/orchestrator/session.py` | `astream_session` + `StreamingNotSupported` + `run_session` preserved | ✓ VERIFIED | Lines 177, 227, preserved `run_session` — import check passed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tts.py play_streaming` receive loop | `stop_event check ordering` | write AFTER output_stream.write | ✓ WIRED | Confirmed at lines 197-199 |
| `barge_in.py speak()` | `stt.py _sd_callback` | `self._stt.muted` boolean | ✓ WIRED | `speak()` sets `self._stt.muted = True` at line 167; `_select_chunk` reads `self.muted` at line 176 |
| `barge_in.py _on_speech_started` | `barge_in.py _commit_barge_in_after_window` | `asyncio.create_task` scheduling 600ms timer | ✓ WIRED | Line 104: `asyncio.create_task(self._commit_barge_in_after_window())` |
| `loop.py main turn loop` | `turn_manager.filter_utterance` | post-utterance hook | ✓ WIRED | Line 205: `if not turn_manager.filter_utterance(user_input): continue` |
| `loop.py main turn loop` | `turn_manager.speak(random.choice(_ACKNOWLEDGEMENTS))` | pre-`run_session` hook | ✓ WIRED | Lines 215-217 — guarded by `not first_turn` |
| `loop.py main turn loop` | `session.astream_session + tts.play_streaming_tokens` | `asyncio.Queue` producer/consumer with `asyncio.gather` | ✓ WIRED | Lines 226-263: `asyncio.Queue(maxsize=64)`, `asyncio.gather(_produce(), turn_manager._tts.play_streaming_tokens(...))` |
| `barge_in.py filter_utterance` | `utils._is_backchannel` | import at line 17 | ✓ WIRED | `from daily.voice.utils import _is_backchannel` confirmed |
| `loop.py` | `session.StreamingNotSupported` | except clause | ✓ WIRED | Line 29 (import), line 263 (except) |

### Behavioral Spot-Checks

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| `_is_backchannel('yeah')` returns True | `python -c "from daily.voice.utils import _is_backchannel; assert _is_backchannel('Yeah.') is True"` | OK | ✓ PASS |
| `_is_backchannel('schedule a meeting')` returns False | as above, `assert ... is False` | OK | ✓ PASS |
| `_looks_like_respond_intent('exit')` returns False | `python -c "from daily.orchestrator.session import _looks_like_respond_intent; assert not _looks_like_respond_intent('exit')"` | OK | ✓ PASS |
| `_looks_like_respond_intent('what is the weather today')` returns True | as above | OK | ✓ PASS |
| `TTSPipeline.play_streaming_tokens` exists | `python -c "from daily.voice.tts import TTSPipeline; assert hasattr(TTSPipeline, 'play_streaming_tokens')"` | OK | ✓ PASS |
| All Phase 17 unit tests pass | `.venv/bin/pytest tests/test_voice_tts.py tests/test_voice_stt.py tests/test_voice_barge_in.py tests/test_voice_utils.py -q` | 49 passed | ✓ PASS |
| All four files parse cleanly | `python -c "import ast; ast.parse(...)"` on all four | OK | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| VOICE-POLISH-03 | 17-01 | Graceful TTS fade-out (write before stop_event) | ✓ SATISFIED | `tts.py` receive loop ordering confirmed |
| VOICE-POLISH-06 | 17-02 | Mic-mute echo cancellation (`_select_chunk` + delayed unmute) | ✓ SATISFIED | `stt.py` `_select_chunk` + `barge_in.py` `_unmute_after_delay` |
| VOICE-POLISH-01 | 17-03 | 600ms barge-in safety window | ✓ SATISFIED | `barge_in.py` `_commit_barge_in_after_window` with `asyncio.sleep(0.6)` |
| VOICE-POLISH-02 | 17-03 | Backchannel detection and suppression | ✓ SATISFIED | `utils.py` `_is_backchannel` + `barge_in.py` `filter_utterance` + `loop.py` `continue` |
| VOICE-POLISH-04 | 17-03 | Agent acknowledgement phrases | ✓ SATISFIED | `loop.py` `_ACKNOWLEDGEMENTS` + `random.choice` before `run_session` |
| VOICE-POLISH-05 | 17-04 | Streaming LLM→TTS with sentence-boundary chunking | ✓ SATISFIED | `session.py` `astream_session`, `tts.py` `play_streaming_tokens`, `loop.py` streaming bridge |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | All implementations are substantive; no stubs, empty returns, or TODO placeholders detected in modified files |

### Human Verification Required

#### 1. Backchannel suppression — live voice test

**Test:** During TTS playback, say a short word such as "yeah", "ok", or make a brief cough sound.
**Expected:** TTS continues without interruption. No barge-in fires. The backchannel is swallowed by `filter_utterance`; `_pending_barge_in_cancelled` is set True; the 600ms timer is cancelled.
**Why human:** Requires a live microphone, running Cartesia TTS stream, and Deepgram STT session. The timer fires on the asyncio loop, the callback chain is real-time, and the 600ms window is only meaningful against actual audio latency.

#### 2. Streaming LLM→TTS latency improvement — perceptual check

**Test:** Ask a conversational question (e.g. "what is the weather today?" or "tell me something interesting") and measure the time from finishing speaking to hearing the first spoken word.
**Expected:** First spoken word arrives noticeably sooner than with the previous full-response `run_session` path. No garbled JSON braces or structural characters spoken aloud (the streaming path uses plain-text prompt, not JSON response_format).
**Why human:** Perceptual latency comparison requires live Cartesia + OpenAI API keys and an active voice session. Sub-sentence latency improvement is experiential and cannot be asserted in a unit test.

### Gaps Summary

No automated gaps found. All 12 must-haves are satisfied at the code level. Two human verification items remain:

1. End-to-end backchannel suppression in a live voice session
2. Perceptual latency improvement from streaming LLM→TTS

Both are expected to pass given the correct wiring confirmed above, but require live API access to verify.

---

_Verified: 2026-04-25T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
