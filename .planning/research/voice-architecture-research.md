# Voice Architecture Research
_Session: 2026-04-27_

---

## 1. Current Stack & Barge-In Struggles

### Architecture
- **STT:** Deepgram Nova-3 (WebSocket streaming, `stt.py`)
- **LLM:** GPT-4.1 / GPT-4.1 mini
- **TTS:** Cartesia Sonic-3 (WebSocket streaming, `tts.py`)
- **Barge-in coordination:** `barge_in.py` → `VoiceTurnManager`

### The Barge-In Problem (summary of bugs fixed in phase 17)

**Bug A — No barge-in possible (TTS plays fully)**
- Mute window was 500ms. Deepgram received silent chunks the whole time, couldn't detect speech.
- Fix: Reduced mute to 150ms.

**Bug B — TTS cuts after 1–2 words (spurious barge-in)**
- Streaming LLM→TTS path in `loop.py` called `play_streaming_tokens()` directly, bypassing `VoiceTurnManager.speak()`.
- `_tts_active` was never set → mic was never muted → Deepgram received TTS bleed-through from speakers → instant barge-in trigger.
- Fix: Added `speak_streaming()` to `VoiceTurnManager` with full state lifecycle.

**Bug C — Ambient noise triggers barge-in (timer had no transcript guard)**
- `SpeechStarted` fires on ambient noise → 600ms timer starts → no real speech → `_transcript_parts` empty → timer fires anyway → TTS stops.
- Fix: Added `_has_speech_transcript` flag (set on any non-empty transcript, interim or final) as guard. Extended timer to 900ms.

**Bug D — Transcript guard too strict (real barge-in broken)**
- `_has_speech_transcript` only set on finals (`is_final=True`). With `endpointing=300ms`, finals only arrive after 300ms of silence. Continuous speech → no finals → flag stays False → timer exits without firing.
- Fix: Flag now set on interim transcripts too.

**Ongoing issue — Acoustic echo (root cause not fully resolved)**
- MacBook Air: TTS plays through built-in speakers, mic picks it up.
- After 150ms mute, Deepgram receives TTS echo → `SpeechStarted` fires → `_has_speech_transcript = True` (Deepgram CAN transcribe its own TTS output) → barge-in fires on echo.
- Added `_tts_active` guard to `_commit_barge_in_after_window` to prevent firing after TTS finishes.
- Added `send_media()` exception handling so WebSocket closure doesn't kill the STT task.
- **Root cause: no acoustic echo cancellation (AEC).** Without headphones or AEC, this architecture will always be fragile on built-in audio hardware.

### Key files
- `src/daily/voice/stt.py` — Deepgram pipeline, mic capture, mute logic
- `src/daily/voice/tts.py` — Cartesia streaming, sounddevice playback
- `src/daily/voice/barge_in.py` — `VoiceTurnManager`, barge-in timer, echo suppression
- `src/daily/voice/loop.py` — Main voice session loop

---

## 2. Alternative Voice Architectures

### OpenAI Realtime API

**What it is:** Single-hop speech-to-speech API. Audio in → audio out. STT + LLM + TTS unified.

**Why it matters for barge-in:**
- Turn detection and barge-in handled server-side by OpenAI — no client VAD, no echo cancellation problem.
- The server detects when you start speaking and kills its own audio output automatically.
- Eliminates the entire `barge_in.py` complexity.

**Reference:** Openclaw issue #71195 — Mac Talk Mode vs phone (voice-call plugin)
- Phone surface uses `RealtimeVoiceBridge` → OpenAI Realtime → sub-second turns, native barge-in.
- Mac Talk (STT→LLM→TTS chain) has 1.7–4.9s latency and fragile barge-in.
- Issue proposes unifying both surfaces onto Realtime API.
- Key insight: "Native turn detection + barge-in handled by the Realtime API rather than client-side VAD."

**Models:**
- `gpt-realtime-1.5` — full quality
- `gpt-realtime-mini` — 60% cheaper, slightly lower reasoning

**Known gotcha:** Input tokens accumulate across turns without caching. Community reports 3–5× actual vs calculated cost. Mitigate with prompt caching ($0.40/M cached vs $32/M uncached for audio input).

**Original objection (from CLAUDE.md):** "Bundles STT + LLM in one hop — removes ability to swap models, adds LLM cost to every voice input, breaks the orchestrator-controls-execution constraint."
- This was a valid call for M1 but worth revisiting given barge-in complexity.

### ElevenLabs Conversational AI

**What it is:** Managed conversational voice agent platform. Handles STT, turn detection, AEC, and TTS. LLM is pluggable (OpenAI, Anthropic, custom).

**Why it matters:**
- Built-in AEC — no acoustic echo problem.
- Barge-in handled by the platform.
- LLM is separate / swappable (not locked to one provider).

**Pricing:** $0.08/minute flat across all tiers. LLM billed separately at provider cost.

---

## 3. Pricing Analysis (April 2026)

### Usage assumption
- 10–15 min/day voice = ~360 min/month per user
- 60% assistant output, 40% user input

### Cost per user per month

| Stack | Cost/user/month | Notes |
|---|---|---|
| **ElevenLabs Conversational AI** | ~$29 | $0.08/min × 360 min + ~$0.20 LLM |
| **OpenAI Realtime (gpt-realtime-1.5)** | ~$16–23 | With prompt caching; 3–5× without |
| **OpenAI Realtime (gpt-realtime-mini)** | ~$7–9 | Best cost/barge-in tradeoff |
| **Current stack (Deepgram + GPT-4.1 + Cartesia)** | ~$15–40 | Cartesia rate uncertain; check invoices |

### ElevenLabs tier detail
All tiers converge to $0.08/minute overage. Plan tiers are effectively prepay discounts, not user-count tiers.

| Plan | $/month | Included minutes |
|---|---|---|
| Starter | $6 | 75 min |
| Creator | $22 | 275 min |
| Pro | $99 | 1,238 min |
| Scale | $299 | 3,738 min |
| Business | $990 | 12,375 min |

At 360 min/user/month: a single user exhausts Starter in 5 days. Pro ($99) covers ~3.4 users at this usage rate.

### OpenAI Realtime token rates
- Audio input: $32/M tokens (1 token = 100ms)
- Audio output: $64/M tokens (1 token = 50ms)
- Audio input cached: $0.40/M tokens
- gpt-realtime-mini input: $10/M, output: $20/M

### Current stack breakdown (7 hrs/month)
- Deepgram Nova-3 STT: $0.0077/min × 168 min = ~$1.30
- GPT-4.1 LLM: ~$0.10
- Cartesia Sonic-3 TTS: rate uncertain (agent found $0.18/min → $45; likely lower — verify)

---

## 4. Business / Pricing Model Implications

### The margin problem
Voice infrastructure alone costs $7–29/user/month. Typical SaaS needs ~70% gross margin.

| Charge | Infrastructure | Gross margin |
|---|---|---|
| $15/mo | $7–29 | -93% to 53% |
| $25/mo | $7–29 | -16% to 72% |
| $40/mo | $7–29 | 28% to 83% |

Viable margin only appears at $30–40+/month, or if infrastructure cost is kept to $7–10 (gpt-realtime-mini, capped usage).

### Pricing model options

**Option 1: Tiered feature gating (recommended)**
- Free: text briefing only, no voice
- Pro (~$15/mo): voice briefing read-back only (5 min/day cap)
- Premium (~$30/mo): full voice conversation, unlimited follow-ups

Voice briefing only (5 min/day) costs ~$1.50/user/month on gpt-realtime-mini — viable at $15. Full conversation ($7–29/month cost) only makes sense at $30+.

**Option 2: Usage-based voice add-on**
- Base plan ($10/mo): text briefing + integrations
- Voice minutes: metered above a free allowance

Transparent but B2C users dislike variable billing.

**Option 3: Freemium + voice trial**
- Free: text only, 1 integration
- Paid ($20–30/mo): voice + all integrations

PLG motion — briefing as hook, voice as upsell.

### Strategic recommendation
Launch with text briefing + voice read-back only (no conversation). Proves value cheaply. Add full conversational voice as a premium tier once retention is validated. Switch to gpt-realtime-mini for the conversation tier when it launches — solves barge-in and keeps cost at ~$7/user/month.

---

## 5. Open Questions / Next Research

- [ ] Verify actual Cartesia Sonic-3 per-minute rate from invoice
- [ ] Benchmark gpt-realtime-mini quality vs current GPT-4.1 mini for dAIly use case
- [ ] Evaluate ElevenLabs Conversational AI SDK — does it allow custom STT/LLM injection or is it fully managed?
- [ ] Research whether OpenAI Realtime API supports tool use / function calling for action layer (required for M2+)
- [ ] Investigate software AEC libraries (WebRTC AEC, RNNoise) as an alternative to switching providers
- [ ] Look at Amazon Nova Sonic (mentioned in Openclaw #71195 as second Realtime provider) — pricing unknown

---

## 6. Backlog Items Added (2026-04-27)

- **Phase 999.1:** Voice-first onboarding — setup as a conversation, not menus
- **Phase 999.2:** Deep customization — briefing length, sources, news prefs, three-tier security, all discoverable and easy
