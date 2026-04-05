<!-- GSD:project-start source:PROJECT.md -->
## Project

**dAIly**

A voice-first AI personal assistant that proactively synthesises a user's digital life into an intelligent daily briefing. It acts as a semi-autonomous operator for communication, scheduling, and decision support — combining executive briefing, conversational assistant, and action-taking agent. Built backend-first, targeting busy professionals and operators who want their life to brief them rather than manually checking multiple apps.

**Core Value:** The briefing always delivers: every morning, the user gets a prioritised, conversational summary of what matters — without touching a single app.

### Constraints

- **Architecture**: LLM must not directly access APIs or hold credentials — backend mediates everything
- **Privacy**: Raw email/message bodies must not be stored long-term — only summaries and metadata
- **Latency**: Voice responses must feel instant — precompute briefings, stream TTS
- **Security**: OAuth tokens encrypted at rest (AES-256), stored in secure vault (never frontend)
- **Autonomy**: All external-facing actions require user approval in M1 — auto-actions are M2+
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
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
### TTS — Text to Speech
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Cartesia Sonic-3 | API (current) | Real-time TTS streaming | 40–90ms TTFB — industry-leading latency. WebSocket streaming. 73% cheaper than ElevenLabs. Built for voice agents. |
| cartesia | 2.x (Python SDK) | SDK | Official, WebSocket streaming, multi-concurrent streams on single socket. |
### LLM Orchestration
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| LangGraph | 0.2+ | Agent orchestration | Stateful graph execution with human-in-the-loop interrupts (required for M1 approval flow). Better than LangChain for cyclic agent workflows. |
| OpenAI Python SDK | 1.x | LLM API access | Direct SDK for GPT-4.1 and GPT-4.1 mini; streaming responses. |
| GPT-4.1 | API (current) | Briefing generation + reasoning | 1M token context, better instruction following than GPT-4o, $2/M input tokens. Ideal for multi-email/calendar summarisation. |
| GPT-4.1 mini | API (current) | Quick responses + follow-ups | $0.40/M input tokens, low latency, good instruction following. Use for conversational follow-ups after briefing. |
### Memory & Personalisation
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| mem0 | 0.1+ (mem0ai PyPI) | User memory layer | Extracts facts from interactions, stores in pgvector, retrieves at query time. ~50K GitHub stars. Works with LangGraph and OpenAI. |
| pgvector (via SQLAlchemy) | — | Semantic memory retrieval | Embeddings stored in same Postgres instance — no separate Chroma/Pinecone. Keeps architecture simple for M1. |
### Integrations
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| google-api-python-client | 2.x | Gmail + Google Calendar API | Official Google client. Required since March 2025 when Google mandated OAuth for all third-party Gmail/Calendar access. |
| google-auth-oauthlib | 1.x | OAuth 2.0 flow for Google | Handles token refresh, scope incrementalism, secure storage. |
| slack-sdk | 3.x | Slack messaging ingestion | Official Slack Python SDK. WebSocket for real-time events, REST for history ingestion. |
| msgraph-sdk | 1.x | Microsoft Graph (Outlook/Teams) | Official Microsoft Graph Python SDK. Replaces older MSAL-only patterns. Covers Outlook mail + calendar. |
| msal | 1.x | Microsoft OAuth 2.0 | Microsoft Authentication Library — token acquisition for Graph API scopes. |
| authlib | 1.x | OAuth token storage + encryption | Replaces python-jose for token handling (python-jose is nearly unmaintained as of 2025). Handles JWT + AES-256 token encryption at rest. |
### Scheduling (Briefing Pipeline)
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| APScheduler | 4.x (AsyncIOScheduler) | Cron-scheduled briefing precompute | In-process async scheduler; integrates with FastAPI's asyncio loop. No broker dependency. Right scale for M1 single-process deployment. |
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
## Installation
# Core runtime
# Database
# Vector / memory
# Cache
# STT
# TTS
# LLM / orchestration
# Integrations — Google
# Integrations — Slack
# Integrations — Microsoft
# Security
# Scheduler
# Dev dependencies
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Deepgram Nova-3 | AssemblyAI Universal-2 | If you need automatic speaker diarisation or chapter detection out of the box |
| Deepgram Nova-3 | OpenAI Realtime API | If you want STT + LLM bundled in one hop (but you lose model control — LLM is locked to GPT-4o) |
| Cartesia Sonic-3 | ElevenLabs Flash 2.5 | If voice cloning from the user's own voice becomes a product requirement (M2+) |
| Cartesia Sonic-3 | OpenAI TTS-1 | If you want a single vendor (OpenAI) for simplicity — but TTS-1 has 200ms TTFB vs Cartesia's 40ms |
| LangGraph | Custom state machine | If LangGraph's abstraction cost (debugging multi-layer indirection) becomes a bottleneck in M2+ |
| GPT-4.1 | Claude 3.5 Sonnet | If instruction-following on very long structured outputs degrades — Anthropic excels at structured output |
| GPT-4.1 mini | Gemini 2.5 Flash-Lite | If you need sub-100ms LLM TTFB for real-time interrupts — Flash-Lite is faster than GPT-4.1 mini |
| PostgreSQL + pgvector | Pinecone / Weaviate | Only if vector queries exceed ~1M embeddings and Postgres query performance degrades |
| APScheduler | Celery Beat | If M2 requires multiple workers, distributed task queuing, or retry-with-backoff job pipelines |
| mem0 | Custom vector memory | If you need tighter control over the extraction prompts or memory graph structure (M2 consideration) |
| authlib | python-jose | Do not use python-jose — near-abandoned in 2025, flagged by FastAPI maintainers |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| python-jose | Near-abandoned as of 2025 (no active maintenance, flagged in FastAPI's own issue tracker #9587). Security library requiring active maintenance. | authlib |
| OpenAI Realtime API (for STT) | Bundles STT + LLM in one pipeline — removes ability to swap models, adds LLM cost to every voice input, breaks the orchestrator-controls-execution constraint in PROJECT.md | Deepgram Nova-3 (STT) + OpenAI (LLM) separately |
| LangChain (chains, not LangGraph) | Sequential chain API doesn't support human-in-the-loop interrupts or state persistence — needed for M1 approval flow | LangGraph (which supersedes LangChain chains for agent use cases) |
| On-device STT (Whisper.cpp) | High setup complexity, no streaming support out of the box, CPU latency unacceptable for voice loop. Explicitly out of scope per PROJECT.md. | Deepgram Nova-3 |
| Celery for M1 | Requires Redis broker + separate worker processes — infrastructure overhead before any value is proven | APScheduler (AsyncIOScheduler) |
| Chroma / Pinecone as separate vector DB | Adds an external service dependency. pgvector on the existing Postgres instance handles M1 scale with zero additional infra. | pgvector extension on PostgreSQL |
| Flask | Synchronous-first; requires WSGI workarounds for async voice streaming. No native WebSocket or streaming response. | FastAPI |
## Stack Patterns by Variant
- APScheduler cron at 05:30 local time triggers the pipeline
- Pipeline: Google/Microsoft/Slack ingestion → LLM summarisation (GPT-4.1) → TTS render (Cartesia) → write audio bytes + transcript to Redis with TTL=24h
- On wake, briefing plays from cache — zero LLM or TTS latency
- Deepgram Nova-3 WebSocket STT → LangGraph agent → GPT-4.1 mini (fast, cheap) → Cartesia Sonic-3 WebSocket TTS
- Target: sub-500ms end-to-end for follow-up turns
- LangGraph human-in-the-loop interrupt holds execution pending user approval
- User approval triggers integration module (Google/Microsoft APIs) — LLM never touches credentials
- All actions logged to Postgres action_log table with timestamp, type, approval_status
- Tokens encrypted with AES-256-GCM (cryptography library) before writing to Postgres
- Decrypted in-memory only at API call time — never logged, never passed to LLM layer
## Version Compatibility
| Package | Compatible With | Notes |
|---------|-----------------|-------|
| SQLAlchemy 2.0.x | asyncpg 0.29+ | SQLAlchemy 2.0 async engine requires asyncpg as the driver backend |
| FastAPI 0.115+ | Pydantic 2.x | FastAPI 0.100+ migrated to Pydantic v2 — do not pin Pydantic 1.x |
| LangGraph 0.2+ | LangChain-core (not langchain full package) | Only need langchain-core for LangGraph; avoid installing full langchain to reduce dep conflicts |
| APScheduler 4.x | asyncio / FastAPI | APScheduler 4.x (pre-release as of 2025) has breaking changes from 3.x — verify 4.x stability or pin 3.10.x AsyncIOScheduler |
| mem0ai | OpenAI SDK 1.x, pgvector | mem0 uses OpenAI embeddings by default — pin openai>=1.0.0 |
| Python 3.11+ | FastAPI 0.115+ | FastAPI dropped Python 3.9 support in Feb 2026 (0.130.0); use 3.11 minimum today |
## Sources
- AssemblyAI — [The voice AI stack for building agents (2026)](https://www.assemblyai.com/blog/the-voice-ai-stack-for-building-agents) — HIGH confidence (vendor docs, current)
- Deepgram — [Nova-3 pricing and Python SDK](https://deepgram.com/pricing) — HIGH confidence (official pricing page)
- Cartesia — [Sonic-3 docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest) — HIGH confidence (official docs)
- Cartesia — [Python SDK v2](https://cartesia.ai/blog/python-sdk) — HIGH confidence
- OpenAI — [GPT-4.1 model comparison](https://platform.openai.com/docs/models/compare) — HIGH confidence (official)
- LangChain — [LangGraph overview](https://www.langchain.com/langgraph) — HIGH confidence (official)
- FastAPI — [FastAPI discussion #9587 on python-jose](https://github.com/fastapi/fastapi/discussions/9587) — HIGH confidence (maintainer-flagged)
- Google — [OAuth 2.0 for Google APIs](https://developers.google.com/identity/protocols/oauth2) — HIGH confidence (official, March 2025 mandate confirmed)
- mem0 — [GitHub repo ~50K stars](https://github.com/mem0ai/mem0) — MEDIUM confidence (community adoption signal)
- ZenML — [LangGraph alternatives + criticism](https://www.zenml.io/blog/langgraph-alternatives) — MEDIUM confidence (engineering blog)
- Layercode — [TTS Voice AI Model Guide 2025](https://layercode.com/blog/tts-voice-ai-model-guide) — MEDIUM confidence (vendor-adjacent)
- Deepgram — [STT API comparison 2025](https://deepgram.com/learn/best-speech-to-text-apis-2026) — MEDIUM confidence (vendor-authored comparison)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
