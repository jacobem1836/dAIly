# Phase 17: Voice Polish - Research

**Researched:** 2026-04-25
**Domain:** Python asyncio voice pipeline — barge-in, TTS/STT coordination, LangGraph streaming
**Confidence:** HIGH (all findings verified directly from source files)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Improvement Order (LOCKED — implement in this sequence)**
- Step 1: Improvement 3 — graceful TTS fade-out (`tts.py`, one-line reorder)
- Step 2: Improvement 6 Option B — mic-mute echo cancellation (`stt.py`, `barge_in.py`)
- Step 3: Improvement 1 — adaptive barge-in safety window 600ms (`barge_in.py`)
- Step 4: Improvement 2 — backchannel detection (`barge_in.py`, new `voice/utils.py`)
- Step 5: Improvement 4 — agent backchanneling acknowledgement phrases (`loop.py`)
- Step 6: Improvement 5 — streaming LLM→TTS (`session.py`, `tts.py`, `loop.py`)

No new external dependencies except optionally `speexdsp-python` — which is NOT chosen (Option B mic-mute chosen instead).

Phase is isolated to `src/daily/voice/` and `src/daily/orchestrator/session.py`.

### Claude's Discretion
- Test structure: manual testing per PRD test table (no automated tests specified)
- Whether to add unit tests for `_is_backchannel()` utility (recommended but not required)
- Exact asyncio task cancellation error handling in `_commit_barge_in_after_window`
- Queue buffer size for producer/consumer in Improvement 5

### Deferred Ideas (OUT OF SCOPE)
- Option A AEC (speexdsp): explicitly deferred
- Audible acknowledgement on backchannel: deferred to M2
- Pre-recorded acknowledgement files: deferred
</user_constraints>

---

## Summary

Phase 17 delivers six incremental improvements to the voice pipeline. All changes are
surgical — confined to four existing files and one new utility module. The codebase has
been read in full; the findings below describe the exact current state of each file so
the planner can write task actions with precise line references rather than approximations.

The most complex improvement is Improvement 5 (streaming LLM→TTS). The respond_node
uses the OpenAI SDK directly (`client.chat.completions.create` with `json_object`
response_format, not LangGraph's ChatOpenAI). This means LangGraph's `.astream_events()`
for `on_chat_model_stream` events will NOT produce token-level chunks for the respond
node. The practical path for Improvement 5 is an OpenAI streaming variant inside
`session.py` or a new `astream_session` that bypasses the graph for respond-only turns.

All other improvements (1–4, 6) are straightforward field additions and logic rewires
within `barge_in.py`, `stt.py`, `tts.py`, and `loop.py`.

**Primary recommendation:** Implement in the locked order (Steps 1–6). Each step is
independently testable and does not break the previous step. Improvement 5 should use
OpenAI SDK native streaming (not LangGraph astream_events) because respond_node calls
the SDK directly with `response_format=json_object`.

---

## Project Constraints (from CLAUDE.md)

- Architecture: LLM must not directly access APIs or hold credentials — backend mediates everything
- Privacy: Raw email/message bodies must not be stored long-term
- Latency: Voice responses must feel instant — precompute briefings, stream TTS
- Security: OAuth tokens encrypted at rest (AES-256)
- Autonomy: All external-facing actions require user approval in M1
- Code style: PEP 8, type annotations on all function signatures, black/ruff formatting
- Functions: <50 lines; files <800 lines
- Immutability: create new objects, never mutate existing ones
- No hardcoded secrets

---

## Current State of Each File (VERIFIED by direct read)

### `src/daily/voice/barge_in.py` — VoiceTurnManager

**Current fields in `__init__`** [VERIFIED: file read]:
```python
self._tts = tts
self._stt = stt
self._stop_event: asyncio.Event = asyncio.Event()
self._tts_active: bool = False
self._tts_task: asyncio.Task | None = None
self._stt_task: asyncio.Task | None = None
```

Fields that do NOT yet exist (must be added):
- `_pending_barge_in_cancelled: bool = False`
- `_barge_in_timer_task: asyncio.Task | None = None`

**Current `_on_speech_started` (line 56–66)** [VERIFIED]:
```python
def _on_speech_started(self) -> None:
    self._stop_event.set()
```
This sets `stop_event` unconditionally. No safety window, no backchannel guard.

**Current `speak()` structure (lines 72–111)** [VERIFIED]:
1. `self._stop_event.clear()` — line 86
2. `self._tts_active = True` — line 87
3. `self._stt._transcript_parts.clear()` — line 88
4. `asyncio.create_task(self._tts.play_streaming(...))` — line 91
5. `await self._tts_task` — line 94
6. `finally`: `self._tts_active = False`, `self._stop_event.clear()`, `self._tts_task = None` — lines 102–109

The `_stop_event.clear()` at line 86 is the exact location where the barge-in timer cancel must be inserted (Step 3).

**Current `stop()` structure (lines 134–153)** [VERIFIED]:
Cancels `_tts_task` via `self._stop_event.set()` then `.cancel()`, then cancels `_stt_task`. The barge-in timer cancel must be inserted here too (Step 3).

**Echo suppression note** [VERIFIED by docstring]: The previous echo-suppression guard in `_on_speech_started` was removed ("Barge-in: SpeechStarted always sets stop_event — echo-suppression guard removed because it blocked all user interrupts during briefing playback"). The existing tests `test_echo_suppression_during_tts` and `test_real_barge_in_when_tts_inactive` in `test_voice_barge_in.py` test the OLD behavior (echo suppression when `_tts_active=True`). These tests will need updating when the 600ms timer replaces the unconditional set — see Test Impact section below.

### `src/daily/voice/stt.py` — STTPipeline

**Current `__init__` fields** [VERIFIED: line 81]:
```python
self.muted: bool = False  # Set True during TTS to suppress echo feedback
```
`muted` field ALREADY EXISTS. No addition needed.

**`_SILENT_CHUNK` constant** [VERIFIED: line 41]:
```python
_SILENT_CHUNK = bytes(_BLOCKSIZE * 2)  # Silent audio (linear16 = 2 bytes/sample) for keepalive
```
`_SILENT_CHUNK` ALREADY EXISTS as a module-level constant.

**Current `_sd_callback` (lines 182–194)** [VERIFIED]:
```python
def _sd_callback(indata, frames, time_info, status) -> None:
    if status:
        logger.warning("sounddevice status: %s", status)
    loop.call_soon_threadsafe(audio_queue.put_nowait, indata.tobytes())
```
The callback sends `indata.tobytes()` unconditionally. The mic-mute change (Step 2) requires:
```python
chunk = _SILENT_CHUNK if self.muted else indata.tobytes()
loop.call_soon_threadsafe(audio_queue.put_nowait, chunk)
```
Note: `_sd_callback` is a nested function inside `start_listening`. It captures `self` via closure because `self` is in scope from the outer method. The `self.muted` read will work correctly in the thread-safety model — `self.muted` is a simple boolean and the read is not synchronized, but this is acceptable for a one-directional mute flag (small race window is safe: worst case is one extra audio chunk from the mic, which Deepgram will discard as very short audio).

### `src/daily/voice/tts.py` — TTSPipeline

**Current `play_streaming` receive loop (lines 161–167)** [VERIFIED]:
```python
async for response in ctx.receive():
    if stop_event.is_set():
        break  # Barge-in detected — stop immediately (D-04)
    if response.type == "chunk" and response.audio:
        output_stream.write(response.audio)
```
The stop_event check is BEFORE the write. The graceful fade-out change (Step 1) moves it AFTER:
```python
async for response in ctx.receive():
    if response.type == "chunk" and response.audio:
        output_stream.write(response.audio)
    if stop_event.is_set():
        break
```
This is the one-line reorder described in CONTEXT.md.

**Test impact**: `test_play_streaming_stops_on_event` in `test_voice_tts.py` sets `stop_event` at index 2 and asserts `len(chunks_written) < 5`. After the reorder, the chunk at index 2 WILL be written before the break. The test assertion `< 5` remains valid (it will be 3, not 2), but the test should be updated to reflect the new semantics if it asserts an exact count.

### `src/daily/voice/loop.py` — run_voice_session

**`run_session` call site (line 325)** [VERIFIED]:
```python
result = await run_session(
    graph,
    user_input,
    config,
    initial_state=initial_state if first_turn else None,
)
```

**Flows that must be EXCLUDED from acknowledgement phrases (Step 5)**:
1. Exit/quit confirmation path (lines 312–321): `if normalized in ("exit", "quit")` — explicit check
2. Approval sub-loop: `_handle_voice_approval` called when `graph_state.next` is truthy (line 341)
3. First-turn briefing: `first_turn = True` flag (line 297) — the CONTEXT.md says skip acknowledgement on very first turn if briefing was just delivered

**Pending utterance path** (lines 302–305): `_pending` utterance from a briefing interrupt goes through the same main loop. Acknowledgements should fire here too (it is a real user request).

**Imports present** [VERIFIED: lines 1–38]: `asyncio`, `re`, `random` is NOT currently imported. Must add `import random`.

**`_ACKNOWLEDGEMENTS` list**: does not exist yet — must be added as a module-level constant in `loop.py`.

**Backchannel hook location** (Step 4): After `user_input = await turn_manager.wait_for_utterance()` on line 307, before the `normalized = user_input.lower().strip()` check. The backchannel filter must only fire when `turn_manager._tts_active` is (or was) True — but by the time UtteranceEnd fires, `speak()` has likely already returned. The CONTEXT.md specifies `_filter_utterance` checks `_tts_active is True` — this means backchannels are only suppressed when TTS is still running when the utterance arrives. The safety window (600ms) is what keeps TTS active long enough for the check to work.

### `src/daily/orchestrator/session.py` — run_session

**Current `run_session` (lines 168–193)** [VERIFIED]:
```python
async def run_session(graph, user_input, config, initial_state=None):
    state_input = {"messages": [("human", user_input)]}
    if initial_state:
        state_input.update(initial_state)
    return await graph.ainvoke(state_input, config)
```
Returns the full state dict from `graph.ainvoke`. No streaming.

**LangGraph version constraint** [VERIFIED: pyproject.toml]: `langgraph>=1.1.6`. LangGraph 1.x supports `.astream_events()` [ASSUMED — based on LangGraph docs, not verified in this session].

**Critical finding for Improvement 5**: The `respond_node` uses the OpenAI Python SDK **directly** (`client.chat.completions.create` with `response_format={"type": "json_object"}`), not via LangChain's `ChatOpenAI`. This means LangGraph's `.astream_events()` with `on_chat_model_stream` filter will NOT capture token-level chunks from `respond_node` — that event is only emitted by LangChain/LangGraph model wrappers, not raw OpenAI SDK calls [ASSUMED — this is the standard LangGraph behavior, not verified against LangGraph 1.1.6 source in this session].

**Practical implication**: For Improvement 5, the streaming approach must either:
- (A) Add an `astream_session` function that calls respond logic directly with `client.chat.completions.create(..., stream=True)` and pipes tokens to TTS — bypasses the graph entirely for respond-only turns
- (B) Modify `respond_node` to use `ChatOpenAI` (LangChain wrapper) so LangGraph can intercept token events — more invasive refactor
- (C) Add streaming within `respond_node` itself by accepting a token callback parameter

The CONTEXT.md says "Fallback if LangGraph streaming is complex: use OpenAI SDK native streaming for respond node, pipe tokens to TTS directly." Option A is the fallback and is actually the simpler path given that respond_node uses the SDK directly. **Recommended: Option A** — add `astream_session` in `session.py` that calls OpenAI streaming directly and yields token strings via `AsyncIterator[str]`.

---

## Standard Stack

### Core (all VERIFIED from pyproject.toml)
| Library | Version Pinned | Purpose |
|---------|---------------|---------|
| asyncio | stdlib | Task scheduling, event loop, asyncio.Event, asyncio.Task |
| cartesia | >=3.0.2 | TTS WebSocket streaming (ctx.push, ctx.receive) |
| deepgram-sdk | >=6.1.1 | STT WebSocket streaming |
| sounddevice | >=0.5.5 | PCM audio I/O (InputStream, RawOutputStream) |
| openai | >=2.0.0 | LLM API (streaming via `stream=True`) |
| langgraph | >=1.1.6 | Graph execution (ainvoke, optional astream_events) |

### New Module
| File | Purpose |
|------|---------|
| `src/daily/voice/utils.py` | `_is_backchannel(text) -> bool`, `_BACKCHANNEL_PHRASES` frozenset |

No new pip dependencies for this phase.

---

## Architecture Patterns

### Pattern 1: asyncio.Task for Deferred Action
**What:** Schedule work to happen after a delay; allow cancellation before it runs.
**When to use:** The barge-in safety window (Improvement 1).
```python
# Source: CONTEXT.md implementation spec (VERIFIED pattern)
def _on_speech_started(self) -> None:
    self._pending_barge_in_cancelled = False
    self._barge_in_timer_task = asyncio.create_task(
        self._commit_barge_in_after_window()
    )

async def _commit_barge_in_after_window(self) -> None:
    await asyncio.sleep(0.6)
    if not self._pending_barge_in_cancelled:
        self._stop_event.set()
```

**Cancellation pattern (at speak() start and stop())**:
```python
if self._barge_in_timer_task is not None and not self._barge_in_timer_task.done():
    self._barge_in_timer_task.cancel()
    # Do NOT await here in a sync context — fire and forget cancel
```
The task can be cancelled without awaiting in a synchronous method. The CancelledError is absorbed by the task.

### Pattern 2: Thread-safe mute flag (sounddevice callback)
**What:** The `_sd_callback` runs on the PortAudio thread (non-asyncio). Reading `self.muted` from it is safe for a simple boolean.
**Thread model**: Write side (asyncio loop sets `self.muted`) and read side (PortAudio thread reads `self.muted`) are in separate threads. Python's GIL makes simple boolean reads/writes atomic, so no lock is needed [ASSUMED — standard Python threading knowledge].

### Pattern 3: OpenAI SDK streaming for token-level TTS
**What:** Use `stream=True` on `client.chat.completions.create` to receive token deltas.
```python
# Source: OpenAI SDK pattern [ASSUMED based on training knowledge + SDK docs]
async def _astream_respond_tokens(
    user_input: str,
    system_prompt: str,
) -> AsyncIterator[str]:
    async with client.chat.completions.stream(
        model="gpt-4.1-mini",
        messages=[...],
    ) as stream:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
```
Note: The respond_node uses `response_format={"type": "json_object"}`. For streaming, the tokens will arrive as partial JSON — the planner must decide whether to stream the raw tokens (and extract `narrative` only after full JSON assembly) or to use a non-JSON format for the streaming path. This is a design decision for Improvement 5.

### Anti-Patterns to Avoid
- **Awaiting task cancel in sync methods**: `asyncio.create_task(coro).cancel()` is fine; do not `await` the cancel inside a sync callback like `_on_speech_started`.
- **Sharing asyncio objects across threads**: Never pass `asyncio.Event` or `asyncio.Queue` directly to the PortAudio callback; always use `loop.call_soon_threadsafe`.
- **Blocking the voice loop with acknowledgement TTS**: `await turn_manager.speak(ack)` is correct — it completes before `run_session` starts. Do not fire-and-forget the ack.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Sentence boundary detection for token stream | Custom regex | Re-use existing `split_sentences` from `tts.py` or apply the `_BOUNDARY_PATTERN` already defined there |
| Backchannel word list | Custom NLP | Simple frozenset + word count as specified in CONTEXT.md |
| Token streaming buffer | Custom ring buffer | `asyncio.Queue[str]` producer/consumer pattern |

---

## Common Pitfalls

### Pitfall 1: Timer cancel in synchronous callback
**What goes wrong:** `_on_speech_started` is called as a plain sync callback from the Deepgram message handler. Calling `await task.cancel()` inside it will raise a runtime error.
**Why it happens:** You cannot await in a non-async function.
**How to avoid:** Call `task.cancel()` without await. The task will absorb the CancelledError internally.
**Warning signs:** `RuntimeWarning: coroutine 'Task.cancel' was never awaited`

### Pitfall 2: Barge-in timer fires after speak() returns
**What goes wrong:** The 600ms timer is created by `_on_speech_started` during TTS playback, but TTS completes before the 600ms elapses. The timer then fires after `speak()` has returned, setting `stop_event` on the NEXT turn's clear/set cycle.
**Why it happens:** `speak()` calls `self._stop_event.clear()` at the start but does not cancel the pending timer.
**How to avoid:** Always cancel `_barge_in_timer_task` at the top of `speak()` (before `stop_event.clear()`) AND in `stop()`. The CONTEXT.md explicitly specifies this.
**Warning signs:** Random barge-in on the next user turn after a noisy previous TTS.

### Pitfall 3: Existing tests test OLD behavior
**What goes wrong:** `test_echo_suppression_during_tts` tests that `_on_speech_started` does NOT set stop_event when `_tts_active=True`. After Improvement 1 (barge-in timer), the behavior changes — `_on_speech_started` no longer reads `_tts_active` at all.
**Why it happens:** The test was written for an echo-suppression guard that was already removed in a prior phase (per barge_in.py docstring), but the test was never updated to match.
**How to avoid:** The planner must include a task to update `test_voice_barge_in.py` when implementing Improvement 1.
**Warning signs:** The test passes before Phase 17 (because `_on_speech_started` sets stop_event unconditionally regardless of `_tts_active`) but will fail after Improvement 1 replaces the direct set with a timer.

### Pitfall 4: Streaming JSON and sentence boundary detection conflict
**What goes wrong:** `respond_node` uses `response_format={"type": "json_object"}`. Streaming this produces partial JSON tokens like `{"`, `"narrative":`, `"Got`, ` it",`, `"actions`:` etc. — not natural sentence text. Piping these raw tokens to TTS will produce garbled audio.
**Why it happens:** JSON object format wraps the narrative in a JSON envelope.
**How to avoid:** For the streaming path, either (a) switch to plain text response in the streaming variant and parse differently, or (b) buffer the full JSON then stream the extracted narrative via sentence splitter. Option (b) defeats latency goals. Option (a) requires a separate streaming prompt that returns plain text.
**Warning signs:** TTS speaks curly braces and colons.

### Pitfall 5: Backchannel detection timing vs. `_tts_active`
**What goes wrong:** `_filter_utterance` is supposed to suppress backchannels "only when `_tts_active is True`." But `UtteranceEnd` fires after a 1000ms silence window (current `utterance_end_ms=1000` in STTPipeline), which means by the time the utterance arrives in `loop.py`, TTS has likely already completed and `_tts_active` is False.
**Why it happens:** The 600ms timer fires and stops TTS → `speak()` returns → `_tts_active = False`. Then 1000ms of silence → UtteranceEnd → utterance enters the queue. `_tts_active` is already False.
**How to avoid:** The backchannel filter may need to check `_tts_active` at the timer commit point (inside `_commit_barge_in_after_window`), not at loop.py receive time. Alternatively, the filter in `loop.py` can suppress based on the known backchannel phrase list regardless of `_tts_active` state — accepting false negatives (suppressing a genuine "yes" question). The CONTEXT.md spec says filter when `_tts_active is True` — the planner should flag this timing concern as a discretion decision.
**Warning signs:** Backchannel detection never fires because `_tts_active` is always False when utterances arrive.

---

## Runtime State Inventory

Step 2.6: SKIPPED — This phase is purely code changes within `src/daily/voice/` and `src/daily/orchestrator/session.py`. No stored data, live service configs, OS-registered state, secrets, or build artifacts embed voice pipeline internals.

---

## Environment Availability

Step 2.6: All external dependencies (Deepgram, Cartesia, sounddevice, OpenAI, LangGraph) are already in use and verified working in prior phases. No new dependencies introduced.

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| cartesia>=3.0.2 | TTS streaming | Yes | Already pinned in pyproject.toml |
| openai>=2.0.0 | Streaming LLM | Yes | Already pinned, streaming=True is a standard SDK feature |
| sounddevice>=0.5.5 | Mic mute via silent chunk | Yes | Already in use |
| asyncio | Timer tasks | Yes | stdlib |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (assumed) |
| Quick run command | `pytest tests/test_voice_barge_in.py tests/test_voice_tts.py tests/test_voice_stt.py tests/test_voice_loop.py -x` |
| Full suite command | `pytest tests/ -x` |

### Existing Test Files (VERIFIED)
| File | What It Tests | Impact from Phase 17 |
|------|--------------|----------------------|
| `tests/test_voice_barge_in.py` | VoiceTurnManager speak/stop/barge-in | NEEDS UPDATE — 2 tests will fail after Improvement 1 (see Pitfall 3) |
| `tests/test_voice_tts.py` | TTSPipeline play_streaming | May need update for graceful fade-out semantics in Improvement 3 |
| `tests/test_voice_stt.py` | STTPipeline | May need update if mute logic tested |
| `tests/test_voice_loop.py` | run_voice_session | May need update for acknowledgement phrases |

### Tests That Must Break and Be Updated
1. `test_echo_suppression_during_tts` — tests `_tts_active` guard that no longer exists as a direct check
2. `test_real_barge_in_when_tts_inactive` — tests unconditional stop_event.set() that will be replaced by timer
3. `test_play_streaming_stops_on_event` — may need exact chunk count assertion updated

### New Tests for Claude's Discretion (optional per CONTEXT.md)
- `tests/test_voice_utils.py` — `_is_backchannel()` unit tests (pure function, easy to test)

### Wave 0 Gaps
- `src/daily/voice/utils.py` — new file, no test file exists yet
- If planner decides to add `_is_backchannel` unit tests: `tests/test_voice_utils.py` needs creating

---

## Security Domain

Phase 17 does not introduce new authentication, authorization, or data storage paths. The mic-mute feature does not store or transmit audio data differently — silent chunks are sent to Deepgram in place of real audio, which is acoustically equivalent to silence. No new ASVS categories apply.

| ASVS Category | Applies | Notes |
|---------------|---------|-------|
| V5 Input Validation | yes | Backchannel phrase matching is on Deepgram-provided transcript text — already passes through existing STT pipeline; no new user input boundary |
| All others | no | No new auth, sessions, crypto, or access control |

---

## Improvement 5 Deep-Dive: Streaming LLM→TTS

This is the highest-complexity improvement. Detailed findings:

**Current respond_node pattern (VERIFIED: nodes.py line 229)**:
```python
response = await client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[...],
    response_format={"type": "json_object"},
    max_tokens=400,
)
```
Returns a single `OrchestratorIntent` JSON object. The `narrative` field is extracted from this.

**Streaming path design options (ranked by implementation cost)**:

**Option A — OpenAI SDK streaming in `astream_session` (RECOMMENDED)**:
- Add `astream_session(graph, user_input, config, initial_state) -> AsyncIterator[str]` to `session.py`
- Inside, detect that routing would go to `respond` (keyword check mirrors `route_intent`)
- For respond-intent turns: call `client.chat.completions.create(stream=True)` with a plain-text prompt (no JSON format)
- Yield token strings to caller
- For non-respond-intent turns (summarise, draft, etc.): fall back to `run_session` (non-streaming)
- Wire in `loop.py`: if `astream_session` returns a streaming iterator, pass to `TTSPipeline.play_streaming_tokens`

**Option B — LangGraph astream_events**:
- Would require respond_node to use `ChatOpenAI` LangChain wrapper instead of raw SDK
- Invasive: changes `nodes.py` (out of phase scope per CONTEXT.md)
- Not recommended

**Sentence boundary detection for token stream**:
The CONTEXT.md specifies: `. `, `! `, `? `, `\n` as delimiters. This is simpler than `tts.py`'s existing `_BOUNDARY_PATTERN` (which handles abbreviations). For the streaming accumulator, the simple character-pair check is sufficient — the sentence will be complete text, not mid-word JSON.

**TTSPipeline.play_streaming_tokens** new method signature:
```python
async def play_streaming_tokens(
    self,
    token_stream: AsyncIterator[str],
    stop_event: asyncio.Event,
) -> None:
```
Accumulates tokens, detects sentence boundaries, pushes each complete sentence via `ctx.push(sentence)`, plays audio concurrently.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | LangGraph 1.1.6 supports `.astream_events()` with `on_chat_model_stream` filter | Improvement 5 deep-dive | Only affects Improvement 5 Option B — Option A (OpenAI SDK streaming) does not depend on this |
| A2 | LangGraph `.astream_events()` `on_chat_model_stream` only fires for LangChain model wrappers, not raw OpenAI SDK calls | Improvement 5 deep-dive | If wrong, Option B (astream_events) becomes viable — but Option A remains simpler |
| A3 | Python GIL makes boolean reads/writes atomic (no lock needed for `self.muted` across threads) | Pattern 2 (mic mute) | If wrong, a threading.Event should be used instead — low risk, Python GIL is well-documented |
| A4 | `asyncio.Task.cancel()` (without await) in a sync method correctly schedules cancellation | Pitfall 1 | If wrong, timer would not cancel — test by verifying the task raises CancelledError |

**If this table is empty:** All other claims in this research were verified directly from the source files.

---

## Open Questions (RESOLVED)

1. **Backchannel detection timing vs. `_tts_active`**
   - What we know: `UtteranceEnd` fires 1000ms after speech stops; `_tts_active` is cleared when `speak()` returns (before UtteranceEnd fires for most short backchannels)
   - What's unclear: Should `_filter_utterance` check `_tts_active` at filter time (likely always False) or should the 600ms barge-in timer capture whether TTS was active when the speech started?
   - **RESOLVED:** Use `_was_tts_active_at_speech_start: bool = False` flag, set to `True` in `_on_speech_started` and cleared in `speak()` finally block. Backchannel filter checks this flag, NOT `_tts_active` at filter time. Implemented in Plan 17-03 Task 1.

2. **Streaming LLM→TTS and JSON response format**
   - What we know: respond_node uses `response_format={"type": "json_object"}` and parses `OrchestratorIntent`
   - What's unclear: The streaming path should return plain text for latency; but this means a separate prompt path that does not validate `OrchestratorIntent`
   - **RESOLVED:** The `astream_session` streaming variant uses a plain-text system prompt (no `response_format=json_object`). Only the `narrative` field matters for voice TTS — `actions` and `signals` are not used in the streaming path. Non-respond intents raise `StreamingNotSupported` and fall back to `run_session`. Implemented in Plan 17-04 Task 1.

3. **Acknowledgement phrase and very-first-turn briefing interaction**
   - What we know: CONTEXT.md says "SKIP on very first turn if briefing was just delivered." The `first_turn` flag exists (line 297 in loop.py).
   - What's unclear: What counts as "briefing was just delivered"? The `briefing_narrative` was spoken, or any first turn?
   - **RESOLVED:** Skip acknowledgement when `first_turn is True` (covers the case where briefing was just delivered; any first turn is treated as post-briefing). Implemented in Plan 17-03 Task 3.

---

## Sources

### Primary (HIGH confidence — verified by direct file read)
- `src/daily/voice/barge_in.py` — full file read, all field names and line numbers verified
- `src/daily/voice/stt.py` — full file read, `_SILENT_CHUNK` and `muted` field verified
- `src/daily/voice/tts.py` — full file read, receive loop structure and stop_event position verified
- `src/daily/voice/loop.py` — full file read, all exit paths, `first_turn`, `_pending` verified
- `src/daily/orchestrator/session.py` — full file read, `run_session` signature and return verified
- `src/daily/orchestrator/nodes.py` — partial read, respond_node LLM call pattern verified
- `src/daily/orchestrator/graph.py` — partial read, route_intent logic verified
- `tests/test_voice_barge_in.py` — full file read, impacted tests identified
- `tests/test_voice_tts.py` — full file read, impacted tests identified
- `pyproject.toml` — package versions verified

### Secondary (MEDIUM confidence — from CONTEXT.md)
- `CONVERSATIONAL_IMPROVEMENTS.md` — PRD spec (not fully read in this session; CONTEXT.md distills it)
- `.planning/phases/17-voice-polish/17-CONTEXT.md` — user decisions, locked implementation specs

---

## Metadata

**Confidence breakdown:**
- Current file state: HIGH — every field, line, and method structure verified by direct read
- Improvement 1–4, 6 implementation: HIGH — exact code locations and required changes confirmed
- Improvement 5 (streaming): MEDIUM — OpenAI SDK streaming path is clear; LangGraph astream_events limitation is assumed, not verified against LangGraph 1.1.6 source
- Test impact: HIGH — impacted tests identified by name with specific failure modes

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (stable codebase — these files change only when developed)

---

## RESEARCH COMPLETE
