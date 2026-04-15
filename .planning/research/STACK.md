# Stack Research

**Domain:** Voice-first AI personal assistant (backend-first)
**Researched:** 2026-04-05 (v1.0) / updated 2026-04-15 (v1.1)
**Confidence:** MEDIUM-HIGH (core stack HIGH; memory/scheduling MEDIUM)

---

## v1.1 Intelligence Layer — New Additions

> The sections below cover ONLY what is new or changed for v1.1. The full v1.0 stack is preserved below and remains the baseline.

### Decision Summary

| Feature | Approach | New Dependency? |
|---------|----------|-----------------|
| Cross-session memory (INTEL-02) | LangGraph `AsyncPostgresStore` + `langmem` | YES — `langmem>=0.0.30` |
| Adaptive priority scoring (INTEL-01) | scikit-learn `SGDClassifier` via `partial_fit` | YES — `scikit-learn>=1.4.0` |
| Memory transparency API (MEM-01/02/03) | Native FastAPI CRUD over `AsyncPostgresStore` | NO |
| Autonomy level config (ACT-07) | LangGraph conditional interrupt + `user_profile` JSONB field | NO |
| Conversational flow (CONV-01/02/03) | LangGraph graph restructure + mode enum in state | NO |

### New Dependency 1: LangMem — Cross-Session Memory

**Package:** `langmem`
**Version:** `>=0.0.30` (current as of 2026-04-15; released 2025-10-27; Python >= 3.10)
**Install:** `uv add langmem`

**What it does:** Extracts structured facts from conversation messages and writes them into LangGraph's `BaseStore` in a namespace keyed by user. At briefing precompute time, `store.search(namespace)` retrieves the user's memory context. The `create_memory_store_manager()` call runs as an async background task after each session — it does not block the voice path.

**Why LangMem over mem0ai:**

The existing v1.0 stack already includes `langgraph-checkpoint-postgres 3.0.5`, which ships `AsyncPostgresStore`. LangMem is the official LangChain-maintained library that targets this exact store. Integrating it adds one new package, zero new infrastructure, and zero additional Postgres connection pools.

mem0ai was included in early research as a placeholder for "memory layer TBD." On evaluation it is inappropriate here for three reasons: (1) mem0 manages its own pgvector connection pool, separate from SQLAlchemy's async engine — two pools against the same Postgres instance with no transaction coordination; (2) documented production instability in OSS pgvector mode as of April 2026 (GitHub issues #1740, #4727); (3) mem0's value-add is managed cloud hosting and a standalone API, neither of which apply when the DB is already owned. **Remove `mem0ai` from v1.1 — it was never integrated and should not be added.**

**Integration pattern:**
- `AsyncPostgresStore` (already available via `langgraph-checkpoint-postgres`) handles persistence.
- LangMem's `create_memory_store_manager()` is called after each briefing session with the session messages and a Pydantic schema defining what fields to extract (name, inferred communication preferences, topic interests, VIP senders, recurring concerns).
- Memories are retrieved in `context_builder.py` during briefing precompute via `store.search(("users", user_id, "memory"))`.
- Memory CRUD for transparency endpoints (MEM-01/02/03) calls `store.list()`, `store.delete()`, and `store.put()` directly — no extra library.

**Version compatibility check required:** Verify `langmem/pyproject.toml` pins a `langgraph` range compatible with the installed `langgraph 1.1.6` before adding to lockfile. Run `uv add langmem` and inspect the resolver output.

**Confidence:** MEDIUM-HIGH. LangMem is official LangChain tooling, actively maintained, and the `AsyncPostgresStore` integration is explicitly documented for production use. Pre-v1.0 version number (`0.0.x`) means the API surface could change; pin the exact version.

---

### New Dependency 2: scikit-learn — Adaptive Priority Scoring

**Package:** `scikit-learn`
**Version:** `>=1.4.0` (stable; current is 1.7.x–1.8.x as of April 2026)
**Install:** `uv add scikit-learn`

**What it does:** Replaces the heuristic `briefing/ranker.py` scoring formula with a per-user learned ranker. `SGDClassifier` with `partial_fit()` is an online binary classifier that updates per new signal batch without retraining from scratch. Each call to `partial_fit()` takes a feature vector (sender hash, subject keywords, time-of-day, thread depth, direct/cc flag) and a label (was this email positively engaged with — re-requested, expanded — or skipped/corrected?).

The model weights are serialised with `joblib.dumps()` to `bytes` and stored in the existing `user_profile.preferences` JSONB column as a base64 string, or in a dedicated `scorer_bytes` column (bytea) added via Alembic. The model is loaded at briefing precompute, applied to rank, then released.

**Cold-start:** When signal count < 20, the existing heuristic ranker runs unchanged. Score from the learned model blends linearly from 0% to 100% as signal count grows from 20 to 100. No separate library needed for this logic.

**Why not `river` or `vowpal-wabbit`:** The signal volume for a single user is tens to hundreds per week. scikit-learn's `partial_fit` handles this comfortably on CPU with no infrastructure. `river` is designed for millions of events per second streaming. `vowpal-wabbit` requires a daemon process. Both are over-engineered for this use case.

`joblib` is a transitive dependency of scikit-learn; it does not need a separate pin.

**Confidence:** HIGH. `SGDClassifier.partial_fit()` is stable and production-proven across many scikit-learn versions. The serialisation pattern is standard Python ML.

---

### No New Dependencies Needed for Other v1.1 Features

**Memory transparency API (MEM-01, MEM-02, MEM-03):** Standard FastAPI CRUD routes over `AsyncPostgresStore`. `GET /memory`, `DELETE /memory/{id}`, `POST /memory/disable`. Follows the existing `profile/service.py` pattern. No new library.

**Autonomy levels (ACT-07):** Add an `autonomy_level: Literal["suggest", "approve", "auto"]` field to `UserPreferences` in `profile/models.py`. At graph invocation time, set `interrupt_on` dynamically based on the loaded preference. LangGraph already supports `interrupt_on: bool | InterruptOnConfig` per tool/node. No new library. No Alembic migration needed — `user_profile.preferences` is already JSONB.

**Conversational flow (CONV-01, CONV-02, CONV-03):** Add a `ConversationMode` enum (`briefing | discussion | action`) to LangGraph state. Add conditional routing edges based on detected intent. Extend `UserPreferences` with a `verbosity` field derived from `briefing_length` + interaction signals. All of this is graph restructuring and model extension work — no new library.

---

### Updated pyproject.toml

```toml
# Add to [project] dependencies (v1.1 additions only):
"langmem>=0.0.30",
"scikit-learn>=1.4.0",

# Remove (was placeholder, never integrated, not needed):
# mem0ai — replaced by langmem + AsyncPostgresStore
```

---

### Version Compatibility

| Package | Constraint | Notes |
|---------|------------|-------|
| `langmem 0.0.30` | Requires `langgraph` (exact range in its pyproject.toml) | Verify against installed `langgraph 1.1.6` at `uv add` time |
| `scikit-learn >=1.4` | No conflicts — pure NumPy/SciPy | No async concerns |
| `AsyncPostgresStore` | Already in `langgraph-checkpoint-postgres 3.0.5` | LangMem targets this store API directly |

---

### What NOT to Add (v1.1)

| Package | Why Not |
|---------|---------|
| `mem0ai` | Redundant; separate DB connection pool; documented OSS pgvector instability April 2026; was never integrated in v1.0 and should not be added in v1.1 |
| `river` / `vowpal-wabbit` | Online ML overkill at single-user signal volumes; scikit-learn `partial_fit` is sufficient |
| `Pinecone` / `Weaviate` | pgvector already present; no new vector DB needed |
| `MongoDB` as LangGraph store | Already have Postgres; no benefit |
| `Zep` / `Letta` / `Hindsight` | Third-party memory services with their own infra; LangMem + AsyncPostgresStore is the first-party answer |
| `cognee` | Graph memory — overkill for user profile extraction at v1.1 scale |
| `Celery` | APScheduler 3.x handles briefing pipeline; no distributed workers needed yet |

---

### Sources (v1.1 research)

- [LangMem PyPI — v0.0.30](https://pypi.org/project/langmem/)
- [LangMem — Manage User Profiles guide](https://langchain-ai.github.io/langmem/guides/manage_user_profile/)
- [LangMem — Extract Semantic Memories guide](https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/)
- [LangGraph — Memory overview](https://docs.langchain.com/oss/python/langgraph/memory)
- [LangGraph AsyncPostgresStore — forum implementation](https://forum.langchain.com/t/how-do-i-implement-asyncpostgresstore/1666)
- [mem0 pgvector issue #1740](https://github.com/mem0ai/mem0/issues/1740) — documented pgvector setup failures
- [mem0 OpenClaw pgvector crash #4727](https://github.com/mem0ai/mem0/issues/4727) — OSS mode instability
- [Best AI Agent Memory Frameworks 2026 — Atlan](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
- [Best Mem0 Alternatives 2026 — Vectorize](https://vectorize.io/articles/mem0-alternatives)
- [scikit-learn SGDClassifier official docs 1.8.0](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDClassifier.html)
- [scikit-learn Model Persistence official docs 1.8.0](https://scikit-learn.org/stable/model_persistence.html)
- [LangGraph interrupt_on config — LangChain blog](https://blog.langchain.com/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt/)
- [LangGraph Human-in-the-Loop 2026 — GrowwStacks](https://growwstacks.com/blog/human-in-the-loop-ai-agents-langgraph)
- [Voice AI state machine pattern — Voxam](https://voxam.hashnode.dev/stop-letting-llm-drive-voice-agent-state-machine)

---

---

## v1.0 Stack (Validated Baseline)

> Full v1.0 stack preserved below. Do not re-research these components.

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Primary language | Async-native, dominates AI/ML ecosystem, all relevant SDKs are Python-first. 3.11+ required for modern typing. |
| FastAPI | 0.115+ | HTTP API + WebSocket server | Async-first, native Pydantic v2, handles 3000+ req/s, excellent for streaming voice audio. Standard for Python AI backends in 2025. |
| Pydantic | 2.x | Data validation & settings | v2 is 50x faster than v1; FastAPI requires it; models every request/response and settings boundary. |
| PostgreSQL | 15+ | Primary persistent store | Supports pgvector extension for semantic memory, JSONB for flexible profile storage, mature, self-hostable. |
| pgvector | 0.7+ | Vector similarity search | Turns Postgres into a memory retrieval store — no separate vector DB needed for M1 scale. |
| Redis | 7.x | Briefing cache + session state | In-memory TTL cache for precomputed briefings; semantic audio cache (AUDIO_CACHE_TTL=86400). Sub-millisecond reads. |
| SQLAlchemy | 2.0.x | Async ORM | 2.0 rewrites async properly — use `create_async_engine` + `asyncpg` driver. Only choice for async Postgres in Python. |
| Alembic | 1.13+ | Database migrations | Pairs with SQLAlchemy 2.0; async migration support. Manages schema evolution safely. |
| asyncpg | 0.29+ | PostgreSQL async driver | Fastest Python Postgres driver; required backend for SQLAlchemy async engine. |

### STT — Speech to Text

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Deepgram Nova-3 | API (current) | Real-time STT | Sub-300ms streaming latency, $0.0077/min, best real-time latency of any hosted STT. $200 free credits for new accounts. |
| Deepgram Python SDK | 3.x | SDK | Official, maintained, WebSocket streaming built-in. |

**Rationale:** Deepgram Nova-3 consistently benchmarks fastest for conversational STT (real-time factor 0.2–0.3x vs Whisper's 0.5x+). OpenAI Whisper has no native real-time streaming — requires custom chunking or the Realtime API which bundles LLM (not desired here). AssemblyAI Universal-2 is competitive but priced higher for streaming.

### TTS — Text to Speech

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Cartesia Sonic-3 | API (current) | Real-time TTS streaming | 40–90ms TTFB — industry-leading latency. WebSocket streaming. 73% cheaper than ElevenLabs. Built for voice agents. |
| cartesia | 2.x (Python SDK) | SDK | Official, WebSocket streaming, multi-concurrent streams on single socket. |

**Rationale:** For a briefing assistant where the precomputed audio is cached, raw latency matters less — but for interruption/follow-up responses, TTFB is critical. Cartesia Sonic-3 is the fastest at 40–90ms TTFB, cheaper than ElevenLabs, and purpose-built for real-time agents. ElevenLabs is reserved for M2+ if voice cloning or emotional expressiveness becomes a product requirement.

### LLM Orchestration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| LangGraph | 0.2+ | Agent orchestration | Stateful graph execution with human-in-the-loop interrupts (required for M1 approval flow). Better than LangChain for cyclic agent workflows. |
| OpenAI Python SDK | 1.x | LLM API access | Direct SDK for GPT-4.1 and GPT-4.1 mini; streaming responses. |
| GPT-4.1 | API (current) | Briefing generation + reasoning | 1M token context, better instruction following than GPT-4o, $2/M input tokens. Ideal for multi-email/calendar summarisation. |
| GPT-4.1 mini | API (current) | Quick responses + follow-ups | $0.40/M input tokens, low latency, good instruction following. Use for conversational follow-ups after briefing. |

**Rationale:** LangGraph wins over raw LangChain for this use case because the approval flow requires stateful human-in-the-loop interrupts — LangGraph has this built-in. GPT-4.1 (not GPT-4o) is the correct primary model: it has 8x the context of GPT-4o, better instruction following for structured briefings, and competitive pricing. Multi-model: GPT-4.1 for briefing generation, GPT-4.1 mini for real-time follow-up responses.

### Memory & Personalisation

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| pgvector (via SQLAlchemy) | — | Semantic memory retrieval | Embeddings stored in same Postgres instance — no separate Chroma/Pinecone. Keeps architecture simple for M1. |

**Note:** mem0ai was in the original research as a candidate. It was never integrated in v1.0 and is superseded by the LangMem + AsyncPostgresStore approach in v1.1. Do not add it.

### Integrations

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| google-api-python-client | 2.x | Gmail + Google Calendar API | Official Google client. Required since March 2025 when Google mandated OAuth for all third-party Gmail/Calendar access. |
| google-auth-oauthlib | 1.x | OAuth 2.0 flow for Google | Handles token refresh, scope incrementalism, secure storage. |
| slack-sdk | 3.x | Slack messaging ingestion | Official Slack Python SDK. WebSocket for real-time events, REST for history ingestion. |
| msgraph-sdk | 1.x | Microsoft Graph (Outlook/Teams) | Official Microsoft Graph Python SDK. Replaces older MSAL-only patterns. Covers Outlook mail + calendar. |
| msal | 1.x | Microsoft OAuth 2.0 | Microsoft Authentication Library — token acquisition for Graph API scopes. |
| authlib | 1.x | OAuth token storage + encryption | Replaces python-jose for token handling (python-jose is nearly unmaintained as of 2025). Handles JWT + AES-256 token encryption at rest. |

**Rationale:** Google's March 2025 mandate means OAuth is now non-negotiable for Gmail/Calendar. Microsoft Graph SDK (not just MSAL) provides cleaner Python bindings than raw requests. authlib is the actively maintained replacement for python-jose — the FastAPI community has flagged python-jose as near-abandoned in 2025 (FastAPI discussion #9587).

### Scheduling (Briefing Pipeline)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| APScheduler | 3.10.x (AsyncIOScheduler) | Cron-scheduled briefing precompute | In-process async scheduler; integrates with FastAPI's asyncio loop. No broker dependency. Right scale for M1 single-process deployment. |

**Rationale:** Celery is overkill for M1 — it requires a broker (Redis or RabbitMQ) and worker processes. APScheduler's `AsyncIOScheduler` runs inside FastAPI's event loop and handles the nightly briefing cron and token-refresh jobs without external dependencies. Migrate to Celery in M2 only if multi-worker horizontal scaling is needed.

### Security

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| cryptography | 42+ | AES-256-GCM encryption | Industry standard for Python crypto. Encrypt OAuth tokens at rest before writing to DB. |
| passlib[bcrypt] | 1.7+ | Password hashing (if local auth needed) | Standard bcrypt wrapper. |
| python-dotenv | 1.x | Secrets loading from .env | Keep credentials out of code; load at startup. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package/venv management | Replaces pip + virtualenv; 10–100x faster. Standard in 2025 Python projects. |
| pytest + pytest-asyncio | Async test suite | Required for testing FastAPI async endpoints and pipeline stages. |
| httpx | Async HTTP client (tests + integration calls) | Drop-in async requests replacement; used by FastAPI's TestClient. |
| docker compose | Local dev orchestration | Spin up Postgres + Redis locally without cloud dependency. |
| Alembic | Migration management | Already listed above — mention here as the dev workflow tool. |

---

## Stack Patterns by Variant

**Nightly briefing precompute pipeline:**
- APScheduler cron at 05:30 local time triggers the pipeline
- Pipeline: Google/Microsoft/Slack ingestion → LLM summarisation (GPT-4.1) → TTS render (Cartesia) → write audio bytes + transcript to Redis with TTL=24h
- On wake, briefing plays from cache — zero LLM or TTS latency

**Real-time follow-up conversation:**
- Deepgram Nova-3 WebSocket STT → LangGraph agent → GPT-4.1 mini (fast, cheap) → Cartesia Sonic-3 WebSocket TTS
- Target: sub-500ms end-to-end for follow-up turns

**Action execution (draft email, schedule event):**
- LangGraph human-in-the-loop interrupt holds execution pending user approval
- User approval triggers integration module (Google/Microsoft APIs) — LLM never touches credentials
- All actions logged to Postgres action_log table with timestamp, type, approval_status

**OAuth token storage:**
- Tokens encrypted with AES-256-GCM (cryptography library) before writing to Postgres
- Decrypted in-memory only at API call time — never logged, never passed to LLM layer

---

## Version Compatibility (v1.0 baseline)

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| SQLAlchemy 2.0.x | asyncpg 0.29+ | SQLAlchemy 2.0 async engine requires asyncpg as the driver backend |
| FastAPI 0.115+ | Pydantic 2.x | FastAPI 0.100+ migrated to Pydantic v2 — do not pin Pydantic 1.x |
| LangGraph 0.2+ | LangChain-core (not langchain full package) | Only need langchain-core for LangGraph; avoid installing full langchain to reduce dep conflicts |
| APScheduler 3.10.x | asyncio / FastAPI | Pinned to 3.x; APScheduler 4.x has breaking changes and is pre-release |
| Python 3.11+ | FastAPI 0.115+ | FastAPI dropped Python 3.9 support in Feb 2026 (0.130.0); use 3.11 minimum today |

---

## Sources (v1.0)

- AssemblyAI — [The voice AI stack for building agents (2026)](https://www.assemblyai.com/blog/the-voice-ai-stack-for-building-agents) — HIGH confidence
- Deepgram — [Nova-3 pricing and Python SDK](https://deepgram.com/pricing) — HIGH confidence
- Cartesia — [Sonic-3 docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest) — HIGH confidence
- Cartesia — [Python SDK v2](https://cartesia.ai/blog/python-sdk) — HIGH confidence
- OpenAI — [GPT-4.1 model comparison](https://platform.openai.com/docs/models/compare) — HIGH confidence
- LangChain — [LangGraph overview](https://www.langchain.com/langgraph) — HIGH confidence
- FastAPI — [FastAPI discussion #9587 on python-jose](https://github.com/fastapi/fastapi/discussions/9587) — HIGH confidence
- Google — [OAuth 2.0 for Google APIs](https://developers.google.com/identity/protocols/oauth2) — HIGH confidence

---

*Stack research for: voice-first AI personal assistant (dAIly)*
*v1.0 researched: 2026-04-05 | v1.1 additions researched: 2026-04-15*
