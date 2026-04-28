---
status: closed_structural
trigger: "TTS barge-in during voice session is broken in two intermittent ways: (1) sometimes briefing plays fully with no barge-in at all, (2) sometimes TTS cuts out after 1-2 words"
created: 2026-04-26T00:00:00Z
updated: 2026-04-26T00:01:00Z
---

## Current Focus

hypothesis: _transcript_parts guard fails for continuous real speech. endpointing=300ms means Deepgram only marks a word as "final" after 300ms of silence within the phrase. Continuous uninterrupted speech produces NO finals during the 900ms barge-in window. _transcript_parts stays empty → timer exits without setting stop_event → TTS never stops despite real speech.
test: Code trace: _on_transcript only appends to _transcript_parts when result.is_final=True. Interim results (is_final=False) display on terminal but are NOT accumulated. Finals require endpointing gap (300ms silence). A user speaking continuously has no silence gaps → no finals → _transcript_parts empty at 900ms → barge-in fails.
expecting: Fix by using interim transcript flag instead of _transcript_parts. Track _has_speech_transcript=True when ANY non-empty transcript arrives (interim OR final). Timer checks this flag. Interims arrive within ~200-400ms of onset even for continuous speech.
next_action: Add _has_speech_transcript flag to STTPipeline; set in _on_transcript for any non-empty text; clear in speak()/speak_streaming() alongside _transcript_parts.clear(); check in _commit_barge_in_after_window instead of _transcript_parts

## Symptoms

expected: User can interrupt (barge-in) TTS playback mid-sentence. TTS stops, STT picks up user speech, LLM responds.
actual: Either (a) TTS plays fully with no barge-in possible — STT not listening during playback, OR (b) TTS cuts out after 1-2 words as if barge-in fired spuriously. Non-deterministic.
errors: "TTS play_streaming: Cartesia returned no audio chunks for text len=138" seen in previous session — unclear if related.
reproduction: Run `daily voice`, wait for briefing, try to interrupt. Also cuts out with no interruption attempt.
started: Known issue on phase 17 voice polish branch.

## Eliminated

- hypothesis: stop_event being set before streaming starts (from prior barge-in)
  evidence: speak() clears stop_event in its finally block before control returns, and speak() is called for briefing + acknowledgements. Stop_event is cleared by the time streaming starts.
  timestamp: 2026-04-26

## Evidence

- timestamp: 2026-04-26
  checked: loop.py lines 253-258
  found: play_streaming_tokens() is called directly (turn_manager._tts.play_streaming_tokens()), bypassing VoiceTurnManager.speak() entirely.
  implication: _tts_active is NEVER set to True, STT mic is NEVER muted, _stop_event is not cleared before playback.

- timestamp: 2026-04-26
  checked: barge_in.py _on_speech_started() method (line 98)
  found: _was_tts_active_at_speech_start = self._tts_active. Since _tts_active=False during streaming, _was_tts_active_at_speech_start is always False.
  implication: filter_utterance() never recognizes streaming TTS as "during TTS", so backchannel suppression is disabled AND the barge-in timer fires for any ambient noise.

- timestamp: 2026-04-26
  checked: barge_in.py speak() method, _unmute_after_delay
  found: STT is muted for 500ms from TTS START to prevent echo. During this window, silent chunks are sent to Deepgram, so Deepgram cannot detect any user speech at all.
  implication: Bug A — if user begins speaking within the first 500ms of a TTS turn, Deepgram receives silence and never fires SpeechStarted. No barge-in fires, TTS completes normally.

- timestamp: 2026-04-26
  checked: STT muted=True effect in stt.py _select_chunk() (line 182)
  found: When muted, _SILENT_CHUNK (all zeros) is sent to Deepgram instead of real mic audio. Deepgram sees silence.
  implication: Confirms 500ms window is a complete dead zone for barge-in detection.

- timestamp: 2026-04-26
  checked: loop.py streaming path — _tts_active state and mute during play_streaming_tokens
  found: Neither _tts_active=True nor stt.muted=True is set. Deepgram receives live mic audio including TTS echo. SpeechStarted can fire from ambient noise or TTS bleed-through.
  implication: Bug B — spurious barge-in cuts streaming TTS after 1-2 words.

- timestamp: 2026-04-26 (second session)
  checked: _commit_barge_in_after_window and barge-in timer lifecycle
  found: Timer fires after 600ms with only one guard: _pending_barge_in_cancelled. That flag is only set True by filter_utterance() (called on UtteranceEnd) or by speak()/speak_streaming() starting. UtteranceEnd requires 1000ms of silence after SpeechStarted — which is LONGER than the 600ms timer. So for any noise that triggers SpeechStarted, the timer always fires before filter_utterance can cancel it.
  implication: Even with speak_streaming wrapper in place (Bug B fix), ambient room noise that crosses Deepgram's VAD threshold triggers SpeechStarted → 600ms timer → stop_event → TTS cut. This is Bug C — the barge-in fires without any real speech transcript.

- timestamp: 2026-04-26 (second session)
  checked: _commit_barge_in_after_window — what could gate it
  found: No check of _stt._transcript_parts. If Deepgram's VAD fires on ambient noise without producing any final transcript words, _transcript_parts remains empty (was cleared at start of speak_streaming). Real speech produces final transcripts via _on_transcript within ~300-500ms of utterance onset.
  implication: Adding a guard "only commit if _transcript_parts is non-empty OR if wait extended to give Deepgram time" would distinguish ambient noise from real speech. Best fix: extend window to 900ms (past 300ms endpointing) AND require non-empty transcript parts.

- timestamp: 2026-04-26 (third session)
  checked: Deepgram endpointing=300ms interaction with _transcript_parts guard
  found: _transcript_parts only gets populated when is_final=True. Deepgram marks a word final only after 300ms of intra-utterance silence (endpointing). Continuous speech (user speaks without pausing) has NO 300ms gaps → no finals produced → _transcript_parts stays empty for the entire 900ms barge-in window. This is why real barge-in stopped working — the guard was too strict.
  implication: Need to use interim transcripts as the gate. _on_transcript fires for BOTH interim and final results. Interims arrive within ~200-400ms of speech onset regardless of whether the user pauses. Ambient noise that crosses Deepgram's VAD without producing any recognisable words results in NO transcript events at all.

- timestamp: 2026-04-26 (third session)
  checked: stt.py _on_transcript — interim vs final handling
  found: interim results (is_final=False) are displayed on terminal but NOT accumulated in _transcript_parts. They are discarded after display. So _transcript_parts == [] throughout continuous speech.
  implication: Added _has_speech_transcript flag to STTPipeline. Set to True in _on_transcript for ANY non-empty text (interim OR final). Cleared in speak()/speak_streaming() at turn start and in finally blocks. _commit_barge_in_after_window checks _has_speech_transcript instead of _transcript_parts.

## Resolution

root_cause: |
  THREE ROOT CAUSES:
  
  BUG A — "TTS plays fully, no barge-in possible" (FIXED in prior session):
  The STT mic sends silent chunks (muted=True) for the first 500ms of every TTS turn.
  During this window, Deepgram receives silence and cannot detect user speech.
  Fix: Shortened mute window to 150ms.
  
  BUG B — "Streaming TTS cut by spurious barge-in" (FIXED in prior session):
  The streaming LLM→TTS path in loop.py called play_streaming_tokens() directly,
  bypassing VoiceTurnManager.speak(), so _tts_active was never set and STT was never muted.
  Fix: Added speak_streaming() wrapper to VoiceTurnManager; loop.py uses it.
  
  BUG C — "TTS cuts halfway through first word with ambient room noise" (FIXED — see below):
  _commit_barge_in_after_window fires stop_event after 600ms with only one guard:
  _pending_barge_in_cancelled. That flag is only cleared by filter_utterance(), which is
  called only on UtteranceEnd events. UtteranceEnd requires 1000ms of silence after
  speech — i.e., it arrives AFTER the 600ms timer fires. So ambient noise that triggers
  Deepgram's VAD (SpeechStarted) without producing any real speech will ALWAYS cause the
  timer to fire and set stop_event, cutting TTS immediately. filter_utterance() never gets
  a chance to intervene because UtteranceEnd arrives 400ms too late.

  BUG D — "Real barge-in broken after Bug C fix" (CURRENT — FIXED):
  The _transcript_parts guard added for Bug C was too strict. _transcript_parts only holds
  is_final=True results, which Deepgram only emits after 300ms of intra-utterance silence
  (endpointing=300ms). Continuous real speech never pauses 300ms mid-utterance, so
  _transcript_parts stays empty for the entire 900ms window → stop_event never set →
  TTS never interrupted. The guard needed to use interim transcripts (any non-empty
  Deepgram transcript result) as the signal, not just finals.

fix: |
  FIX 1 (Bug B — prior session): speak_streaming() wrapper added to VoiceTurnManager.
  FIX 2 (Bug A — prior session): Mute window shortened from 500ms to 150ms.
  
  FIX 3 (Bug C — prior session): Added transcript guard to _commit_barge_in_after_window.
  Changed window from 600ms to 900ms. Used _transcript_parts as gate (too strict — see Bug D).
  
  FIX 4 (Bug D — this session): Replaced _transcript_parts gate with _has_speech_transcript flag.
  Added _has_speech_transcript: bool = False to STTPipeline.__init__.
  Set to True in _on_transcript for ANY non-empty transcript text (interim OR final).
  Cleared in speak() and speak_streaming() at turn start AND in their finally blocks.
  _commit_barge_in_after_window checks self._stt._has_speech_transcript instead of _transcript_parts.

  Timing analysis for new fix:
  Real barge-in: user speaks → SpeechStarted → 150ms mute elapses → Deepgram receives real audio →
    interim transcript arrives ~200-400ms after onset → _has_speech_transcript=True →
    timer fires at ~900ms+150ms=1050ms → flag True → stop_event set → TTS stops. ✓
  Ambient noise (no words): VAD fires → no recognisable words → no transcript events at all →
    _has_speech_transcript stays False → timer fires → flag False → TTS continues. ✓

verification: syntax check passed (python3 ast.parse). Awaiting human verification.

closing_note: |
  Root cause is structural — no hardware AEC on macOS built-in speakers. 4 successive fixes
  (Bugs A-D) are heuristic workarounds. Solved by mobile-first architecture (v1.2) where
  iOS/Android provide OS-level AEC via AVAudioEngine and Oboe respectively. No further desktop
  voice fixes planned. Debug session closed 2026-04-27.

files_changed:
  - src/daily/voice/barge_in.py
  - src/daily/voice/stt.py
  - src/daily/voice/loop.py
