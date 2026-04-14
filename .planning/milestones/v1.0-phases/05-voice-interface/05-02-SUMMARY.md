---
phase: "05-voice-interface"
plan: "02"
subsystem: "voice/stt"
tags: ["deepgram", "stt", "websocket", "sounddevice", "asyncio"]
dependency_graph:
  requires:
    - "05-01: voice package scaffold, pyproject.toml voice deps base"
  provides:
    - "STTPipeline class with start_listening(stop_event)"
    - "utterance_queue (asyncio.Queue[str]) for orchestrator turns"
    - "on_speech_started callback hook for Plan 03 barge-in"
  affects:
    - "05-03: barge-in uses STTPipeline.on_speech_started"
    - "05-04: voice loop calls STTPipeline.start_listening()"
tech_stack:
  added:
    - "deepgram-sdk==6.1.1 (Fern-generated SDK, new API vs older research patterns)"
    - "sounddevice==0.5.5 (PortAudio wrapper for mic capture)"
    - "websockets==16.0 (transitive dep from deepgram-sdk)"
  patterns:
    - "asyncio.Queue bridge: loop.call_soon_threadsafe in sounddevice callback (Pitfall 1)"
    - "Deepgram SDK 6.x: client.listen.v1.connect() async context manager + EventType.MESSAGE dispatch"
    - "isinstance() dispatch over typed union: ListenV1Results | ListenV1UtteranceEnd | ListenV1SpeechStarted"
    - "model_construct-free test mocking via __class__ override on MagicMock"
key_files:
  created:
    - "src/daily/voice/stt.py"
    - "src/daily/voice/__init__.py"
    - "tests/test_voice_stt.py"
  modified:
    - "pyproject.toml (added deepgram-sdk, sounddevice)"
    - "uv.lock"
decisions:
  - "Deepgram SDK 6.x uses new Fern-generated API — resolved Assumption A5. Namespace is client.listen.v1.connect() not client.listen.asynclive.v1() as older docs suggested."
  - "Used __class__ override on MagicMock to pass isinstance() checks for Deepgram SDK types in tests — Deepgram UncheckedBaseModel prevents clean model_construct() for nested types."
  - "Voice __init__.py created with STTPipeline only (no TTSPipeline) since Plan 02 runs in parallel worktree. Merge will combine exports."
metrics:
  duration: "~15 minutes"
  completed: "2026-04-13T10:24:43Z"
  tasks_completed: 1
  files_changed: 5
---

# Phase 5 Plan 2: STT Pipeline (Deepgram Nova-3) Summary

**One-liner:** Deepgram Nova-3 WebSocket STT with sounddevice mic capture, interim ANSI display, and UtteranceEnd-based turn detection via SDK 6.x Fern-generated API.

## What Was Built

`STTPipeline` class in `src/daily/voice/stt.py`:

- `start_listening(stop_event)`: Opens Deepgram Nova-3 WebSocket and sounddevice InputStream; streams PCM audio until stop_event is set
- `utterance_queue: asyncio.Queue[str]`: Receives joined transcripts when UtteranceEnd fires (D-06)
- `on_speech_started` callback: Hook for Plan 03 barge-in (D-03)
- `_handle_message(msg)`: Dispatches typed Deepgram SDK messages via isinstance()
- In-place interim transcript display via ANSI escape codes (D-10: `\r\033[K{text}`)

LiveOptions used: `model="nova-3"`, `interim_results=True`, `utterance_end_ms="1000"`, `vad_events=True`, `endpointing=300`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 5-02-01 | STTPipeline with Deepgram WebSocket, mic capture, transcript accumulation, UtteranceEnd | 36ef20b | stt.py, __init__.py, test_voice_stt.py, pyproject.toml, uv.lock |

## Decisions Made

1. **Deepgram SDK 6.x API**: Resolved Assumption A5 from RESEARCH.md. The installed SDK (6.1.1) uses a new Fern-generated API where the connection pattern is `async with client.listen.v1.connect(model=...) as socket` — not `client.listen.asynclive.v1()` as the older research patterns suggested. Events are dispatched via `socket.on(EventType.MESSAGE, handler)` where messages are typed as `ListenV1Results | ListenV1UtteranceEnd | ListenV1SpeechStarted`.

2. **Test mocking strategy**: The Deepgram `UncheckedBaseModel` prevents building nested model instances via `model_construct()` because it eagerly reconstructs nested types. Used `__class__` override on MagicMock to satisfy `isinstance()` checks in `_handle_message` without requiring valid Pydantic object construction.

3. **Parallel worktree isolation**: Plan 02 runs in a parallel worktree with Plan 01 (TTS pipeline). The `voice/__init__.py` in this worktree only exports `STTPipeline`. After wave merge, the orchestrator will combine exports from both plans.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deepgram SDK namespace differs from research**
- **Found during:** Wave 0 smoke test (Task 5-02-01)
- **Issue:** RESEARCH.md / plan assumed `client.listen.asynclive.v1()` pattern from older SDK docs. SDK 6.1.1 uses Fern-generated API with `client.listen.v1.connect()` as async context manager.
- **Fix:** Implemented against the actual 6.x API. Documented in code with SDK migration note.
- **Files modified:** `src/daily/voice/stt.py`
- **Commit:** 36ef20b

**2. [Rule 1 - Bug] Deepgram UncheckedBaseModel prevents model_construct for nested types**
- **Found during:** TDD GREEN phase — test helper construction
- **Issue:** `ListenV1ResultsChannel.model_construct(alternatives=[alt])` fails because UncheckedBaseModel eagerly re-constructs typed lists, calling `model_construct(**item)` on already-constructed instances.
- **Fix:** Used `__class__` override on MagicMock so `isinstance()` checks pass without requiring valid Pydantic construction.
- **Files modified:** `tests/test_voice_stt.py`
- **Commit:** 36ef20b

## Verification Results

1. `uv run pytest tests/test_voice_stt.py -x -q` — **14 passed**
2. `from daily.voice import STTPipeline` — **OK**
3. `grep "interim_results=True" stt.py` — **confirmed (line 199)**
4. `grep "call_soon_threadsafe" stt.py` — **confirmed (line 191)**

## Known Stubs

None — all core STTPipeline logic is implemented. The `start_listening()` method requires a real Deepgram API key and microphone at runtime, but unit-testable logic is fully wired.

## Threat Flags

No new threat surface introduced beyond the plan's threat model:
- T-05-04 (API key): `deepgram_api_key` is pydantic-settings field, never logged. Present in `config.py`.
- T-05-05 (mic audio): Mitigated by explicit `daily voice` invocation — no ambient capture.
- T-05-06 (transcript injection): Transcript routes through existing `route_intent` keyword filter.

## Self-Check: PASSED

- `src/daily/voice/stt.py` — FOUND
- `src/daily/voice/__init__.py` — FOUND
- `tests/test_voice_stt.py` — FOUND
- Commit `36ef20b` — FOUND (`git log --oneline | head -1` confirms)
