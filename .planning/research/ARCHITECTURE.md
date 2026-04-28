# Architecture Research — v1.4 Mobile Voice (LiveKit Integration)

**Domain:** Voice-first AI personal assistant — native mobile client architecture
**Researched:** 2026-04-28
**Confidence:** HIGH (official LiveKit docs, verified livekit-plugins-langchain PyPI/GitHub, agent-starter-swift/android repos)

---

## Context

This document supersedes the original ARCHITECTURE.md (2026-04-05) for the v1.4 milestone scope. The original document covered the backend-first v1.0 architecture. This document covers the structural changes needed to add native mobile voice via LiveKit, while leaving the existing backend largely intact.

The core question: how does the existing Python voice loop (`voice/loop.py`, `voice/stt.py`, `voice/tts.py`, `voice/barge_in.py`) get replaced by LiveKit Agents, and what does the new end-to-end architecture look like?

---

## Architecture Shift: What Changes in v1.4

### Before (v1.3 — CLI voice loop)

```
MacBook mic (sounddevice)
  → STTPipeline (Deepgram WebSocket, stt.py)
      → VoiceTurnManager (barge_in.py — timer, mute, echo guard)
          → LangGraph orchestrator (graph.py)
              → TTSPipeline (Cartesia WebSocket, tts.py)
                  → sounddevice playback
```

All audio I/O runs inside the Python process. AEC is software-only and structurally fragile on built-in speakers. The `barge_in.py` module accumulated 4 bug fixes and the root cause (no hardware AEC) was never resolved.

### After (v1.4 — LiveKit mobile architecture)

```
iOS/Android mic (hardware AEC via AVAudioEngine / Oboe)
  → WebRTC audio track
      → LiveKit SFU (room)
          → LiveKit Agent Worker (Python process — separate from FastAPI)
              → AgentSession: Deepgram STT → LangGraphAdapter → LLMAdapter → Cartesia TTS
                  → WebRTC audio track back to client
```

Audio I/O moves entirely to device hardware. Python backend handles orchestration only — no sounddevice, no PCM queues, no echo suppression code.

---

## Full System Architecture (v1.4)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                    │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │   iOS Client     │  │ Android Client   │  │  Web Fallback        │  │
│  │  (Swift / Xcode) │  │ (Kotlin / AS)    │  │  (LiveKit web SDK)   │  │
│  │                  │  │                  │  │                      │  │
│  │ AVAudioEngine    │  │ Oboe AEC         │  │ WebRTC browser AEC   │  │
│  │ AEC (hardware)   │  │ (hardware)       │  │ (software, limited)  │  │
│  │                  │  │                  │  │                      │  │
│  │ LiveKit Swift SDK│  │ LiveKit Android  │  │ LiveKit JS SDK       │  │
│  │ Session + Local  │  │ SDK (Kotlin)     │  │                      │  │
│  │ Media objects    │  │ Room + Local-    │  │                      │  │
│  │                  │  │ Participant      │  │                      │  │
│  └────────┬─────────┘  └────────┬─────────┘  └─────────┬────────────┘  │
│           │ WebRTC               │ WebRTC               │ WebRTC         │
└───────────┼──────────────────────┼──────────────────────┼───────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        LIVEKIT SERVER (SFU)                              │
│                                                                          │
│   • Manages rooms — one room per user session                           │
│   • Routes WebRTC audio between clients and agent workers               │
│   • Self-hostable (Apache 2.0) or LiveKit Cloud                         │
│   • Dispatches jobs to agent workers via authenticated WebSocket         │
│                                                                          │
│   docker-compose service: livekit (port 7880 HTTP, 7881 TCP)           │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ WebSocket (job dispatch)
            ┌───────────────────────┴────────────────────────┐
            │                                                │
            ▼                                                ▼
┌───────────────────────────┐              ┌──────────────────────────────┐
│  LIVEKIT AGENT WORKER     │              │     FASTAPI SERVER           │
│  (separate Python process)│              │  (existing, unchanged)       │
│                           │              │                              │
│  livekit/agent.py         │              │  main.py (FastAPI + lifespan)│
│    entrypoint()           │              │  APScheduler (briefing cron) │
│    AgentSession(           │              │  /api/token endpoint (NEW)   │
│      vad=silero,          │              │  /api/* existing endpoints   │
│      stt=deepgram,        │              │                              │
│      llm=LLMAdapter(      │              │  Postgres + Redis (shared)   │
│        graph=build_graph()│              │                              │
│      ),                   │              └──────────────────────────────┘
│      tts=cartesia         │
│    )                      │
│                           │
│  Connects to LiveKit SFU  │
│  via LIVEKIT_URL env var  │
│  No inbound ports needed  │
└───────────────────────────┘
```

---

## Component Map: New vs Modified vs Unchanged

### New Components

| Component | What It Is | Location |
|-----------|-----------|---------|
| LiveKit Server | SFU (Selective Forwarding Unit) — routes WebRTC audio. Added to docker-compose. | `docker-compose.yml` (new service) |
| LiveKit Agent Worker | Separate Python process. Registers with LiveKit server, receives dispatch, runs AgentSession with VAD+STT+LLM+TTS. | `src/daily/livekit/agent.py` (new) |
| LangGraphAdapter | Bridges LangGraph compiled graph to LiveKit LLMAdapter interface. Converts messages between formats. | `src/daily/livekit/adapter.py` (new) |
| FastAPI token endpoint | `POST /api/token` — generates LiveKit JWT (room name + participant identity). Clients call this before joining a room. | `src/daily/api/token.py` (new) |
| iOS Client | Swift/SwiftUI app using LiveKit Swift SDK. `Session` + `LocalMedia` objects. `preConnectAudio` enabled for instant feel. | `clients/ios/` (new Xcode project) |
| Android Client | Kotlin/Jetpack Compose app using LiveKit Android SDK. `Room` + `LocalParticipant`. Oboe AEC via SDK. | `clients/android/` (new Android project) |

### Modified Components

| Component | What Changes | What Stays |
|-----------|-------------|-----------|
| `docker-compose.yml` | Add `livekit` service (LiveKit server container) with `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` env vars. | `app`, `db`, `redis` services unchanged. |
| `src/daily/main.py` | Add token endpoint router. Add LIVEKIT_* env vars to Settings. | APScheduler, lifespan, all existing routes. |
| `src/daily/config.py` | Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` to Settings. | All existing settings. |
| `src/daily/orchestrator/graph.py` | No code changes. Graph passes through LangGraphAdapter as-is — adapter handles message format conversion. | All nodes, edges, state, checkpointer logic. |

### Deleted / Retired Components

| Component | Why |
|-----------|-----|
| `src/daily/voice/stt.py` | Deepgram STT now runs inside LiveKit AgentSession. sounddevice mic capture removed. |
| `src/daily/voice/tts.py` | Cartesia TTS now runs inside LiveKit AgentSession. sounddevice playback removed. |
| `src/daily/voice/barge_in.py` | VoiceTurnManager, timer, echo suppression — all replaced by LiveKit's built-in turn detection + WebRTC AEC. |
| `src/daily/voice/loop.py` | run_voice_session() replaced by LiveKit Agent entrypoint pattern. |
| `daily voice` CLI command | Voice sessions now initiated via mobile client joining a room, not CLI. |

Note: `src/daily/voice/utils.py` should be reviewed — any utilities unrelated to sounddevice/PCM can be kept.

### Unchanged Components

Everything in the backend except the voice layer is untouched:
- `src/daily/orchestrator/` — graph, nodes, session, state, models
- `src/daily/briefing/` — pipeline, scheduler, cache
- `src/daily/integrations/` — Gmail, GCal, Outlook, Slack adapters
- `src/daily/actions/` — approval gate, executor, action log
- `src/daily/db/` — all models, migrations
- `src/daily/profile/` — memory, preferences
- `src/daily/vault/` — token encryption

---

## Data Flow: v1.4 Voice Session

### Session Initiation

```
Mobile Client
  1. POST /api/token { room_name, participant_identity }
       → FastAPI generates LiveKit JWT (livekit-server-sdk-python AccessToken)
       → Returns { server_url, participant_token }
  2. Client joins LiveKit room with token
  3. LiveKit Server dispatches job to Agent Worker
  4. Agent Worker joins same room as a participant
  5. AgentSession starts: VAD + STT + LLM + TTS pipeline active
```

### Voice Turn (conversational follow-up)

```
User speaks (iOS/Android mic)
  → AVAudioEngine / Oboe applies hardware AEC
  → WebRTC audio track → LiveKit SFU → Agent Worker
      → Silero VAD: detects end of utterance
      → Deepgram Nova-3 STT: transcript
      → LangGraphAdapter.chat() called with transcript
          → Converts to LangGraph message format
          → build_graph() compiled graph runs (existing orchestrator)
              → route_intent → respond / draft / summarise_thread nodes
              → Returns streaming tokens
      → LangGraphAdapter streams tokens back as LiveKit ChatChunks
      → Cartesia Sonic-3 TTS: streams audio chunks
  → WebRTC audio track → LiveKit SFU → mobile client
```

### Morning Briefing Delivery

```
[Nightly: APScheduler, unchanged]
  → briefing pipeline precomputes → Redis cache (unchanged)

[User opens app → joins room]
  → Agent Worker joins room
  → AgentSession.say() reads briefing from Redis cache
      → Cartesia TTS streams precomputed narrative
  → User hears briefing via device speaker (hardware volume, AEC irrelevant for TTS-out)
  → User can barge in at any time — LiveKit VAD interrupts TTS naturally
```

### Action Approval Flow

The existing LangGraph human-in-the-loop interrupt is preserved. When the graph hits an `interrupt()` at the approval node:
- LiveKit AgentSession pauses LLM streaming
- Agent speaks the approval prompt via TTS: "Want me to send that reply?"
- User responds via voice
- STT transcript feeds back into the graph's approval decision parser
- Graph resumes from checkpoint; action executes or cancels

This works because LangGraphAdapter uses `thread_id` from participant metadata for session continuity — the graph state and checkpointer are preserved across turns.

---

## LiveKit Agent Worker Architecture

### Process Model

The Agent Worker is a separate Python process from the FastAPI server. It:
1. Opens an authenticated WebSocket to the LiveKit server
2. Registers as available for job dispatch
3. On dispatch: spawns a job subprocess that joins the room
4. Each job handles one user session in isolation

No inbound ports are needed on the agent worker — it makes outbound connections only.

### Agent Entrypoint Pattern

```python
# src/daily/livekit/agent.py (pseudocode — not implementation)

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    thread_id = ctx.room.metadata or ctx.participant.identity  # session continuity
    
    graph = build_graph(checkpointer=AsyncPostgresSaver(...))
    
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-3"),
        llm=langchain.LLMAdapter(
            graph=graph,
            config={"configurable": {"thread_id": thread_id}}
        ),
        tts=cartesia.TTS(model="sonic-3"),
    )
    
    # Play briefing from cache if morning session
    briefing = await redis.get(f"briefing:{user_id}")
    if briefing:
        await session.say(briefing.narrative)
    
    await session.start(ctx.room)

cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

### LangGraphAdapter Role

`langchain.LLMAdapter` (from `livekit-plugins-langchain`) wraps the compiled LangGraph graph. It:
- Converts LiveKit's `ChatContext` (list of messages) → LangGraph `HumanMessage` / `AIMessage` / `SystemMessage`
- Runs `graph.astream()` in `messages` stream mode
- Yields streamed tokens back to LiveKit as `ChatChunk` objects
- Passes `config` with `thread_id` for graph state persistence

The existing graph requires no modification. The adapter is a translation shim only.

---

## iOS Client Architecture

### SDK Components Used

| Component | Purpose |
|-----------|---------|
| `LiveKit` (Swift Package) | Core SDK — WebRTC transport, room management |
| `Session` observable | Manages connection to LiveKit room, agent interaction, local state, text messages |
| `LocalMedia` observable | Manages microphone track lifecycle |
| `preConnectAudio` | Captures and buffers mic audio before room connection completes — creates instant-feeling join |
| AVAudioEngine (via SDK) | Hardware AEC — applied automatically when using device speaker + mic |

### Connection Flow

```
VoiceAgentApp.swift:
  1. Fetch token from dAIly backend: POST /api/token
  2. Create Session with server_url + participant_token
  3. Enable LocalMedia.voice (mic)
  4. Session.connect() → joins LiveKit room
  5. Agent joins room → AgentSession starts on backend
  6. UI shows: "Listening..." / "Speaking..." based on session state
```

### Project Structure (Xcode)

```
clients/ios/dAIly/
├── dAIlyApp.swift           # App entry, environment setup
├── ContentView.swift        # Root UI — voice button, status
├── VoiceSession.swift       # Session + LocalMedia wiring
├── TokenService.swift       # POST /api/token network call
└── Assets.xcassets/
```

---

## Android Client Architecture

### SDK Components Used

| Component | Purpose |
|-----------|---------|
| `io.livekit:livekit-android` | Core SDK — WebRTC, Kotlin coroutines API |
| `Room` | Manages connection, participant events |
| `LocalParticipant` | `setMicrophoneEnabled()` / `setCameraEnabled()` |
| Oboe (via SDK) | Android audio engine — hardware AEC when device supports it |
| Kotlin Flows | `room.events.collect()` for reactive UI updates |

### Connection Flow

```
MainActivity.kt / VoiceViewModel.kt:
  1. POST /api/token → get server_url + participant_token
  2. LiveKit.create(applicationContext) → Room
  3. room.connect(server_url, token)
  4. localParticipant.setMicrophoneEnabled(true)
  5. Collect room events → update UI composables
```

### Project Structure (Android Studio)

```
clients/android/app/src/main/java/ai/daily/
├── MainActivity.kt           # Entry point
├── ui/
│   ├── VoiceScreen.kt        # Jetpack Compose UI
│   └── VoiceViewModel.kt     # Room connection + state
├── data/
│   └── TokenRepository.kt    # /api/token network call
└── di/
    └── AppModule.kt          # Hilt DI (optional)
```

---

## FastAPI Token Endpoint

The existing FastAPI server gains one new route. This is the only required backend addition beyond the agent worker.

```python
# src/daily/api/token.py (pseudocode)

from livekit import api as livekit_api

@router.post("/api/token")
async def get_token(request: TokenRequest, user=Depends(get_current_user)):
    token = livekit_api.AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret
    )
    token.with_identity(user.id).with_name(user.name)
    token.with_grants(livekit_api.VideoGrants(room_join=True, room=request.room_name))
    
    return {
        "server_url": settings.livekit_url,
        "participant_token": token.to_jwt()
    }
```

---

## Docker Compose Changes

```yaml
# New service added to docker-compose.yml
livekit:
  image: livekit/livekit-server:latest
  ports:
    - "7880:7880"   # HTTP (health check, API)
    - "7881:7881"   # TCP (WebRTC signaling)
    - "50000-60000:50000-60000/udp"  # WebRTC media (dev only)
  environment:
    - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
    - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}

# New: agent worker service
agent:
  build: .
  command: python -m daily.livekit.agent start
  environment:
    - LIVEKIT_URL=ws://livekit:7880
    - LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
    - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=${REDIS_URL}
    - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
    - CARTESIA_API_KEY=${CARTESIA_API_KEY}
    - OPENAI_API_KEY=${OPENAI_API_KEY}
  depends_on:
    - db
    - redis
    - livekit
```

The FastAPI `app` service is unchanged. The agent worker runs as a separate service in the same compose stack, sharing Postgres and Redis.

---

## Suggested Build Order

Dependencies determine order. Each step builds on the previous.

### Step 1 — Backend: LiveKit Server + Token Endpoint

**What:** Add LiveKit server to docker-compose. Add `POST /api/token` to FastAPI. Add `LIVEKIT_*` to Settings.

**Why first:** All clients need a token endpoint. The LiveKit server must be running before the agent worker can register. No new Python dependencies on the core orchestrator — just `livekit-server-sdk-python` for token generation.

**Validation:** `POST /api/token` returns a valid JWT. LiveKit server health check passes.

---

### Step 2 — Backend: LiveKit Agent Worker

**What:** Create `src/daily/livekit/agent.py`. Install `livekit-agents`, `livekit-plugins-deepgram`, `livekit-plugins-cartesia`, `livekit-plugins-langchain`. Wire `LLMAdapter(graph=build_graph())`. Add agent service to docker-compose.

**Why second:** Agent worker is the critical path — without it, mobile clients connect to a room but no AI responds. This step proves the LangGraph integration works end-to-end before any mobile client exists.

**Validation:** Start agent worker locally. Use LiveKit CLI (`lk room join`) or LiveKit Playground web client to connect to a test room and confirm the agent responds conversationally.

**Key decisions at this step:**
- Thread ID strategy: use `participant.identity` (= user ID) for persistent cross-session state via AsyncPostgresSaver
- Briefing delivery: check Redis cache in `entrypoint()`, call `session.say()` if cache hit
- Approval prompts: the graph's `interrupt()` pauses the agent; re-enter with user's transcript

---

### Step 3 — iOS Client (Swift)

**What:** Create Xcode project. Integrate LiveKit Swift SDK via Swift Package Manager. Wire `Session` + `LocalMedia`. Implement `TokenService` to call `POST /api/token`. Build minimal UI: connect button, speaking/listening state indicator.

**Why third:** iOS is the primary target platform. Completing it validates the full round-trip: device mic → LiveKit → agent → device speaker with hardware AEC.

**Validation:** iPhone connects to a room via real device (not simulator — simulator has no mic). Agent responds. Barge-in works on built-in speaker without echo. Hardware AEC confirmed.

---

### Step 4 — Android Client (Kotlin)

**What:** Create Android Studio project. Add `io.livekit:livekit-android` dependency. Wire `Room` + `LocalParticipant`. Implement `TokenRepository`. Build minimal Compose UI matching iOS.

**Why fourth:** Android follows the same pattern as iOS. By this point the backend and agent are proven — Android is purely a client implementation.

**Validation:** Android device connects to same backend. Voice session works. Oboe AEC confirmed on a device with hardware support.

---

### Step 5 — Web Fallback (Next.js or plain HTML)

**What:** Minimal web page using `@livekit/components-react` or raw `livekit-client` JS SDK. Fetches token from `/api/token`. Connects to room. Microphone via browser WebRTC.

**Why last:** Web AEC is browser-managed (software) and less reliable than native. This is explicitly a fallback, not the primary surface.

**Validation:** Chrome on desktop connects. Agent responds. Acceptable for users without mobile device.

---

## Integration Points Summary

| Boundary | Protocol | Notes |
|----------|----------|-------|
| Mobile client → LiveKit Server | WebRTC (SRTP audio) | Via LiveKit Swift/Android SDK |
| Mobile client → FastAPI | HTTPS REST | Token fetch only (`POST /api/token`) |
| LiveKit Server → Agent Worker | WebSocket (authenticated) | Agent registers and receives job dispatch |
| Agent Worker → Deepgram | WebSocket | STT — same service as before, different invocation |
| Agent Worker → Cartesia | WebSocket | TTS — same service as before, different invocation |
| Agent Worker → LangGraph | In-process function call | `LLMAdapter` wraps `build_graph()` |
| Agent Worker → Postgres | asyncpg | AsyncPostgresSaver for graph checkpoints |
| Agent Worker → Redis | aioredis | Briefing cache reads |
| FastAPI → Postgres | asyncpg | Unchanged |
| FastAPI → Redis | aioredis | Unchanged |

---

## Anti-Patterns to Avoid

### Sharing the Agent Worker Process with FastAPI

**Trap:** Run `agent.py` inside the FastAPI process using background tasks or lifespan hooks.

**Why wrong:** LiveKit agents run a long-lived `cli.run_app()` event loop that conflicts with Uvicorn's loop. Agent state isolation (one job subprocess per session) requires process-level separation.

**Do this instead:** Separate docker-compose service. Shared Postgres + Redis via environment variables.

### Using Room Metadata for Sensitive State

**Trap:** Inject user preferences, OAuth tokens, or briefing content into LiveKit room metadata.

**Why wrong:** Room metadata is visible to all room participants and to the LiveKit server. The backend already has all context via Postgres + Redis keyed on user ID.

**Do this instead:** Pass only `participant_identity` (= user ID) via the token. Agent worker looks up all context from Postgres/Redis on job start.

### Keeping the Old Voice CLI as a Fallback

**Trap:** Leave `daily voice` CLI active "just in case" while shipping the LiveKit path.

**Why wrong:** The old voice loop uses sounddevice, which grabs the audio device. Running both creates device conflicts and a maintenance burden. The structural AEC problem is the reason we're switching — keeping the old path keeps the problem alive.

**Do this instead:** Delete `voice/stt.py`, `voice/tts.py`, `voice/barge_in.py`, `voice/loop.py` at the start of v1.4. Retire `daily voice` CLI subcommand. All voice sessions go through LiveKit from this point forward.

### Building Mobile Clients Before the Agent Worker

**Trap:** Start iOS development before the agent is working.

**Why wrong:** The iOS client has nothing to connect to without an agent. Debugging a broken experience is harder when it's split across two untested surfaces simultaneously.

**Do this instead:** Validate the full backend round-trip first using LiveKit CLI or Playground. Then build iOS. Then Android.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|-----------|-------|
| LangGraph/LLMAdapter integration | HIGH | `livekit-plugins-langchain` 0.1.0 shipped 2026-04-08. Official docs confirmed LLMAdapter wraps compiled graph. `langgraph-livekit-agents` community adapter also confirmed this pattern. |
| iOS client pattern | HIGH | Official `agent-starter-swift` repo. `Session` + `LocalMedia` pattern documented. AVAudioEngine AEC confirmed via SDK. |
| Android client pattern | HIGH | Official `agent-starter-android` repo. `Room` + `LocalParticipant` Kotlin API confirmed. |
| Token endpoint pattern | HIGH | Official LiveKit docs at `/frontends/authentication/tokens/endpoint/`. FastAPI example provided directly. |
| Agent worker deployment (separate process) | HIGH | Worker model confirmed via `livekit/agents` source and deployment docs. WebSocket-out registration confirmed. No inbound ports needed. |
| docker-compose LiveKit service | MEDIUM | Self-hosted LiveKit well-documented. UDP port range for dev confirmed. Production networking (TURN, STUN) requires additional config — not in scope for local dev. |
| Briefing delivery via `session.say()` | MEDIUM | `say()` method confirmed in `langgraph-livekit-agents` README. Verify actual API surface against installed `livekit-agents` version. |

---

## Sources

- [LiveKit Agents — LangChain integration guide](https://docs.livekit.io/agents/models/llm/plugins/langchain/) — HIGH confidence (official docs)
- [livekit-plugins-langchain on PyPI](https://pypi.org/project/livekit-plugins-langchain/) — HIGH confidence (released 2026-04-08)
- [langgraph-livekit-agents (dqbd/langgraph-livekit-agents)](https://github.com/dqbd/langgraph-livekit-agents/blob/main/python/README.md) — HIGH confidence (adapter pattern confirmed)
- [langgraph-voice-call-agent (ahmad2b)](https://github.com/ahmad2b/langgraph-voice-call-agent) — MEDIUM confidence (community implementation, architecture confirmed)
- [LiveKit agent-starter-swift](https://github.com/livekit-examples/agent-starter-swift) — HIGH confidence (official LiveKit examples)
- [LiveKit agent-starter-android](https://github.com/livekit-examples/agent-starter-android) — HIGH confidence (official LiveKit examples)
- [LiveKit token endpoint docs](https://docs.livekit.io/frontends/authentication/tokens/endpoint/) — HIGH confidence (official docs with FastAPI example)
- [LiveKit voice agent architecture blog](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained) — HIGH confidence (official LiveKit)
- [LiveKit agent deployment docs](https://docs.livekit.io/deploy/agents/) — HIGH confidence (official docs)
- [livekit/agents GitHub — worker.py](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/worker.py) — HIGH confidence (source)

---
*Architecture research for: dAIly v1.4 Mobile Voice milestone*
*Researched: 2026-04-28*
