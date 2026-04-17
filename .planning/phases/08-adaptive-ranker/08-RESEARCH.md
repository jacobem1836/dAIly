# Phase 8: Adaptive Ranker — Research

**Researched:** 2026-04-16
**Domain:** Signal aggregation, sigmoid normalisation, SQLAlchemy 2.0 async query patterns
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Blend strategy:** Per-sender float multiplier (0.5–2.0 sigmoid-normalised) applied to the full `score_email()` result. Heuristics compute first, then multiply.
2. **Signal weights:** re_request=+1.0, expand=+0.5, follow_up=+0.3, correction=−0.3, skip=−0.5
3. **Decay:** 14-day exponential half-life per signal: `exp(-ln(2) * days_old / 14)`
4. **Scope:** Per-sender only (email address). No topic/keyword learning.
5. **Module boundary:** New file `src/daily/profile/adaptive_ranker.py` exporting `get_sender_multipliers(user_id, session, min_signals=30) -> dict[str, float]`
6. **Cold-start:** < 30 total signals for user → return `{}` (all multipliers default to 1.0)
7. **Graceful degradation:** Any DB error → return `{}`, log warning. Never raise.
8. **Wiring:** `context_builder.build_context()` gains optional `db_session: AsyncSession | None = None`; `rank_emails()` gains optional `sender_multipliers: dict[str, float] = {}`. Both default to no-op when not supplied.
9. **All signature changes backward-compatible** — existing callers need zero changes.

### Claude's Discretion

None specified — all key decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- Per-user configurable signal weights (`signal_weights` in `user_profile.preferences`) — v2.0
- Per-user configurable attention half-life (`attention_halflife_days`) — v2.0
- Per-user configurable multiplier range (`ADAPTIVE_WEIGHT_MIN` / `ADAPTIVE_WEIGHT_MAX`) — v2.0
- Per-sender minimum signal threshold before multiplier applied — v2.0
- Topic/keyword-level attention learning — v2.0
- Dashboard visibility into computed sender multipliers — v2.0 (DASH-01)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTEL-01 | User receives briefing ranked by learned personal priorities, not static heuristics | Adaptive ranker module computes per-sender multipliers from signal_log and blends them into the existing heuristic scores |
</phase_requirements>

---

## Summary

Phase 8 replaces static email ranking with a signal-learned personal scoring layer. The implementation has three logical parts: (1) a new `adaptive_ranker.py` module that queries `signal_log` and computes per-sender float multipliers, (2) minimal wiring changes to `rank_emails()` and `build_context()` to thread multipliers through, and (3) a scheduler update so the cron pipeline passes a DB session.

The critical finding from codebase inspection is that **sender email is NOT stored in `signal_log` today**. The `_capture_signal()` helper in `nodes.py` passes only `target_id` (a `message_id`) and no `metadata`. To map signals to senders, `adaptive_ranker.py` must join `signal_log` against `email_context` state data — but that data is ephemeral (session state, not persisted). The practical resolution is a **two-part change**: (a) update `_capture_signal()` to pass `metadata={"sender": "<email>"}` when the signal type is email-related, and (b) have `adaptive_ranker.py` read sender from `metadata_json->>'sender'`.

The existing `async_session` factory from `daily.db.engine` is already used in the scheduler (`_build_pipeline_kwargs`) via the `async with async_session() as session:` pattern. The session does not need to be passed into the pipeline at construction time — `_build_pipeline_kwargs` can open a dedicated short-lived session just for the adaptive ranker query and pass the already-fetched multipliers dict into the pipeline, or pass the session factory through. The cleanest approach (matching existing patterns) is to open a session inside `_build_pipeline_kwargs`, call `get_sender_multipliers()`, and pass the resulting `dict[str, float]` directly into `run_briefing_pipeline()` as a new optional parameter. This avoids threading a session through the entire pipeline.

**Primary recommendation:** Store sender in signal metadata at capture time; aggregate per-sender in `adaptive_ranker.py` using a single async query with JSONB extraction; blend results into existing ranker via an optional multipliers dict.

---

## Critical Finding: Sender Email Is Not Stored in signal_log Today

**[VERIFIED: codebase grep]**

Current `_capture_signal()` in `nodes.py` (lines 337–365):

```python
await append_signal(
    user_id=user_id,
    signal_type=signal_type,
    session=session,
    target_id=target_id,      # message_id or None
    # metadata= not passed at any callsite
)
```

The two active callsites are:
- `summarise_thread_node` → `SignalType.expand`, `target_id=message_id`
- `respond_node` → `SignalType.follow_up`, `target_id=None`

Neither passes a sender email address. The `SignalLog.metadata_json` column exists and is JSONB-typed, but is always `NULL` in practice today.

**Resolution required in this phase:** Update `_capture_signal()` to accept an optional `sender` parameter and include it in `metadata`. Update both callsites. The `summarise_thread_node` has access to `state.email_context` (list of dicts with a `"sender"` key) — the sender can be looked up by `message_id` from that list. The `respond_node` does not target a specific email, so sender remains `None` there.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.x | Async ORM + query builder | Already in use; `select()` + `AsyncSession.execute()` pattern throughout codebase |
| asyncpg | 0.29+ | PostgreSQL async driver | Already in use as SQLAlchemy engine backend |
| Python `math` (stdlib) | 3.11+ | `exp()`, `log()` for decay formula | No new dependency needed |

**[VERIFIED: pyproject.toml and existing imports in codebase]**

No new packages required for this phase.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-asyncio` | 1.3.0+ | Async test support | All `get_sender_multipliers` tests use `AsyncMock` — same pattern as `test_signal_log.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single SQL query with JSONB extraction | Python-side join with two queries | Single query is cleaner, reduces round-trips, keeps aggregation in DB |
| Sigmoid normalisation (0.5–2.0) | Clamp + linear map | Sigmoid avoids hard edge effects; a single extreme signal does not snap to 0.5/2.0 |

---

## Architecture Patterns

### Recommended Project Structure

```
src/daily/profile/
├── signals.py           # existing — SignalLog ORM, append_signal
├── adaptive_ranker.py   # NEW — get_sender_multipliers()
├── models.py            # existing — UserPreferences
└── service.py           # existing — load_profile
```

### Pattern 1: JSONB Field Extraction in SQLAlchemy 2.0 Async

SQLAlchemy 2.0 supports PostgreSQL JSONB path extraction via the `[` operator or `cast`. For extracting `metadata_json->>'sender'`:

```python
# [VERIFIED: SQLAlchemy 2.0 docs — https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB]
from sqlalchemy import select, func, cast
from sqlalchemy.dialects.postgresql import JSONB

stmt = (
    select(
        cast(SignalLog.metadata_json["sender"], String).label("sender"),
        SignalLog.signal_type,
        SignalLog.created_at,
    )
    .where(SignalLog.user_id == user_id)
    .where(SignalLog.metadata_json["sender"].isnot(None))
)
result = await session.execute(stmt)
rows = result.fetchall()
```

The `["sender"]` access on a JSONB-mapped column returns a JSONB fragment; `cast(..., String)` extracts it as text, stripping quotes. This is the correct pattern — do not use `.as_string()` (deprecated in SA 2.0).

**[VERIFIED: SQLAlchemy 2.0 changelog and JSONB docs]**

### Pattern 2: Exponential Decay Formula

```python
# [ASSUMED — math formula, standard ML practice]
import math
from datetime import datetime, timezone

HALF_LIFE_DAYS = 14.0

def _decay_weight(created_at: datetime) -> float:
    now = datetime.now(tz=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days_old = (now - created_at).total_seconds() / 86400.0
    return math.exp(-math.log(2) * days_old / HALF_LIFE_DAYS)
```

Decay is applied per-signal before summing (per CONTEXT.md requirement 3).

### Pattern 3: Sigmoid Normalisation to [0.5, 2.0]

```python
# [ASSUMED — standard sigmoid scaling, locked by CONTEXT.md]
import math

MIN_MULT = 0.5
MAX_MULT = 2.0

def _sigmoid_normalise(raw_score: float) -> float:
    """Map raw_score (−∞, +∞) → (0.5, 2.0) via logistic sigmoid."""
    sig = 1.0 / (1.0 + math.exp(-raw_score))  # → (0, 1)
    return MIN_MULT + sig * (MAX_MULT - MIN_MULT)  # → (0.5, 2.0)
```

Raw score of 0 maps to 1.25 (midpoint), not 1.0. The asymptote ensures no sender is ever fully muted (min 0.5) or weighted more than double (max 2.0).

### Pattern 4: get_sender_multipliers Skeleton

```python
# [VERIFIED: pattern matches existing session usage in scheduler.py and nodes.py]
async def get_sender_multipliers(
    user_id: int,
    session: AsyncSession,
    min_signals: int = 30,
) -> dict[str, float]:
    try:
        # 1. Count total signals for cold-start check
        count_stmt = select(func.count()).where(SignalLog.user_id == user_id)
        total = (await session.execute(count_stmt)).scalar_one()
        if total < min_signals:
            return {}

        # 2. Fetch all signals with sender in metadata
        rows = await _fetch_sender_signals(session, user_id)

        # 3. Aggregate per sender with decay and signal weights
        return _compute_multipliers(rows)

    except Exception:
        logger.warning("get_sender_multipliers: DB error, skipping adaptive ranking")
        return {}
```

### Pattern 5: Scheduler Wiring (Preferred Approach)

The cleanest wiring that avoids threading a session through 4 function signatures is to fetch the multipliers dict inside `_build_pipeline_kwargs()` and pass the dict as a new optional parameter `sender_multipliers: dict[str, float] | None = None` to `run_briefing_pipeline()`.

```python
# In scheduler._build_pipeline_kwargs()
# [VERIFIED: existing pattern in scheduler.py lines 68–107]
async with async_session() as session:
    from daily.profile.adaptive_ranker import get_sender_multipliers
    sender_multipliers = await get_sender_multipliers(user_id, session)

return {
    ...existing keys...,
    "sender_multipliers": sender_multipliers,
}
```

Then `run_briefing_pipeline()` accepts `sender_multipliers: dict[str, float] | None = None` and passes it to `build_context()`, which passes it to `rank_emails()`. This is three small, backward-compatible signature additions.

### Anti-Patterns to Avoid

- **Passing AsyncSession through the full pipeline:** Breaks the existing separation where pipeline.py has no DB awareness. The multipliers dict is a simple value — pass the value, not the session.
- **Aggregating with GROUP BY in SQL:** Decay must be applied per-signal before aggregation (per CONTEXT.md requirement 3). A pure GROUP BY aggregate cannot apply per-row time-decay. Fetch all rows and aggregate in Python.
- **Using `metadata_json['sender']` without a NULL guard:** Rows without sender in metadata_json (historical rows and follow_up signals) must be excluded from the sender aggregation.
- **Raising on DB failure:** `get_sender_multipliers` must catch all exceptions and return `{}` (CONTEXT.md requirement 1).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sigmoid function | Custom piecewise approximation | `math.exp()` (stdlib) | One-liner, exact, no dependency |
| Async DB session | Custom connection management | `async_session()` factory from `daily.db.engine` | Already battle-tested; same pattern in scheduler and nodes |
| JSONB path access | String parsing of JSON in Python | SQLAlchemy JSONB `[]` operator | DB handles extraction; cleaner and indexed if needed |

---

## Signal Metadata Gap — Implementation Guide

**[VERIFIED: codebase inspection of nodes.py, signals.py]**

### What must change in `nodes.py`

1. `_capture_signal()` signature gains an optional `sender: str | None = None` parameter.
2. Passes `metadata={"sender": sender}` to `append_signal()` when sender is not None.
3. `summarise_thread_node` callsite: look up sender from `state.email_context` by `message_id` before firing the task:

```python
# Existing callsite in summarise_thread_node (line 330-332)
asyncio.create_task(
    _capture_signal(state.active_user_id, SignalType.expand, target_id=message_id)
)

# Updated callsite
sender = next(
    (e["sender"] for e in state.email_context if e["message_id"] == message_id),
    None,
)
asyncio.create_task(
    _capture_signal(state.active_user_id, SignalType.expand, target_id=message_id, sender=sender)
)
```

4. `respond_node` callsite: sender remains `None` (follow_up signals are not email-specific).
5. Historical rows in `signal_log` with `metadata_json IS NULL` are silently excluded from adaptive ranking by the NULL guard in the query — no migration needed.

### What can be deferred

`skip` and `re_request` signals are not yet wired to any node in the current codebase — these signal types exist in the enum but are never captured. Phase 8 does not add new capture points for them beyond updating the existing callsites. The ranker will accumulate `expand` and `follow_up` signals immediately; `skip`/`re_request` weights only matter once those signals are captured (future phases or follow-up work).

---

## Common Pitfalls

### Pitfall 1: NULL metadata_json breaks JSONB extraction
**What goes wrong:** SQLAlchemy JSONB `["sender"]` on a NULL `metadata_json` column raises or returns unexpected results depending on the DB driver.
**Why it happens:** `metadata_json IS NULL` on historical rows and `follow_up` signals.
**How to avoid:** Add `.where(SignalLog.metadata_json["sender"].isnot(None))` and `.where(SignalLog.metadata_json.isnot(None))` to every query that touches `metadata_json`.
**Warning signs:** `AttributeError` or `NoneType` errors in the aggregation step.

### Pitfall 2: Timezone-naive `created_at` from DB
**What goes wrong:** Decay formula computes a negative or enormous `days_old` when `created_at` from the DB is timezone-naive and `datetime.now(tz=timezone.utc)` is timezone-aware.
**Why it happens:** `server_default=func.now()` stores timestamps in the DB timezone; SQLAlchemy may return them as naive depending on asyncpg config.
**How to avoid:** Defensively replace `tzinfo=timezone.utc` on any naive `created_at` in the decay function — same guard used in `ranker.py` lines 105–108.
**Warning signs:** `TypeError: can't subtract offset-naive and offset-aware datetimes`.

### Pitfall 3: Sigmoid midpoint is not 1.0
**What goes wrong:** A sender with net score 0 (equal positive and negative signals) gets multiplier 1.25, not 1.0. If tested against "no signals = no change", the test will fail.
**Why it happens:** The sigmoid maps 0 → 0.5 (in the unit range), which maps to 1.25 in the [0.5, 2.0] range.
**How to avoid:** Test assertions must account for the actual midpoint. If 1.0 is the desired neutral for zero-signal senders, the sigmoid formula needs a shift — confirm with the locked design before implementing.
**Warning signs:** Test for "neutral sender has multiplier ≈ 1.0" fails with 1.25.

### Pitfall 4: Empty dict vs None in optional parameters
**What goes wrong:** `rank_emails()` checks `if sender_multipliers:` which is falsy for `{}`. Any sender lookup returns the default multiplier of 1.0, which is correct behaviour — but tests that assert "no multipliers applied" might pass for the wrong reason.
**Why it happens:** Python treats empty dict as falsy.
**How to avoid:** Use `sender_multipliers.get(sender_email, 1.0)` unconditionally rather than gating on dict truthiness. The default 1.0 for unknown senders is the correct no-op.

### Pitfall 5: sender stored with different casing or display name prefix
**What goes wrong:** `metadata_json->>'sender'` stores `"Alice <alice@example.com>"` but `EmailMetadata.sender` in the ranker is already `"alice@example.com"` (normalised by the adapter). Lookup fails.
**Why it happens:** `_extract_email()` in `session.py` strips display names. If the same normalisation is not applied when storing sender in metadata, keys won't match.
**How to avoid:** Apply the same `_extract_email()` normalisation before storing sender in signal metadata and before looking up in the multipliers dict. Either import the function or duplicate the `<...>` strip logic.

---

## Code Examples

### Multiplier Lookup in rank_emails (backward-compatible extension)

```python
# Source: existing ranker.py pattern, extended
def rank_emails(
    emails: list[EmailMetadata],
    vip_senders: frozenset[str],
    user_email: str,
    top_n: int = 5,
    sender_multipliers: dict[str, float] | None = None,  # NEW
) -> list[RankedEmail]:
    _multipliers = sender_multipliers or {}
    now = datetime.now(tz=timezone.utc)
    thread_counts: dict[str, int] = {}
    for email in emails:
        thread_counts[email.thread_id] = thread_counts.get(email.thread_id, 0) + 1

    scored: list[tuple[float, EmailMetadata]] = []
    for email in emails:
        base_score = score_email(email, vip_senders, user_email, now, thread_counts)
        multiplier = _multipliers.get(email.sender.lower().strip(), 1.0)
        scored.append((base_score * multiplier, email))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [RankedEmail(metadata=email, score=score) for score, email in scored[:top_n]]
```

**Note:** `email.sender.lower().strip()` must match the normalisation used when storing sender in `metadata_json`. Confirm both sides use the same format (bare email address, lowercase).

### Mock Pattern for Tests (no live DB)

```python
# Source: existing pattern in test_signal_log.py and test_briefing_ranker.py
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_get_sender_multipliers_cold_start():
    """< 30 total signals returns empty dict."""
    from daily.profile.adaptive_ranker import get_sender_multipliers

    mock_session = AsyncMock(spec=AsyncSession)
    # Simulate count query returning 5
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    mock_session.execute.return_value = mock_result

    result = await get_sender_multipliers(user_id=1, session=mock_session)
    assert result == {}
```

---

## Runtime State Inventory

This is a greenfield addition to an existing system (not a rename/refactor). However, there is one runtime state consideration:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `signal_log` rows — existing rows have `metadata_json = NULL` (no sender stored) | No migration needed. NULL guard in query silently excludes them. Adaptive ranking accumulates only from new rows onward. |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | None | — |
| Build artifacts | None | — |

**Cold start is expected:** The first days after deployment, total signal count will be < 30 and the ranker will operate in pure heuristic mode. This is correct and tested behaviour.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]` |
| Quick run command | `pytest tests/test_adaptive_ranker.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTEL-01 (SC1) | Sender with repeated expand/re_request signals gets multiplier > 1.0 and ranks higher than skipped sender | unit | `pytest tests/test_adaptive_ranker.py::test_engaged_sender_ranks_higher -x` | Wave 0 |
| INTEL-01 (SC2) | < 30 total signals → `get_sender_multipliers` returns `{}` → `rank_emails` output unchanged | unit | `pytest tests/test_adaptive_ranker.py::test_cold_start_returns_empty -x` | Wave 0 |
| INTEL-01 (SC3) | DB session unavailable → pipeline runs, returns briefing with no multipliers applied | unit | `pytest tests/test_adaptive_ranker.py::test_db_error_returns_empty -x` | Wave 0 |
| INTEL-01 (SC3) | `build_context(db_session=None)` runs without error and returns full `BriefingContext` | unit | `pytest tests/test_briefing_context.py::test_build_context_no_db_session -x` | Wave 0 |
| INTEL-01 general | Decay: signal from 14 days ago contributes half weight of today's signal | unit | `pytest tests/test_adaptive_ranker.py::test_decay_half_life -x` | Wave 0 |
| INTEL-01 general | Sigmoid: sender with score 0 gets neutral multiplier (confirm whether 1.0 or 1.25) | unit | `pytest tests/test_adaptive_ranker.py::test_sigmoid_zero_score -x` | Wave 0 |
| INTEL-01 general | Sender not in multipliers dict → multiplier defaults to 1.0 | unit | `pytest tests/test_briefing_ranker.py::test_rank_emails_unknown_sender_defaults_to_1 -x` | Wave 0 |
| INTEL-01 general | `metadata_json=None` rows excluded from aggregation without error | unit | `pytest tests/test_adaptive_ranker.py::test_null_metadata_excluded -x` | Wave 0 |

### Success Criteria → Test Mapping

**SC1: "A sender the user has repeatedly expanded or re-requested appears higher"**

Test scenario: Create two sets of mock signal rows. Sender A has 5 `expand` signals (decayed weight ≈ 5 × 0.5 = 2.5 raw score → multiplier > 1.25). Sender B has 5 `skip` signals (raw score ≈ −2.5 → multiplier < 1.0). Build two emails with identical heuristic scores but different senders. Assert sender A email ranks first after `rank_emails()` with the computed multipliers.

**SC2: "Cold start (fewer than 30 signals) falls back to heuristic defaults without error"**

Test scenario: Mock `session.execute()` to return count=15 on the first call. Assert `get_sender_multipliers()` returns `{}` without raising. Assert `rank_emails()` called with `sender_multipliers={}` produces identical output to `rank_emails()` called with `sender_multipliers=None`.

**SC3: "Briefing pipeline delivers on schedule if signal retrieval fails"**

Test scenario: Mock `session.execute()` to raise `sqlalchemy.exc.OperationalError`. Assert `get_sender_multipliers()` returns `{}` and logs a warning. Assert `build_context(db_session=mock_failing_session)` completes and returns a `BriefingContext` with non-empty `emails`. Assert `run_briefing_pipeline()` with `db_session=None` produces a `BriefingOutput`.

### Sampling Rate

- **Per task commit:** `pytest tests/test_adaptive_ranker.py tests/test_briefing_ranker.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_adaptive_ranker.py` — covers all SC1/SC2/SC3 scenarios plus decay, sigmoid, null guard, default multiplier
- [ ] New test in `tests/test_briefing_context.py` — `test_build_context_no_db_session` (SC3 wiring test)
- [ ] New test in `tests/test_briefing_ranker.py` — `test_rank_emails_unknown_sender_defaults_to_1` (verifies backward compatibility)

---

## Open Questions

1. **Sigmoid midpoint at 1.25, not 1.0**
   - What we know: The locked sigmoid maps raw score 0 → multiplier 1.25 (midpoint of [0.5, 2.0]).
   - What's unclear: Is the intended "neutral" for a sender with balanced signals 1.0 (no change) or 1.25 (slight boost)?
   - Recommendation: Implement as specified (1.25 midpoint). Document in code. If product intent is "neutral = 1.0", the formula needs adjustment: use `(MAX - MIN) * sigmoid(raw) + MIN` but shift the raw score input so that 0 maps to the midpoint of the unit sigmoid (which it does — sigmoid(0) = 0.5, mapping to 1.25). No change needed unless Jacob explicitly wants 1.0 as neutral.

2. **`skip` and `re_request` signals are never captured today**
   - What we know: Both signal types exist in `SignalType` enum but no node fires them.
   - What's unclear: Should Phase 8 add new capture points (e.g., skip node, re-request intent routing)?
   - Recommendation: Phase 8 should not add new signal capture points beyond updating the existing `expand` callsite. The ranker framework will be ready to use them when they are wired in future phases.

3. **Email address normalisation consistency**
   - What we know: `_extract_email()` in `session.py` strips display name (`"Alice <alice@example.com>"` → `"alice@example.com"`). `EmailMetadata.sender` from adapters may or may not be pre-normalised.
   - What's unclear: Whether Gmail/Outlook adapters already normalise sender to bare email address.
   - Recommendation: Apply `_extract_email()` normalisation both at signal capture time (before storing in metadata) and at multiplier lookup time (before dict key access). Makes it idempotent and safe regardless of adapter behaviour.

---

## Environment Availability

Step 2.6: SKIPPED — no new external dependencies. All required tools (PostgreSQL, SQLAlchemy, asyncpg, pytest-asyncio) are already installed and confirmed by existing passing test suite.

---

## Security Domain

This phase adds a new DB query path and extends two existing function signatures. ASVS coverage below.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a |
| V3 Session Management | no | n/a |
| V4 Access Control | yes | `user_id` scoping on all `signal_log` queries — must use `where(SignalLog.user_id == user_id)` |
| V5 Input Validation | yes | `user_id` is an int from authenticated session, not from user input. No additional validation needed beyond existing auth layer. |
| V6 Cryptography | no | No new encryption — signal metadata is operational data, not sensitive content |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| User A's signals influencing User B's ranking | Spoofing / Tampering | `user_id` WHERE clause on every signal query — enforced in `get_sender_multipliers()` |
| Signal metadata leaking raw email content | Information Disclosure | metadata only stores sender email (not subject or body) — SEC-04 contract maintained |
| `_capture_signal` storing attacker-controlled sender string | Tampering | Sender is extracted from `state.email_context` (loaded from authenticated adapter at session init), not from user utterance — not user-controlled |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | sigmoid(0) → 1.25 is the intended neutral; product intent is not "0 signals = exactly 1.0" | Architecture Patterns (Pattern 3), Open Questions | If 1.0 is required neutral, sigmoid formula needs a constant-shift input adjustment |
| A2 | `_extract_email()` normalisation in `session.py` is the canonical normalisation for email addresses throughout the codebase | Code Examples, Common Pitfalls | If adapters return pre-normalised bare addresses, double-normalisation is harmless; if they return display-name format and `_extract_email` is not applied, multiplier lookups will miss |
| A3 | Phase 8 does not add new capture points for `skip` and `re_request` signals | Open Questions | If product intent is to make those signals immediately useful (not just framework-ready), additional node wiring is needed |

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: codebase]` `src/daily/orchestrator/nodes.py` — `_capture_signal()` implementation, active callsites, absence of metadata
- `[VERIFIED: codebase]` `src/daily/profile/signals.py` — `SignalLog` ORM columns, `append_signal()` signature
- `[VERIFIED: codebase]` `src/daily/briefing/ranker.py` — `score_email()` and `rank_emails()` signatures, VIP logic
- `[VERIFIED: codebase]` `src/daily/briefing/context_builder.py` — `build_context()` call to `rank_emails()` at line 164
- `[VERIFIED: codebase]` `src/daily/briefing/pipeline.py` — `run_briefing_pipeline()` signature, no DB session today
- `[VERIFIED: codebase]` `src/daily/briefing/scheduler.py` — `_build_pipeline_kwargs()` pattern using `async with async_session() as session:`
- `[VERIFIED: codebase]` `src/daily/db/engine.py` — `async_session` factory, `make_session_factory()` pattern
- `[VERIFIED: codebase]` `src/daily/orchestrator/session.py` — `email_context` dict structure (keys: `message_id`, `sender`, `subject`, `thread_id`, `recipient`, `timestamp`)
- `[VERIFIED: codebase]` `tests/test_signal_log.py` — mock `AsyncSession` test pattern
- `[VERIFIED: codebase]` `tests/test_briefing_ranker.py` — `make_email()` helper, existing coverage baseline
- `[CITED: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB]` — JSONB column access and casting in SQLAlchemy 2.0

### Secondary (MEDIUM confidence)
- `[ASSUMED]` Sigmoid normalisation to [0.5, 2.0] — locked design decision from CONTEXT.md, formula is standard mathematical sigmoid with linear remap

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all tools already in use and tested
- Architecture: HIGH — based on direct codebase inspection of all relevant files
- Pitfalls: HIGH — derived from reading actual implementations, not assumptions
- Signal metadata gap: HIGH (VERIFIED) — confirmed by grep across all `append_signal` callsites
- Sigmoid midpoint: MEDIUM — formula is correct but product intent for "neutral" is an open question

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable domain — no external APIs involved)
