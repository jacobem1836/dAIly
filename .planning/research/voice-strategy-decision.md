# Voice Strategy Decision
_Date: 2026-04-27_

## Context

The current voice pipeline (Deepgram STT → LangGraph → Cartesia TTS) has a structural barge-in/latency problem. This document captures the analysis and decision on the path forward.

---

## Current Architecture

```
Mic (sounddevice)
  → PCM chunks (16kHz) via queue
  → Deepgram Nova-3 WebSocket (STTPipeline)
      → UtteranceEnd (1000ms silence) → utterance_queue
          → VoiceTurnManager.wait_for_utterance()
              → LangGraph + GPT-4.1 mini
                  → token stream
                      → Cartesia Sonic-3 WebSocket (sentence by sentence)
                          → PCM audio → sounddevice
```

**Barge-in:** `SpeechStarted` fires a 900ms asyncio timer. If a non-empty transcript arrives while `_tts_active`, `stop_event` is set and TTS checks between audio chunks.

**Echo suppression:** mic muted for 150ms at TTS start, then real audio resumes.

---

## Top 3 Bottlenecks

1. **UtteranceEnd: mandatory 1000ms forced wait** — every turn waits a full second after speech ends before processing starts
2. **No real AEC** — without headphones, TTS bleeds into the mic after the 150ms mute ends; triggers phantom barge-in. Root cause documented in `barge_in.py` as unresolved after 4 separate bug fixes.
3. **LLM on critical path** — minimum latency from end-of-speech to first audio byte is ~1400–1900ms; typically 2–4 seconds in practice

Human threshold for "natural" conversation: 200–300ms. Consumer assistants feel OK at 600–800ms. Above 1000ms = clearly robotic.

---

## Root Cause

The `UtteranceEnd` turn model makes the system permanently reactive. It cannot process until the user has been silent for the configured window — this is a structural incompatibility with natural conversation, not just an implementation gap.

Software AEC without hardware (echo-cancelling mic or headphones) is a hard engineering bet. The research file already documents 4 distinct fixes in `barge_in.py` with the underlying root cause still unresolved. More effort in that direction is debt accumulation.

---

## Improvement Path (Current Stack) — Not Recommended

| Change | Difficulty | Time | Impact |
|--------|-----------|------|--------|
| Reduce `utterance_end_ms` to 500ms | Low | 1 day | -500ms wait |
| Software AEC (WebRTC AEC3) | High | 1–2 weeks | Uncertain |
| Speculative LLM pre-fetch | High | 2–3 weeks | -400–800ms perceived |

Even after all improvements: theoretical minimum ~800–1200ms with headphones, AEC on built-in speakers still uncertain. **Risk of still feeling non-conversational: High.**

---

## Alternative: OpenAI Realtime API

Unified WebSocket — audio in, audio out. STT, LLM, TTS, VAD, barge-in all server-side.

**What it eliminates from the codebase:**
- All of `barge_in.py` (VoiceTurnManager, timer logic, echo suppression)
- All of `stt.py` (Deepgram WebSocket)
- All of `tts.py` (Cartesia WebSocket, sentence splitting)
- The entire three-component async coordination problem

**Latency:** ~300–600ms TTFB (gpt-realtime-mini) vs current 1400–4000ms.

**Tradeoff:** LLM locked to OpenAI's realtime model for the conversational path. Briefing generation pipeline (GPT-4.1, LangGraph, email synthesis) is unaffected.

### Cost Per User/Month (10–15 min/day conversation, ~360 min/month)

| Scenario | Cost/user/month |
|----------|----------------|
| With prompt caching | ~$6–8 |
| Without caching | ~$18–40 |

Prompt caching is mandatory — without it, cost blows up.

---

## Decision: Hybrid Approach

**Keep current stack for voice briefing read-back (Pro). Add OpenAI Realtime for conversational voice (Premium).**

- The current Cartesia TTS pipeline is excellent at reading a cached briefing — 40–90ms TTFB, works reliably, no barge-in needed. Ship this as Pro.
- The conversational layer is structurally blocked. Engineering more patches is the wrong direction.
- gpt-realtime-mini replaces `barge_in.py` + `stt.py` + `tts.py` for the conversational path. LangGraph orchestration, action execution, and approval flow are untouched.

### Do NOT release the limited version first

WOM and landing page are built around "conversational AI assistant." A voice briefing reader will disappoint early adopters and damage credibility. Wait for Realtime integration (1–2 weeks) and launch matching what was promised.

---

## Tier Structure

| Tier | Experience | Stack | Cost/user | Price | Margin |
|------|-----------|-------|-----------|-------|--------|
| Free | Text briefing only | — | ~$0 | $0 | — |
| Pro (~$15/mo) | Voice briefing read-back | Cartesia TTS, no conversation | ~$1.50–2 | $15 | ~85–90% |
| Premium (~$30–35/mo) | Full conversational voice | OpenAI Realtime | ~$7–10 | $30–35 | ~70–75% |

---

## User Testing Cost (Conversational)

For 10 test users doing active daily use:

| Scenario | Cost/user/month | 10 users |
|----------|----------------|----------|
| With prompt caching | ~$8–12 | ~$80–120/mo |
| Without caching | ~$20–40 | ~$200–400/mo |

Testing sessions are more exploratory → worse cache hit rate → assume higher end. **$200–350/month for 10 users** is realistic. Keep initial testers to 5–8 to stay ~$100–200/month.

---

## Privacy & Security: New Concerns with Realtime API

### Current architecture (data flow per vendor)
- **Deepgram** — audio only (STT)
- **OpenAI** — text only (summarized email/calendar content)
- **Cartesia** — text only (response)

### With Realtime API
- **OpenAI** receives **raw audio** — voice biometrics, everything said in the room, references to personal email/calendar content in the conversation

This is an incremental expansion of OpenAI trust (already used for text), but the modality shift matters.

### Required before launch

1. **Verify OpenAI Realtime data retention policy** — OpenAI does not train on API data by default, but confirm audio retention windows specifically
2. **Add explicit audio consent to privacy policy** — users must know voice is transmitted to OpenAI
3. **Do not inject raw email bodies into the Realtime session** — summaries only (same discipline as the text pipeline)
4. **GDPR** — if targeting EU users, raw audio may qualify as biometric data. Requires a Data Processing Agreement with OpenAI (they provide a standard API DPA)

---

## Execution Plan

**Week 1:**
1. Audit the non-conversational briefing path (TTS reads cached briefing, no STT) — confirm stable for Pro launch
2. Build minimal Realtime API proof-of-concept: WebSocket, send mic audio, play audio back
3. Test barge-in specifically **without headphones on MacBook** (the failure case the current stack can't solve)

**Week 2:**
4. If prototype shows <800ms TTFB and reliable barge-in on built-in speakers → integrate as Premium tier
5. If barge-in still breaks without headphones → evaluate ElevenLabs Conversational AI (platform-managed AEC) or launch with headphone requirement

**Do not** spend more time on software AEC, `utterance_end_ms` tuning, or more `barge_in.py` edge cases.

### Validation Signals
- Realtime prototype: <800ms TTFB without headphones
- Barge-in works ≥9/10 times in ambient conditions
- gpt-realtime-mini quality acceptable for conversational follow-ups
- Cost calculator confirms $7–10/user/month with caching enabled

---

## Update: Mobile-First Architecture (2026-04-27)

Research confirmed that mobile OS AEC eliminates the echo problem that blocked the desktop voice pipeline. The structural root cause (no hardware AEC on macOS built-in speakers) cannot be solved in software — 4 separate barge-in fixes proved this.

**Decision:** Native iOS (Swift) + Android (Kotlin) with LiveKit over Flutter/React Native.

**Why native:** Voice quality is the core product differentiator. Cross-platform frameworks (Flutter, React Native) add abstraction layers on the audio path — unacceptable for a voice-first product. Native gives direct access to AVAudioEngine (iOS) and Oboe (Android) for hardware AEC.

**Why LiveKit:** ML-based barge-in, WebRTC AEC, mobile SDKs for iOS/Android/Web, self-hostable (Apache 2.0). Integrates with existing LangGraph backend via `livekit-plugins-langchain`. Eliminates the entire `barge_in.py` / `stt.py` / `tts.py` async coordination problem.

**Architecture shift:** Audio I/O moves to mobile clients. Python backend becomes orchestration-only (LangGraph, integrations, action engine). Desktop becomes a web fallback via LiveKit web SDK.

**Latency targets:**
- Mobile (iOS/Android): sub-800ms conversational latency achievable
- Desktop (macOS, current stack): realistic floor 900–1400ms (acceptable as secondary platform)

**Impact on current strategy:** The hybrid approach (Cartesia Pro / OpenAI Realtime Premium) documented above is superseded by the LiveKit mobile-first path. OpenAI Realtime API remains a potential option for the conversational tier but is no longer the primary plan — LiveKit gives model flexibility without vendor lock-in.
