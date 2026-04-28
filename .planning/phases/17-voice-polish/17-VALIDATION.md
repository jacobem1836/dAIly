---
phase: 17
slug: voice-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_voice_barge_in.py tests/test_voice_tts.py tests/test_voice_stt.py tests/test_voice_loop.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_voice_barge_in.py tests/test_voice_tts.py tests/test_voice_stt.py tests/test_voice_loop.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|--------|
| 17-01-01 | 01 | 1 | D-03 graceful fade-out | N/A | unit | `pytest tests/test_voice_tts.py -x` | ⬜ pending |
| 17-01-02 | 01 | 1 | D-03 test update | N/A | unit | `pytest tests/test_voice_tts.py -x` | ⬜ pending |
| 17-02-01 | 02 | 1 | D-06 mic mute stt | N/A | unit | `pytest tests/test_voice_stt.py -x` | ⬜ pending |
| 17-02-02 | 02 | 1 | D-06 mic mute barge_in | N/A | unit | `pytest tests/test_voice_barge_in.py -x` | ⬜ pending |
| 17-03-01 | 03 | 2 | D-01 safety window | N/A | unit | `pytest tests/test_voice_barge_in.py -x` | ⬜ pending |
| 17-03-02 | 03 | 2 | D-02 backchannel detection | N/A | unit | `pytest tests/test_voice_utils.py tests/test_voice_barge_in.py -x` | ⬜ pending |
| 17-03-03 | 03 | 2 | D-04 ack phrases | N/A | unit | `pytest tests/test_voice_loop.py -x` | ⬜ pending |
| 17-04-01 | 04 | 3 | D-05 astream_session | N/A | unit | `pytest tests/test_voice_session.py -x` | ⬜ pending |
| 17-04-02 | 04 | 3 | D-05 play_streaming_tokens | N/A | unit | `pytest tests/test_voice_tts.py -x` | ⬜ pending |
| 17-04-03 | 04 | 3 | D-05 loop wiring | N/A | unit | `pytest tests/test_voice_loop.py -x` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_voice_utils.py` — stubs for `_is_backchannel()` (new file, no test exists yet)
- [ ] `tests/test_voice_session.py` — stubs for `astream_session` streaming path (new test file for Plan 17-04)

*Note: `tests/test_voice_barge_in.py`, `tests/test_voice_tts.py`, `tests/test_voice_stt.py`, `tests/test_voice_loop.py` already exist — they need updating, not creating.*

---

## Tests That Must Break and Be Updated

| Test | Plan | Why It Breaks | Required Fix |
|------|------|---------------|--------------|
| `test_echo_suppression_during_tts` | 17-03 | Tests `_tts_active` guard that is replaced by `_was_tts_active_at_speech_start` flag | Rewrite to assert backchannel suppression uses new flag |
| `test_real_barge_in_when_tts_inactive` | 17-03 | Tests unconditional `stop_event.set()` which is replaced by 600ms timer | Rewrite to assert timer fires after 600ms with no cancellation |
| `test_play_streaming_stops_on_event` | 17-01 | Chunk count assertion may need updating after stop_event check reorder | Update to assert current chunk completes before stop |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cough during TTS does not interrupt | D-01 safety window | Perceptual/acoustic — requires live microphone | Cough or make brief noise while dAIly speaks; TTS should continue |
| "Yeah" during TTS continues speech | D-02 backchannel | Perceptual — requires live voice | Say "yeah" during TTS playback; TTS should not stop |
| TTS echo on speakers does not trigger barge-in | D-06 mic mute | Requires external speaker setup | Play at volume on laptop speakers; no spurious barge-in should fire |
| First spoken word under 400ms after utterance | D-05 streaming | Perceptual latency | Ask a question; first TTS word should begin well before full response is generated |
| Acknowledgement phrase plays immediately | D-04 ack phrases | Perceptual — requires live voice | Ask a question; "Got it." or similar should play within ~100ms |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
