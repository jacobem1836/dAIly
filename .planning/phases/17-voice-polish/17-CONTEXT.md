# Phase 17: Voice Polish - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning
**Source:** PRD Express Path (CONVERSATIONAL_IMPROVEMENTS.md)

<domain>
## Phase Boundary

This phase delivers six improvements to dAIly's voice interaction layer to make it feel natural and conversational. All changes are isolated to `src/daily/voice/` and `src/daily/orchestrator/session.py`. No new external dependencies are introduced except optionally `speexdsp-python` (which is NOT chosen — Option B mic-mute is the recommendation). The phase does not touch briefing, integrations, scheduling, or the CLI.

Deliverables:
- Adaptive barge-in safety window (600ms) preventing accidental interruptions from noise/coughs
- Backchannel detection suppressing "yeah", "ok", "right" etc. from triggering barge-in
- Graceful TTS fade-out — current audio chunk finishes before stopping
- Agent acknowledgement phrases ("Got it.", "One sec.", etc.) bridging the silent LLM wait
- Streaming LLM→TTS — first sentence plays ~300ms after generation starts, not after full response
- Echo cancellation via mic-mute during TTS playback (Option B, not speexdsp AEC)

</domain>

<decisions>
## Implementation Decisions

### Improvement Order (LOCKED — implement in this sequence)
- **Step 1:** Improvement 3 — graceful TTS fade-out (`tts.py`, one-line reorder)
- **Step 2:** Improvement 6 Option B — mic-mute echo cancellation (`stt.py`, `barge_in.py`)
- **Step 3:** Improvement 1 — adaptive barge-in safety window 600ms (`barge_in.py`)
- **Step 4:** Improvement 2 — backchannel detection (`barge_in.py`, new `voice/utils.py`)
- **Step 5:** Improvement 4 — agent backchanneling acknowledgement phrases (`loop.py`)
- **Step 6:** Improvement 5 — streaming LLM→TTS (`session.py`, `tts.py`, `loop.py`)

### Improvement 1: Adaptive Barge-In Safety Window
- Replace immediate `stop_event.set()` in `VoiceTurnManager._on_speech_started` with a 600ms asyncio timer
- Add `_pending_barge_in_cancelled: bool = False` and `_barge_in_timer_task: asyncio.Task | None = None` to `VoiceTurnManager`
- `_on_speech_started` schedules `_commit_barge_in_after_window()` task instead of setting event directly
- Cancel in-flight timer in `speak()` at `stop_event.clear()` call and in `stop()`
- Exact implementation:
  ```python
  def _on_speech_started(self) -> None:
      self._pending_barge_in_cancelled = False
      self._barge_in_timer_task = asyncio.create_task(self._commit_barge_in_after_window())

  async def _commit_barge_in_after_window(self) -> None:
      await asyncio.sleep(0.6)
      if not self._pending_barge_in_cancelled:
          self._stop_event.set()
  ```

### Improvement 2: Backchannel Detection
- Add `_is_backchannel(text: str) -> bool` — module-level function in new `src/daily/voice/utils.py`
- Backchannel phrase set (frozenset, lowercase):
  `"yeah", "yep", "yup", "yes", "ok", "okay", "right", "got it", "uh-huh", "mm-hmm", "mmhm", "sure", "alright", "cool", "go on", "continue", "and", "so", "mm", "hmm", "interesting", "i see", "ah", "oh"`
- Match criteria: `word_count <= 3` AND `normalized in _BACKCHANNEL_PHRASES`
- Normalization: `text.strip().lower().rstrip(".,!?")`
- Add `_filter_utterance(text: str) -> bool` to `VoiceTurnManager`; only suppresses when `_tts_active is True`
- On backchannel: set `_pending_barge_in_cancelled = True`, cancel `_barge_in_timer_task`, return `False`
- Hook into utterance path in `loop.py` before passing to orchestrator

### Improvement 3: Graceful TTS Fade-Out
- In `TTSPipeline.play_streaming()`, move `stop_event.is_set()` check to AFTER `output_stream.write(response.audio)`, not before
- Exact change: move `if stop_event.is_set(): break` to below `output_stream.write(...)` line
- Do NOT drain the full sentence buffer — only current chunk completes

### Improvement 4: Agent Backchanneling
- Add `_ACKNOWLEDGEMENTS` list to `loop.py`: `["Got it.", "One sec.", "Sure.", "On it.", "Mmhm."]`
- Import `random` in `loop.py`
- After `user_input = await turn_manager.wait_for_utterance()`, before `run_session(...)`, call `await turn_manager.speak(random.choice(_ACKNOWLEDGEMENTS))`
- SKIP acknowledgement for: exit/quit confirmation flow, approval sub-loop
- SKIP on very first turn if briefing was just delivered

### Improvement 5: Streaming LLM→TTS
- Add `astream_session` variant in `src/daily/orchestrator/session.py` using LangGraph `.astream_events()`, filtering `on_chat_model_stream` events
- Add `play_streaming_tokens(token_stream: AsyncIterator[str], stop_event: asyncio.Event)` to `TTSPipeline`
  - Accumulates tokens into buffer
  - Sentence boundary detection: `. `, `! `, `? `, `\n`
  - Pushes each completed sentence to Cartesia via `ctx.push(sentence)`
  - At stream end, pushes any remaining buffer
  - Checks `stop_event` between chunks
- Wire in `loop.py` using `asyncio.gather` or producer/consumer `asyncio.Queue[str]`
- Fallback if LangGraph streaming is complex: use OpenAI SDK native streaming for `respond` node, pipe tokens to TTS directly

### Improvement 6: Echo Cancellation (Option B — mic mute)
- Use existing `muted: bool = False` field on `STTPipeline`
- In `STTPipeline._sd_callback`: send `_SILENT_CHUNK` instead of `indata.tobytes()` when `self.muted is True`
- In `VoiceTurnManager.speak()`: set `self._stt.muted = True` before TTS starts, `False` after TTS completes or is interrupted
- Unmute mic after 500ms delay into TTS playback (matches safety window from Improvement 1) to allow genuine barge-in while preventing echo at start
- Do NOT implement Option A (speexdsp AEC) — out of scope for this phase

### Claude's Discretion
- Test structure: manual testing per the test table in the PRD (no automated tests specified — these are perceptual UX changes)
- Whether to add unit tests for `_is_backchannel()` utility (recommended but not required by PRD)
- Exact asyncio task cancellation error handling in `_commit_barge_in_after_window`
- Queue buffer size for producer/consumer in Improvement 5

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Voice Layer Implementation
- `src/daily/voice/barge_in.py` — VoiceTurnManager, stop_event ownership, _tts_active flag, _on_speech_started
- `src/daily/voice/stt.py` — STTPipeline, _sd_callback, muted field, audio_queue
- `src/daily/voice/tts.py` — TTSPipeline, play_streaming(), output_stream, stop_event usage pattern
- `src/daily/voice/loop.py` — run_voice_session(), wait_for_utterance(), run_session() call site, exit/quit flow

### Orchestrator
- `src/daily/orchestrator/session.py` — run_session(), LangGraph graph, ainvoke pattern to be extended with astream_events

### PRD Source
- `CONVERSATIONAL_IMPROVEMENTS.md` — Full implementation specifications for all 6 improvements (authoritative)

</canonical_refs>

<specifics>
## Specific Ideas

### Key Implementation Details from PRD

**Barge-in safety window exact timing:** 600ms (`asyncio.sleep(0.6)`)

**Backchannel word list (exact, frozenset):**
```python
_BACKCHANNEL_PHRASES = frozenset({
    "yeah", "yep", "yup", "yes", "ok", "okay", "right", "got it",
    "uh-huh", "mm-hmm", "mmhm", "sure", "alright", "cool", "go on",
    "continue", "and", "so", "mm", "hmm", "interesting", "i see",
    "ah", "oh",
})
```

**Acknowledgement phrases (exact list):**
```python
_ACKNOWLEDGEMENTS = ["Got it.", "One sec.", "Sure.", "On it.", "Mmhm."]
```

**TTS fade-out — exact change:** Move `if stop_event.is_set(): break` to BELOW `output_stream.write(response.audio)` in the `async for response in ctx.receive()` loop.

**Mic mute timing:** Mute at TTS start, unmute after 500ms delay (allows genuine barge-in once TTS echo window has passed).

**Sentence boundary delimiters for streaming:** `. `, `! `, `? `, `\n`

### Test Scenarios (from PRD)
| Scenario | Expected |
|----------|----------|
| Cough while dAIly speaks | TTS continues |
| Say "yeah" while dAIly speaks | TTS continues (backchannel suppressed) |
| Say "stop" while dAIly speaks | TTS stops, dAIly listens |
| TTS echo triggers Deepgram | No barge-in (mic muted) |
| User asks question | Acknowledgement plays immediately |
| First word of response heard | Under 400ms after utterance completes |

</specifics>

<deferred>
## Deferred Ideas

- **Option A AEC (speexdsp):** Explicitly deferred — implement only if open-speaker setups become a requirement in future milestone
- **Audible acknowledgement on backchannel:** Playing a brief "mmhm" audio when detecting user backchannels — marked optional in PRD, defer to M2
- **Pre-recorded acknowledgement files:** PRD specifies real TTS calls (consistent voice); pre-recorded fallback deferred

</deferred>

---

*Phase: 17-voice-polish*
*Context gathered: 2026-04-25 via PRD Express Path*
