# Feature Landscape: dAIly v1.1 Intelligence Layer

**Domain:** Voice-first AI daily briefing assistant — intelligence, memory, and autonomy features
**Researched:** 2026-04-15
**Confidence:** MEDIUM-HIGH (industry patterns verified; small-dataset learning specifics rely on inference from recommendation systems literature)

---

## Category 1: Adaptive Prioritisation (INTEL-01)

**What it is:** Replace static heuristic weights (WEIGHT_DIRECT=10, WEIGHT_CC=2, etc.) with a scoring system that shifts based on stored interaction signals (PERS-02 data: skips, re-requests, corrections).

### Table Stakes

| Feature | Why Expected | Complexity | v1.0 Dependency |
|---------|--------------|------------|-----------------|
| Signal-weighted score adjustment | Any "smart" inbox does this (Gmail, Outlook both do it); absence means the heuristics never improve no matter how much the user interacts | Medium | PERS-02 signal store, FIX-01 (user_email bug must be fixed first — WEIGHT_DIRECT path is dead without it) |
| Graceful cold-start fallback | System has weeks of data at best; must not regress from heuristics when signal count is low | Low | PERS-03 heuristic defaults |
| Recency weighting on signals | A skip from 3 weeks ago is less meaningful than one from yesterday | Low | SignalLog timestamps |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Sender-level learned weight | Learns that replies from "boss@company.com" are always acted on, so they get boosted beyond the direct-recipient heuristic | Medium | Requires per-sender score store, not just global weight adjustments |
| Keyword drift detection | Adapts when a new project introduces new deadline-adjacent terms the heuristic doesn't know | High | Probably out of scope v1.1; flag for v2.0 |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Full ML model (BPR, matrix factorisation, neural ranking) | Requires hundreds of positive/negative pairs minimum; weeks of data yields ~20-50 training examples — model will overfit or be worse than heuristics | Weighted score adjustment: multiply existing heuristic weights by a learned multiplier per signal type, updated via simple EWM (exponentially weighted mean) or Bayesian update on the existing score fields |
| Separate recommender service | Infrastructure overhead with no benefit at single-user, ~100 items/day scale | Extend `ranker.py` with a `learned_multipliers` dict loaded from DB at pipeline start |
| A/B testing framework | Single user — meaningless | N/A |
| Cold-start ML model with no fallback | No fallback path if signal count is below threshold | Always blend: `final_score = alpha * heuristic_score + (1 - alpha) * learned_score` where alpha starts at 1.0 and decreases as signal count grows |

### Complexity Assessment

**Low-to-Medium.** The right approach is a score-multiplier table per signal type, stored in Postgres, updated incrementally as signals arrive. This is a week of work, not a research project. The main dependency is FIX-01 — WEIGHT_DIRECT scoring is currently broken because `user_email=""` in the scheduler, making the "direct email" signal never fire. Fix that first or the learned weights will train on biased data.

**Recommended approach:** Extend `ranker.py`. Add a `signal_weights` table: `(signal_type, sender_domain, adjustment_factor)`. On each signal event, do a small update (e.g., EWM with alpha=0.1). At briefing time, load the table and apply multipliers to the heuristic weights. Blended score ensures heuristics dominate at cold start.

---

## Category 2: Cross-Session Memory (INTEL-02)

**What it is:** Persist a user profile — preferences, facts, patterns — across days. The existing `AsyncPostgresSaver` handles single-session context only; it does not extract durable facts.

### Table Stakes

| Feature | Why Expected | Complexity | v1.0 Dependency |
|---------|--------------|------------|-----------------|
| Durable fact extraction | Users expect the assistant to remember "I have a board meeting every Monday at 9am" without being told again | Medium | pgvector already in stack; profile service exists |
| Session-to-session preference continuity | If the user said "be more concise" two days ago, it should still apply | Low | UserPreferences model in profile/models.py |
| Explicit memory saves ("remember that...") | Industry table stakes since ChatGPT memory launched (2024); users expect to be able to explicitly teach the system | Low | LangGraph intent routing |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Proactive fact extraction | System notices recurring patterns (same person cc'd on all important emails) and surfaces them without being asked | High | Requires extraction prompt run over conversation history; adds LLM cost per session |
| Temporal relevance decay | Facts about "Q1 project" become less relevant after Q2 starts | Medium | Timestamp + relevance score on memory entries |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| mem0 library as drop-in | mem0 is excellent for multi-user SaaS; for a single-user personal assistant with tight control requirements, it adds an abstraction layer over a pgvector schema you already own, and its extraction prompts are not tuned for a briefing domain | Store facts as structured rows in a `user_memory` table: `(id, user_id, fact_text, embedding vector(1536), source, created_at, last_recalled_at, confidence)`. Run extraction via a post-session LLM call with a targeted prompt. |
| Vector-only memory (semantic search as sole retrieval) | Short fact lists (<200 items for weeks of data) don't need approximate nearest-neighbour search. Direct SQL `LIKE` or exact match is faster and more reliable at this scale | Add pgvector embedding for future scalability, but use SQL exact/prefix match as primary retrieval for now |
| Full episodic transcript storage | Violates SEC-04 (raw content not stored long-term) | Store summaries and extracted facts only |

### Complexity Assessment

**Medium.** The pgvector extension is already deployed. The main work is: (1) a `user_memory` table schema, (2) a post-session extraction prompt (run once after each voice session ends), (3) a pre-session retrieval that injects top-N relevant memories into the briefing context. The LangGraph session already has a clear entry/exit point in `graph.py` — hook in at session end.

**Recommended approach:** Add a `memory_service.py` in a new `src/daily/memory/` module. Post-session: run extraction LLM call, upsert facts into `user_memory`. Pre-briefing: retrieve top-10 semantically relevant facts and inject into `context_builder.py`'s prompt context. Keep extraction call cheap — use GPT-4.1 mini, not GPT-4.1.

---

## Category 3: Memory Transparency (MEM-01, MEM-02, MEM-03)

**What it is:** User can ask "what do you know about me?", edit or delete specific entries, and disable or reset learning entirely.

### Table Stakes

| Feature | Why Expected | Complexity | v1.0 Dependency |
|---------|--------------|------------|-----------------|
| "What do you know about me?" query | ChatGPT memory launched this as the reference pattern in 2024; any memory-having assistant without it feels opaque and untrustworthy (CMU CyLab research: transparency improves trust by 40%) | Low | INTEL-02 memory table must exist first |
| Delete specific memory entry | GDPR Article 17 (right to erasure) is legally required in EU; even outside EU it's a basic trust feature | Low | MEM-01 must exist |
| Disable learning / reset all | Users need an escape hatch; without it, a bad extraction snowballs | Low | MEM-01, MEM-02 |
| Verbal memory management ("forget that I said...") | Voice-first interface means keyboard memory management menus are out; must be voice-accessible | Medium | LangGraph intent routing + new intent class |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Memory confidence display ("I'm fairly sure you prefer...") | Distinguishes between a fact told explicitly vs inferred — helps user evaluate what to correct | Low | Add `confidence` enum (explicit / inferred) to memory table |
| Memory audit trail (how was this learned?) | Shows source session, date, and trigger for each fact | Low-Medium | Store `source_session_id` and `created_at` in memory table; expose on query |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| GUI/web dashboard for memory management | No UI in v1.x scope; PROJECT.md explicitly defers dashboard to v2.0 | All memory management via voice commands and CLI `daily memory` subcommand |
| Granular per-field edit (edit just the date in a fact) | Extremely complex NLP; high error rate. The ChatGPT team explicitly doesn't support this — users must delete and re-state | Delete-and-re-say pattern: "Forget that I have a 9am Monday meeting. I actually have it at 10am." |
| Automatic memory export to third-party services | Scope creep; not in v1.1 target | N/A |

### Complexity Assessment

**Low, given INTEL-02 is implemented first.** Memory transparency is almost entirely UI/intent work on top of the memory table. The hard part is INTEL-02 (building the memory store). MEM-01/02/03 are retrieval + delete operations plus new LangGraph intent routing. The only non-trivial part is building the voice UX so "what do you know?" produces a scannable verbal response (not a 20-item list read aloud).

**Recommended approach:** Limit "what do you know?" to top-10 most recently recalled or highest-confidence facts, grouped by category (preferences, recurring patterns, people). Voice response: "I remember 8 things about you. Want me to go through them?" — then step through with user confirmation to keep, edit, or delete each one.

---

## Category 4: Trusted Actions (ACT-07)

**What it is:** User configures autonomy levels: suggest-only (no action taken), approve-per-action (existing v1.0 behaviour), or trusted-auto (auto-execute for pre-approved action types).

### Table Stakes

| Feature | Why Expected | Complexity | v1.0 Dependency |
|---------|--------------|------------|-----------------|
| Three-tier model (suggest / approve / auto) | Industry standard for agentic AI (Anthropic, CSA, and five-level frameworks all converge on graduated autonomy; 85% of enterprise AI is semi-autonomous as of early 2025) | Low-Medium | LangGraph `interrupt()` already in place in `graph.py`; need to make it conditional |
| Per-action-type configuration | User may trust "create calendar event" but not "send email" for auto | Low | ActionLog already has `action_type`; add `autonomy_level` per type to user preferences |
| Explicit opt-in required for auto | PROJECT.md constraint: "Trusted-auto level requires explicit user opt-in; high-impact actions always surface for approval at default level" | Low | Logic change in `route_after_approval` node |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Auto-approval summary in morning briefing ("I automatically did 3 things overnight...") | Keeps user informed without requiring approval; builds trust in the auto tier | Low | Aggregate auto-actioned items into briefing preamble |
| Velocity limit on auto tier (max N auto-actions per day) | Safety rail that prevents runaway auto-execution if the system misclassifies intent | Low | Counter in Redis with daily TTL |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Full bypass path for high-impact actions (send email to new recipient, delete calendar event) | PROJECT.md explicitly out of scope for v1.1; also a trust-destroying failure mode if the system misclassifies | Keep high-impact actions in approve tier always; only low-impact (create draft, add personal reminder) eligible for auto |
| Trust transfer between action types | If user trusts "add calendar event," do not infer they trust "send calendar invite to external contacts" | Each action type is independently configured |
| ML-driven auto-tier promotion (automatically promoting based on approval patterns) | Can silently expand permissions; must be explicit | Only manual opt-in; patterns can surface a suggestion ("You've approved all calendar creates this week — want to auto them?") but never promote silently |

### Complexity Assessment

**Low-Medium.** The LangGraph interrupt mechanism is already in `graph.py`. The change is: before calling `interrupt()`, check the user's `autonomy_level` for this action type. If `auto`, skip the interrupt and execute. Add `autonomy_settings` JSONB column to `user_preferences` table. The main design question is the UX for configuring it — voice command or `daily config` CLI.

**Recommended approach:** Extend `UserPreferences` model with `autonomy_settings: dict[str, str]` (action_type -> 'suggest'|'approve'|'auto'). Default all to 'approve' (v1.0 behaviour preserved with no regression). Modify `route_after_approval` to check this before raising the interrupt. Add `daily config autonomy set calendar_event auto` CLI command.

---

## Category 5: Conversational Flow (CONV-01, CONV-02, CONV-03)

**What it is:** Natural interruption mid-briefing, fluid switching between briefing / discussion / action modes, and adaptive tone/verbosity.

### Table Stakes

| Feature | Why Expected | Complexity | v1.0 Dependency |
|---------|--------------|------------|-----------------|
| Graceful mid-briefing interruption with resume | v1.0 has barge-in via VAD stop_event (VOICE-04), but the state machine doesn't handle "resume briefing from where I left off" — users expect this from any modern voice assistant | Medium | VOICE-04 barge-in, LangGraph session state (need to store briefing position) |
| Mode switching without re-triggering briefing | User asks a follow-up question mid-briefing and then says "ok, continue" — system should resume without replaying already-heard content | Medium | Briefing position tracking (cursor into precomputed sections) |
| Context handoff between modes | If user interrupts to say "reply to that email from Sarah" — system should know which email was being read at the time of interruption | Medium | Briefing position + section metadata in session state |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Adaptive verbosity on re-listen (compress second time) | If user asks to re-hear a section, deliver a shorter version the second time | Medium | Requires re-render with compression instruction; adds one LLM call |
| Proactive action offer ("Want to reply to that?") | After reading a high-priority email, system offers the action rather than waiting | Low | Post-section check against action type whitelist; gated on user preference |
| Time-of-day tone adaptation | More structured early morning; more casual during follow-ups later in the day | Low | Time-aware modifier on system prompt |

### Anti-Features (CONV-03 — Adaptive Tone)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time sentiment analysis of user's voice | Adds latency and complexity; high error rate; invasive at personal assistant scale | Use explicit signals: user sets preferred tone in `daily config`; system detects implicit signals from session length and interruption frequency |
| Full NLP formality classifier on user speech | Overkill; takes weeks to train well on one user's data | Heuristic: if user's questions are short and direct, match with brief responses; if elaborate, match with more detail. GPT-4.1 mini handles this well with a simple system prompt instruction ("match the user's verbosity level") |
| Emotion detection | Out of scope, invasive, unreliable | N/A |
| Re-synthesising the full briefing TTS from scratch on resume | Huge latency spike (full Cartesia render) on every resume | Track section cursor; only re-render from the interrupted section forward |

### Complexity Assessment

**Medium overall, with variance by sub-feature:**

- **CONV-01 (mid-session interruption resume):** Medium. Need to add a `briefing_cursor` field to session state tracking which section was being delivered when interrupted. The section list is already computed in the cached briefing — just need to track the index. The tricky part is the audio cursor (which sentence within a section). Simplification: track at section level, not sentence level.

- **CONV-02 (fluid mode switching):** Medium. LangGraph's `route_intent` already handles switching. The gap is that after an action-mode interaction, there's no "resume briefing" intent. Add it to the intent classifier and restore from `briefing_cursor`.

- **CONV-03 (adaptive tone):** Low. Already partially implemented via the existing `tone` preference field. Extension: add a dynamic modifier in the briefing narrator that adjusts based on session context signals (number of interruptions this session = user in a hurry = compress output).

---

## Feature Dependencies (Build Order)

```
FIX-01 (user_email bug in scheduler)
  └── INTEL-01 (adaptive prioritisation — heuristic inputs must be correct first)

INTEL-02 (cross-session memory — memory table + extraction pipeline)
  ├── MEM-01 (inspect memory — reads from memory table)
  ├── MEM-02 (edit/delete memory — writes to memory table)
  └── MEM-03 (disable/reset — clears memory table)

LangGraph graph.py (route_intent, route_after_approval already exist in v1.0)
  ├── ACT-07 (trusted actions — conditional interrupt based on autonomy_settings)
  └── CONV-02 (mode switching — new 'resume_briefing' intent + cursor restore)

CONV-01 (briefing cursor tracking in session state)
  └── CONV-02 (mode switching resumes from cursor — depends on cursor existing)

CONV-03 (adaptive tone) — independent, lowest dependency
```

---

## MVP Recommendation for v1.1

**Ship in this order:**

1. **FIX-01, FIX-02, FIX-03** — Tech debt. FIX-01 is a blocker for INTEL-01 correctness (the entire WEIGHT_DIRECT signal path is dead without it). FIX-02 and FIX-03 are data quality fixes that improve signal reliability for all downstream features.

2. **INTEL-01 (adaptive prioritisation)** — Highest visible daily impact. User sees briefing improve each morning. Low risk (blended score falls back to heuristics). Does not require the memory system — they are orthogonal.

3. **INTEL-02 + MEM-01/02/03 (memory system + transparency)** — Build together as one phase since MEM-01/02/03 are nearly trivial given INTEL-02, and MEM-01/02/03 are needed to make INTEL-02 trustworthy from a user perspective.

4. **ACT-07 (trusted actions)** — Small code delta on existing approval flow. High trust-building value. Can ship before conversational flow work.

5. **CONV-01/02/03 (conversational flow)** — Polish layer. Table-stakes for voice-first but the most fiddly to get right; better after memory and autonomy are stable.

**Defer:**
- Proactive fact extraction (INTEL-02 differentiator) — adds per-session LLM cost; defer to v1.2 after baseline memory is validated
- Adaptive verbosity on re-listen (CONV differentiator) — extra LLM call per re-request; defer to v1.2
- Velocity limits on auto tier — add in v1.2 once auto-tier usage patterns are observable
- Keyword drift detection (INTEL-01 differentiator) — High complexity, Low ROI at weeks-of-data scale

---

## Phase-Specific Complexity Flags

| Phase Topic | Complexity Note | Key Risk |
|-------------|----------------|----------|
| Adaptive prioritisation | Low-Medium once FIX-01 done | Risk of over-tuning on <30 signal samples; blend ratio (alpha) should start at 0.8 heuristic weight — be conservative |
| Memory extraction | Medium | GPT-4.1 mini extraction prompts need careful design — risk of extracting incorrect or overly broad facts that then pollute future sessions |
| Memory transparency voice UX | Low-Medium | Presenting a list of facts verbally is hard to make non-annoying; cap to 10 items, paginate with user confirmation |
| Trusted auto-tier | Low | Risk is scope creep into full-bypass; keep high-impact actions (send email, create external calendar invite) always in 'approve' regardless of tier setting |
| Briefing cursor / mode switching | Medium | Audio cursor granularity (section vs sentence); recommend section-level only for v1.1 |
| Adaptive tone | Low | Already partially working via tone preference field; incremental extension via system prompt modifier |

---

## Sources

- OpenAI Memory FAQ: https://help.openai.com/en/articles/8590148-memory-faq — HIGH confidence (production reference for memory transparency UX patterns, ChatGPT's "What do you know about me?" interface)
- LangGraph human-in-the-loop docs: https://docs.langchain.com/oss/python/langchain/human-in-the-loop — HIGH confidence (official; interrupt() pattern is the v1.0 mechanism)
- CSA Agentic Trust Framework (autonomy levels): https://cloudsecurityalliance.org/blog/2026/01/28/levels-of-autonomy — MEDIUM confidence (industry framework, not implementation guide)
- Anthropic agent autonomy measurement: https://www.anthropic.com/research/measuring-agent-autonomy — MEDIUM confidence (research framing for graduated autonomy tiers)
- DigitalOcean LangGraph + Mem0 integration: https://www.digitalocean.com/community/tutorials/langgraph-mem0-integration-long-term-ai-memory — MEDIUM confidence (tutorial pattern for post-session memory extraction)
- Mem0 pgvector backend docs: https://docs.mem0.ai/components/vectordbs/dbs/pgvector — HIGH confidence (official docs confirming pgvector is supported backend)
- Barge-in handling guide: https://sparkco.ai/blog/optimizing-voice-agent-barge-in-detection-for-2025 — MEDIUM confidence (production patterns for VAD + state machine coordination)
- BPR from implicit feedback: https://arxiv.org/pdf/1205.2618 — HIGH confidence (foundational paper; approach is overkill for dAIly scale, which informs the EWM multiplier recommendation instead)
- Gmail AI prioritisation signals: https://www.getmailbird.com/gmail-ai-inbox-categorization-guide/ — LOW confidence (third-party summary of Gmail behaviour)
- GDPR AI agent compliance architecture: https://tianpan.co/blog/2026-04-10-gdpr-ai-agents-compliance-architecture — MEDIUM confidence (recent post, detailed on multi-layer deletion requirements)
