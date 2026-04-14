> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-13
**Phase:** 05-voice-interface
**Mode:** discuss
**Areas discussed:** Entry point, Barge-in design, VAD approach, Plan structure

## Gray Areas Presented

| Area | Question | Decision |
|------|----------|----------|
| Entry point | `daily voice` CLI vs FastAPI WebSocket + browser vs FastAPI WebSocket + Python client | `daily voice` CLI — will expand to FastAPI WebSocket in M2+ |
| Barge-in | Asyncio tasks + event flag vs separate threads | Asyncio tasks + `asyncio.Event` stop flag |
| VAD | Deepgram built-in VAD vs Silero VAD | Deepgram built-in VAD — avoids Silero tuning concern |
| Plan split | 3 plans vs 2 plans vs 4 plans | 4 plans: TTS → STT → barge-in → integration |

## Discussion Notes

**Entry point:** User confirmed CLI is the right surface for M1 and noted it will be expanded later. FastAPI WebSocket architecture is a deliberate future expansion, not a cut. Voice package kept in `src/daily/voice/` to be reusable when that happens.

**Barge-in:** Asyncio tasks chosen for clean async composition — matches the async-first pattern throughout the codebase. TTS task must check `stop_event` between chunks, not just sentence boundaries, for immediate interrupt feel.

**VAD:** STATE.md had flagged "Silero VAD tuning may require iteration" as a concern for Phase 5. User confirmed Deepgram built-in VAD — eliminates that risk entirely. `UtteranceEnd` event drives end-of-utterance detection.

**Plan split:** 4 plans chosen over 3 to separate barge-in into its own verifiable unit. Each plan has a clear, independently testable output: TTS plays text, STT transcribes speech, barge-in interrupts correctly, full loop runs end-to-end.

## Codebase Evidence

- `src/daily/cli.py` `_run_chat_session()` — existing session wiring pattern that voice mirrors
- `src/daily/orchestrator/session.py` comments — "AsyncPostgresSaver will be wired in Phase 5" already noted by prior developer
- `src/daily/config.py` — no Deepgram/Cartesia keys yet; need to add
- No existing voice/ package — Phase 5 creates it from scratch
