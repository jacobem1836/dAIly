# Project Research Summary

**Project:** dAIly — Voice-First AI Personal Assistant
**Domain:** Voice AI agent with proactive briefing + action layer
**Researched:** 2026-04-05
**Confidence:** HIGH

## Executive Summary

dAIly is a voice-first AI personal assistant that proactively synthesises a user's email, calendar, and messaging data into a spoken morning briefing, then supports conversational follow-up and gated action execution. Research confirms this is a well-understood product category with a clear competitive gap: every major competitor (ChatGPT Pulse, Google CC, Alfred_) delivers briefings via inbox or app card — none deliver via voice with conversational follow-up. The target architecture is a multi-layer Python async backend with precomputed briefing caches, a plan-then-execute trust boundary between the LLM and external APIs, and a dual-model LLM strategy (large model for briefing generation, fast model for voice turn-around).

The recommended stack centres on FastAPI + LangGraph + PostgreSQL + pgvector + Redis, with Deepgram Nova-3 for STT, Cartesia Sonic-3 for TTS, and GPT-4.1/GPT-4.1 mini for LLM tasks. All OAuth integrations are mandatory (Google mandated OAuth for Gmail/Calendar in March 2025). The precomputed briefing cache is not an optimisation — it is the architectural default required to make voice delivery feel instant. The single biggest risk is allowing the LLM to hold credentials or invoke external APIs directly; this must be structurally prevented from day one, not retrofitted.

The highest-confidence research areas are stack selection, features, and architecture — all have multiple authoritative 2025–2026 sources. The primary gaps are APScheduler 4.x stability (possible version pin needed) and mem0 adoption maturity (MEDIUM confidence, community signal). Neither gap blocks M1; both should be validated during implementation.

---

## Key Findings

### Recommended Stack

The core runtime is Python 3.11+ / FastAPI 0.115+ / Pydantic 2.x. For persistence: PostgreSQL 15+ with pgvector extension (handles both relational and vector/semantic memory in one DB) via SQLAlchemy 2.0 async + asyncpg. Redis 7.x provides briefing cache and session state with sub-millisecond reads. LLM orchestration uses LangGraph 0.2+ (chosen over plain LangChain for its stateful human-in-the-loop interrupt support, required for the M1 approval flow) with GPT-4.1 for briefing generation and GPT-4.1 mini for voice follow-ups.

For the voice pipeline: Deepgram Nova-3 for STT (sub-300ms streaming latency, $0.0077/min), Cartesia Sonic-3 for TTS (40–90ms TTFB, 73% cheaper than ElevenLabs). mem0 wraps the extract-embed-retrieve memory pattern backed by pgvector so no separate vector DB is needed. APScheduler AsyncIOScheduler handles the nightly cron inside FastAPI's event loop — Celery is overkill for M1.

**Core technologies:**
- Python 3.11+ / FastAPI 0.115+: async-native, dominates AI/ML ecosystem, 3000+ req/s
- LangGraph 0.2+: stateful agent orchestration with built-in HITL interrupts
- GPT-4.1 / GPT-4.1 mini: 1M context window, best instruction-following for structured briefings; mini for fast voice turns
- Deepgram Nova-3: sub-300ms streaming STT, best real-time latency of any hosted provider
- Cartesia Sonic-3: 40–90ms TTS TTFB, purpose-built for voice agents
- PostgreSQL 15+ + pgvector: primary store + semantic memory, no separate vector DB required
- Redis 7.x: briefing cache (8h TTL) + session state
- mem0: memory layer (extract, embed, retrieve) backed by pgvector
- APScheduler 4.x AsyncIOScheduler: in-process nightly cron, no broker required
- authlib: OAuth token handling — do NOT use python-jose (near-abandoned in 2025)
- cryptography 42+: AES-256-GCM for OAuth token encryption at rest

**Version flags:**
- APScheduler 4.x is pre-release as of 2025 — verify stability or pin 3.10.x
- FastAPI 0.130+ drops Python 3.9 — use Python 3.11 minimum
- SQLAlchemy 2.0 async requires asyncpg (not psycopg2) as the engine driver

### Expected Features

Research confirms a clear MVP scope and a competitive moat in voice delivery.

**Must have (table stakes — M1):**
- Daily proactive briefing — precomputed and cached, delivered via TTS on request
- Email ingestion + triage — Gmail + Outlook OAuth, heuristic priority ranking
- Calendar ingestion — today + 48h, conflict detection, meeting prep context
- Slack messaging ingestion — mentions, DMs, priority channels
- Voice output (TTS streaming) — sub-150ms synthesis, Cartesia Sonic-3
- Voice input (STT streaming) — interim results, Deepgram Nova-3
- Interruption handling + follow-up questions — barge-in, VAD, multi-turn context
- Action drafting — email/Slack/calendar, never auto-send in M1
- Approval flow — confirm/reject gate, mandatory for all external-facing actions
- Action log — immutable append-only record of every action
- Basic user profile + signal capture — implicit feedback (skips, corrections, re-requests)

**Should have (differentiators — M2):**
- Priority ranking engine — learned from signal data collected in M1
- Cross-session conversational memory — context persists across days via pgvector
- Staged autonomy model — trusted auto-actions for flagged contacts after explicit grant
- Web dashboard — visual companion for action log review and preference management

**Explicitly defer (v2+):**
- Travel/finance integrations — high complexity, niche signal, regulatory exposure
- News/content briefing layer — separate curation problem, dilutes personal signal
- On-device LLM — model quality insufficient in 2026, revisit 2027+
- Multi-user/team briefings — different product category

**Anti-features to never build in M1:**
- Auto-send without approval — destroys trust on first mistake
- Always-on ambient listening — privacy exposure, VAD false positives
- Web dashboard — burns frontend time before core value is proven
- Real-time inbox sync (webhooks) — complexity spike with no briefing benefit

### Architecture Approach

The system has six logical layers: Voice Interface (STT/TTS/VAD), Orchestrator (session manager + agent), Context Builder (ingest + rank + summarise + cache), Action Layer (approval gate + executor + action log), Integration Adapters (Gmail/GCal/Slack + OAuth token vault), and Memory Layer (short-term Redis + long-term Postgres/pgvector + briefing cache). The key architectural constraint from PROJECT.md — and confirmed by security research — is the plan-then-execute trust boundary: the LLM outputs structured tool-call intents; the backend orchestrator validates and executes. The LLM never holds credentials or calls external APIs directly.

**Major components:**
1. Orchestrator (LangGraph) — intent routing, context assembly, tool dispatch, approval enforcement
2. Context Builder — async fetch from all integrations, pre-rank, per-item summarise, write to briefing cache
3. LLM Gateway — model selection by task (GPT-4.1 for briefing, GPT-4.1 mini for voice turns); all LLM calls through single gateway
4. Approval Gate — durable pending-action queue (PostgreSQL), voice confirm/reject, idempotency key
5. Integration Adapters — per-service read/write behind a common interface; OAuth token vault (AES-256 encrypted)
6. Memory Layer — short-term (Redis, session-scoped), long-term (Postgres + pgvector), briefing cache (Redis 8h TTL)

**Build order (dependency-driven):**
OAuth Vault + Integration Adapters → Context Builder → Briefing Cache + DB Schema → LLM Gateway → Orchestrator → Approval Gate + Action Executor → Voice Layer → Personalisation/Memory

### Critical Pitfalls

1. **LLM with direct API access** — Structural, not retrofittable. LLM must never hold credentials or have tool definitions that invoke live APIs. Enforce from day one: LLM returns structured intent JSON; orchestrator validates and executes. (CVSS 9.3 real-world exploit: EchoLeak CVE-2025-32711)

2. **Synchronous briefing generation at delivery time** — If briefing is generated on-demand when the user asks, they wait 15–60 seconds in silence. Precomputed cache is the architectural default, not a later optimisation. Must be designed in before any briefing pipeline work.

3. **Late TTS streaming** — Waiting for the full LLM response before starting TTS adds 1–3 seconds of dead silence. Stream LLM tokens to TTS from the first sentence boundary. Target time-to-first-audio under 300ms.

4. **OAuth token expiry in unattended jobs** — Access tokens expire in ~1 hour. Token refresh must run as a proactive background job (not inline with the 05:30 briefing cron), with a distributed lock to prevent refresh races. Silent failure = user wakes to no briefing.

5. **Raw email/message bodies stored long-term** — GDPR/privacy risk + unbounded PII accumulation. Raw bodies must be processed (summarised, metadata extracted) and discarded in-memory. Only summaries and metadata persist. Enforced at schema design time, not patched later.

6. **Context window overload** — Passing 50 emails + 100 Slack messages raw to GPT-4.1 bloats context to 30–80K tokens, degrades quality, and costs $0.10–0.20/briefing. Target <8,000 tokens per briefing by pre-ranking and per-item summarisation with a cheaper model (GPT-4.1 mini).

7. **Indirect prompt injection** — Adversarial content in email/Slack bodies hijacks the LLM. All external data must pass through a sanitisation/summarisation layer before entering LLM context. Use structural prompt framing marking external data as untrusted.

---

## Implications for Roadmap

Based on the dependency graph in ARCHITECTURE.md and the feature dependencies in FEATURES.md, the following phase structure is recommended. Architecture research explicitly validates this ordering — each layer depends on the layer below it.

### Phase 1: Foundation — OAuth, Integrations, and Database Schema

**Rationale:** Nothing works without authenticated data access and a correct database schema. OAuth token expiry is a CRITICAL pitfall if token vault is built as an afterthought. Data lifecycle policy (no raw bodies) must be enforced at schema design time.

**Delivers:** Encrypted OAuth token vault (AES-256), read-only integration adapters for Gmail/GCal/Slack, PostgreSQL schema with correct data lifecycle (no raw body columns, TTL columns defined), Redis configured locally.

**Addresses:** Email ingestion, calendar ingestion, Slack ingestion (data access layer only)

**Avoids:** Over-permissioned OAuth scopes (read-only scopes only in M1), raw email body storage, OAuth token expiry in unattended jobs, tokens logged in application logs

**Research flag:** Standard patterns — Google OAuth, Microsoft Graph SDK, and Slack SDK are well-documented. No deep research phase needed.

---

### Phase 2: Briefing Pipeline — Context Builder and Cache

**Rationale:** The briefing pipeline must be precomputed by design. PITFALLS.md is unambiguous: synchronous briefing generation at delivery time is unrecoverable as a UX failure. Build the cron + cache architecture before any briefing features are visible.

**Delivers:** APScheduler cron job (05:30 default), context builder (async parallel fetch → pre-rank → per-item summarise → LLM narrative), Redis briefing cache (8h TTL), long-term PostgreSQL memory (summaries only).

**Addresses:** Proactive daily briefing (precomputed), signal capture (metadata stored), basic priority ranking (heuristic)

**Avoids:** Context window overload (pre-rank + summarise to <8,000 tokens), indirect prompt injection (summarisation layer is the sanitisation pass), briefing cache miss at delivery

**Research flag:** APScheduler 4.x pre-release stability needs validation. Verify at implementation start: if unstable, pin 3.10.x AsyncIOScheduler.

---

### Phase 3: Reasoning — LLM Gateway and Orchestrator

**Rationale:** LLM gateway and orchestrator are the coordination layer. They depend on having context (Phase 2) and produce the session flow. CRITICAL: the trust boundary (LLM outputs intents only, orchestrator executes) must be enforced structurally from the first line of orchestrator code — not retrofitted.

**Delivers:** LLM gateway with dual-model routing (GPT-4.1 for briefing generation, GPT-4.1 mini for voice turns), LangGraph agent orchestrator, intent classification (briefing / Q&A / action-request), session manager with in-session short-term memory (Redis).

**Addresses:** Follow-up question handling, multi-turn conversational context, LLM-powered briefing narrative generation

**Avoids:** LLM direct API access (LLM returns JSON intents only), single-model-for-all-tasks cost trap, context window overload (gateway enforces token budget)

**Research flag:** LangGraph 0.2+ human-in-the-loop interrupt pattern is well-documented. Standard patterns apply.

---

### Phase 4: Actions — Approval Gate, Executor, and Action Log

**Rationale:** Action drafting without an approval gate is explicitly unsafe. PITFALLS.md: action execution without approval is unrecoverable trust damage. The approval gate must be the default; there is no "add approval later." Action log must be append-only from day one — backfill is impossible.

**Delivers:** Approval gate with durable pending-action queue (PostgreSQL), voice confirm/reject flow, idempotency keying, action executor (email draft/send, calendar create, Slack DM), append-only action log table with full audit fields.

**Addresses:** Action drafting (email/message/calendar), approval flow, action log, write OAuth scopes (incremental auth — only requested when action layer activates)

**Avoids:** Action execution without approval record, audit log with UPDATE/DELETE permissions, write scopes requested before write features exist

**Research flag:** Standard patterns for approval queues and audit tables. No research phase needed.

---

### Phase 5: Voice Interface — STT, TTS, and Session Manager

**Rationale:** Voice layer is the topmost layer — depends on orchestrator (Phase 3) to consume/produce text. Building voice last ensures the upstream pipeline is solid before adding real-time latency pressure. Streaming TTS must be implemented correctly from the start (CRITICAL pitfall — not retrofittable without pipeline restructure).

**Delivers:** Deepgram Nova-3 WebSocket STT with VAD pre-filter and confidence threshold (Silero VAD recommended), Cartesia Sonic-3 streaming TTS (sentence-boundary buffering, target <300ms TTFA), barge-in/interruption detection (cancel active TTS on new speech), voice session manager (turn-taking, endpointing), FastAPI WebSocket endpoint for voice I/O.

**Addresses:** Voice output, voice input, interruption handling, low-latency response loop

**Avoids:** Late TTS streaming (stream from sentence boundary, not after full LLM response), STT treating background noise as commands (Silero VAD pre-filter + confidence threshold), no audio before LLM response complete

**Research flag:** VAD tuning for real-world noise conditions may need iteration. Deepgram and Cartesia streaming WebSocket integration patterns are well-documented, but end-to-end latency benchmarking (target <800ms) should be tested early.

---

### Phase 6: Personalisation — Long-Term Memory and User Profile

**Rationale:** Personalisation enhances everything but blocks nothing. Session memory (in-session Redis) ships in Phase 3. Cross-session memory ships here. mem0 + pgvector is the implementation path. Memory PII must be scoped and encrypted — schema design happens here, not as a retrofit.

**Delivers:** Cross-session memory extraction pipeline (end-of-session consolidation: skips, corrections, preferences → long-term Postgres/pgvector), user profile store (tone, briefing structure preferences), mem0 integration with pgvector backend, memory TTL enforcement and user-visible memory review stub (for M2 dashboard).

**Addresses:** Conversational memory across sessions, basic personalisation, signal capture (skips/corrections logged for M2 priority ranking)

**Avoids:** Memory PII without retention policy (all memory tables have TTL column at schema design), embeddings stored unencrypted, user unable to see/delete stored signals

**Research flag:** mem0 adoption maturity is MEDIUM confidence. Validate mem0 pgvector integration at Phase 6 start. If mem0 is insufficient, the custom extract-embed-retrieve pattern via pgvector directly is a documented fallback.

---

### Phase Ordering Rationale

- OAuth and schema come first because every other layer depends on authenticated data access and a correct data model. Fixing schema after data is written is expensive.
- Briefing pipeline precedes orchestrator because the orchestrator needs a cache to serve from. Building voice before the pipeline produces garbage output.
- The trust boundary (LLM as intent-only, orchestrator as executor) must be enforced in Phase 3 — it cannot be retrofitted in Phase 4 after action logic exists.
- Voice is last because real-time latency pressure before the pipeline is solid creates misattributed debugging. Latency problems in a broken pipeline look like voice problems.
- Personalisation is last because it enhances everything but blocks nothing, and requires signal data from M1 operation to be useful.

### Research Flags

Phases likely needing validation/research during planning:
- **Phase 2 (Briefing Pipeline):** APScheduler 4.x pre-release — verify stability before committing or pin 3.10.x
- **Phase 5 (Voice Interface):** End-to-end latency benchmarking under real-world noise conditions. Silero VAD tuning may require iteration.
- **Phase 6 (Personalisation):** mem0 pgvector integration maturity — MEDIUM confidence. Validate at phase start.

Phases with standard, well-documented patterns (no research phase needed):
- **Phase 1 (OAuth/Integrations):** Google, Microsoft, and Slack OAuth are fully documented with official Python SDKs
- **Phase 3 (Orchestrator):** LangGraph HITL interrupt pattern is well-documented
- **Phase 4 (Actions):** Approval queue + append-only audit log are standard patterns

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core stack (FastAPI, LangGraph, GPT-4.1, Deepgram, Cartesia) has official docs + recent engineering blog confirmation. Two gaps: APScheduler 4.x stability (pre-release) and mem0 adoption maturity (community signal). |
| Features | HIGH | Verified against ChatGPT Pulse, Google CC, Alfred_, Lindy competitor landscape. MVP scope is well-validated. Competitor gap (voice delivery with conversational follow-up) is confirmed. |
| Architecture | HIGH | Multiple authoritative 2025–2026 sources (Sierra AI, AssemblyAI, Calculus VC, arXiv). Plan-then-execute trust boundary is widely validated in production agent literature. |
| Pitfalls | HIGH | All critical pitfalls have multiple verified sources. EchoLeak CVE is real (CVSS 9.3). OWASP 2025 data on prompt injection is authoritative. Slack API rate limit changes (May 2025) are documented in official changelog. |

**Overall confidence:** HIGH

### Gaps to Address

- **APScheduler 4.x stability:** Pre-release as of 2025. At Phase 2 implementation start, check PyPI for stable release; if not available, pin 3.10.x `AsyncIOScheduler`. The API interface is similar enough that migration later is low-cost.
- **mem0 pgvector integration:** MEDIUM confidence. mem0 has strong GitHub adoption (~50K stars) but the pgvector backend integration is less documented than the Chroma/OpenAI path. At Phase 6 start, run a spike to validate the integration before committing to it as the memory layer.
- **Cartesia Sonic-3 concurrency:** Multiple concurrent TTS streams on a single WebSocket connection is documented but not stress-tested in research. Validate at Phase 5 that multi-stream behaviour meets requirements for concurrent sessions.
- **Slack internal app registration:** After May 2025, non-Marketplace apps are rate-limited to 1 req/min on `conversations.history`. Register dAIly as an internal app to get 50+ req/min. This must happen before Phase 2 Slack ingestion is tested.

---

## Sources

### Primary (HIGH confidence)
- [Deepgram Nova-3 pricing and Python SDK](https://deepgram.com/pricing) — STT latency benchmarks, pricing
- [Cartesia Sonic-3 docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest) — TTS TTFB, streaming WebSocket
- [OpenAI GPT-4.1 model comparison](https://platform.openai.com/docs/models/compare) — model selection rationale
- [LangGraph overview](https://www.langchain.com/langgraph) — HITL interrupt pattern
- [FastAPI discussion #9587 on python-jose](https://github.com/fastapi/fastapi/discussions/9587) — authlib over python-jose decision
- [Google OAuth 2.0 for Google APIs](https://developers.google.com/identity/protocols/oauth2) — March 2025 mandate, incremental auth
- [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — prompt injection #1, 73% prevalence
- [EchoLeak CVE-2025-32711](https://christian-schneider.net/blog/prompt-injection-agentic-amplification/) — CVSS 9.3, real-world exploit
- [Slack API Rate Limit Changes May 2025](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/) — Slack rate limit changes
- [The 2026 Voice AI Stack — Calculus VC](https://calculusvc.com/the-2026-voice-ai-stack-every-layer-explained/) — architecture layer breakdown
- [Engineering Low-Latency Voice Agents — Sierra AI](https://sierra.ai/blog/voice-latency) — production latency targets
- [Human-in-the-Loop Architecture — Agent Patterns](https://www.agentpatterns.tech/en/architecture/human-in-the-loop-architecture) — approval gate patterns

### Secondary (MEDIUM confidence)
- [mem0 GitHub (~50K stars)](https://github.com/mem0ai/mem0) — memory layer adoption signal
- [ZenML — LangGraph alternatives](https://www.zenml.io/blog/langgraph-alternatives) — LangGraph critique and trade-offs
- [OpenAI ChatGPT Pulse launch — TechCrunch](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/) — competitor feature analysis
- [Layercode — TTS Voice AI Model Guide 2025](https://layercode.com/blog/tts-voice-ai-model-guide) — TTS comparison
- [Deepgram — STT API comparison 2026](https://deepgram.com/learn/best-speech-to-text-apis-2026) — STT benchmarks (vendor-authored)
- [7 Voice AI Pitfalls Kill Enterprise Projects — Picovoice 2025](https://picovoice.ai/blog/voice-ai-projects-pitfalls/) — VAD, STT failure modes

### Tertiary (LOW confidence)
- None identified — all findings have medium or high source confidence

---
*Research completed: 2026-04-05*
*Ready for roadmap: yes*
