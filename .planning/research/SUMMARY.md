# dAIly v1.1 Intelligence Layer — Research Summary

**Synthesised:** 2026-04-15
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Executive Summary

v1.1 adds an intelligence layer on top of a solid v1.0 backend — cross-session memory, adaptive email ranking, user-controllable autonomy, and better conversational flow. The architecture research confirms all five feature areas can be built by modifying or extending existing files; only two new libraries are needed (`langmem`, `scikit-learn`). The dominant risk is build order: if FIX-01 (user_email bug in scheduler) is not fixed first, the adaptive ranker will train on poisoned data, and if INTEL-02 (memory) is not solid before MEM-01/02/03 (transparency), the trust features ship with nothing to show. The ACT-07 approval-gate change is the most security-critical item — it must be modelled as a graph topology change, not a node-level conditional.

---

## Stack Additions (v1.1 only)

| Package | Version | Purpose | Decision |
|---------|---------|---------|----------|
| `langmem` | `>=0.0.30` | Post-session fact extraction into `AsyncPostgresStore` | ADD — first-party LangChain tooling, zero new infra |
| `scikit-learn` | `>=1.4.0` | `SGDClassifier.partial_fit()` for adaptive email scoring | ADD — stable, no infra, right scale for single-user |
| `mem0ai` | — | Memory layer (was in v1.0 spec as placeholder) | REMOVE — never integrated, OSS pgvector instability, redundant with langmem + AsyncPostgresStore |

No other new dependencies. All other v1.1 features (memory transparency API, autonomy levels, conversational flow) are graph restructuring and model extension work on the existing stack.

**Compatibility check required:** Verify `langmem 0.0.30` pyproject.toml pins a `langgraph` range compatible with the installed `langgraph 1.1.6` before committing to lockfile.

---

## Feature Table Stakes vs Differentiators

### Adaptive Prioritisation (INTEL-01)

| Category | Features |
|----------|---------|
| Table stakes | Signal-weighted score adjustment, graceful cold-start fallback (heuristic floor), recency weighting on signals |
| Differentiators | Sender-level learned weights (per-sender score, not just global) |
| Defer | Keyword drift detection (high complexity, low ROI at weeks-of-data scale) |
| Anti-features | Full ML model (BPR, neural ranking) — too few training examples; separate recommender service — wrong scale |

### Cross-Session Memory (INTEL-02)

| Category | Features |
|----------|---------|
| Table stakes | Durable fact extraction, session-to-session preference continuity, explicit memory saves ("remember that...") |
| Differentiators | Proactive pattern detection, temporal relevance decay |
| Defer | Proactive fact extraction (adds per-session LLM cost — validate baseline first) |
| Anti-features | mem0 as drop-in, vector-only retrieval (SQL match is faster at <200 entries), raw transcript storage (SEC-04 violation) |

### Memory Transparency (MEM-01/02/03)

| Category | Features |
|----------|---------|
| Table stakes | "What do you know about me?" query (GDPR + trust baseline), delete specific entry, disable/reset all, verbal memory management |
| Differentiators | Confidence display (explicit vs inferred), memory audit trail (source session, date) |
| Anti-features | GUI dashboard (deferred to v2.0), granular per-field edits (delete-and-re-say pattern instead) |

### Trusted Actions (ACT-07)

| Category | Features |
|----------|---------|
| Table stakes | Three-tier model (suggest / approve / auto), per-action-type config, explicit opt-in required for auto |
| Differentiators | Auto-summary in morning briefing, velocity limit on auto tier (Redis counter, daily TTL) |
| Anti-features | High-impact actions (send email, create external invite) in auto tier, ML-driven silent tier promotion |

### Conversational Flow (CONV-01/02/03)

| Category | Features |
|----------|---------|
| Table stakes | Mid-briefing interruption with resume (section-level cursor), mode switching without re-triggering briefing, context handoff between modes |
| Differentiators | Adaptive verbosity on re-listen (compress second time), proactive action offer post-section, time-of-day tone |
| Anti-features | Real-time voice sentiment analysis, full NLP formality classifier, re-synthesising full briefing TTS on resume |

---

## Recommended Build Order

| Phase | Focus | Rationale | Key Constraint |
|-------|-------|-----------|----------------|
| 1 | FIX-01, FIX-02, FIX-03 | Unblocks everything — corrupt signals poison INTEL-01 training data | Hard sequencing dependency; do not start INTEL-01 until FIX-01 is deployed |
| 2 | INTEL-01 + DB migration (`add_user_memories`) | Highest daily visible impact; pure logic change; migration runs in parallel with no code dependency | Needs clean signal data from Phase 1; `user_memories` table required before Phase 3/4 |
| 3 | INTEL-02 (memory extraction + retrieval) | Highest complexity; establishes the memory store all transparency features depend on | `user_memories` migration must exist; use `user_id` not `thread_id` for namespace keying |
| 4 | MEM-01/02/03 (memory transparency API) | Near-trivial given Phase 3; required to make INTEL-02 trustworthy to the user | Needs populated memory table; CASCADE DELETE on embedding FK before this ships |
| 5 | ACT-07 (trusted actions) | Small code delta on approval flow; high trust-building value | Model as graph topology change (autonomy_router conditional edge), not in-node conditional |
| 6 | CONV-01/02/03 (conversational flow) | Polish layer; safest last given it touches graph.py and state.py | Append-only SessionState fields only; verify barge-in during TTS streaming before calling done |

---

## Top 5 Pitfalls

**1. FIX-01 must precede INTEL-01 — no exceptions (CRITICAL)**
`user_email=""` in scheduler means WEIGHT_DIRECT never fires during scheduled runs. The adaptive ranker will train on systematically wrong scores. Fixing it later does not retroactively clean the training data. This is a hard ordering dependency.

**2. Approval gate bypass must be a graph topology change (CRITICAL)**
Adding autonomy levels via an in-node conditional on `interrupt()` causes the graph to reach `execute_node` with `approval_decision = None`, silently auto-approving or crashing. Model it as an `autonomy_router` conditional edge before `approval_node`. Add a `RuntimeError` assertion at the top of `execute_node` as a safety net.

**3. Memory extraction feedback loop produces junk (HIGH)**
Running extraction on every message (including recalled memories injected back into context) creates a hallucination loop. One production audit found 97.8% of entries were junk after 32 days. Trigger extraction only on explicit signal events (correction, re_request, expand). Confidence threshold > 0.8 before storing. Mark injected recalled context clearly so the extraction pass can filter it.

**4. Thread ID != User ID for cross-session memory (HIGH)**
`thread_id` scopes a single conversation session — a user accumulates dozens across weeks. Memory namespaced under `thread_id` is invisible to every subsequent session. Always scope memory operations with `user_id` (available as `SessionState.active_user_id`). Write a two-session test for this on day one.

**5. SessionState schema changes corrupt active checkpoints (HIGH)**
Adding new fields to `SessionState` while a session is interrupted at `approval_node` causes deserialization failures when the checkpoint is resumed. Rule: only add fields with `Field(default=...)`, never rename or remove. Test `graph.aget_state()` against a pre-existing checkpoint before deploying any `state.py` change.

---

## Open Questions — Decisions Needed Before/During Planning

| # | Question | Why It Matters | Suggested Default |
|---|---------|----------------|-------------------|
| Q1 | What is the cold-start blend ratio alpha for INTEL-01? | Controls how fast the learned scorer takes over from heuristics — too aggressive = early overfitting on <30 signals | alpha = 0.2 learned / 0.8 heuristic until 30+ days of signals; increase linearly to 0.8/0.2 at 90 days |
| Q2 | What action types are eligible for `auto` tier in ACT-07 v1.1? | Needs an explicit whitelist before any `auto` code ships; otherwise scope creep into high-impact actions | Whitelist: `add_personal_reminder`, `create_draft` only; `send_email`, `create_calendar_invite` locked to `approve` always |
| Q3 | Should memory extraction be session-end only, or also run as part of the nightly briefing pipeline? | Session-end = fresher facts; nightly = batch efficiency. Nightly risks blocking APScheduler briefing job if not isolated | Session-end via `asyncio.create_task` (fire-and-forget); separate from nightly briefing cron |
| Q4 | What is the max memory entries cap per user? | Unbounded growth degrades retrieval quality and transparency UX | Cap at 200 active entries; deduplication/consolidation pass when threshold reached |
| Q5 | Is `langmem 0.0.30` version range compatible with `langgraph 1.1.6`? | Must verify before committing to lockfile; pre-v1.0 package API could change | Run `uv add langmem` and inspect resolver output before Phase 3 starts |

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Stack additions | MEDIUM-HIGH | langmem is official LangChain tooling, pre-v1.0 API surface is the main uncertainty; scikit-learn is HIGH |
| Feature scope | HIGH | Based on direct codebase inspection + industry reference patterns (ChatGPT memory, CSA autonomy framework) |
| Architecture / integration points | HIGH | Research was based on direct code inspection of the v1.0 codebase |
| Pitfalls | HIGH (critical 4) / MEDIUM (others) | Critical pitfalls confirmed via LangGraph GitHub issues and production audit data |
| Build order | HIGH | Dependency graph is clear and verified against codebase |

**Main gap:** The correct blend ratio alpha and signal volume thresholds for INTEL-01 are inferred from recommender systems literature, not empirical dAIly data. Start conservative (alpha = 0.2) and adjust after 30 days of real signal data.
