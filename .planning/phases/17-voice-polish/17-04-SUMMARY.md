---
phase: 17-voice-polish
plan: "04"
subsystem: voice
tags: [voice, streaming, tts, llm, openai, cartesia, asyncio]
dependency_graph:
  requires: [graceful-tts-fade-out, barge-in-safety-window, backchannel-detection, agent-acknowledgements]
  provides: [streaming-llm-tts, astream-session, play-streaming-tokens]
  affects: [voice-loop, tts-pipeline, orchestrator-session]
tech_stack:
  added: []
  patterns: [asyncio-producer-consumer-queue, openai-sdk-stream-true, sentence-boundary-accumulator, streaming-not-supported-exception-as-fallback-signal]
key_files:
  created: []
  modified:
    - src/daily/orchestrator/session.py
    - src/daily/voice/tts.py
    - src/daily/voice/loop.py
decisions:
  - "astream_session uses OpenAI SDK stream=True not LangGraph .astream_events() — respond_node uses response_format=json_object which prevents LangGraph token interception"
  - "StreamingNotSupported exception pattern chosen over bool return to keep call site clean and allow clean fallback to run_session"
  - "_NON_RESPOND_KEYWORDS kept as standalone copy in session.py to avoid circular import with graph.py"
  - "result=None convention for streaming path; if result is not None guard wraps all graph_state access"
  - "AsyncIterator from collections.abc used (not typing) per Python 3.11+ best practice"
metrics:
  duration_minutes: 20
  completed_date: "2026-04-25"
  tasks_completed: 3
  files_modified: 3
requirements: [VOICE-POLISH-05]
---

# Phase 17 Plan 04: Streaming LLM to TTS Summary

**One-liner:** OpenAI SDK stream=True yields plain-text token deltas accumulated into sentence boundaries (". ", "! ", "? ", "\n") and pushed to Cartesia via asyncio.Queue producer/consumer bridge, eliminating the silent wait between user utterance and first spoken word.

## What Was Built

### Task 1 — session.py: astream_session + StreamingNotSupported

New additions to `src/daily/orchestrator/session.py`:

- `StreamingNotSupported` exception class — raised by `astream_session` when the intent is not a plain respond turn, signalling the caller to fall back to `run_session`.
- `_NON_RESPOND_KEYWORDS: tuple[str, ...]` — 35-entry denylist covering memory, briefing resume, skip/repeat, summarise, draft/action, and exit/quit/approval keywords. Kept as a standalone copy in session.py (not imported from graph.py) to avoid circular imports.
- `_looks_like_respond_intent(user_input: str) -> bool` — normalizes input and returns False if any denylist keyword is found.
- `astream_session(graph, user_input, config, initial_state) -> AsyncIterator[str]` — async generator that:
  - Raises `StreamingNotSupported` for non-respond inputs
  - Builds the OpenAI client the same way nodes.py does (`_openai_client` pattern)
  - Mirrors the RESPOND_SYSTEM_PROMPT structure but drops `response_format={"type": "json_object"}` and requests plain narrative text
  - Calls `client.chat.completions.create(model="gpt-4.1-mini", ..., stream=True, max_tokens=400)`
  - Yields each non-empty `chunk.choices[0].delta.content` string
- `run_session` preserved unchanged — non-streaming fallback remains fully functional.

### Task 2 — tts.py: play_streaming_tokens + _split_at_boundary

New additions to `src/daily/voice/tts.py`:

- `_SENTENCE_BOUNDARIES: tuple[str, ...] = (". ", "! ", "? ", "\n")` — four two-character boundary markers.
- `_split_at_boundary(buffer: str) -> tuple[str | None, str]` — finds the earliest boundary in the accumulated buffer and returns `(sentence, remainder)` or `(None, buffer)` when no boundary exists.
- `TTSPipeline.play_streaming_tokens(token_stream, stop_event)` — new async method that:
  - Opens Cartesia WebSocket context with same settings as `play_streaming`
  - Opens sounddevice RawOutputStream
  - Runs two coroutines via `asyncio.gather`:
    - `_produce()`: iterates `token_stream`, accumulates into buffer, flushes all completed sentences via `ctx.push(sentence)`, pushes remaining buffer and calls `ctx.no_more_inputs()` at end; respects `stop_event` between tokens
    - `_consume()`: `async for response in ctx.receive()` — writes chunk then checks stop_event (Plan 01 graceful fade-out ordering replicated)
  - `try/finally` closes output_stream on any exit

### Task 3 — loop.py: streaming bridge in main turn

Changes to `src/daily/voice/loop.py`:

- Imports: `StreamingNotSupported`, `astream_session` added to the `daily.orchestrator.session` import block; `from typing import AsyncIterator` added for the `_tts_iter()` annotation.
- At the `run_session` call site (after acknowledgement speak):
  - Attempts `astream_session` first
  - `asyncio.Queue[str | None]` with maxsize=64 bridges producer and TTS consumer
  - `_produce()` inner coroutine accumulates `streamed_text` and puts deltas into queue (sentinel `None` at end)
  - `_tts_iter()` inner async generator drains the queue and yields to `play_streaming_tokens`
  - `asyncio.gather(_produce(), turn_manager._tts.play_streaming_tokens(_tts_iter(), turn_manager._stop_event))`
  - `used_streaming = True; result = None` on success
  - `except StreamingNotSupported:` falls back to `run_session`
  - `except Exception:` handles OpenAIError on both paths
- `if result is not None:` guard wraps all `graph_state.next` approval flow access — streaming path skips this block entirely since `astream_session` only handles plain respond turns.
- Debug logging: `logger.debug("Streamed respond turn: %d chars", len(streamed_text))` and `logger.debug("Streaming not supported, fell back to run_session")`.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: astream_session + StreamingNotSupported | `e25a7a3` | src/daily/orchestrator/session.py |
| Task 2: play_streaming_tokens + sentence-boundary chunking | `e0b5ab7` | src/daily/voice/tts.py |
| Task 3: streaming bridge in loop.py | `c5f5d3b` | src/daily/voice/loop.py |

## Verification

- `pytest tests/test_voice_tts.py`: 14 passed (no regressions)
- `pytest tests/test_voice_loop.py`: 5 pre-existing failures (Pydantic Settings log_level validation error — confirmed failing on 9e6bdda base before Plan 17-04 changes; out of scope)
- `python -c "from daily.orchestrator.session import astream_session, StreamingNotSupported, run_session; from daily.voice.tts import TTSPipeline; assert hasattr(TTSPipeline, 'play_streaming_tokens')"`: exits 0
- `grep -n "stream=True" src/daily/orchestrator/session.py`: matches inside `astream_session` (line 291)
- `grep -n "_SENTENCE_BOUNDARIES" src/daily/voice/tts.py`: matches with all four boundaries
- `_looks_like_respond_intent('exit') == False`, `_looks_like_respond_intent('yes') == False`, `_looks_like_respond_intent('draft an email') == False`, `_looks_like_respond_intent('what is the weather today') == True`: all correct
- Manual perceptual check: deferred to phase verification (requires live Cartesia + OpenAI API keys)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as specified.

### Pre-existing Issues (Out of Scope)

**test_voice_loop.py failures:** All 5 tests fail with `pydantic_core.ValidationError: 1 validation error for Settings: log_level — Extra inputs are not permitted`. Confirmed pre-existing on the 9e6bdda base commit before any Plan 17-04 changes. Documented in Plan 17-03 SUMMARY. Out of scope for this plan.

## Known Stubs

None. All three components are fully wired:
- `astream_session` is called by `loop.py` for respond-intent turns
- `_looks_like_respond_intent` gates the streaming path correctly
- `play_streaming_tokens` receives the token queue iterator and drives Cartesia audio output
- Fallback to `run_session` via `except StreamingNotSupported` is active for all non-respond intents

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes. The streaming path uses the same OpenAI client pattern as respond_node (credentials from Settings, never passed to user). The plain-text system prompt explicitly avoids exposing any credential or internal state.

## Self-Check: PASSED

- [x] `src/daily/orchestrator/session.py` contains `astream_session`, `StreamingNotSupported`, `_NON_RESPOND_KEYWORDS`, `_looks_like_respond_intent`, `run_session` — all confirmed
- [x] `src/daily/voice/tts.py` contains `play_streaming_tokens`, `_SENTENCE_BOUNDARIES`, `_split_at_boundary` — all confirmed
- [x] `src/daily/voice/loop.py` contains `astream_session` (import + call), `StreamingNotSupported` (import + except), `play_streaming_tokens` (call), `asyncio.Queue`, `asyncio.gather`, `if result is not None` — all confirmed
- [x] All three files parse cleanly (`python3 -c "import ast; ast.parse(...)"` exits 0)
- [x] Commit e25a7a3 exists (Task 1)
- [x] Commit e0b5ab7 exists (Task 2)
- [x] Commit c5f5d3b exists (Task 3)
- [x] 14 TTS tests pass
- [x] `stream=True` appears in `astream_session` body (line 291)
- [x] `response_format` does NOT appear inside `astream_session` — confirmed (only appears in the URL comment referencing respond_node)
