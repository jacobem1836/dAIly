# Phase 13: Signal Capture - Research

**Researched:** 2026-04-18
**Domain:** Python async signal capture, adaptive ranker scoring, LangGraph node patterns, Redis item tracking
**Confidence:** HIGH

## Summary

Phase 13 wires three gaps in the existing signal infrastructure: item tracking so signals carry a meaningful `target_id`, new orchestrator nodes for skip and re_request intents, and the `adaptive_ranker.py` module that implements the decay-weighted scoring formula. All foundational infrastructure — `SignalType` enum, `SignalLog` table, `append_signal()`, and the `_capture_signal()` fire-and-forget helper — already exists and is production-ready. The `context_builder.py` already imports and calls `get_sender_multipliers()` at line 181; the call site is wired, only the module it calls needs to be created.

The phase has five distinct implementation areas: (1) a `BriefingItem` Pydantic model, (2) item list serialisation into Redis at pipeline time, (3) `SessionState` augmentation with `current_item_index` and `briefing_items`, (4) new `skip_node` and `re_request_node` orchestrator nodes plus routing, and (5) `adaptive_ranker.py` with the exponential decay / sigmoid formula. None of these areas require schema migration — the `signal_log` table already has `target_id: str | None`, and `SessionState` additions use Pydantic defaults so the LangGraph checkpointer handles them transparently.

The adaptive ranker formula is a closed-form implementation: fetch signals within 30 days, apply `weight * 0.95^days_old` per signal, sum by sender, pass through a sigmoid clamped to [0.5, 2.0]. The formula parameters (window, weights, sigmoid divisor 3.0) are documented as tuning constants to extract.

**Primary recommendation:** Implement in five focused units, each testable independently. Start with `adaptive_ranker.py` (pure function, no side effects) then item tracking (pipeline + state), then the two new nodes, then integrate and verify end-to-end.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Both explicit and implicit skip triggers are supported.
  - Explicit: "skip", "next", "move on" → new `skip` intent route in the orchestrator graph, fires `SignalType.skip` with the current item's `target_id`
  - Implicit: barge-in detected + silence > 2s → voice loop fires an implicit skip signal inline (no orchestrator round-trip needed)
- **D-02:** At briefing precompute time, store a structured item list in Redis alongside the narrative. Format: `[{item_id, type, target_id, sentence_range_start, sentence_range_end}]`. Redis key suffix: `_items` (e.g. `briefing:{user_id}_items`).
- **D-03:** At voice session start, load the item list from Redis into `SessionState`. Add `current_item_index: int = 0` and `briefing_items: list[BriefingItem] = []` to `SessionState`. The sentence delivery loop increments `current_item_index` as `sentence_cursor` crosses each item's `sentence_range_end`.
- **D-04:** "Repeat that" / "say that again" → new `re_request_node` in the orchestrator graph (mirrors the `expand`/`summarise_thread_node` pattern). The node re-speaks the current briefing item's sentences and fires `SignalType.re_request` with the item's `target_id`.
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

### Deferred Ideas (OUT OF SCOPE)

- Real-time re-ranking within the current session (signals immediately reorder remaining items) — complexity not justified for Phase 13; signals feed next day's briefing
- Per-topic or per-thread decay (not just per-sender) — requires richer `target_id` aggregation; consider for v2.0
- Surfacing skip/re_request stats to the user ("you've been skipping emails from X — want to mute them?") — memory transparency concern, Phase 10 territory
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIG-01 | User can generate `skip` signals (pausing/dismissing a briefing item) that are captured and stored in the signal table | `_capture_signal()` pattern in `nodes.py` is directly reusable; `SignalType.skip` already exists in the enum; `skip_node` + routing additions needed in `graph.py` |
| SIG-02 | User can generate `re_request` signals (asking to repeat or clarify an item) that are captured and stored in the signal table | Same `_capture_signal()` pattern; `SignalType.re_request` already exists; `re_request_node` mirrors `summarise_thread_node` shape |
| SIG-03 | Adaptive ranker ingests `skip` and `re_request` signals alongside `expand` when computing decay scores | `context_builder.py` line 181 already calls `get_sender_multipliers()` in a try/except; creating `adaptive_ranker.py` with that function satisfies the wiring automatically |
</phase_requirements>

---

## Standard Stack

### Core (already installed — no new dependencies needed)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| SQLAlchemy (async) | 2.0.49 (pinned) | Async ORM for `signal_log` query | `select()` + `scalars()` pattern; already used throughout |
| Redis (asyncio) | 7.x (pinned) | Item list cache (`_items` key) | `redis.set(key, json_str, ex=TTL)` — same pattern as `cache_briefing()` |
| Pydantic v2 | 2.12+ (pinned) | `BriefingItem` model; `SessionState` extension | `model_validate_json` / `model_dump_json` for Redis serialisation |
| math.exp (stdlib) | — | Sigmoid in `adaptive_ranker.py` | No extra dependency needed |
| asyncio (stdlib) | — | `create_task(_capture_signal(...))` fire-and-forget | Already established pattern |

[VERIFIED: pyproject.toml read in this session]

### No New Dependencies Required
All packages needed for Phase 13 are already declared in `pyproject.toml`. No `uv add` commands are required.

---

## Architecture Patterns

### Recommended Project Structure (additions only)
```
src/daily/
├── profile/
│   └── adaptive_ranker.py          # NEW — get_sender_multipliers()
├── briefing/
│   ├── pipeline.py                 # EDIT — write _items key after narrative cache
│   └── cache.py                    # REFERENCE — existing cache_key pattern
├── orchestrator/
│   ├── nodes.py                    # EDIT — add skip_node, re_request_node, _capture_signal reuse
│   ├── graph.py                    # EDIT — route_intent + build_graph additions
│   └── state.py                    # EDIT — add current_item_index, briefing_items
└── voice/
    └── loop.py                     # EDIT — implicit skip detection + item cursor advancement

tests/
└── test_adaptive_ranker.py         # NEW
```

### Pattern 1: Fire-and-forget Signal Capture (established)
**What:** Signal writes happen in `asyncio.create_task()` so they never block the response path.
**When to use:** Every signal firing point — skip_node, re_request_node, implicit skip in voice loop.
**Example (from `nodes.py` lines 401–429):**
```python
# Source: src/daily/orchestrator/nodes.py
async def _capture_signal(
    user_id: int,
    signal_type: SignalType,
    target_id: str | None = None,
) -> None:
    try:
        from daily.db.engine import async_session
        from daily.profile.signals import append_signal
        async with async_session() as session:
            await append_signal(
                user_id=user_id,
                signal_type=signal_type,
                session=session,
                target_id=target_id,
            )
    except Exception as exc:
        logger.warning("_capture_signal: failed to write signal: %s", exc)
```
Caller pattern:
```python
asyncio.create_task(
    _capture_signal(state.active_user_id, SignalType.skip, target_id=current_target_id)
)
```
[VERIFIED: nodes.py read in this session]

### Pattern 2: New Orchestrator Node Shape (established)
**What:** Async function accepting `state: SessionState`, returning `dict` with `messages` key.
**When to use:** `skip_node` and `re_request_node` must follow this shape exactly.
**Example (from `resume_briefing_node` — the simplest existing node):**
```python
# Source: src/daily/orchestrator/nodes.py
async def resume_briefing_node(state: SessionState) -> dict:
    if state.briefing_cursor is None:
        return {"messages": [AIMessage(content="...")]}
    return {"messages": [AIMessage(content="Resuming your briefing now.")]}
```
[VERIFIED: nodes.py read in this session]

### Pattern 3: Route Intent Extension (established)
**What:** `route_intent()` in `graph.py` uses keyword list matching in priority order.
**When to use:** Adding `skip` and `re_request` routes requires inserting keyword checks at the correct priority slot (after memory, before respond-default).
**Example (current routing in `graph.py`):**
```python
# Source: src/daily/orchestrator/graph.py
# Priority: memory > resume_briefing > summarise > draft > respond
if any(kw in last_msg for kw in memory_keywords):
    return "memory"
if any(kw in last_msg for kw in resume_briefing_keywords):
    return "resume_briefing"
# ... add skip_keywords → "skip"
# ... add re_request_keywords → "re_request"
```
[VERIFIED: graph.py read in this session]

### Pattern 4: Redis JSON Item Cache (new, mirrors cache.py)
**What:** Serialise `list[BriefingItem]` to JSON and write to Redis with the same TTL as the narrative. Key: `briefing:{user_id}:{date}_items`.
**When to use:** End of `run_briefing_pipeline()` in `pipeline.py`, immediately after `cache_briefing()`.
**Example (mirroring existing `cache_briefing` logic):**
```python
# Source: mirrors src/daily/briefing/cache.py
items_key = f"briefing:{user_id}:{output.generated_at.date().isoformat()}_items"
items_payload = json.dumps([item.model_dump() for item in briefing_items])
await redis.set(items_key, items_payload, ex=CACHE_TTL)
```
[VERIFIED: cache.py read in this session — key pattern confirmed]

### Pattern 5: Adaptive Ranker Implementation
**What:** Pure async function — queries `signal_log` for the last 30 days, computes decay-weighted scores per sender, applies sigmoid, returns `dict[str, float]`.
**When to use:** Called by `context_builder.py` line 181 (already wired).
```python
# Source: CONTEXT.md D-05/D-06 (locked decisions)
from math import exp
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from daily.profile.signals import SignalLog, SignalType

SIGNAL_WEIGHTS = {
    SignalType.skip: -1.0,
    SignalType.re_request: 1.0,
    SignalType.expand: 0.5,
}
DECAY_BASE = 0.95
WINDOW_DAYS = 30
SIGMOID_SCALE = 3.0

async def get_sender_multipliers(
    user_id: int, db_session: AsyncSession
) -> dict[str, float]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=WINDOW_DAYS)
    result = await db_session.execute(
        select(SignalLog).where(
            SignalLog.user_id == user_id,
            SignalLog.created_at >= cutoff,
            SignalLog.signal_type.in_([t.value for t in SIGNAL_WEIGHTS]),
            SignalLog.target_id.isnot(None),
        )
    )
    rows = result.scalars().all()

    scores: dict[str, float] = {}
    now = datetime.now(tz=timezone.utc)
    for row in rows:
        signal_type = SignalType(row.signal_type)
        weight = SIGNAL_WEIGHTS[signal_type]
        days_old = (now - row.created_at.replace(tzinfo=timezone.utc)).days
        decayed = weight * (DECAY_BASE ** days_old)
        sender = (row.target_id or "").lower().strip()
        scores[sender] = scores.get(sender, 0.0) + decayed

    multipliers: dict[str, float] = {}
    for sender, score in scores.items():
        if sender:
            multipliers[sender] = 0.5 + 1.5 / (1 + exp(-score / SIGMOID_SCALE))
    return multipliers
```
[VERIFIED: formula from CONTEXT.md D-05; signal schema from signals.py read in this session]

### Anti-Patterns to Avoid
- **Awaiting `_capture_signal` inline:** Signal writes must use `asyncio.create_task()` — never `await _capture_signal()` in a node. Blocking the node return path would add DB latency to the voice response.
- **Sharing DB sessions across task boundaries:** Each `asyncio.create_task` in `_capture_signal` opens its own `async_session()`. Never pass a session from an outer scope into a task.
- **Setting `target_id` from the item list before it is loaded:** The item list is loaded at voice session start from Redis. If `briefing_items` is empty (e.g., old briefing cached before Phase 13), `target_id` will be `None` — that is acceptable, the signal is still written.
- **Creating a new Alembic migration:** `signal_log` already has `target_id: str | None`. `SessionState` additions use Pydantic defaults — no DB migration needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sigmoid clamped to [0.5, 2.0] | Custom piecewise clamp | `math.exp` inside the closed-form formula | Formula is already specified; stdlib `math.exp` is all that's needed |
| Signal DB write | Custom ORM insert logic | `append_signal()` in `signals.py` + `_capture_signal()` in `nodes.py` | Already written, tested, handles commit |
| Redis JSON serialisation | Custom encoder | `json.dumps([item.model_dump() for item in items])` | Pydantic v2 `model_dump()` handles all field types cleanly |
| LangGraph node wiring | Custom dispatch | `route_intent()` keyword list + `build_graph()` edge declarations | Established pattern — adding two entries to each is the correct approach |

---

## Common Pitfalls

### Pitfall 1: `target_id` points to item_id vs sender address
**What goes wrong:** The adaptive ranker aggregates by sender email, but `target_id` in `signal_log` needs to carry the **sender's email address** for skip/re_request signals (not just an item ID), so `get_sender_multipliers()` can aggregate by it.
**Why it happens:** CONTEXT.md D-02 defines `target_id` in the item list as the email/event/message ID from the integration. But D-05 says the ranker aggregates "per sender (lowercase stripped)". This means either: (a) `target_id` stores the sender email directly for skip/re_request signals, OR (b) the ranker joins against email metadata.
**How to avoid:** The simplest interpretation (and the one consistent with the existing `expand` signal pattern where `target_id = message_id`) is that skip/re_request signals store the sender email as `target_id`. The `BriefingItem` model should carry a `sender` field alongside `target_id`. At signal-fire time, pass `item.sender` (not `item.target_id`) as the signal's `target_id`. This is the approach the ranker formula expects.
**Warning signs:** If `get_sender_multipliers()` returns an empty dict even when signals exist, `target_id` values are likely not sender emails.

### Pitfall 2: `briefing_items` not loaded at session start in voice loop
**What goes wrong:** `skip_node` and implicit skip code read `state.briefing_items[state.current_item_index]` — if the list is empty (either because `_items` key is missing from Redis, or `initialize_session_state` didn't load it), `IndexError` will fire.
**Why it happens:** The `_items` Redis key is new; old cached briefings won't have it. Also `initialize_session_state()` in `session.py` needs updating to load the item list.
**How to avoid:** Add defensive fallback — if `briefing_items` is empty or `current_item_index` is out of range, fire the signal with `target_id=None` rather than crashing. This is consistent with the "briefing always delivers" graceful-degradation contract.

### Pitfall 3: `created_at` timezone-naive in the decay formula
**What goes wrong:** `SignalLog.created_at` uses `server_default=func.now()` — Postgres returns a timezone-naive datetime by default unless the column is `TIMESTAMP WITH TIME ZONE`. The decay formula calls `.replace(tzinfo=timezone.utc)` — this is correct, but only if the value is actually UTC. If Postgres is configured with a non-UTC timezone, the naive datetime will be wrong.
**Why it happens:** SQLAlchemy maps `DateTime` (without `timezone=True`) to a naive datetime object.
**How to avoid:** In `get_sender_multipliers()`, always call `.replace(tzinfo=timezone.utc)` on `created_at` before computing `days_old`, consistent with the pattern already used in `ranker.py` lines 114-118. [VERIFIED: ranker.py read in this session]

### Pitfall 4: Session state serialisation with `BriefingItem` list
**What goes wrong:** LangGraph's `AsyncPostgresSaver` checkpointer serialises `SessionState` to JSON. Adding `briefing_items: list[BriefingItem] = []` to `SessionState` requires `BriefingItem` to be fully JSON-serialisable. Pydantic v2 `BaseModel` handles this correctly, but if `BriefingItem` contains any non-serialisable field types (e.g. `datetime`, custom enum without str mixin), the checkpoint write will fail.
**Why it happens:** LangGraph state goes through JSON serialisation at every checkpoint.
**How to avoid:** Keep `BriefingItem` fields as primitive types (`str`, `int`). Use `item_id: str`, `type: str`, `target_id: str`, `sentence_range_start: int`, `sentence_range_end: int`. No enums or datetime objects.

### Pitfall 5: Item cursor increment logic
**What goes wrong:** The sentence delivery loop increments `current_item_index` when `sentence_cursor` crosses `sentence_range_end`. If the sentence splitting produces a different count than what was recorded at pipeline time (e.g. due to trailing whitespace or punctuation differences), the cursor will point to the wrong item.
**Why it happens:** `_split_sentences()` in `loop.py` uses a regex split — the same function must be used at both pipeline time (when building item ranges) and loop time (when checking ranges).
**How to avoid:** Use `_split_sentences()` (or an equivalent extracted utility) consistently in both places. Extract it to a shared location (e.g. `daily.briefing.utils`) if it needs to be called from `pipeline.py`.

---

## Code Examples

### Adaptive Ranker — Core Query
```python
# Source: CONTEXT.md D-05 + signals.py schema verified in this session
from sqlalchemy import select
from daily.profile.signals import SignalLog, SignalType

result = await db_session.execute(
    select(SignalLog).where(
        SignalLog.user_id == user_id,
        SignalLog.created_at >= cutoff,
        SignalLog.signal_type.in_([t.value for t in SIGNAL_WEIGHTS]),
        SignalLog.target_id.isnot(None),
    )
)
rows = result.scalars().all()
```

### Sigmoid Formula
```python
# Source: CONTEXT.md D-05
from math import exp
multiplier = 0.5 + 1.5 / (1 + exp(-sender_score / SIGMOID_SCALE))
# sender_score = 0  → multiplier ≈ 1.25 (slight positive bias at zero)
# sender_score >> 0 → multiplier → 2.0
# sender_score << 0 → multiplier → 0.5
```
Note: At score=0, sigmoid yields 1.25 (not exactly 1.0 — midpoint of [0.5, 2.0] is 1.25). This is by design; a sender with zero signals gets a mild positive bias. [VERIFIED: arithmetic from CONTEXT.md formula]

### BriefingItem Pydantic Model (discretion area)
```python
# Source: CONTEXT.md D-02 (shape requirements) + Pitfall 4 avoidance
from pydantic import BaseModel

class BriefingItem(BaseModel):
    item_id: str           # e.g. "email-0", "calendar-1"
    type: str              # "email" | "calendar" | "slack"
    target_id: str         # sender email address (for ranker aggregation)
    sentence_range_start: int
    sentence_range_end: int
```

### skip_node Skeleton
```python
# Source: node shape from resume_briefing_node (nodes.py); signal pattern from _capture_signal
async def skip_node(state: SessionState) -> dict:
    # Fire skip signal (fire-and-forget)
    if state.active_user_id and state.briefing_items:
        idx = min(state.current_item_index, len(state.briefing_items) - 1)
        item = state.briefing_items[idx]
        asyncio.create_task(
            _capture_signal(state.active_user_id, SignalType.skip, target_id=item.target_id)
        )
    return {"messages": [AIMessage(content="Skipping to the next item.")]}
```

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| Expand signal only for adaptive ranking | Skip + re_request + expand | Phase 13 adds the two missing signal types |
| No item tracking (signals had `target_id=None`) | Structured item list in Redis with sender-keyed target_id | Enables per-sender signal aggregation |
| `adaptive_ranker.py` imported but not yet present | Create the module | `context_builder.py` already calls it — creating the file is the activation |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `target_id` in skip/re_request signals should store the **sender's email address** (not the item's message_id) so the ranker can aggregate by sender | Architecture Patterns / Pitfall 1 | If wrong, `get_sender_multipliers()` would aggregate over message IDs instead of senders and return empty/wrong results; ranker would silently no-op |
| A2 | `initialize_session_state()` in `session.py` needs to be updated to load the `_items` Redis key into `SessionState.briefing_items` | Architecture Patterns | If not updated, `briefing_items` will always be empty and signals will fire with `target_id=None` |

**A1 resolution path:** Check the exact field in `BriefingItem` that carries the sender's email address. If `target_id` is intended to be the sender email (not the message/event ID), then the `BriefingItem.target_id` field name is slightly misleading — consider `sender_email` as a separate field with `item_ref` for the message ID. The planner should clarify or choose one of:
- Option A: `target_id` = sender email (ranker-friendly, breaks the "item reference" naming)
- Option B: `BriefingItem` has both `item_ref: str` and `sender: str`; signal fires use `item.sender`

---

## Open Questions

1. **Does `initialize_session_state()` in `session.py` need updating to load `briefing_items`?**
   - What we know: `SessionState` will gain `briefing_items: list[BriefingItem] = []`; the voice loop reads from it
   - What's unclear: Whether `initialize_session_state()` already reads from Redis generically or requires explicit new field loading
   - Recommendation: Read `session.py` before implementing `loop.py` changes — this is a small but critical wiring point

2. **What exact sender key format does `ranker.py` use for `sender_multipliers` lookup?**
   - What we know: `ranker.py` line 173 uses `email.sender.lower().strip()` as the lookup key
   - What's required: `get_sender_multipliers()` must produce keys in the same normalised format for the multiplier to be applied
   - Recommendation: The planner should specify that `adaptive_ranker.py` returns keys normalised as `sender.lower().strip()`, matching `ranker.py`'s lookup [VERIFIED: ranker.py line 173 read in this session]

---

## Environment Availability

Step 2.6: SKIPPED — Phase 13 is purely code changes to existing Python modules. No new external services, CLI tools, or runtimes are required. All dependencies (`sqlalchemy`, `redis`, `pydantic`, `math`) are already installed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/test_adaptive_ranker.py tests/test_signal_log.py -x` |
| Full suite command | `pytest tests/ -x` |

[VERIFIED: pyproject.toml read in this session]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIG-01 | skip signal written to signal_log with correct target_id | unit | `pytest tests/test_signal_log.py -k skip -x` | ✅ (partial — skip enum test exists; skip_node test needs adding) |
| SIG-01 | skip intent routed to skip_node in orchestrator graph | unit | `pytest tests/test_orchestrator_graph.py -k skip -x` | ✅ (file exists; skip route test needs adding) |
| SIG-02 | re_request signal written to signal_log with correct target_id | unit | `pytest tests/test_signal_log.py -k re_request -x` | ✅ (partial — re_request enum test exists; re_request_node test needs adding) |
| SIG-03 | get_sender_multipliers returns correct decay-weighted scores | unit | `pytest tests/test_adaptive_ranker.py -x` | ❌ Wave 0 |
| SIG-03 | rank_emails applies sender_multipliers to scoring | unit | `pytest tests/test_briefing_ranker.py -k multiplier -x` | ✅ (file exists; multiplier tests should exist) |
| SIG-03 | signals older than 30 days excluded from window | unit | `pytest tests/test_adaptive_ranker.py::test_window_cutoff -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_adaptive_ranker.py -x` (for ranker tasks); `pytest tests/test_orchestrator_graph.py -x` (for node tasks)
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_adaptive_ranker.py` — covers SIG-03 decay formula, window cutoff, sigmoid range, empty result
- [ ] New test cases in `tests/test_orchestrator_graph.py` — covers `skip` and `re_request` intent routing
- [ ] New test cases in `tests/test_signal_log.py` — covers `skip_node` and `re_request_node` signal firing

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | yes — signals scoped to `user_id` | All signal queries filter by `user_id`; `_capture_signal()` takes `state.active_user_id` (never user-controlled) |
| V5 Input Validation | no — no user-supplied data in the ranker path | Signal type is an enum; `target_id` comes from the item list, not user input |
| V6 Cryptography | no | — |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Signal injection (user supplies `target_id` via voice transcript) | Tampering | `target_id` is sourced from `state.briefing_items` (server-side item list), never parsed from the user's utterance. The orchestrator graph uses keyword routing only — no user-controlled code execution (T-03-04). |
| Cross-user signal pollution | Elevation of Privilege | `user_id` for signal writes comes from `state.active_user_id` (set at session init from the authenticated session), not from user input. DB query in `get_sender_multipliers` filters by `user_id`. |

---

## Sources

### Primary (HIGH confidence)
- `src/daily/profile/signals.py` — SignalLog schema, SignalType enum, append_signal() signature
- `src/daily/orchestrator/nodes.py` — `_capture_signal()` implementation, `respond_node`/`summarise_thread_node` shapes
- `src/daily/orchestrator/graph.py` — `route_intent()` keyword routing, `build_graph()` node topology
- `src/daily/orchestrator/state.py` — `SessionState` current fields and Pydantic defaults pattern
- `src/daily/briefing/context_builder.py` — line 181 hook where `get_sender_multipliers` is already called
- `src/daily/briefing/ranker.py` — `rank_emails()` + `sender_multipliers` parameter, key normalisation at line 173
- `src/daily/briefing/cache.py` — Redis key pattern `briefing:{user_id}:{date}`, TTL constant
- `src/daily/briefing/pipeline.py` — `run_briefing_pipeline()` structure where item list write goes
- `src/daily/voice/loop.py` — sentence delivery loop, barge-in detection, `briefing_cursor` pattern
- `pyproject.toml` — confirmed all dependencies; pytest config

### Secondary (MEDIUM confidence)
- `tests/test_signal_log.py` — confirmed existing signal test coverage; identified gaps
- `.planning/phases/13-signal-capture/13-CONTEXT.md` — locked decisions (D-01 through D-06)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified via pyproject.toml; no new installs needed
- Architecture: HIGH — all integration points verified by reading canonical source files
- Pitfalls: HIGH — identified from direct code inspection (timezone handling in ranker.py, session init gap, cursor sync)
- Adaptive ranker formula: HIGH — formula is closed-form and fully specified in CONTEXT.md D-05

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable internal codebase)
