# Phase 5: Voice Interface - Research

**Researched:** 2026-04-13
**Domain:** Real-time voice I/O — Deepgram STT WebSocket, Cartesia TTS WebSocket, asyncio barge-in, sounddevice, AsyncPostgresSaver
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** New `daily voice` CLI command mirrors `daily chat` structure. Python captures microphone via sounddevice/pyaudio, streams audio to Deepgram WebSocket, plays Cartesia TTS audio back locally. No new server infrastructure — everything runs in-process like `daily chat`. FastAPI WebSocket architecture is deferred to M2+.
- **D-02:** `daily voice` wires the same orchestrator graph as `daily chat` (`build_graph`, `create_session_config`, `initialize_session_state`, `run_session`). Voice is an I/O layer on top of the existing orchestrator — not a separate agent.
- **D-03:** Asyncio tasks + `asyncio.Event` stop flag for barge-in. TTS playback runs in a task; STT listener runs in parallel. When Deepgram fires `speech_started` (VAD utterance detected), the stop_event is set, cancelling the TTS task.
- **D-04:** TTS task must check the stop_event between audio chunks, not just at sentence boundaries. Barge-in should feel immediate — don't finish the current sentence before stopping.
- **D-05:** Deepgram built-in VAD only. Use `UtteranceEnd` and `speech_started` events from the Deepgram streaming API. No Silero VAD.
- **D-06:** End-of-utterance detection uses Deepgram `UtteranceEnd` event. When `UtteranceEnd` fires, the accumulated transcript is sent to the orchestrator for processing.
- **D-07:** Cartesia Sonic-3 via WebSocket SDK. Stream audio sentence-by-sentence — split the LLM response into sentences, send each to Cartesia, begin playback as the first chunk arrives. Do not wait for full response before starting TTS.
- **D-08:** Audio playback via `sounddevice`. Stream raw PCM bytes from Cartesia directly to sounddevice output stream.
- **D-09:** Deepgram Nova-3 via WebSocket SDK (`deepgram-sdk` Python package). Mic capture via `sounddevice` input stream, fed into Deepgram WebSocket. Use interim results for low-latency display; act on `UtteranceEnd`.
- **D-10:** Interim transcripts displayed in-place on the terminal (not sent to orchestrator). Final transcript triggers the orchestrator turn.
- **D-11:** Switch from `MemorySaver` to `AsyncPostgresSaver` in Phase 5. Voice sessions persist state across turns. The `daily voice` command initialises the checkpointer the same way FastAPI lifespan will in M2+.
- **D-12:** 4 plans: Plan 1 — TTS pipeline; Plan 2 — STT pipeline; Plan 3 — Barge-in; Plan 4 — Full voice loop integration.

### Claude's Discretion

- Exact sentence splitter logic (regex vs NLTK)
- Cartesia voice ID / model parameter selection
- Deepgram model parameters (language, encoding, sample_rate)
- sounddevice input/output stream configuration (sample rate, channels, dtype)
- How partial transcripts are displayed in-place (ANSI escape codes or simple reprint)
- Error recovery when Deepgram or Cartesia WebSocket disconnects mid-session
- Module structure within `src/daily/voice/`

### Deferred Ideas (OUT OF SCOPE)

- FastAPI WebSocket voice endpoint — M2+
- Silero VAD — rejected for M1
- Voice cloning — M2+
- Wake word ("Hey Daily") — out of scope for M1
- Multi-speaker diarisation — not needed in single-user M1
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VOICE-01 | System streams TTS output sentence-by-sentence (Cartesia Sonic-3), beginning playback before full response is generated | Cartesia WebSocket SDK `ctx.push()` per sentence + `ctx.receive()` streaming pattern documented; sounddevice raw PCM playback confirmed |
| VOICE-02 | System streams STT input with interim results (Deepgram Nova-3) to minimise perceived latency | Deepgram `interim_results=True` + `LiveTranscriptionEvents.Transcript` on_message confirmed; in-place terminal display via ANSI codes |
| VOICE-03 | End-to-end voice response latency under 1.5s for follow-up turns; briefing delivery begins within 1s (from cache) | Deepgram sub-300ms STT + Cartesia 40-90ms TTS TTFB; Redis cache pre-loads briefing narrative; existing `initialize_session_state` reused |
| VOICE-04 | User can interrupt briefing mid-sentence (VAD-based barge-in) | `speech_started` event from Deepgram triggers `asyncio.Event`; TTS task checks stop_event per chunk; `asyncio.Task.cancel()` confirmed pattern |
| VOICE-05 | User can ask follow-up questions with session context retained | `AsyncPostgresSaver` replacing `MemorySaver` persists graph state across turns by thread_id; existing `run_session` reused unchanged |
</phase_requirements>

---

## Summary

Phase 5 adds voice I/O as a thin layer over the existing LangGraph orchestrator. The core pattern mirrors `_run_chat_session()` in `cli.py` exactly — the only difference is replacing `input()`/`print()` with microphone capture and TTS playback. No new graph nodes are needed.

The two new external dependencies are `deepgram-sdk>=6.1.1` (current latest on PyPI) and `cartesia>=3.0.2` (current latest, with `cartesia[websockets]` extra), plus `sounddevice>=0.5.5` for cross-platform audio I/O. All three are not currently in `pyproject.toml` and must be added.

The barge-in architecture is the most technically novel part. It requires two concurrent asyncio tasks — a TTS playback task and a continuous Deepgram STT listener — coordinated by a shared `asyncio.Event`. The Deepgram `speech_started` VAD event triggers the stop_event, which the TTS task polls between PCM chunks. This gives sub-chunk interrupt latency rather than waiting for sentence completion.

`AsyncPostgresSaver` is already in the lock file (`langgraph-checkpoint-postgres==3.0.5`, `psycopg[binary]>=3.3.3`). No new DB dependency is needed — just wiring it into the voice session initialisation.

**Primary recommendation:** Build all voice modules in `src/daily/voice/` as a clean package (tts.py, stt.py, barge_in.py, loop.py). Keep CLI wiring in `cli.py` thin. This makes the M2 WebSocket upgrade straightforward.

---

## Standard Stack

### Core New Dependencies

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| deepgram-sdk | 6.1.1 | STT WebSocket — Nova-3 live transcription | Official SDK; v6 is current GA; Python-first; AsyncDeepgramClient for asyncio |
| cartesia | 3.0.2 | TTS WebSocket — Sonic-3 sentence streaming | Official SDK; `cartesia[websockets]` extra required for WebSocket support; v3.x is current GA |
| sounddevice | 0.5.5 | Mic capture + PCM playback | Cross-platform PortAudio wrapper; asyncio-queue pattern documented; already chosen in CONTEXT.md |

[VERIFIED: pip index versions deepgram-sdk, cartesia, sounddevice]

### Already in Lock File (no new install)

| Library | Version | Purpose |
|---------|---------|---------|
| langgraph-checkpoint-postgres | 3.0.5 | `AsyncPostgresSaver` for persistent checkpointing |
| psycopg[binary] | 3.3.3+ | Async Postgres driver for AsyncPostgresSaver |
| redis | 7.x | Briefing cache (already used by existing CLI) |
| langgraph | 1.1.6 | Graph execution — unchanged |

[VERIFIED: uv.lock grep]

### Installation

```bash
uv add deepgram-sdk cartesia "cartesia[websockets]" sounddevice
```

Note: `cartesia[websockets]` installs the `websockets` library required for WebSocket streaming. Without this extra, `client.tts.websocket_connect()` will fail at runtime with an import error.

---

## Architecture Patterns

### Recommended Module Structure

```
src/daily/voice/
├── __init__.py          # Public re-exports: TTSPipeline, STTPipeline, run_voice_session
├── tts.py               # Cartesia WebSocket TTS: sentence splitter + PCM streaming
├── stt.py               # Deepgram WebSocket STT: mic capture + transcript handling
├── barge_in.py          # asyncio task coordination: stop_event, TTS/STT concurrency
└── loop.py              # run_voice_session(): top-level voice session (mirrors _run_chat_session)
```

`cli.py` additions: one `@app.command()` `voice()` function that calls `asyncio.run(_run_voice_session())`.
`config.py` additions: `deepgram_api_key: str = ""` and `cartesia_api_key: str = ""`.

### Pattern 1: Deepgram Async STT with Mic Capture

Key: `sounddevice.InputStream` callback is called on a non-asyncio thread. Must use `loop.call_soon_threadsafe(queue.put_nowait, data)` to hand audio data to the asyncio event loop safely.

```python
# Source: sounddevice docs asyncio_generators.py pattern [CITED: python-sounddevice.readthedocs.io]
# + Deepgram SDK 6.x AsyncDeepgramClient pattern [CITED: developers.deepgram.com/docs/live-streaming-audio]

import asyncio
import sounddevice as sd
from deepgram import AsyncDeepgramClient, LiveTranscriptionEvents, LiveOptions

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_FRAMES = 1024

async def stream_mic_to_deepgram(
    dg_connection,
    stop_event: asyncio.Event,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Capture mic audio and send to Deepgram WebSocket until stop_event is set."""
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def _sd_callback(indata, frames, time_info, status):
        loop.call_soon_threadsafe(audio_queue.put_nowait, indata.tobytes())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=CHUNK_FRAMES,
        callback=_sd_callback,
    )
    with stream:
        while not stop_event.is_set():
            chunk = await audio_queue.get()
            await dg_connection.send(chunk)
```

**Deepgram LiveOptions for barge-in + UtteranceEnd:**

```python
options = LiveOptions(
    model="nova-3",
    language="en-US",
    encoding="linear16",
    sample_rate=SAMPLE_RATE,
    channels=CHANNELS,
    interim_results=True,       # Required for UtteranceEnd
    utterance_end_ms="1000",    # 1000ms silence gap triggers UtteranceEnd
    vad_events=True,            # Enables speech_started event for barge-in
    endpointing=300,            # 300ms silence to finalize a word
)
```

[CITED: developers.deepgram.com/docs/utterance-end — `interim_results=True` is mandatory alongside `utterance_end_ms`]

**Event handler registration:**

```python
from deepgram import LiveTranscriptionEvents

dg_connection.on(LiveTranscriptionEvents.Open, on_open)
dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)   # is_final + interim
dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)  # trigger turn
dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)  # barge-in
dg_connection.on(LiveTranscriptionEvents.Error, on_error)
dg_connection.on(LiveTranscriptionEvents.Close, on_close)
```

[CITED: developers.deepgram.com/docs/live-streaming-audio]

### Pattern 2: Cartesia Async TTS with Sentence Streaming

```python
# Source: pypi.org/project/cartesia + cartesia-ai/cartesia-python async_examples.py
# [CITED: pypi.org/project/cartesia/]

import asyncio
import sounddevice as sd
from cartesia import AsyncCartesia

CARTESIA_VOICE_ID = "6ccbfb76-1fc6-48f7-b71d-91ac6298247b"  # Default, see Discretion
CARTESIA_SAMPLE_RATE = 44100
OUTPUT_FORMAT = {
    "container": "raw",
    "encoding": "pcm_f32le",
    "sample_rate": CARTESIA_SAMPLE_RATE,
}

async def play_tts_streaming(
    client: AsyncCartesia,
    text: str,
    stop_event: asyncio.Event,
) -> None:
    """Stream TTS audio sentence-by-sentence, checking stop_event between chunks."""
    sentences = split_sentences(text)  # regex splitter — see Discretion

    async with client.tts.websocket_connect() as connection:
        ctx = connection.context(
            model_id="sonic-3",
            voice={"mode": "id", "id": CARTESIA_VOICE_ID},
            output_format=OUTPUT_FORMAT,
        )

        # Push sentences incrementally (low-latency: first audio arrives after first push)
        for sentence in sentences:
            await ctx.push(sentence)
        await ctx.no_more_inputs()

        # Stream PCM chunks to sounddevice output, checking barge-in between chunks
        with sd.RawOutputStream(
            samplerate=CARTESIA_SAMPLE_RATE,
            channels=1,
            dtype="float32",
        ) as output_stream:
            async for response in ctx.receive():
                if stop_event.is_set():
                    break  # Barge-in detected — stop mid-chunk
                if response.type == "chunk" and response.audio:
                    output_stream.write(response.audio)
```

[CITED: pypi.org/project/cartesia/ — WebSocket pattern with `ctx.push()`, `ctx.receive()`, `response.type == "chunk"`]

### Pattern 3: Barge-in Coordination

```python
# asyncio task pattern for barge-in
# [ASSUMED: based on asyncio Task/Event patterns in Python stdlib]

async def voice_turn_loop(orchestrator_graph, config, initial_state):
    stop_event = asyncio.Event()
    transcript_accumulator = []

    # SpeechStarted fires when Deepgram detects new speech — this is the barge-in trigger
    def on_speech_started(event, **kwargs):
        stop_event.set()  # Signal TTS task to stop immediately

    def on_transcript(transcript, **kwargs):
        # Display interim results in-place, accumulate finals
        if transcript.is_final:
            transcript_accumulator.append(transcript.channel.alternatives[0].transcript)
        else:
            # Display interim in-place (overwrite current line)
            print(f"\r{transcript.channel.alternatives[0].transcript}", end="", flush=True)

    def on_utterance_end(event, **kwargs):
        # Full utterance detected — send to orchestrator
        full_text = " ".join(transcript_accumulator).strip()
        transcript_accumulator.clear()
        if full_text:
            asyncio.get_event_loop().call_soon_threadsafe(
                utterance_queue.put_nowait, full_text
            )

    # TTS plays in one task; STT listens continuously in another
    # When barge-in fires: cancel tts_task, clear stop_event, continue STT listening
    tts_task = asyncio.create_task(play_tts_streaming(cartesia_client, response_text, stop_event))
    try:
        await tts_task
    except asyncio.CancelledError:
        pass  # Barge-in cancelled TTS — normal path
    finally:
        stop_event.clear()
```

### Pattern 4: AsyncPostgresSaver Wiring

The `AsyncPostgresSaver` requires a one-time `setup()` call to create checkpoint tables. In the CLI context, call this at voice session start before the first graph invocation.

```python
# Source: pypi.org/project/langgraph-checkpoint-postgres/
# [CITED: reference.langchain.com/python/langgraph.checkpoint.postgres/aio/AsyncPostgresSaver]

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from daily.config import Settings

async def _run_voice_session(user_id: int = 1) -> None:
    settings = Settings()
    # database_url_psycopg uses psycopg (not asyncpg) — required by AsyncPostgresSaver
    async with AsyncPostgresSaver.from_conn_string(settings.database_url_psycopg) as checkpointer:
        await checkpointer.setup()  # Idempotent — safe to call every session start
        graph = build_graph(checkpointer=checkpointer)
        config = await create_session_config(user_id)
        # ... rest of voice session
```

Note: `AsyncPostgresSaver` uses `psycopg` (3.x), not `asyncpg`. The project already has `database_url_psycopg` in `Settings` for this purpose — confirmed in `src/daily/config.py`.

[CITED: pypi.org/project/langgraph-checkpoint-postgres/]

### Anti-Patterns to Avoid

- **Calling `sd.play()` or `sd.wait()`** — these are blocking calls. Use `sd.RawOutputStream` with `write()` in an async loop instead.
- **Sending audio from the sounddevice callback thread directly to the Deepgram WebSocket** — the callback thread is not the asyncio thread. Always use `loop.call_soon_threadsafe(queue.put_nowait, data)`.
- **Setting `stop_event` from a Deepgram callback without checking the asyncio loop** — Deepgram callbacks may fire on a different thread. Use `loop.call_soon_threadsafe(stop_event.set)` if the callback is not already awaited.
- **Waiting for a full LLM response before starting TTS** — defeats VOICE-01. Push sentences to Cartesia as they arrive from the streaming LLM response.
- **Using `MemorySaver` in the voice session** — breaks VOICE-05 cross-turn persistence. Must use `AsyncPostgresSaver` per D-11.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| End-of-utterance detection | Silence timer / energy threshold | Deepgram `UtteranceEnd` event | Tuned for real-world noise; handles partial words; no local model needed |
| VAD for barge-in | Audio energy threshold | Deepgram `speech_started` event | Server-side VAD already running; `speech_started` fires immediately on voice onset |
| TTS audio streaming | HTTP chunked streaming | Cartesia WebSocket `ctx.receive()` | 40-90ms TTFB via WebSocket; chunked HTTP adds ~200ms latency on top |
| Sentence splitting | Full NLP pipeline (NLTK, spacy) | Regex sentence splitter | NLTK adds 50MB+ dependency; simple regex (`[.!?]+\s`) sufficient for spoken English |
| Cross-thread async queue | `threading.Queue` with manual polling | `asyncio.Queue` + `loop.call_soon_threadsafe` | Native asyncio; no polling overhead; standard pattern for sounddevice+asyncio |
| Graph state persistence | Custom state serialisation | `AsyncPostgresSaver` | Already in lock file; handles LangGraph state schema; thread_id scoping built-in |

---

## Common Pitfalls

### Pitfall 1: sounddevice callback is not on the asyncio thread

**What goes wrong:** Calling `asyncio.Queue.put_nowait()` directly from the sounddevice `InputStream` callback raises `RuntimeError: This event loop is already running` or silently drops items.

**Why it happens:** sounddevice callbacks fire on a PortAudio C thread, not the Python asyncio event loop thread.

**How to avoid:** Capture the event loop before starting the stream (`loop = asyncio.get_event_loop()`), then use `loop.call_soon_threadsafe(queue.put_nowait, data.tobytes())` inside the callback.

**Warning signs:** Audio chunks not arriving in Deepgram; queue size stays at zero; no transcripts.

### Pitfall 2: `utterance_end_ms` requires `interim_results=True`

**What goes wrong:** `UtteranceEnd` events never fire even though utterance_end_ms is set.

**Why it happens:** Deepgram's UtteranceEnd analysis runs on the gap between finalized and interim word timings. Without `interim_results=True`, there are no interim timings to analyze.

**How to avoid:** Always pair `utterance_end_ms` with `interim_results=True`. Set `utterance_end_ms` to at least `"1000"` (1 second).

**Warning signs:** STT transcript arrives but `on_utterance_end` callback never fires; orchestrator never receives a turn.

[CITED: developers.deepgram.com/docs/utterance-end]

### Pitfall 3: `cartesia[websockets]` extra must be installed explicitly

**What goes wrong:** `ImportError` or `AttributeError` when calling `client.tts.websocket_connect()` even though `cartesia` is installed.

**Why it happens:** The `websockets` library is not a base dependency of `cartesia` — it's in the `[websockets]` optional extra.

**How to avoid:** Install with `uv add "cartesia[websockets]"`. In `pyproject.toml`, pin as `cartesia[websockets]>=3.0.2`.

**Warning signs:** `ModuleNotFoundError: No module named 'websockets'` at runtime.

### Pitfall 4: AsyncPostgresSaver uses psycopg3, not asyncpg

**What goes wrong:** Passing the `asyncpg`-style URL (`postgresql+asyncpg://...`) to `AsyncPostgresSaver.from_conn_string()` raises a connection error.

**Why it happens:** `langgraph-checkpoint-postgres` uses `psycopg` (v3), not `asyncpg`. They use different URL schemes and connection protocols.

**How to avoid:** Use `settings.database_url_psycopg` (`postgresql://...` without the `+asyncpg` driver suffix). This field already exists in `config.py` for this purpose.

**Warning signs:** `ProgrammingError` or `InterfaceError` on checkpointer setup; works with MemorySaver but fails with AsyncPostgresSaver.

### Pitfall 5: TTS task cancellation leaves sounddevice stream open

**What goes wrong:** After barge-in cancels the TTS task, subsequent TTS attempts fail with `PortAudioError: Device unavailable` or produce no audio.

**Why it happens:** `sd.RawOutputStream` opened inside the cancelled task is not properly closed on `asyncio.CancelledError` if the `with` block is inside the task.

**How to avoid:** Use a `try/finally` block inside the TTS task to ensure the output stream is closed on cancellation. Alternatively, use `contextlib.asynccontextmanager` to manage the stream lifecycle.

**Warning signs:** Second TTS playback attempt silently fails; no audio on second turn after barge-in.

### Pitfall 6: Deepgram `speech_started` fires during TTS playback (echo)

**What goes wrong:** The Deepgram microphone picks up the system's own TTS audio output, triggering `speech_started` and immediately interrupting every TTS playback.

**Why it happens:** Microphone and speaker on the same machine without acoustic echo cancellation (AEC). sounddevice has no built-in AEC.

**How to avoid:** Use headphones during development/testing. For production, add a "TTS active" flag that suppresses `speech_started` triggers while TTS is playing (with a short buffer after TTS ends). This is a known voice agent challenge — document it in the plan as an optional enhancement.

**Warning signs:** TTS immediately cancels itself on first audio chunk; barge-in fires 50-100ms after TTS starts.

### Pitfall 7: Sentence splitter creates too-short segments

**What goes wrong:** Cartesia receives single-word or 2-word segments (e.g., "Good." then "Morning."). Each `ctx.push()` call has a minimum latency overhead; too-short segments produce stuttering.

**Why it happens:** Aggressive sentence splitting on abbreviations, numbers, or punctuation within a sentence.

**How to avoid:** Use a minimum segment length (e.g., 5 words or 30 characters). Buffer very short "sentences" and append them to the next sentence before pushing.

---

## Code Examples

### Deepgram Client Initialization (SDK 6.x)

```python
# Source: [CITED: developers.deepgram.com/docs/live-streaming-audio]
from deepgram import AsyncDeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions

config = DeepgramClientOptions(verbose=False)
client = AsyncDeepgramClient(api_key=settings.deepgram_api_key, config=config)

# Async context manager for connection lifecycle
async with client.listen.asynclive.v1() as dg_connection:
    # Register event handlers before starting
    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    options = LiveOptions(
        model="nova-3",
        language="en-US",
        encoding="linear16",
        sample_rate=16000,
        channels=1,
        interim_results=True,
        utterance_end_ms="1000",
        vad_events=True,
        endpointing=300,
    )
    await dg_connection.start(options)
    # ... send audio via await dg_connection.send(audio_bytes)
```

### Cartesia Client Initialization (SDK 3.x)

```python
# Source: [CITED: pypi.org/project/cartesia/]
from cartesia import AsyncCartesia

client = AsyncCartesia(api_key=settings.cartesia_api_key)

# Context manager automatically handles WebSocket lifecycle
async with client.tts.websocket_connect() as connection:
    ctx = connection.context(
        model_id="sonic-3",
        voice={"mode": "id", "id": CARTESIA_VOICE_ID},
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le",
            "sample_rate": 44100,
        },
    )
    for sentence in sentences:
        await ctx.push(sentence)
    await ctx.no_more_inputs()

    async for response in ctx.receive():
        if response.type == "chunk" and response.audio:
            # response.audio is bytes — write directly to sd.RawOutputStream
            output_stream.write(response.audio)
```

### Simple Regex Sentence Splitter (Discretion)

```python
# [ASSUMED: Standard pattern; no library needed]
import re

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

def split_sentences(text: str) -> list[str]:
    """Split text into sentences for incremental TTS push.
    
    Merges segments shorter than MIN_CHARS into the next one to avoid
    stuttering from Cartesia per-segment latency overhead.
    """
    MIN_CHARS = 30
    raw = _SENTENCE_END.split(text.strip())
    merged = []
    buffer = ""
    for segment in raw:
        buffer = (buffer + " " + segment).strip() if buffer else segment
        if len(buffer) >= MIN_CHARS:
            merged.append(buffer)
            buffer = ""
    if buffer:
        merged.append(buffer)
    return merged or [text]
```

### In-Place Terminal Transcript Display

```python
# [ASSUMED: ANSI escape code pattern for in-place terminal reprint]
import sys

def display_interim_transcript(text: str) -> None:
    """Overwrite current terminal line with interim transcript."""
    sys.stdout.write(f"\r\033[K{text}")
    sys.stdout.flush()

def finalize_transcript_line(text: str) -> None:
    """Move to next line after utterance ends."""
    sys.stdout.write(f"\r\033[KYou: {text}\n")
    sys.stdout.flush()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Deepgram SDK v2/v3 (blocking API) | SDK v6.x (async-first, `AsyncDeepgramClient`) | 2024-2025 | Event-driven callbacks; `asynclive` namespace; breaking changes from v3 |
| Cartesia SDK v1/v2 (`push_stream`) | SDK v3.x (`ctx.push()`, `ctx.receive()`) | 2024 | New context-based API; WebSocket multiplexing; `cartesia[websockets]` extra |
| LangGraph MemorySaver | AsyncPostgresSaver (v3.0.5) | Phase 5 | Persistent cross-session state; requires psycopg3 URL; `await setup()` call required |
| Silero VAD (local model) | Deepgram server-side VAD (`vad_events=True`) | Decision D-05 | Eliminates local model load; `speech_started` event fires ~50ms after voice onset |

**Deprecated/outdated:**
- Deepgram SDK v2/v3 event pattern (`deepgram.transcription.live()`): replaced by `client.listen.asynclive.v1()` in v3+
- Cartesia SDK v1 `client.tts.sse()`: replaced by WebSocket context API in v2/v3
- `langgraph-checkpoint-postgres` `PostgresSaver` (sync): replaced by `AsyncPostgresSaver` for asyncio contexts

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Regex sentence splitter (`[.!?]+\s`) is sufficient for spoken English TTS segmentation | Code Examples | Stuttering on abbreviations (Mr., Dr., etc.); fix by using NLTK `sent_tokenize` or a simple heuristic for known abbreviations |
| A2 | ANSI escape codes (`\r\033[K`) work correctly for in-place terminal display | Code Examples | Some terminals may not support; fallback is simple `\r` overwrite |
| A3 | Default Cartesia voice ID `6ccbfb76-1fc6-48f7-b71d-91ac6298247b` is a valid Sonic-3 voice | Standard Stack / Code Examples | TTS returns error on first call; fix by listing voices via API and picking a valid ID |
| A4 | `speech_started` event fires reliably enough for barge-in without AEC concerns in headphone use | Pitfall 6 | Barge-in fires on TTS audio bleed if user uses speakers; mitigation: suppress `speech_started` during TTS playback window |
| A5 | `AsyncDeepgramClient` with `client.listen.asynclive.v1()` is the correct SDK 6.x async namespace | Code Examples | SDK 6.x may use different namespace (e.g. `listen.v2`); verify against SDK 6.1.1 source |

---

## Open Questions

1. **Deepgram SDK 6.x exact async namespace**
   - What we know: SDK 6.1.1 is on PyPI; v6 announcement confirmed `AsyncDeepgramClient`; deepwiki shows `client.listen.v2.connect()` for sync and `asynclive` for async
   - What's unclear: Whether it's `client.listen.asynclive.v1()`, `client.listen.v2.connect()`, or another namespace in 6.1.1
   - Recommendation: Wave 0 of Plan 2 should include a 5-line smoke test to confirm the correct import path before implementing the full STT pipeline

2. **Cartesia voice ID for Sonic-3**
   - What we know: The example voice ID `6ccbfb76-1fc6-48f7-b71d-91ac6298247b` appears in Cartesia docs
   - What's unclear: Whether this is a stable default or a sample placeholder
   - Recommendation: Plan 1 Wave 0 should call `client.voices.list()` and document available Sonic-3 voices; store chosen ID in config

3. **AEC (acoustic echo cancellation) for speaker mode**
   - What we know: sounddevice has no built-in AEC; headphone use avoids the issue
   - What's unclear: Whether M1 usage is exclusively headphones or also speakers
   - Recommendation: Add a "suppress barge-in during TTS playback" flag as a simple heuristic; document as known limitation

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| deepgram-sdk | STT pipeline (Plan 2) | ✗ | — | None — must add to pyproject.toml |
| cartesia[websockets] | TTS pipeline (Plan 1) | ✗ | — | None — must add to pyproject.toml |
| sounddevice | Mic capture + PCM playback | ✗ | — | None — must add to pyproject.toml; requires PortAudio system library |
| PortAudio (system lib) | sounddevice | [ASSUMED: present on macOS] | — | `brew install portaudio` if missing; Linux: `apt install libportaudio2` |
| langgraph-checkpoint-postgres | AsyncPostgresSaver (Plan 4) | ✓ (in lock) | 3.0.5 | — |
| psycopg[binary] | AsyncPostgresSaver | ✓ (in lock) | 3.3.3+ | — |
| PostgreSQL (running) | AsyncPostgresSaver.setup() | [ASSUMED: running via docker-compose] | 15+ | Run `docker compose up -d` |
| Redis (running) | Briefing cache first turn | [ASSUMED: running via docker-compose] | 7.x | Run `docker compose up -d` |

**Missing dependencies with no fallback:**
- `deepgram-sdk`, `cartesia[websockets]`, `sounddevice` — must be added to `pyproject.toml` before Plan 1/2 work begins (Wave 0 task)

**Missing dependencies with fallback:**
- PortAudio system library — install via Homebrew (macOS) or apt (Linux) if sounddevice fails to import

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| Quick run command | `uv run pytest tests/test_voice_*.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VOICE-01 | TTS plays first audio before full response generated | unit (mock Cartesia WebSocket) | `pytest tests/test_voice_tts.py::test_sentence_streaming_begins_immediately -x` | ❌ Wave 0 |
| VOICE-02 | Interim transcripts displayed; final transcript triggers orchestrator | unit (mock Deepgram callbacks) | `pytest tests/test_voice_stt.py::test_interim_transcript_display -x` | ❌ Wave 0 |
| VOICE-03 | Briefing loaded from Redis cache (zero LLM latency on first turn) | integration (fakeredis) | `pytest tests/test_voice_loop.py::test_briefing_cache_loaded -x` | ❌ Wave 0 |
| VOICE-04 | Barge-in: stop_event set on speech_started; TTS task cancels | unit (asyncio.Event mock) | `pytest tests/test_voice_barge_in.py::test_barge_in_cancels_tts_task -x` | ❌ Wave 0 |
| VOICE-05 | Graph state persists across voice turns via AsyncPostgresSaver | integration (AsyncPostgresSaver + test DB) | `pytest tests/test_voice_loop.py::test_session_state_persists -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_voice_*.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_voice_tts.py` — covers VOICE-01 (mock Cartesia, sentence streaming)
- [ ] `tests/test_voice_stt.py` — covers VOICE-02 (mock Deepgram callbacks, transcript display)
- [ ] `tests/test_voice_barge_in.py` — covers VOICE-04 (asyncio.Event stop_event + task cancel)
- [ ] `tests/test_voice_loop.py` — covers VOICE-03, VOICE-05 (session wiring, Redis cache, AsyncPostgresSaver)
- [ ] `src/daily/voice/__init__.py`, `tts.py`, `stt.py`, `barge_in.py`, `loop.py` — empty module files

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth surface — CLI inherits existing session model |
| V3 Session Management | Yes (partial) | AsyncPostgresSaver thread_id scoped per user per day — same as MemorySaver pattern |
| V4 Access Control | No | Single-user M1; no new access control surface |
| V5 Input Validation | Yes | Deepgram transcript text passed to orchestrator — same LLM input path as chat; existing sanitisation applies |
| V6 Cryptography | No | No new keys; `deepgram_api_key` and `cartesia_api_key` follow existing `.env` / pydantic-settings pattern |

### Known Threat Patterns for Voice Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key in logs | Information Disclosure | Never log `deepgram_api_key` / `cartesia_api_key`; existing logging practice; pydantic-settings masks secrets |
| Transcript injection (adversarial speech) | Tampering | Transcript passes through existing `route_intent` keyword filter; LLM is intent-only (SEC-05 constraint) |
| Microphone always-on listening | Privacy | Wake word / ambient mode explicitly out of scope (CONTEXT.md Deferred); `daily voice` is manually invoked |

---

## Sources

### Primary (HIGH confidence)
- [CITED: developers.deepgram.com/docs/utterance-end] — UtteranceEnd parameters, `interim_results` requirement, `last_word_end` schema
- [CITED: developers.deepgram.com/docs/live-streaming-audio] — LiveOptions, event handler registration, Nova-3
- [CITED: pypi.org/project/cartesia/] — WebSocket TTS SDK 3.x pattern, `ctx.push()`, `ctx.receive()`, output_format
- [CITED: python-sounddevice.readthedocs.io asyncio_generators.py] — `loop.call_soon_threadsafe` pattern for asyncio queue from PortAudio callback
- [CITED: reference.langchain.com/python/langgraph.checkpoint.postgres/aio/AsyncPostgresSaver] — `AsyncPostgresSaver.from_conn_string()`, `await setup()` idempotent
- [VERIFIED: pip index versions] — deepgram-sdk 6.1.1, cartesia 3.0.2, sounddevice 0.5.5 (current latest)
- [VERIFIED: uv.lock] — langgraph 1.1.6, langgraph-checkpoint-postgres 3.0.5 already in project lock file
- [VERIFIED: src/daily/config.py] — `database_url_psycopg` field exists for psycopg3 connections
- [VERIFIED: src/daily/cli.py] — `_run_chat_session()` pattern to mirror for `_run_voice_session()`
- [VERIFIED: pyproject.toml] — current dependencies; deepgram-sdk, cartesia, sounddevice all absent

### Secondary (MEDIUM confidence)
- [deepgram.com/learn/deepgram-javascript-sdk-v5-python-sdk-v6] — SDK v6 release notes confirming `AsyncDeepgramClient` and `EventType` namespace
- [cartesia.ai/blog/python-sdk] — SDK v2 WebSocket context API announcement

### Tertiary (LOW confidence)
- [ASSUMED] Sentence splitter regex pattern — standard Python practice, not verified against Cartesia latency behavior
- [ASSUMED] ANSI escape code in-place terminal display — standard terminal pattern, not tested on all platforms
- [ASSUMED] Cartesia voice ID `6ccbfb76-1fc6-48f7-b71d-91ac6298247b` is a stable Sonic-3 voice — taken from example; must verify at implementation time

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI registry
- Architecture: HIGH — patterns confirmed from official SDKs and existing codebase analysis
- Pitfalls: MEDIUM — pitfalls 1-5 derived from official docs; pitfalls 6-7 are ASSUMED from known voice agent patterns
- Sentence splitter: LOW — regex is standard but behavior with Cartesia latency is not benchmarked

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (Deepgram/Cartesia SDKs move fast; re-verify API namespaces if > 30 days)
