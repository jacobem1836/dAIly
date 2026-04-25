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
