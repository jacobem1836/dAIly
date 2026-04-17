# Architecture Research

**Domain:** Voice-first AI personal assistant (backend-first)
**Researched:** 2026-04-05
**Confidence:** HIGH (multiple authoritative sources, 2025-2026 literature, production systems)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        VOICE INTERFACE LAYER                     │
│  ┌──────────────┐              ┌──────────────────────────────┐  │
│  │  STT Engine  │              │       TTS Engine             │  │
│  │  (Whisper /  │              │  (ElevenLabs / neural TTS)   │  │
│  │  Deepgram)   │              │  Streaming + phrase cache    │  │
│  └──────┬───────┘              └──────────────┬───────────────┘  │
│         │  transcript text                    │ audio chunks     │
└─────────┼───────────────────────────────────  ┼ ────────────────┘
          │                                     ↑
┌─────────┼─────────────────────────────────────┼────────────────┐
│                        ORCHESTRATOR LAYER                        │
│         ↓                                     │                  │
│  ┌─────────────────────────────────────────┐  │                  │
│  │           Session Manager               │  │                  │
│  │  • Turn-taking / endpointing            │  │                  │
│  │  • Interruption detection               │  │                  │
│  │  • Conversation thread state            │  │                  │
│  └──────────────────┬──────────────────────┘  │                  │
│                     ↓                         │                  │
│  ┌─────────────────────────────────────────┐  │                  │
│  │           Agent Orchestrator            │──┘                  │
│  │  • Determines intent (briefing / Q&A /  │                      │
│  │    action request)                      │                      │
│  │  • Selects context window contents      │                      │
│  │  • Routes to LLM with tool schema       │                      │
│  │  • Receives tool-call intent from LLM   │                      │
│  │  • Dispatches to Action Executor        │                      │
│  │  • Enforces approval gate               │                      │
│  └──────┬──────────────┬───────────────────┘                      │
│         │              │                                          │
└─────────┼──────────────┼──────────────────────────────────────────┘
          │              │
          ↓              ↓
┌──────────────┐  ┌─────────────────────────────────────────────┐
│  CONTEXT     │  │              ACTION LAYER                   │
│  BUILDER     │  │  ┌────────────────┐  ┌──────────────────┐  │
│              │  │  │ Approval Gate  │  │ Action Executor  │  │
│ • Fetches    │  │  │ (HITL queue)   │→ │ (email draft /   │  │
│   email      │  │  │ • Stores       │  │  cal reschedule / │  │
│ • Fetches    │  │  │   pending ops  │  │  Slack DM)       │  │
│   calendar   │  │  │ • User confirm │  └──────┬───────────┘  │
│ • Fetches    │  │  │ • Idempotency  │         │              │
│   Slack      │  │  └────────────────┘         ↓              │
│ • Ranks /    │  │                      ┌──────────────┐      │
│   filters    │  │                      │ Action Log   │      │
│ • Summarises │  │                      └──────────────┘      │
│ • Builds     │  └─────────────────────────────────────────────┘
│   briefing   │                │
│   state      │                ↓
└──────┬───────┘  ┌─────────────────────────────────────────────┐
       │          │           INTEGRATION LAYER                  │
       └─────────→│  ┌──────────┐ ┌─────────┐ ┌─────────────┐  │
                  │  │  Gmail   │ │  GCal   │ │    Slack    │  │
                  │  │  Reader  │ │  Reader │ │    Reader   │  │
                  │  └──────────┘ └─────────┘ └─────────────┘  │
                  │       ↑            ↑             ↑          │
                  │  ┌────────────────────────────────────────┐ │
                  │  │        OAuth Token Vault               │ │
                  │  │  (encrypted at rest, AES-256)          │ │
                  │  └────────────────────────────────────────┘ │
                  └─────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         MEMORY LAYER                             │
│  ┌─────────────────────────┐  ┌────────────────────────────┐    │
│  │   Short-Term Memory     │  │   Long-Term Memory         │    │
│  │   (per-session)         │  │   (persistent)             │    │
│  │  • Conversation thread  │  │  • User profile            │    │
│  │  • Tool call results    │  │  • Preference signals      │    │
│  │  • Current briefing ctx │  │  • Briefing personalisation│    │
│  │  • In-progress actions  │  │  • Historical summaries    │    │
│  │  [Redis / in-process]   │  │  [PostgreSQL + pgvector]   │    │
│  └─────────────────────────┘  └────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                Briefing Cache                            │    │
│  │  • Pre-generated briefing narrative (nightly cron)       │    │
│  │  • Structured JSON: ranked items, narrative text, TTL    │    │
│  │  • Invalidated on significant new events                 │    │
│  │  [Redis with TTL]                                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         LLM GATEWAY                              │
│  • Large model (GPT-4-class) for briefing generation & planning │
│  • Fast model (GPT-4o-mini / Haiku) for conversational Q&A      │
│  • LLM never holds credentials, never calls APIs directly       │
│  • Receives tool schemas → returns tool-call intents only       │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| STT Engine | Audio → transcript, VAD endpointing | Whisper (self-hosted) or Deepgram streaming API |
| TTS Engine | Text → audio stream, phrase cache | ElevenLabs streaming, or Coqui TTS |
| Session Manager | Turn-taking, interruption detection, conversation thread | Custom state machine, VAD model |
| Agent Orchestrator | Intent routing, context assembly, tool dispatch, approval enforcement | LangGraph / custom Python async |
| Context Builder | Pull + rank + summarise email/cal/slack into briefing state | Async ingestion pipeline (cron + incremental) |
| LLM Gateway | Reasoning, planning, narrative generation | OpenAI / Anthropic API, model-selected by task |
| Approval Gate | Durable pending-action store, user confirm/reject, idempotency | PostgreSQL queue or Redis + notification hook |
| Action Executor | Execute approved actions against external APIs | Service classes per integration |
| Action Log | Immutable record of every action (type, timestamp, approval, result) | PostgreSQL append-only table |
| OAuth Token Vault | Encrypted storage and rotation of user OAuth tokens | Encrypted PostgreSQL column (AES-256) |
| Integration Adapters | Per-service read/write operations | Gmail API, GCal API, Slack API clients |
| Short-Term Memory | In-session conversation state, tool call results | Redis hash or in-process dict |
| Long-Term Memory | User profile, preferences, historical summaries | PostgreSQL + pgvector for semantic recall |
| Briefing Cache | Pre-generated briefing for instant voice delivery | Redis with TTL (~8h), rebuilt nightly |

## Recommended Project Structure

```
src/
├── orchestrator/           # Agent orchestrator + session manager
│   ├── agent.py            # Main orchestration loop
│   ├── session.py          # Conversation state, turn-taking
│   ├── intent_router.py    # Classify: briefing / Q&A / action
│   └── tool_registry.py    # Tool schema definitions for LLM
├── context/                # Context builder + briefing pipeline
│   ├── builder.py          # Aggregate sources → briefing state
│   ├── ranker.py           # Priority scoring for items
│   ├── summariser.py       # LLM-powered per-source summaries
│   └── cache.py            # Briefing cache read/write
├── integrations/           # External data sources
│   ├── base.py             # Adapter interface
│   ├── gmail.py            # Gmail ingestion
│   ├── gcal.py             # Google Calendar ingestion
│   ├── slack.py            # Slack ingestion
│   └── oauth/              # Token vault, refresh orchestration
│       ├── vault.py        # Encrypted token storage
│       └── flows.py        # OAuth 2.0 consent flows
├── actions/                # Action execution layer
│   ├── executor.py         # Dispatches approved actions
│   ├── approval.py         # Approval gate queue + HITL interface
│   ├── log.py              # Append-only action log
│   └── handlers/           # Per-action implementations
│       ├── email.py
│       ├── calendar.py
│       └── slack.py
├── memory/                 # Memory systems
│   ├── short_term.py       # Session state (Redis)
│   ├── long_term.py        # User profile + history (PostgreSQL/pgvector)
│   └── briefing_cache.py   # Pre-generated briefing store
├── llm/                    # LLM gateway
│   ├── gateway.py          # Model selection + request routing
│   ├── prompts/            # Prompt templates per task type
│   └── tools.py            # Tool schema builder
├── voice/                  # STT + TTS pipeline
│   ├── stt.py              # Speech-to-text adapter
│   ├── tts.py              # Text-to-speech streaming adapter
│   └── vad.py              # Voice activity detection
└── api/                    # Internal API surface
    ├── voice_endpoint.py   # WebSocket for voice I/O
    └── approval_endpoint.py # Approval queue interface
```

### Structure Rationale

- **orchestrator/**: All coordination logic in one place; prevents business logic leaking into integrations or LLM layer
- **context/**: Decoupled from orchestrator so briefing pipeline can run as a background cron job independently
- **integrations/**: Adapter pattern — each source behind a common interface so adding M3 sources (travel, finance) is isolated
- **actions/**: Separating approval gate from executor makes HITL enforceable at the boundary, not by convention
- **memory/**: Short-term and long-term separated by implementation type; briefing cache is a distinct concern
- **llm/**: All LLM calls go through one gateway — enables model swapping, cost tracking, and latency monitoring

## Architectural Patterns

### Pattern 1: Plan-then-Execute with Trust Boundary

**What:** The LLM produces a structured plan (tool names + parameters). A non-LLM orchestrator validates and executes each step. The LLM never invokes an API call directly.

**When to use:** Any time agent actions have real-world side effects (email, calendar, messages). Mandatory for this project per PROJECT.md constraint.

**Trade-offs:** Adds a hop between LLM response and execution. Gain: LLM prompt injections cannot hijack API calls; security is structural not prompt-based.

**Flow:**
```
LLM returns:
  { "tool": "draft_email", "to": "alice@...", "subject": "...", "body": "..." }
                  ↓
Orchestrator validates: tool exists, parameters schema-valid, user scope allows
                  ↓
Approval Gate: store pending action → notify user → await confirm/reject
                  ↓
Action Executor: execute with idempotency key, log result
```

### Pattern 2: Precomputed Briefing Cache

**What:** A background job runs nightly (e.g. 5am) that pulls all integrations, generates the full briefing narrative, and stores it in Redis with a TTL. At voice delivery time, the cache is served instantly — no LLM call at delivery.

**When to use:** Whenever latency at briefing start must feel instant (voice use case). Confirmed practice used by production voice systems (Sierra, Calculus VC 2026 stack article).

**Trade-offs:** Briefing is slightly stale (minutes to hours). Mitigation: run an incremental update pass if cache was built >2h ago and significant new items arrived.

**Flow:**
```
Nightly cron (5am):
  Context Builder → pulls email/cal/slack → ranks → summarises → LLM narrative
                  ↓
  Redis: SET briefing:{user_id} {json} EX 28800  (8h TTL)

Voice delivery (7am):
  Session Manager → GET briefing:{user_id}  (~1ms)
                  ↓
  TTS: stream pre-generated narrative immediately
```

### Pattern 3: Streaming STT/TTS Pipeline

**What:** STT streams transcript chunks as speech is detected. LLM begins generating before full transcript is complete (if confidence is high). TTS begins streaming audio before LLM response is finished. Each stage overlaps rather than waiting for the prior to finish.

**When to use:** All voice interaction paths for natural conversation feel. Target: sub-800ms perceived latency.

**Trade-offs:** Requires careful interrupt handling (user starts speaking mid-response). Need VAD to detect interruption and cancel in-flight TTS.

**Latency budget (target):**
```
STT streaming:          ~200ms to first useful transcript chunk
LLM time-to-first-token: ~200-300ms
TTS first audio chunk:  ~100-200ms
─────────────────────────────────────
Total perceived:         ~500-700ms  (overlapped stages)
```

### Pattern 4: Dual-Model LLM Strategy

**What:** Route LLM requests to different models by task complexity. Large model (GPT-4-class) for briefing generation and multi-step planning. Fast model (GPT-4o-mini or Claude Haiku) for conversational follow-up questions where speed matters more than depth.

**When to use:** When latency and cost matter. Briefing generation is offline/cached so large model cost is acceptable. Voice Q&A needs fast model.

**Trade-offs:** Two model integrations to maintain. Mitigation: single LLM gateway that selects model based on task type enum.

### Pattern 5: Dual-Layer Memory

**What:** Short-term memory (Redis, in-session) stores conversation thread and tool call results. Long-term memory (PostgreSQL + pgvector) stores user profile, preferences, and historical summaries. Memory extraction runs end-of-session to consolidate relevant signals into long-term.

**When to use:** All stateful agent interactions. Separation prevents short-term session state from polluting long-term profile and keeps latency profile distinct per use.

**Flow:**
```
Session start:
  Load user profile from long-term → inject into system prompt

During session:
  All turns + tool results → short-term (Redis, keyed by session_id)

Session end:
  Extraction pipeline: identify preference signals, corrections, skips
  → write summaries to long-term PostgreSQL
```

## Data Flow

### Morning Briefing Flow (primary)

```
[Nightly Cron: 5am]
  Integration Layer (Gmail + GCal + Slack)
      ↓ raw items
  Context Builder
      ↓ ranked + summarised briefing state
  LLM Gateway (large model)
      ↓ briefing narrative (JSON + text)
  Briefing Cache (Redis, 8h TTL)

[User wakes: 7am voice request]
  STT Engine
      ↓ "play my briefing" transcript
  Session Manager
      ↓ intent: BRIEFING
  Agent Orchestrator
      ↓ cache hit? YES
  Briefing Cache
      ↓ pre-generated narrative (~1ms)
  TTS Engine
      ↓ streaming audio
  [User hears briefing instantly]
```

### Conversational Follow-Up Flow

```
[User interrupts or asks follow-up]
  STT Engine
      ↓ transcript
  Session Manager (interruption detected → cancel active TTS)
      ↓ conversation turn
  Agent Orchestrator
      ↓ loads short-term memory (session context)
  LLM Gateway (fast model + tool schema)
      ↓ response OR tool-call intent
      ↓ if tool-call →
  Approval Gate (if external-facing)
      ↓ user confirms
  Action Executor
      ↓ executes, logs
  Orchestrator assembles response
      ↓
  TTS Engine → streaming audio
```

### Integration Ingestion Flow

```
[Cron or incremental trigger]
  OAuth Token Vault
      ↓ decrypts + provides token
  Integration Adapter (Gmail / GCal / Slack)
      ↓ raw items (emails, events, messages)
  Context Builder → filter → rank → per-item summaries
      ↓
  Long-Term Memory (summaries stored; raw bodies NOT stored)
      ↓
  Briefing Cache (invalidated if significant new items)
```

### Action Execution Flow

```
[LLM returns tool-call intent]
  Orchestrator validates: tool in registry, params schema-valid
      ↓
  Approval Gate
      ↓ stores pending action (PostgreSQL)
      ↓ notifies user (voice prompt: "Want me to send that reply?")
  [User: "yes"]
      ↓
  Action Executor
      ↓ calls Integration Adapter (e.g. Gmail send)
      ↓ idempotency key checked
  Action Log (immutable append)
      ↓
  Orchestrator → confirmation response to user
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user (MVP) | Single Python process, SQLite or single Postgres, Redis local. Briefing cron is a simple script. |
| 10-100 users | Postgres on managed host, Redis hosted (Upstash), async task queue (Celery/ARQ) for cron jobs. Separate briefing worker process. |
| 1k+ users | Per-user briefing workers with scheduled offsets, connection pooling, rate limit management per OAuth app, consider queue-based ingestion (Kafka/SQS). |

### Scaling Priorities

1. **First bottleneck:** OAuth rate limits — Gmail API has per-user per-day quotas. At 100 users all running briefings at 5am, fan-out hits quota. Fix: stagger cron offsets per user (5:00, 5:03, 5:06...).
2. **Second bottleneck:** LLM cost + latency for briefing generation. Fix: batch summarisation sub-calls, cache summaries separately so only the final narrative needs regeneration on incremental updates.

## Anti-Patterns

### Anti-Pattern 1: LLM with Direct API Access

**What people do:** Give the LLM an OAuth token and let it call Gmail/GCal APIs directly via tool calls.

**Why it's wrong:** Prompt injection in an email body can hijack the agent to exfiltrate data, send rogue emails, or delete calendar events. The LLM becomes the trust boundary — which fails in production.

**Do this instead:** All tool calls return to the orchestrator as structured intents. The backend validates and executes with a separate approval gate. LLM never sees credentials.

### Anti-Pattern 2: Storing Raw Email Bodies

**What people do:** Ingest full email bodies into the database for LLM context.

**Why it's wrong:** GDPR/privacy risk. Long-term storage of sensitive content. LLM context window bloat. Per PROJECT.md constraint: raw bodies must not be stored long-term.

**Do this instead:** Extract summaries and metadata at ingestion time. Pass only summaries to LLM. Discard raw bodies after summarisation pass.

### Anti-Pattern 3: Synchronous Briefing Generation at Delivery Time

**What people do:** When user asks for briefing, trigger the full pipeline: fetch → summarise → generate → speak.

**Why it's wrong:** End-to-end latency is 30-60 seconds. Voice interaction feels broken. User is left waiting in silence.

**Do this instead:** Precompute and cache. Briefing pipeline runs nightly. At delivery, serve from cache in milliseconds.

### Anti-Pattern 4: Single-Model for All LLM Tasks

**What people do:** Route all LLM requests to GPT-4 for quality uniformity.

**Why it's wrong:** Simple conversational Q&A during a briefing does not need a frontier model. Latency is 2-5x higher and cost is 10-20x higher than necessary for fast-response tasks.

**Do this instead:** Dual-model strategy. Large model for offline briefing generation (cost/latency acceptable). Fast model for voice turn-around where sub-300ms TTFT is required.

### Anti-Pattern 5: Blocking Approval on Voice-Only Channel

**What people do:** Approval gate delivered only via voice ("Say yes to confirm").

**Why it's wrong:** Voice-only approval fails when the user is in a meeting, driving, or hands-free. Approval for irreversible actions needs a durable async channel.

**Do this instead:** Approval gate uses a push notification or accessible UI (later milestones). For M1 backend-only, approve via CLI/API hook; voice confirmation is an enhancement not a hard dependency.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Gmail | OAuth 2.0 + Gmail API (users.messages.list, users.messages.get, users.messages.send) | 25K quota units/user/day; batch read requests |
| Google Calendar | OAuth 2.0 + GCal API (events.list) | Shared OAuth consent with Gmail if using same Google app |
| Slack | OAuth 2.0 + Slack Web API (conversations.history, chat.postMessage) | Bot token scoped to specific channels |
| OpenAI / Anthropic | API key (server-side only) | Never expose to frontend or LLM context |
| STT provider | Streaming WebSocket (Deepgram) or local Whisper | Deepgram for low-latency streaming; Whisper for privacy/offline |
| TTS provider | Streaming HTTP (ElevenLabs) or local neural TTS | ElevenLabs for quality; local Coqui for cost/privacy |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Orchestrator ↔ LLM Gateway | Async function call, returns tool-call intents | Gateway handles model selection, retries |
| Orchestrator ↔ Context Builder | Read from cache / trigger rebuild | Cache is the contract; builder is fire-and-forget |
| Orchestrator ↔ Approval Gate | Write pending action, poll or await callback | Durable queue — survives process restart |
| Orchestrator ↔ Short-Term Memory | Direct read/write (Redis in-session) | Keyed by session_id, cleared on session end |
| Context Builder ↔ Integration Adapters | Async pull, returns structured item list | Adapter interface: `fetch(since: datetime) → List[Item]` |
| Action Executor ↔ Integration Adapters | Write operations (send, create, update) | Same adapter, write path — uses same OAuth token |
| Context Builder ↔ Long-Term Memory | Write summaries + metadata | Raw bodies never written |

## Suggested Build Order

Dependencies determine build order. Each layer depends on the layer below it.

```
1. OAuth Token Vault + Integration Adapters (read-only)
   → Nothing works without authenticated data access

2. Context Builder (fetch → rank → summarise)
   → Depends on: adapters
   → Produces: briefing state / cache

3. Briefing Cache + Long-Term Memory (PostgreSQL + Redis)
   → Depends on: context builder output
   → Produces: instant briefing retrieval

4. LLM Gateway (model routing, tool schema, prompt templates)
   → Depends on: context builder output (for context injection)
   → Produces: reasoning, narrative, tool-call intents

5. Agent Orchestrator (intent routing, tool dispatch)
   → Depends on: LLM gateway, memory layers, briefing cache
   → Produces: coordinated session flow

6. Approval Gate + Action Executor + Action Log
   → Depends on: orchestrator (receives tool-call intents)
   → Produces: safe external-facing actions

7. Voice Layer (STT + TTS + Session Manager)
   → Depends on: orchestrator (consumes/produces text)
   → Produces: voice I/O loop
```

**Implication for M1 phase structure:**
- **Phase 1 (Foundation):** Token vault, integration adapters, database schema
- **Phase 2 (Data pipeline):** Context builder, briefing cache, ranking
- **Phase 3 (Reasoning):** LLM gateway, orchestrator, basic conversational Q&A
- **Phase 4 (Actions):** Approval gate, action executor, action log
- **Phase 5 (Voice):** STT, TTS, session manager, voice interaction loop
- **Phase 6 (Personalisation):** Long-term memory, preference signals, user profile

## Sources

- [The 2026 Voice AI Stack: Every Layer Explained — Calculus VC](https://calculusvc.com/the-2026-voice-ai-stack-every-layer-explained/)
- [The Voice AI Stack for Building Agents — AssemblyAI](https://www.assemblyai.com/blog/the-voice-ai-stack-for-building-agents)
- [Engineering Low-Latency Voice Agents — Sierra AI](https://sierra.ai/blog/voice-latency)
- [How to Optimise Latency for Voice Agents — Nikhil R (2025)](https://rnikhil.com/2025/05/18/how-to-reduce-latency-voice-agents)
- [AI Agent Memory: Types, Architecture & Implementation — Redis](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [Human-in-the-Loop Architecture: When Humans Approve Agent Decisions — Agent Patterns](https://www.agentpatterns.tech/en/architecture/human-in-the-loop-architecture)
- [LLM Orchestration Architecture — DEV Community](https://dev.to/prince_d02d8ea487b1268cb5/llm-orchestration-architecture-10mj)
- [OAuth for AI Agents: Production Architecture — Scalekit](https://www.scalekit.com/blog/oauth-ai-agents-architecture)
- [Architecting Resilient LLM Agents: Secure Plan-then-Execute — arXiv](https://arxiv.org/pdf/2509.08646)
- [Context Engineering for Reliable AI Agents — Kubiya (2025)](https://www.kubiya.ai/blog/context-engineering-ai-agents)

---
*Architecture research for: voice-first AI personal assistant (dAIly)*
*Researched: 2026-04-05*
