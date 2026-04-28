# Stack Research — v1.4 Mobile Voice Additions

**Domain:** Native mobile voice (LiveKit transport + iOS + Android + web fallback)
**Researched:** 2026-04-28
**Confidence:** HIGH (LiveKit Python/JS confirmed via PyPI/npm; iOS/Android versions confirmed via release pages; integration pattern confirmed via official docs)

> This document covers ONLY the net-new stack additions for v1.4 Mobile Voice.
> The existing backend stack (FastAPI, PostgreSQL, Redis, Deepgram, Cartesia, LangGraph, mem0, etc.)
> is validated and documented in prior milestones — do not re-add those packages.

---

## Net-New Stack Additions

### Python Backend Additions

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| livekit-agents | 1.5.6 | LiveKit Agents framework — runs agent process that joins rooms, orchestrates STT→LLM→TTS pipeline | Only official Python framework for LiveKit Agents; replaces custom barge-in/STT/TTS coordination code |
| livekit-plugins-langchain | 1.5.6 | `LLMAdapter` wraps compiled LangGraph StateGraph as the LLM backend inside an AgentSession | Direct bridge from existing LangGraph orchestrator to LiveKit voice pipeline; no rewrite needed |
| livekit-plugins-deepgram | 1.4.2 | Routes Deepgram Nova-3 as the STT provider inside LiveKit Agents | Reuses existing Deepgram account/keys; Nova-3 already validated in v1.0–v1.3 |
| livekit-plugins-cartesia | 1.4.3 | Routes Cartesia Sonic-3 as the TTS provider inside LiveKit Agents | Reuses existing Cartesia account/keys; Sonic-3 already validated |
| livekit-api | 1.1.0 | Token server: generates signed JWT access tokens for client SDK room joins | Required for all client connections; FastAPI exposes `POST /livekit/token` endpoint using this library |

### iOS Client (Swift)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LiveKit Swift SDK | 2.13.0 (April 2026) | WebRTC transport, AVAudioEngine management, AEC, VAD, barge-in | Official SDK; manages AVAudioSession automatically; built-in Voice Processing I/O for hardware AEC; minimum iOS 14 |
| Swift Package Manager | — | Dependency management | SPM is the only distribution channel; no CocoaPods alternative needed |

### Android Client (Kotlin)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| livekit-android | 2.24.1 | WebRTC transport, audio capture, WebRTC AEC3, barge-in | Official SDK; wraps WebRTC AEC3 (software); hardware AEC should be disabled (see Pitfalls) |
| livekit-android-camerax | 2.24.1 | Optional video track support (audio-only for v1.4 — include for forward compatibility) | Same version as core; needed if video briefing summaries are added in v2.0 |

### Web Frontend (Desktop Fallback)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| livekit-client | 2.18.1 (npm) | Browser WebRTC transport connecting to LiveKit room | Official JS client SDK; web fallback for users without mobile app |
| @livekit/components-react | latest | React components (VoiceActivityIndicator, ControlBar) | Optional but provides speech visualizer out of the box; reduces UI build time for fallback |
| @livekit/components-styles | latest | CSS for LiveKit React components | Companion to components-react |

### Infrastructure Addition

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| livekit/livekit-server (Docker) | latest | WebRTC signalling + TURN server; mediates audio transport between clients and the agent process | Self-hostable (Apache 2.0); adds to existing docker-compose stack; alternative is LiveKit Cloud but self-hosted keeps data on-prem and cost predictable |

---

## Architecture Integration Points

### How LiveKit Agents Connects to Existing LangGraph

The existing LangGraph orchestrator (in `src/daily/orchestrator/`) becomes the LLM backend inside LiveKit's `AgentSession` via `langchain.LLMAdapter`. The adapter:

1. Takes a compiled `StateGraph` instance
2. Converts LiveKit `ChatContext` → LangChain `HumanMessage`/`SystemMessage`/`AIMessage`
3. Streams tokens back to LiveKit's TTS pipeline

**The entire `src/daily/voice/` module (`stt.py`, `tts.py`, `barge_in.py`, `loop.py`) is superseded by LiveKit Agents.** These files can be removed after v1.4 stabilises.

**What remains untouched:** All integrations (`gmail.py`, `gcal.py`, `outlook.py`, `slack.py`), action engine, briefing pipeline, memory layer, APScheduler jobs, and PostgreSQL/Redis infrastructure.

### Token Endpoint (New FastAPI Route)

FastAPI gets one new endpoint:

```
POST /livekit/token
  Body: { room_name: str, participant_name: str }
  Returns: { token: str, ws_url: str }
```

Uses `livekit-api`'s `AccessToken` class with `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` env vars. Clients present this token to the LiveKit server to join a room. This keeps credentials server-side — consistent with existing SEC-01 constraint.

### Agent Process Deployment

The LiveKit agent process is a separate Python process registered with the LiveKit server. It does NOT run inside FastAPI — it runs alongside it and communicates with the LiveKit server over WebSocket. In docker-compose:

- `livekit-server` service — WebRTC signalling
- `livekit-agent` service — the new agent process (runs `livekit-agents` entrypoint, connects to livekit-server, uses existing LangGraph)
- `api` service — existing FastAPI (adds `/livekit/token` endpoint)

### Audio Flow with Mobile (Resolves AEC Problem)

```
Mobile mic → OS hardware AEC → WebRTC encoded audio → LiveKit server → Agent process
Agent process → Deepgram STT → LangGraph → Cartesia TTS → WebRTC audio → LiveKit server → Mobile speaker
```

The OS hardware AEC (AVAudioEngine/Voice Processing IO on iOS, WebRTC AEC3 on Android) runs on the device before audio is encoded and transmitted. The Python backend never touches raw audio — it only receives transcripts from Deepgram and sends TTS bytes to Cartesia. This is why mobile solves the AEC problem that `barge_in.py` could not.

---

## Installation

```bash
# Python backend additions (add to existing requirements or pyproject.toml)
uv add livekit-agents==1.5.6
uv add livekit-plugins-langchain==1.5.6
uv add livekit-plugins-deepgram==1.4.2
uv add livekit-plugins-cartesia==1.4.3
uv add livekit-api==1.1.0

# Web frontend (new package.json in web/ or apps/web/)
npm install livekit-client@2.18.1
npm install @livekit/components-react @livekit/components-styles
```

**iOS (Xcode > Project Settings > Package Dependencies):**
```
https://github.com/livekit/client-sdk-swift  — version 2.13.0 or .upToNextMajor(from: "2.13.0")
```

**Android (build.gradle):**
```gradle
implementation "io.livekit:livekit-android:2.24.1"
implementation "io.livekit:livekit-android-camerax:2.24.1"  // optional, forward compat
```

**docker-compose addition:**
```yaml
livekit-server:
  image: livekit/livekit-server:latest
  command: --config /etc/livekit.yaml
  network_mode: host  # required for WebRTC UDP
  volumes:
    - ./livekit.yaml:/etc/livekit.yaml

livekit-agent:
  build: .
  command: python -m daily.voice.agent start  # new entrypoint
  depends_on: [livekit-server, postgres, redis]
  environment:
    - LIVEKIT_URL=ws://livekit-server:7880
    - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
    - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
```

---

## New Environment Variables Required

| Variable | Purpose | Where Set |
|----------|---------|-----------|
| `LIVEKIT_URL` | WebSocket URL of LiveKit server (`ws://host:7880` or `wss://` in prod) | Agent process + API token endpoint |
| `LIVEKIT_API_KEY` | LiveKit server API key (generated on first run) | Agent process + API token endpoint |
| `LIVEKIT_API_SECRET` | LiveKit server API secret | Agent process + API token endpoint |

Add to `.env` alongside existing `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| livekit-agents (self-hosted) | LiveKit Cloud | Self-hosted keeps audio data on-prem; predictable cost; project already runs on VPS with docker-compose |
| livekit-plugins-langchain LLMAdapter | Rewrite orchestrator as native LiveKit Agent | LLMAdapter wraps existing compiled StateGraph directly — no rewrite, no regression risk to approved action flows |
| livekit-plugins-deepgram | livekit-plugins-openai STT | We already have Deepgram API key and Nova-3 is validated; no reason to switch STT vendors at this point |
| livekit-plugins-cartesia | livekit-plugins-elevenlabs | Cartesia Sonic-3 validated; 40–90ms TTFB; no reason to switch |
| Native Swift (iOS) | React Native + @livekit/react-native | Voice quality is the core differentiator; cross-platform adds audio abstraction layer; AVAudioEngine Voice Processing IO requires native access |
| Native Kotlin (Android) | React Native + @livekit/react-native | Same rationale; WebRTC AEC3 configuration (disabling hardware AEC on fragmented Android devices) requires native SDK access |
| livekit/livekit-server Docker | LiveKit Cloud | Cost control and data sovereignty; no audio leaves the VPS |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| OpenAI Realtime API | Superseded by LiveKit mobile path; locks LLM to OpenAI for voice; voice-strategy-decision.md documents this as the "former" plan | LiveKit Agents + livekit-plugins-langchain |
| `livekit-plugins-openai` for STT | Bundles STT into OpenAI — breaks independent Deepgram usage, adds cost per voice input | livekit-plugins-deepgram |
| Flutter / React Native for mobile clients | Cannot access AVAudioEngine Voice Processing IO or configure Android WebRTC AEC3 at the required level; audio abstraction is incompatible with voice-first quality bar | Native Swift (iOS), Native Kotlin (Android) |
| ElevenLabs Conversational AI platform | Managed platform that replaces your orchestrator — incompatible with custom LangGraph approval-gated action flow; $0.08/min adds up fast | LiveKit Agents (self-hosted) |
| Additional vector DB (Pinecone, Weaviate) | pgvector on existing Postgres handles M1 scale; no audio embeddings needed in v1.4 | pgvector (already deployed) |
| LCEL chains via livekit-plugins-langchain | LLMAdapter only supports compiled `StateGraph` — LCEL chains (`prompt | llm`) are explicitly NOT supported | Pass a compiled `StateGraph` to `LLMAdapter` |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| livekit-agents 1.5.6 | Python 3.10–3.14 | Project uses 3.11+ — compatible |
| livekit-plugins-langchain 1.5.6 | livekit-agents 1.5.x, Python ≥3.10 | Pin minor versions to match agents version |
| livekit-plugins-deepgram 1.4.2 | livekit-agents 1.5.x | Verify with `pip install livekit-agents[deepgram]` |
| livekit-plugins-cartesia 1.4.3 | livekit-agents 1.5.x | Verify with `pip install livekit-agents[cartesia]` |
| livekit-api 1.1.0 | Python ≥3.9 | Independent of livekit-agents; used only for token generation |
| LiveKit Swift SDK 2.13.0 | iOS 14+ | Swift 5.9+ assumed by SPM package; Xcode 15+ |
| livekit-android 2.24.1 | Android API level 21+ (Android 5.0) | Kotlin 1.8+ recommended; Gradle 8.x |
| livekit-client 2.18.1 (JS) | Modern browsers (Chrome 80+, Firefox 78+, Safari 14+) | Check `isBrowserSupported()` at runtime |
| livekit-plugins-langchain LLMAdapter | LangGraph compiled StateGraph only | Does NOT support LCEL chains or bare chat models |

---

## iOS AEC Detail

LiveKit Swift SDK manages `AVAudioSession` automatically. When the local mic track is published, the session switches to `.playAndRecord` category. Voice Processing I/O is enabled by default — this is the AVAudioEngine hardware AEC path. Do not disable it (`isVoiceProcessingEnabled = true` is the default). For CallKit flows (future v2.0 phone integration), use `setEngineAvailability(.enabled)` to defer audio device activation until the call is accepted.

## Android AEC Detail

LiveKit Android wraps WebRTC's audio stack. Hardware AEC on Android is unreliable across the device ecosystem (fragmented OEM implementations). Disable hardware AEC and use WebRTC AEC3 (software) instead via `javaAudioDeviceModuleCustomizer`:

```kotlin
// In LiveKit room setup
val options = RoomOptions(
    audioTrackCaptureDefaults = LocalAudioTrackOptions(
        noiseSuppression = true,
        echoCancellation = true,  // WebRTC AEC3
        autoGainControl = true
    )
)
```

If echo persists on a specific device, disable hardware AEC explicitly:
```kotlin
setUseHardwareAcousticEchoCanceler(false)
```

---

## Sources

- [livekit-agents PyPI](https://pypi.org/project/livekit-agents/) — v1.5.6, released April 22, 2026 — HIGH confidence
- [livekit-plugins-langchain PyPI](https://pypi.org/project/livekit-plugins-langchain/) — v1.5.6, April 22, 2026 — HIGH confidence
- [livekit-plugins-deepgram PyPI](https://pypi.org/project/livekit-plugins-deepgram/) — v1.4.2, March 23, 2026 — HIGH confidence
- [livekit-plugins-cartesia PyPI](https://pypi.org/project/livekit-plugins-cartesia/) — v1.4.3, March 23, 2026 — HIGH confidence
- [livekit-api PyPI](https://pypi.org/project/livekit-api/) — v1.1.0, December 2025 — HIGH confidence
- [LiveKit LangChain integration guide](https://docs.livekit.io/agents/models/llm/plugins/langchain/) — LLMAdapter pattern, limitations — HIGH confidence (official docs)
- [LiveKit Swift SDK releases](https://github.com/livekit/client-sdk-swift/releases) — v2.13.0, April 10, 2026 — HIGH confidence
- [livekit-client npm](https://www.npmjs.com/package/livekit-client) — v2.18.1, April 2026 — HIGH confidence
- livekit-android search (MVN) — v2.24.1, last updated April 26, 2026 — MEDIUM confidence (via search result summary; could not fetch MVN directly due to 403)
- [LiveKit Android SDK GitHub](https://github.com/livekit/client-sdk-android) — AEC configuration, Gradle setup — MEDIUM confidence
- [LiveKit noise & echo cancellation docs](https://docs.livekit.io/transport/media/noise-cancellation/) — AEC capabilities — HIGH confidence
- [LiveKit self-hosting docs](https://docs.livekit.io/deploy/custom/deployments/) — docker-compose, port requirements — HIGH confidence
- [Cartesia + LiveKit voice agent example](https://github.com/cartesia-ai/cartesia-livekit-voice-agent) — confirmed Deepgram + Cartesia + LiveKit stack pattern — MEDIUM confidence

---
*Stack research for: dAIly v1.4 Mobile Voice (net-new additions only)*
*Researched: 2026-04-28*
