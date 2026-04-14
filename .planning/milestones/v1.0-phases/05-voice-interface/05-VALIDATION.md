---
phase: 5
slug: voice-interface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | VOICE-01 | — | N/A | unit | `uv run pytest tests/test_tts.py -x -q` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | VOICE-01 | — | N/A | unit | `uv run pytest tests/test_tts.py::test_sentence_split -x -q` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 2 | VOICE-01 | — | N/A | integration | `uv run pytest tests/test_tts.py::test_cartesia_stream -x -q` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 1 | VOICE-02 | — | N/A | unit | `uv run pytest tests/test_stt.py -x -q` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 1 | VOICE-02 | — | N/A | unit | `uv run pytest tests/test_stt.py::test_transcript_accumulation -x -q` | ❌ W0 | ⬜ pending |
| 5-02-03 | 02 | 2 | VOICE-02 | — | N/A | integration | `uv run pytest tests/test_stt.py::test_deepgram_connection -x -q` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 1 | VOICE-03 | — | N/A | unit | `uv run pytest tests/test_barge_in.py -x -q` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 2 | VOICE-03 | — | Stop event cancels TTS task | unit | `uv run pytest tests/test_barge_in.py::test_stop_event -x -q` | ❌ W0 | ⬜ pending |
| 5-04-01 | 04 | 1 | VOICE-04 | — | N/A | unit | `uv run pytest tests/test_voice_cli.py -x -q` | ❌ W0 | ⬜ pending |
| 5-04-02 | 04 | 2 | VOICE-05 | — | N/A | integration | `uv run pytest tests/test_voice_cli.py::test_session_persistence -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tts.py` — stubs for VOICE-01 (sentence split, Cartesia stream)
- [ ] `tests/test_stt.py` — stubs for VOICE-02 (transcript accumulation, Deepgram connection)
- [ ] `tests/test_barge_in.py` — stubs for VOICE-03 (stop_event task cancellation)
- [ ] `tests/test_voice_cli.py` — stubs for VOICE-04, VOICE-05 (CLI wiring, session persistence)
- [ ] `tests/conftest.py` — shared async fixtures (mock Deepgram, mock Cartesia, mock sounddevice)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Barge-in latency feels immediate (sub-200ms stop) | VOICE-03 | Requires live audio hardware | Speak during TTS playback; measure time until silence |
| Briefing starts within 1s from Redis cache | VOICE-01 | Requires Redis + precomputed cache | Run `daily voice`, time from command to first audio |
| End-to-end follow-up latency ≤1.5s | VOICE-02 | Requires live Deepgram + Cartesia | Ask follow-up question, measure response audio start |
| Interim transcripts display in-place on terminal | VOICE-02 | Requires live mic | Observe terminal during speech input |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
