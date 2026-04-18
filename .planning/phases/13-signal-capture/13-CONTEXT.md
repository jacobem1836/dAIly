# Phase 13: Signal Capture - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire skip and re_request signals end-to-end into the adaptive ranker. The signal schema already exists; the adaptive ranker hook already exists. This phase fills the gaps: item tracking so signals carry a target_id, skip/re_request firing in the voice loop and orchestrator, and the adaptive_ranker.py scoring implementation.

Signals only influence the next briefing's ranking — no real-time re-scoring within the current session.

</domain>

<decisions>
## Implementation Decisions

### Skip Signal Trigger
- **D-01:** Both explicit and implicit skip triggers are supported.
  - Explicit: "skip", "next", "move on" → new `skip` intent route in the orchestrator graph, fires `SignalType.skip` with the current item's `target_id`
  - Implicit: barge-in detected + silence > 2s → voice loop fires an implicit skip signal inline (no orchestrator round-trip needed)

### Item Tracking
- **D-02:** At briefing precompute time, store a structured item list in Redis alongside the narrative. Format: `[{item_id, type, target_id, sentence_range_start, sentence_range_end}]`. Redis key suffix: `_items` (e.g. `briefing:{user_id}_items`).
- **D-03:** At voice session start, load the item list from Redis into `SessionState`. Add `current_item_index: int = 0` and `briefing_items: list[BriefingItem] = []` to `SessionState`. The sentence delivery loop increments `current_item_index` as `sentence_cursor` crosses each item's `sentence_range_end`.

### Re-request Handling
- **D-04:** "Repeat that" / "say that again" → new `re_request_node` in the orchestrator graph (mirrors the `expand`/`summarise_thread_node` pattern). The node re-speaks the current briefing item's sentences and fires `SignalType.re_request` with the item's `target_id`.

### Adaptive Ranker — Decay Formula
- **D-05:** Implement `adaptive_ranker.py` with exponential time-decay scoring:
  - `weight = signal_weight * (0.95 ** days_old)` where `days_old = (now - created_at).days`
  - Signal weights: skip = −1.0, re_request = +1.0, expand = +0.5
  - Time window: 30 days — signals older than 30 days excluded from query
  - Aggregate per sender (lowercase stripped): `sender_score = sum(weights)`
  - Sigmoid to multiplier range [0.5, 2.0]: `multiplier = 0.5 + 1.5 / (1 + exp(-sender_score / 3.0))`
  - Neutral sender (no signals) → multiplier ≈ 1.0 (sigmoid midpoint at score=0)
- **D-06:** `get_sender_multipliers(user_id, db_session) → dict[str, float]` — returns sender→multiplier map. Called from `context_builder.py` (hook already wired). Only senders with at least one signal in the window are included; missing senders get 1.0 at call site.

### Claude's Discretion
- Exact `BriefingItem` Pydantic model shape (as long as it carries `item_id`, `type`, `target_id`, `sentence_range_start`, `sentence_range_end`)
- Redis serialization format for the item list (JSON)
- Whether implicit skip uses a 2s silence threshold or a different value
- Whether `skip_node` re-advances the briefing (skips to next item) or just fires the signal and resumes normal flow

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — SIG-01, SIG-02, SIG-03 definitions (signal capture + ranker integration)

### Signal infrastructure
- `src/daily/profile/signals.py` — `SignalLog` table, `SignalType` enum (skip/re_request/expand/follow_up/correction), `append_signal()` helper
- `src/daily/orchestrator/nodes.py` — `_capture_signal()` fire-and-forget pattern; existing `respond_node` and `summarise_thread_node` as pattern references for new nodes

### Briefing pipeline (item tracking changes)
- `src/daily/briefing/pipeline.py` — end-to-end precompute pipeline; item list must be written to Redis here
- `src/daily/briefing/context_builder.py` — calls `get_sender_multipliers()` (hook already wired at line ~181)
- `src/daily/briefing/ranker.py` — heuristic scoring + `sender_multipliers` hook; adaptive multipliers are applied here

### Orchestrator (new nodes + routing)
- `src/daily/orchestrator/graph.py` — `route_intent()` and node topology; skip and re_request nodes connect here
- `src/daily/orchestrator/state.py` — `SessionState`; add `current_item_index` and `briefing_items` fields

### Voice loop (implicit skip + item cursor)
- `src/daily/voice/loop.py` — sentence delivery loop; implicit skip detection and item cursor advancement go here

### New file to create
- `src/daily/profile/adaptive_ranker.py` — `get_sender_multipliers()` implementation (does not exist yet)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_capture_signal(user_id, signal_type, target_id, metadata, db_session)` in `nodes.py` — fire-and-forget async helper via `asyncio.create_task`; use this pattern for all new signal firing
- `SignalType` enum in `signals.py` — `skip` and `re_request` already defined, no schema changes needed
- `append_signal()` in `signals.py` — the DB write function; called by `_capture_signal()`
- `route_intent()` in `graph.py` — add `"skip"` and `"re_request"` as intent strings routing to new nodes

### Established Patterns
- Fire-and-forget signals: `asyncio.create_task(_capture_signal(...))` — never `await` in hot path
- New orchestrator nodes follow `respond_node`/`summarise_thread_node` shape: async function accepting `SessionState` + `db_session` kwargs
- Redis briefing cache key: `briefing:{user_id}` for narrative; `briefing:{user_id}_items` for structured item list (new)
- `SessionState` is a Pydantic model in `state.py`; add new fields with defaults so no migration needed in the session store

### Integration Points
- `context_builder.py` line ~181: already imports and calls `get_sender_multipliers` — just needs the module to exist
- `voice/loop.py` sentence delivery loop: increment `state.current_item_index` when `sentence_cursor` crosses `briefing_items[current_item_index].sentence_range_end`
- `briefing/pipeline.py` precompute: after generating narrative, serialize item list to JSON and write to Redis with same TTL as narrative

</code_context>

<specifics>
## Specific Ideas

- Implicit skip threshold: barge-in + silence > 2s → treat as skip (voice loop detects this inline, no orchestrator round-trip)
- Sigmoid midpoint parameter 3.0 (the denominator in `exp(-score / 3.0)`) controls how steeply one skip penalizes a sender — keep it configurable as a constant for easy tuning later
- `BriefingItem.type` values: `"email"`, `"calendar"`, `"slack"` — matches existing integration categories

</specifics>

<deferred>
## Deferred Ideas

- Real-time re-ranking within the current session (signals immediately reorder remaining items) — complexity not justified for Phase 13; signals feed next day's briefing
- Per-topic or per-thread decay (not just per-sender) — requires richer `target_id` aggregation; consider for v2.0
- Surfacing skip/re_request stats to the user ("you've been skipping emails from X — want to mute them?") — memory transparency concern, Phase 10 territory

</deferred>

---

*Phase: 13-signal-capture*
*Context gathered: 2026-04-18*
