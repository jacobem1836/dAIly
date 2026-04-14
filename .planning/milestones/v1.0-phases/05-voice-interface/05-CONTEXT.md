# Phase 5: Voice Interface - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can receive the morning briefing, interrupt it, and complete the full action workflow entirely by voice. Adds Deepgram STT (streaming with VAD), Cartesia TTS (sentence-by-sentence streaming), barge-in detection, and a `daily voice` CLI command that wires the full voice loop into the existing orchestrator.

Requirements in scope: VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05

No browser/mobile client in Phase 5 — CLI only. FastAPI WebSocket architecture is deferred to a later milestone.

</domain>

<decisions>
## Implementation Decisions

### Entry Point
- **D-01:** New `daily voice` CLI command (mirrors `daily chat` structure). Python captures microphone via sounddevice/pyaudio, streams audio to Deepgram WebSocket, plays Cartesia TTS audio back locally. No new server infrastructure — everything runs in-process like `daily chat`. Will be expanded to FastAPI WebSocket architecture in M2+.
- **D-02:** `daily voice` wires the same orchestrator graph as `daily chat` (`build_graph`, `create_session_config`, `initialize_session_state`, `run_session`). Voice is an I/O layer on top of the existing orchestrator — not a separate agent.

### Barge-in Architecture
- **D-03:** Asyncio tasks + `asyncio.Event` stop flag. TTS playback runs in a task; STT listener runs in parallel. When Deepgram fires `speech_started` (VAD utterance detected), the stop_event is set, cancelling the TTS task. Clean async, no threads, no extra processes.
- **D-04:** TTS task must check the stop_event between audio chunks, not just at sentence boundaries. Barge-in should feel immediate — don't finish the current sentence before stopping.

### VAD
- **D-05:** Deepgram built-in VAD only. Use `UtteranceEnd` and `speech_started` events from the Deepgram streaming API. No Silero VAD — eliminates the tuning concern flagged in STATE.md. Deepgram endpointing handles utterance boundary detection.
- **D-06:** End-of-utterance detection uses Deepgram `UtteranceEnd` event (not a silence timer or local VAD). When `UtteranceEnd` fires, the accumulated transcript is sent to the orchestrator for processing.

### TTS Streaming
- **D-07:** Cartesia Sonic-3 via WebSocket SDK. Stream audio sentence-by-sentence — split the LLM response into sentences, send each to Cartesia, begin playback as the first chunk arrives. Do not wait for the full response before starting TTS.
- **D-08:** Audio playback via `sounddevice` (simplest cross-platform option). Stream raw PCM bytes from Cartesia directly to sounddevice output stream.

### STT Pipeline
- **D-09:** Deepgram Nova-3 via WebSocket SDK (`deepgram-sdk` Python package). Mic capture via `sounddevice` input stream, fed into Deepgram WebSocket. Use interim results (`is_final=False`) for low-latency display; act on final transcript (`is_final=True` + `UtteranceEnd`).
- **D-10:** Interim transcripts are displayed in-place on the terminal (not sent to orchestrator) so the user can see what's being heard in real time. Final transcript triggers the orchestrator turn.

### Session Persistence
- **D-11:** Switch from `MemorySaver` to `AsyncPostgresSaver` in Phase 5 (already noted in `orchestrator/session.py` comments). Voice sessions persist state across turns. The `daily voice` command initialises the checkpointer the same way FastAPI lifespan will in M2+.

### Plan Structure
- **D-12:** 4 plans:
  - Plan 1 — TTS pipeline (Cartesia WebSocket + sentence splitter + sounddevice playback)
  - Plan 2 — STT pipeline (Deepgram WebSocket + mic capture + transcript handling)
  - Plan 3 — Barge-in (asyncio task coordination, stop_event, VAD interrupt loop)
  - Plan 4 — Full voice loop integration (`daily voice` command, AsyncPostgresSaver, end-to-end wiring)

### Claude's Discretion
- Exact sentence splitter logic (regex vs NLTK)
- Cartesia voice ID / model parameter selection
- Deepgram model parameters (language, encoding, sample_rate)
- sounddevice input/output stream configuration (sample rate, channels, dtype)
- How partial transcripts are displayed in-place (ANSI escape codes or simple reprint)
- Error recovery when Deepgram or Cartesia WebSocket disconnects mid-session
- Module structure within `src/daily/voice/`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — VOICE-01 through VOICE-05 (exact acceptance criteria)
- `.planning/ROADMAP.md` §Phase 5 — 4 success criteria (latency targets, interrupt, context)

### Technology Stack
- `CLAUDE.md` §Technology Stack — Deepgram Nova-3 (STT), Cartesia Sonic-3 (TTS), their SDKs and latency characteristics
- `CLAUDE.md` §Stack Patterns — "Precomputed Briefing Cache" pattern: TTS serves from Redis cache, zero pipeline latency on first turn

### Upstream Code (must read before implementing)
- `src/daily/cli.py` — `_run_chat_session()` (voice session mirrors this pattern), `chat()` command (voice command structure)
- `src/daily/orchestrator/session.py` — `run_session()`, `create_session_config()`, `initialize_session_state()`, `get_email_adapters()` (all reused)
- `src/daily/orchestrator/graph.py` — `build_graph()` (reused, no changes needed for Phase 5)
- `src/daily/orchestrator/nodes.py` — `approval_node` interrupt pattern (voice must handle approval flow like CLI does)
- `src/daily/config.py` — add `deepgram_api_key` and `cartesia_api_key` here

### Latency Constraints
- VOICE-03: ≤1.5s end-to-end for follow-up turns; briefing starts within 1s (from Redis cache)
- VOICE-01: TTS begins before full response is generated (sentence streaming, not wait-then-play)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/cli.py` `_run_chat_session()` — complete pattern for session wiring (adapters, graph, config, initial state, turn loop). `daily voice` mirrors this exactly, replacing `input()`/`print()` with mic capture and TTS playback.
- `src/daily/orchestrator/session.py` `run_session()` — used unchanged. Voice adds no new graph nodes.
- `src/daily/orchestrator/session.py` `initialize_session_state()` — loads briefing from Redis cache, profile from DB. Phase 5 reuses as-is.
- `src/daily/orchestrator/graph.py` `build_graph()` — no changes. Graph already handles respond/draft/approval/execute.
- `src/daily/orchestrator/nodes.py` approval interrupt — `_run_chat_session()` already handles the interrupt loop. `daily voice` must replicate this for voice (speak the draft, listen for confirm/reject/edit).
- `src/daily/briefing/narrator.py` — narrative already written as spoken English without markdown. First TTS input in voice sessions.

### Established Patterns
- Async-first throughout. All voice I/O (mic capture, Deepgram WebSocket, Cartesia WebSocket) runs as asyncio tasks.
- sounddevice for audio I/O (consistent choice — mic input and speaker output via same library).
- Pydantic settings in `config.py` — add `deepgram_api_key` and `cartesia_api_key` as new fields following existing pattern.
- `asyncio.create_task()` fire-and-forget pattern already used in signal capture and action logging — matches barge-in task pattern.

### Integration Points
- Phase 5 creates: `src/daily/voice/` package (tts.py, stt.py, barge_in.py or similar)
- Phase 5 modifies: `src/daily/cli.py` (add `daily voice` command), `src/daily/config.py` (add API keys)
- Phase 5 wires: `AsyncPostgresSaver` as checkpointer (replacing `MemorySaver` in CLI usage)
- Phase 5 reads from: Redis briefing cache (zero-latency first turn), existing orchestrator graph (no node changes)

</code_context>

<specifics>
## Specific Ideas

- CLI is a temporary I/O surface — the orchestrator graph is permanent. Voice is just a different way to feed input and output from the same graph.
- "Will be expanded later" — FastAPI WebSocket architecture (Phase 5 lays groundwork by keeping voice logic in `src/daily/voice/` as a reusable package, not embedded in CLI)
- Barge-in must feel immediate: stop mid-chunk, not mid-sentence

</specifics>

<deferred>
## Deferred Ideas

- **FastAPI WebSocket voice endpoint** — M2+. Server streams audio over WebSocket to browser/mobile client. Phase 5 CLI lays groundwork but doesn't build the server endpoint.
- **Silero VAD** — Rejected for M1. May revisit in M2 if Deepgram VAD sensitivity proves problematic.
- **Voice cloning** — User's own voice for TTS. ElevenLabs or Cartesia voice cloning. M2+ if product requires it.
- **Wake word** — "Hey Daily" style always-on listening. Out of scope for M1.
- **Multi-speaker diarisation** — Not needed in single-user M1.

</deferred>

---

*Phase: 05-voice-interface*
*Context gathered: 2026-04-13*
