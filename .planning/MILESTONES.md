# Milestones

## v1.0 MVP (Shipped: 2026-04-14)

**Phases:** 1–6 | **Plans:** 22 | **Timeline:** 2026-04-05 → 2026-04-14 (10 days)
**Codebase:** 7,049 Python LOC across 447 files

**Key accomplishments:**

1. Multi-source OAuth integrations — Gmail, Google Calendar, Outlook/Teams (Microsoft Graph), and Slack connected via AES-256-GCM encrypted token vault; proactive background token refresh
2. Precomputed morning briefing pipeline — heuristic email ranking, redaction/summarisation layer, LLM narration (GPT-4.1), APScheduler cron, Redis cache for sub-1s delivery
3. Conversational LangGraph orchestrator — dual-model routing, session-stateful follow-ups, thread summarisation on demand, SEC-05 intent-only LLM outputs
4. Approval-gated action layer — email/Slack/calendar drafting via LLM, human-in-the-loop approval gate, append-only action log with full audit trail
5. Full voice session loop — Cartesia Sonic-3 TTS streaming + Deepgram Nova-3 STT + asyncio barge-in detection + AsyncPostgresSaver session persistence
6. User preferences wired end-to-end — tone/length/category_order stored in profile, loaded by scheduler at briefing time, injected into narrator system prompt for every scheduled run

**Requirements satisfied:** 31/31 v1 requirements

**Tech debt carried to v1.1:**
- `user_email=""` in scheduler — WEIGHT_DIRECT scoring path never fires for scheduled runs
- Slack pagination is single-page only (multi-workspace TODO in place)
- `message_id = last_content` stub in summarise_thread_node (approximate, functional)
- `known_channels=set()` in SlackExecutor — channel whitelist validation deferred

**Archive:** `.planning/milestones/v1.0-ROADMAP.md`, `.planning/milestones/v1.0-REQUIREMENTS.md`

---

## v1.1 Intelligence Layer (Shipped: 2026-04-18)

**Phases:** 7–12 | **Plans:** 17 | **Timeline:** 2026-04-14 → 2026-04-18 (4 days)

**Key accomplishments:**

1. Tech debt closed — RFC 2822 address normalisation (WEIGHT_DIRECT path now fires), Slack cursor-based pagination, real message ID extraction in summarise_thread_node
2. Adaptive ranking replaces heuristics — pgvector-backed signal decay with tanh scoring; sender multipliers personalise briefing order over time
3. Cross-session memory persists context across days — mem0 + pgvector HNSW-indexed 1536-dim embeddings; profile extraction fires on session end
4. Voice-driven memory audit and control — `list_all_memories`, `delete_memory_fact`, `clear_all_memories` helpers + `memory_node` wired into orchestrator graph
5. CLI autonomy configuration — `suggest-only`, `approve-per-action`, `trusted-auto` levels; `BLOCKED_ACTION_TYPES` enforced at code level
6. Briefing supports natural mid-session interruption — sentence-level cursor tracking, resume after barge-in, tone compression adaptation (CONV-01/02/03)

**Archive:** `.planning/milestones/v1.1-ROADMAP.md`, `.planning/milestones/v1.1-REQUIREMENTS.md`

---

## v1.2 Deployability Layer (Shipped: 2026-04-20)

**Phases:** 13–16 | **Plans:** 9 | **Timeline:** 2026-04-18 → 2026-04-20 (2 days)
**Files changed:** 62 (+7,604 / -118 lines)

**Key accomplishments:**

1. Adaptive ranker learns from all three signal types — skip, re_request, and expand — with tanh-centred decay scoring; `BriefingItem` model + Redis item cache enables per-item signal attribution
2. Voice loop tracks item cursor and auto-captures implicit skip signals on silence/barge-in detection
3. Structured JSON logging via stdlib (`JSONFormatter` + `ContextAdapter`) routes all hot-path modules without modification
4. Multi-stage Dockerfile with Alembic auto-migrations and health-checked docker-compose stack (app + Postgres + Redis)
5. All v1.2 tech debt closed — `make_logger` adopted across codebase, VALIDATION.md files compliant

**Archive:** `.planning/milestones/v1.2-ROADMAP.md`, `.planning/milestones/v1.2-REQUIREMENTS.md`

---

## v1.3 Voice Polish (Shipped: 2026-04-28)

**Phases:** 17 | **Plans:** 4 | **Timeline:** 2026-04-25 → 2026-04-28 (3 days)

**Key accomplishments:**

1. Graceful TTS fade-out — completes current audio chunk before stopping on barge-in; no more mid-word cutoffs
2. Mic-mute echo suppression — mic feeds silent chunks to Deepgram during TTS playback (500ms), eliminating TTS bleed-into-STT
3. Barge-in safety window — 600ms asyncio timer before committing an interrupt; accidental sounds don't kill TTS
4. Backchannel detection — "yeah", "right", "got it", "mmhm" etc. swallowed without stopping TTS; user can affirm without disrupting briefing
5. Streaming LLM→TTS bridge — sentence-boundary chunking sends tokens to Cartesia as they arrive; first spoken word noticeably earlier

**Structural decision:** macOS AEC (echo on built-in speakers) is unsolvable in software — closed as won't-fix. The mobile architecture solves it at the OS level via AVAudioEngine/Oboe. Desktop becomes secondary platform.

---

## v2.0 Mobile Voice (Planned)

**Phases:** 18–21 | **Estimated timeline:** 4–6 weeks

**Goal:** Move voice I/O to native mobile clients with OS-level hardware echo cancellation. Python backend becomes orchestration-only. LiveKit handles WebRTC transport, ML-based barge-in, and turn detection — eliminating `barge_in.py`, `stt.py`, `tts.py`, and `loop.py` from the critical path.

**Architecture:**
```
Mobile client (iOS/Android)
  → mic (hardware AEC via AVAudioEngine/Oboe)
  → LiveKit room (WebRTC)
  → LiveKit Agent (Python)
      → livekit-plugins-langchain
          → LangGraph orchestrator (unchanged)
              → GPT-4.1 mini / GPT-4.1
  → Deepgram STT plugin (LiveKit built-in)
  → Cartesia TTS plugin (LiveKit built-in)
  → audio playback on device
```

**Why native over cross-platform (Flutter/RN):** Voice quality is the core product differentiator. Cross-platform audio layers add sample rate and session routing edge cases unacceptable for a voice-first product. Native gives direct AVAudioEngine/AUVoiceIO (iOS) and Oboe (Android) access.

**Tier structure:**
- Pro (~$15/mo): voice briefing read-back — current Cartesia TTS pipeline (works reliably)
- Premium (~$30–35/mo): full conversational voice — LiveKit + mobile native AEC

**Target:** Sub-800ms conversational latency on mobile; barge-in reliable without headphones.

**Planned phases:**
- Phase 18: LiveKit Backend Integration
- Phase 19: Native iOS App
- Phase 20: Native Android App
- Phase 21: Desktop Web Fallback

---

## v2.1 Ecosystem Expansion (Planned)

**Phases:** 22–25 | **Estimated timeline:** 6–8 weeks

**Goal:** Extend the briefing's data surface beyond email/calendar/Slack. Each phase adds a thematic pack of integrations with briefing synthesis and action support.

**Planned phases:**
- Phase 22: Developer Pack (GitHub, Linear, Hacker News)
- Phase 23: Knowledge Pack (Notion, Google Maps Routes)
- Phase 24: Operator Pack (WhatsApp Business, PagerDuty, Vercel)
- Phase 25: Finance Pack (Stripe, Brex/Mercury)

See `integrations-roadmap.md` for full integration analysis and prioritisation.
