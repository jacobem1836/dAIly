# Phase 2: Briefing Pipeline - Research

**Researched:** 2026-04-05
**Domain:** Async pipeline orchestration, LLM summarisation, Redis caching, APScheduler, heuristic ranking
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Phase 1 adapters extended with body-fetch methods: `get_email_body(message_id: str) -> str` on `EmailAdapter`, and `get_message_text(message_id: str, channel_id: str) -> str` on `MessageAdapter`. Calendars have no body to fetch (event metadata is sufficient).
- **D-02:** Pipeline flow: list all metadata (24h) → rank all by heuristic → fetch bodies for top-N only. Body fetch never done for un-ranked items.
- **D-03:** Sender weight uses heuristics AND optional VIP list. Heuristic signals: direct-to-user vs CC/BCC, reply frequency in thread metadata, subject-line keywords (urgent, action required, FYI, deadline, by EOD, due today), sender domain match. VIP override via `daily vip add <email>` — VIP senders always score maximum sender weight.
- **D-04:** Ranking formula: `score = sender_weight + keyword_weight + recency_weight + thread_activity_weight`. Weights are heuristic constants at cold-start. Exact weight values are Claude's discretion.
- **D-05:** Email scope: list ALL emails from last 24h (metadata only). Rank all. Fetch bodies for top-N (default: 5, configurable via `daily config set briefing.email_top_n <N>`).
- **D-06:** Output format: flowing narrative — continuous spoken-English paragraphs. No bullet points. Sections: (1) critical emails, (2) calendar, (3) Slack. Each section one paragraph.
- **D-07:** Target length: 90–120 seconds of spoken content (~225–300 words). Pipeline instructs LLM to stay within this target.
- **D-08:** Briefing always covers all three data sources. If empty: "Nothing notable in [source] today."
- **D-09:** Pre-filter: (1) pass body through "summarise to key actionable facts" prompt (GPT-4.1 mini), then (2) regex-strip credential patterns. LLM for briefing generation receives summary, not raw body.
- **D-10:** Redaction runs per-item (each email/message independently), not per-briefing.
- **D-11:** LLM outputs are structured intent JSON only. Briefing output: `{ "narrative": "..." }`. LLM never calls adapters or holds credentials.
- **D-12:** APScheduler: pin 3.10.x (AsyncIOScheduler). 4.x is pre-release and flagged as a stability risk.
- **D-13:** Default precompute schedule: 05:00 local time. Configurable via `daily config set briefing.schedule_time HH:MM`. Persists across restarts.
- **D-14:** Redis cache: `{ "narrative": "...", "generated_at": ISO-8601, "version": int }`, TTL = 24h. Key: `briefing:{user_id}:{date}`. No audio caching (Phase 5).
- **D-15:** Cache miss → generate on-demand synchronously and cache immediately. Do not return "not ready" errors.
- **D-16:** Configurable items: briefing schedule time, email top-N count, VIP sender list. All stored persistently. CLI: `daily config set`, `daily vip add/remove/list`.

### Claude's Discretion

- Model routing for the pre-summarisation step (GPT-4.1 mini recommended)
- Exact heuristic weight constants for ranking formula
- Internal module structure for the pipeline (context builder, ranker, redactor, narrator)
- How briefing schedule is persisted (DB row vs config file)
- Exact Redis key schema and serialisation format beyond the shape defined in D-14

### Deferred Ideas (OUT OF SCOPE)

- Adaptive briefing length (Short when quiet, longer when inbox is heavy) — hardcoded to 90–120s
- Full PII detection (presidio) — M2+
- Audio caching — Phase 5
- BRIEF-07 (thread summarisation on demand) — Phase 3 scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRIEF-01 | System precomputes a morning briefing overnight (default 5am), caching the result for instant voice delivery | APScheduler 3.10.x AsyncIOScheduler + cron trigger; redis-py async SET with TTL=86400 |
| BRIEF-02 | User can configure the briefing precompute schedule time | APScheduler `reschedule_job` to update cron trigger; config stored in Postgres or JSON |
| BRIEF-03 | System ingests last 24h of email, ranks by heuristic priority | Extend EmailAdapter with `get_email_body`; scoring formula with sender/keyword/recency/thread weights |
| BRIEF-04 | System ingests today's and next 48h of calendar events, including conflict detection | `CalendarAdapter.list_events(since=now, until=now+48h)`; conflict = overlapping start/end ranges |
| BRIEF-05 | System ingests Slack mentions, DMs, and priority channels | Extend MessageAdapter with `get_message_text`; filter by `is_mention` and `is_dm` flags already in models |
| BRIEF-06 | Briefing narrative generated via LLM from pre-ranked, pre-summarised context | GPT-4.1 mini per-item summarisation + regex redaction → GPT-4.1 narrative generation → `{ "narrative": "..." }` |
| PERS-03 | Briefing priority ranking uses heuristic defaults at cold start | Heuristic scoring: sender_weight (VIP > direct > cc) + keyword_weight + recency_weight + thread_activity_weight |
| SEC-02 | Pre-filter/redaction layer sanitises external data before passing to LLM | GPT-4.1 mini summarise → regex strip credential patterns; no raw body reaches narrator LLM |
| SEC-05 | LLM outputs treated as intents only; backend validates and dispatches | Briefing output struct `{ "narrative": "..." }` is intent-only; no tools/credentials in LLM context |
</phase_requirements>

---

## Summary

Phase 2 builds the precomputed briefing pipeline: a scheduled cron job that ingests email/calendar/Slack data, applies heuristic priority ranking, summarises and redacts each item through a cheap LLM, assembles a context object, generates a flowing narrative via GPT-4.1, and caches the result in Redis with a 24h TTL. The pipeline is async throughout, driven by APScheduler 3.10.x `AsyncIOScheduler` integrated into FastAPI's lifespan. Phase 1's adapter abstractions are extended (not replaced) with body-fetch methods.

The key architectural constraint is the two-layer LLM split: GPT-4.1 mini handles per-item summarisation and redaction (cheap, per-item), while GPT-4.1 handles final narrative generation (one call, full context). This separation satisfies SEC-02 (no raw bodies reach the narrator LLM) and keeps costs predictable. A cache miss triggers synchronous on-demand generation rather than returning an error — the briefing always delivers.

The main implementation risk is APScheduler's SQLAlchemyJobStore requiring a **synchronous** database URL (psycopg2) even when the scheduler itself is async. The project's SQLAlchemy engine uses asyncpg; the jobstore must use a separate sync connection string. This is a known gotcha with a clear workaround: use `postgresql+psycopg2://` for the jobstore URL only, or persist the schedule in a simpler way (a Postgres row or a JSON config file read at startup).

**Primary recommendation:** Persist the schedule time as a simple DB row in a new `briefing_config` table (not in the APScheduler jobstore), read it at startup to configure the cron trigger, and update it via `reschedule_job` when the user runs `daily config set briefing.schedule_time`. This avoids the SQLAlchemyJobStore async-URL pitfall entirely.

---

## Standard Stack

### Core (Phase 2 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| apscheduler | 3.10.x (pin, not 3.11.x or 4.x) | Cron-triggered precompute | AsyncIOScheduler integrates with FastAPI asyncio loop; 4.x is alpha-only as of 2026-04-05 [VERIFIED: PyPI] |
| redis | 7.4.0 | Briefing cache reads/writes | redis-py 7.x ships native `redis.asyncio` — no separate aioredis needed [VERIFIED: PyPI] |
| openai | 2.30.0 | GPT-4.1 and GPT-4.1 mini API | Official SDK, async client, structured output support [VERIFIED: PyPI] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psycopg2-binary | 2.9.x | Sync Postgres driver for APScheduler jobstore | Only if using SQLAlchemyJobStore — required because APScheduler 3.x jobstore is sync-only |
| python-dateutil | 2.9+ | Timezone-aware datetime arithmetic for schedule time parsing | For converting HH:MM + local timezone to UTC cron parameters |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DB row for schedule config | APScheduler SQLAlchemyJobStore | Jobstore requires sync psycopg2 URL — adds a second DB connection. DB row is simpler and avoids the gotcha. |
| DB row for schedule config | Plain JSON config file | File works but races on concurrent writes; DB row is atomic and integrates with existing SQLAlchemy engine |
| GPT-4.1 for narrator | Claude 3.5 Sonnet | Use if structured output on long documents degrades; GPT-4.1 is the project standard |
| GPT-4.1 mini for redactor | GPT-4o mini | Both valid; GPT-4.1 mini is the project-standard cheap model per CLAUDE.md |

**Installation (Phase 2 additions):**
```bash
uv add "apscheduler>=3.10.0,<3.11.0" redis openai "python-dateutil>=2.9"
```

**Version verification:** [VERIFIED: PyPI 2026-04-05]
- `apscheduler`: 3.11.2 is latest stable; 3.10.4 is currently installed in the project venv. Pin to `>=3.10.0,<3.11.0` per D-12.
- `redis`: 7.4.0 is current stable on PyPI.
- `openai`: 2.30.0 is current stable on PyPI.
- APScheduler 4.x: alpha releases only (`4.0.0a1` through `4.0.0a6`). Do not use.

---

## Architecture Patterns

### Recommended Module Structure

```
src/daily/
├── briefing/
│   ├── __init__.py
│   ├── pipeline.py          # Orchestrates the full precompute run
│   ├── context_builder.py   # Fetches + assembles BriefingContext from adapters
│   ├── ranker.py            # Heuristic email scoring formula
│   ├── redactor.py          # Per-item GPT-4.1 mini summarise + regex strip
│   ├── narrator.py          # GPT-4.1 narrative generation → { "narrative": "..." }
│   ├── cache.py             # Redis read/write, key schema, TTL management
│   ├── scheduler.py         # APScheduler setup, lifespan integration
│   └── models.py            # BriefingContext, RankedEmail, RedactedItem, BriefingOutput
├── integrations/
│   ├── base.py              # EXTEND: add get_email_body / get_message_text (D-01)
│   └── ...                  # Concrete adapter implementations — add body methods
├── db/
│   └── models.py            # EXTEND: briefing_config table, vip_senders table
└── cli.py                   # EXTEND: daily config set, daily vip add/remove/list
```

### Pattern 1: APScheduler AsyncIOScheduler with FastAPI Lifespan

**What:** Attach the scheduler to FastAPI's `lifespan` async context manager so it starts and stops with the app.

**When to use:** Any FastAPI app that needs background cron jobs sharing the asyncio event loop.

```python
# Source: APScheduler docs + community pattern [ASSUMED pattern, verified via WebSearch]
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

scheduler = AsyncIOScheduler(timezone="local")

@asynccontextmanager
async def lifespan(app: FastAPI):
    schedule_time = await load_schedule_time_from_db()  # reads briefing_config row
    scheduler.add_job(
        run_briefing_pipeline,
        CronTrigger(hour=schedule_time.hour, minute=schedule_time.minute),
        id="briefing_precompute",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

**Reschedule when user updates config:**
```python
# Source: APScheduler 3.x docs [VERIFIED: apscheduler.readthedocs.io]
scheduler.reschedule_job(
    "briefing_precompute",
    trigger=CronTrigger(hour=new_hour, minute=new_minute),
)
```

### Pattern 2: Redis Async GET/SET with TTL

**What:** Use `redis.asyncio.Redis` (built into redis-py 7.x — no separate aioredis needed).

```python
# Source: redis-py asyncio docs [VERIFIED: redis.readthedocs.io/en/stable/examples/asyncio_examples.html]
import json
from redis.asyncio import Redis

async def cache_briefing(redis: Redis, user_id: int, date: str, payload: dict, ttl: int = 86400):
    key = f"briefing:{user_id}:{date}"
    await redis.set(key, json.dumps(payload), ex=ttl)

async def get_briefing(redis: Redis, user_id: int, date: str) -> dict | None:
    key = f"briefing:{user_id}:{date}"
    raw = await redis.get(key)
    return json.loads(raw) if raw else None
```

**Lifecycle — must call aclose():**
```python
redis_client = Redis(host="localhost", port=6379, decode_responses=True)
# At shutdown:
await redis_client.aclose()
```

### Pattern 3: Two-Layer LLM Pipeline (Redactor → Narrator)

**What:** Per-item cheap summarisation, then single narrative call with assembled context.

```python
# Source: [ASSUMED pattern based on CONTEXT.md D-09/D-10 and OpenAI SDK patterns]
import re
from openai import AsyncOpenAI

client = AsyncOpenAI()

CREDENTIAL_PATTERN = re.compile(
    r'(?:password|token|api_key|secret|Authorization)\s*[:=]\s*\S+',
    re.IGNORECASE
)

async def summarise_and_redact(raw_body: str) -> str:
    """Per-item: GPT-4.1 mini summarise + regex redact."""
    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Extract only the key actionable facts from this email body. Be concise. Omit pleasantries, signatures, and boilerplate."},
            {"role": "user", "content": raw_body},
        ],
        max_tokens=200,
    )
    summary = response.choices[0].message.content
    return CREDENTIAL_PATTERN.sub("[REDACTED]", summary)

async def generate_narrative(context: "BriefingContext") -> str:
    """Single GPT-4.1 call for final narrative."""
    response = await client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "Generate a morning briefing as a single flowing spoken-English narrative. Target 225-300 words (90-120 seconds when read aloud). Three paragraphs: critical emails, calendar, Slack. No lists or bullets."},
            {"role": "user", "content": context.to_prompt_string()},
        ],
        response_format={"type": "json_object"},
    )
    import json
    return json.loads(response.choices[0].message.content)["narrative"]
```

### Pattern 4: Heuristic Email Ranking

**What:** Score all email metadata items before any body fetch. Fetch bodies only for top-N.

```python
# Source: [ASSUMED — based on CONTEXT.md D-03/D-04 and domain knowledge]
from dataclasses import dataclass
from daily.integrations.models import EmailMetadata
from datetime import datetime, timezone

DEADLINE_KEYWORDS = frozenset([
    "urgent", "action required", "deadline", "by eod", "due today",
    "asap", "time sensitive", "response needed"
])

WEIGHT_VIP = 40
WEIGHT_DIRECT = 10       # direct-to-user in To:
WEIGHT_CC = 2            # user is CC'd
WEIGHT_KEYWORD_HIT = 8   # per deadline keyword in subject
WEIGHT_RECENCY_MAX = 15  # decays linearly over 24h
WEIGHT_THREAD_ACTIVE = 5 # thread has 3+ messages in metadata

def score_email(email: EmailMetadata, vip_senders: set[str], user_email: str, now: datetime) -> float:
    sender_weight = WEIGHT_VIP if email.sender in vip_senders else (
        WEIGHT_DIRECT if user_email.lower() in email.recipient.lower() else WEIGHT_CC
    )
    subject_lower = email.subject.lower()
    keyword_weight = sum(WEIGHT_KEYWORD_HIT for kw in DEADLINE_KEYWORDS if kw in subject_lower)
    hours_old = (now - email.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    recency_weight = WEIGHT_RECENCY_MAX * max(0, (24 - hours_old) / 24)
    thread_weight = WEIGHT_THREAD_ACTIVE if hasattr(email, 'thread_size') and email.thread_size >= 3 else 0
    return sender_weight + keyword_weight + recency_weight + thread_weight
```

### Pattern 5: Calendar Conflict Detection

**What:** Detect overlapping events from `list[CalendarEvent]` — purely in-memory datetime comparison.

```python
# Source: [ASSUMED — standard interval overlap logic]
from daily.integrations.models import CalendarEvent

def find_conflicts(events: list[CalendarEvent]) -> list[tuple[CalendarEvent, CalendarEvent]]:
    """Return pairs of overlapping non-all-day events."""
    timed = [e for e in events if not e.is_all_day]
    timed.sort(key=lambda e: e.start)
    conflicts = []
    for i, a in enumerate(timed):
        for b in timed[i+1:]:
            if b.start >= a.end:
                break
            conflicts.append((a, b))
    return conflicts
```

### Anti-Patterns to Avoid

- **Fetching all email bodies before ranking:** Wastes API quota on low-priority emails. Always rank metadata first, fetch bodies for top-N only (D-02).
- **Passing raw email bodies to the narrator LLM:** Violates SEC-02. Always run `summarise_and_redact` per item before assembling `BriefingContext`.
- **Using APScheduler SQLAlchemyJobStore with asyncpg URL:** The jobstore is synchronous — it cannot use `postgresql+asyncpg://`. Use a DB row for schedule config instead (see Pitfall 1).
- **Storing the narrative in PostgreSQL:** Raw narrative text is ephemeral; Redis with TTL is correct. Postgres is for durable config (schedule time, VIP list), not for briefing content.
- **Using `aioredis` package:** Deprecated and merged into redis-py 7.x. Use `redis.asyncio.Redis` directly.
- **Calling `scheduler.start()` without awaiting in async context:** AsyncIOScheduler's `start()` is synchronous — call it normally inside the lifespan, before `yield`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async cron scheduling | Custom asyncio.sleep loop | APScheduler 3.10.x AsyncIOScheduler | Handles missed jobs, timezone-aware triggers, job persistence, exception handling |
| Redis TTL caching | Custom dict + expiry daemon | redis-py 7.x `redis.asyncio` | Battle-tested, atomic SET with EX, handles serialisation edge cases |
| Regex credential stripping | Complex parser | Simple `re.compile` pattern set | Scope is "obvious patterns" (tokens, API keys, auth params) — not full PII engine (that's deferred per CONTEXT.md) |
| Calendar overlap detection | Graph algorithm | Simple sorted interval sweep | O(n²) is fine for <100 events/day; no library needed |
| LLM structured output parsing | Custom JSON parser | `response_format={"type": "json_object"}` + `json.loads` | OpenAI API guarantees valid JSON when json_object mode is set |

**Key insight:** The pipeline's complexity is in orchestration (ordering, error handling, async concurrency) not in any individual step. Keep each step simple and testable in isolation.

---

## Common Pitfalls

### Pitfall 1: APScheduler SQLAlchemyJobStore requires sync DB driver

**What goes wrong:** `SQLAlchemyJobStore(url=settings.database_url)` fails if `database_url` contains `postgresql+asyncpg://` — APScheduler's jobstore uses SQLAlchemy synchronously and cannot use asyncpg.

**Why it happens:** APScheduler 3.x's jobstore was designed before SQLAlchemy 2.0's async engine. The `SQLAlchemyJobStore` class uses sync SQLAlchemy operations internally.

**How to avoid:** Do NOT use SQLAlchemyJobStore. Instead, persist the schedule time as a simple row in a `briefing_config` table using the app's async SQLAlchemy engine. Read it at startup, pass to `scheduler.add_job(CronTrigger(...))`. Update via `scheduler.reschedule_job(...)` when user changes config.

**Warning signs:** `OperationalError` or `driver not found` on startup; any import of `psycopg2` that wasn't there before.

**Source:** [VERIFIED: GitHub agronholm/apscheduler issue #499]

### Pitfall 2: Redis decode_responses must be set for JSON strings

**What goes wrong:** `redis.get(key)` returns `bytes` by default. `json.loads(b"...")` fails silently on some decodings or produces unexpected types.

**Why it happens:** redis-py defaults to returning raw bytes. If `decode_responses=True` is not set, JSON parsing breaks.

**How to avoid:** Initialise the Redis client with `decode_responses=True`: `Redis(host=..., decode_responses=True)`. Alternatively, call `.decode("utf-8")` before `json.loads`.

**Warning signs:** `TypeError: the JSON object must be str, bytes or bytearray` with bytes-type input.

### Pitfall 3: APScheduler job added before scheduler.start() is a no-op on some versions

**What goes wrong:** Jobs added to the scheduler before `.start()` may not fire if the scheduler hasn't registered them with the event loop yet.

**Why it happens:** AsyncIOScheduler binds to the running event loop at `start()` time. In FastAPI lifespan, the event loop is running when the lifespan body executes — so calling `.start()` first, then `.add_job()` is safest.

**How to avoid:** Add jobs after `.start()` in the lifespan, or use `replace_existing=True` to re-add safely on restart.

### Pitfall 4: LLM narrative prompt not enforcing word count reliably

**What goes wrong:** GPT-4.1 frequently exceeds the 90–120 second target (225–300 words) unless the prompt is explicit about truncation, not just "concise".

**Why it happens:** LLMs interpret "concise" loosely. Word count targets in system prompts work better than qualitative descriptors.

**How to avoid:** Include: "Limit total output to 300 words. Stop at 300 words even if all items are not covered. Do not use lists or headers." in the system prompt. Verify in tests by asserting `len(narrative.split()) <= 350` as a soft gate.

### Pitfall 5: Calendar timezone handling for 48h window

**What goes wrong:** `list_events(since=now, until=now+timedelta(hours=48))` returns different results depending on whether `now` is timezone-naive or timezone-aware. Google Calendar API returns RFC 3339 datetimes with offsets; comparison with naive datetimes silently produces wrong results.

**Why it happens:** `datetime.now()` returns naive datetime; `datetime.now(tz=timezone.utc)` returns aware datetime.

**How to avoid:** Always use `datetime.now(tz=timezone.utc)` in the pipeline. CalendarEvent model already uses `datetime` for `start`/`end` — validate that concrete adapters return timezone-aware datetimes.

### Pitfall 6: OpenAI SDK v2.x API surface changed from v1.x

**What goes wrong:** Code written for `openai` 1.x (e.g. `openai.ChatCompletion.create(...)`) does not work with `openai` 2.x which ships a unified Responses API alongside the legacy Chat Completions API.

**Why it happens:** OpenAI 2.x renamed and restructured several interfaces.

**How to avoid:** Use `AsyncOpenAI().chat.completions.create(...)` — the Chat Completions interface is stable across 1.x and 2.x. Avoid using the newer Responses API unless specifically needed (it adds complexity with no Phase 2 benefit). Pin `openai>=2.0.0` in pyproject.toml.

---

## Code Examples

### APScheduler lifespan + dynamic reschedule
```python
# Source: APScheduler 3.x userguide + WebSearch-verified community pattern
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

scheduler = AsyncIOScheduler(timezone="UTC")  # Use UTC internally; convert user input to UTC

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = await load_briefing_config()  # reads briefing_config table
    scheduler.add_job(
        run_briefing_pipeline,
        CronTrigger(hour=config.schedule_hour_utc, minute=config.schedule_minute_utc),
        id="briefing_precompute",
        replace_existing=True,
        args=[config.user_id],
    )
    scheduler.start()
    yield
    scheduler.shutdown()

async def update_schedule(new_hour_utc: int, new_minute_utc: int):
    scheduler.reschedule_job(
        "briefing_precompute",
        trigger=CronTrigger(hour=new_hour_utc, minute=new_minute_utc),
    )
```

### Redis async client setup with lifespan
```python
# Source: redis-py asyncio docs [VERIFIED: redis.readthedocs.io]
from redis.asyncio import Redis

async def make_redis_client(host: str, port: int = 6379) -> Redis:
    return Redis(host=host, port=port, decode_responses=True)

# In lifespan:
redis_client = await make_redis_client("localhost")
yield  # app runs
await redis_client.aclose()
```

### Structured LLM output with json_object mode
```python
# Source: OpenAI API docs [VERIFIED: platform.openai.com]
response = await client.chat.completions.create(
    model="gpt-4.1",
    messages=[...],
    response_format={"type": "json_object"},
)
import json
result = json.loads(response.choices[0].message.content)
# result is guaranteed to be valid JSON dict
narrative: str = result["narrative"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `aioredis` (separate package) | `redis.asyncio` (built into redis-py 7.x) | redis-py 4.2+ (2022) | Do not install aioredis; it is deprecated |
| APScheduler 4.x pre-release | APScheduler 3.10.x stable | 4.x still alpha as of 2026-04-05 | Pin 3.10.x per D-12; 4.x has breaking API changes |
| `openai.ChatCompletion.create` (sync) | `AsyncOpenAI().chat.completions.create` | openai SDK v1.0 (2023) | Always use async client in FastAPI context |
| Separate venv for psycopg2 + asyncpg | asyncpg for app engine, psycopg2-binary for APScheduler jobstore only | Ongoing | Only relevant if using SQLAlchemyJobStore — avoided by DB-row config approach |

**Deprecated/outdated:**
- `aioredis`: Deprecated, merged into redis-py — do not use
- APScheduler 4.x: Alpha-only, do not use per D-12
- `openai.ChatCompletion.create`: Synchronous legacy interface — use `AsyncOpenAI`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Heuristic weight constants (WEIGHT_VIP=40, WEIGHT_DIRECT=10, etc.) produce useful ranking | Architecture Patterns / Pattern 4 | Briefing ranks low-priority emails first — user experience degrades; constants are tunable and low risk |
| A2 | `AsyncIOScheduler.start()` is synchronous in APScheduler 3.x (not a coroutine) | Architecture Patterns / Pattern 1 | If it were async, calling without `await` would silently fail; verify in implementation |
| A3 | OpenAI 2.x `chat.completions.create` interface is backward compatible with 1.x usage patterns | Standard Stack | Would require minor SDK migration; low risk |
| A4 | GPT-4.1 reliably produces valid JSON when `response_format={"type": "json_object"}` is set | Code Examples | Rare edge case where API returns non-JSON even with json_object mode — add try/except + retry |
| A5 | `briefing_config` DB row approach (vs SQLAlchemyJobStore) is sufficient for single-user M1 | Architecture | If multi-user support needed in Phase 2 (it isn't per scope), per-user scheduling would need rethinking |

---

## Open Questions (RESOLVED)

1. **Schedule time timezone handling**
   - What we know: User configures `HH:MM` via CLI. APScheduler CronTrigger accepts `hour`/`minute`.
   - What's unclear: Should schedule be stored in UTC or local time? The host machine's local timezone may differ from the user's timezone.
   - RESOLVED: Store in UTC. Accept user input in local time, convert at `daily config set` time using `python-dateutil` + `datetime.astimezone(timezone.utc)`. Implemented in Plan 04 Task 1.

2. **Briefing pipeline error handling — partial failures**
   - What we know: The pipeline fetches from three separate sources (email, calendar, Slack).
   - What's unclear: If one source fails (e.g. Slack token expired), should the whole briefing fail or proceed with available data?
   - RESOLVED: Proceed with available sources; include a one-sentence note per failed source ("Slack data unavailable today."). Log the error. Implemented in Plan 02 Task 2 partial failure handling.

3. **VIP sender list — storage and lookup**
   - What we know: `daily vip add <email>` stores to PostgreSQL. Scoring function needs the VIP set.
   - What's unclear: Should the VIP set be loaded once at pipeline start or queried per email?
   - RESOLVED: Load the full VIP set as a Python `frozenset[str]` once per pipeline run (single DB query). Implemented in Plan 02 build_context signature.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Local Redis + Postgres | Yes | 29.2.1 | — |
| Redis 7 (via Docker) | Briefing cache | Yes (Docker container running) | 7.x | — |
| PostgreSQL 15 (via Docker) | Config storage, token vault | Yes (Docker container running) | 15 | — |
| Python 3.11+ | Runtime | Yes (project requirement) | 3.11+ | — |
| openai SDK | GPT-4.1 calls | Not yet installed in venv | 2.30.0 on PyPI | Add to pyproject.toml |
| apscheduler 3.10.x | Cron scheduler | Not yet in venv | 3.10.4 on PyPI | Add to pyproject.toml |
| redis-py | Async cache client | Not yet in venv | 7.4.0 on PyPI | Add to pyproject.toml |
| OPENAI_API_KEY | LLM calls | Not verified | — | Must be set in .env before running pipeline |

**Missing dependencies with no fallback:**
- `OPENAI_API_KEY` — must be present in `.env` for GPT-4.1 and GPT-4.1 mini calls to work; Wave 0 plan should verify this env var is documented and add it to the `.env.example`.

**Missing dependencies with fallback:**
- None — all missing items are installable via `uv add` in Wave 0.

**Note:** Redis and Postgres containers are running under a different Docker network (`agent-a2132bbc-*`) — the project's `docker-compose.yml` is the canonical way to start them for development. The `docker-compose.yml` is confirmed to include both services.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRIEF-01 | Briefing is written to Redis cache after pipeline run | unit | `pytest tests/test_briefing_cache.py -x` | ❌ Wave 0 |
| BRIEF-02 | Schedule time update persists and reschedules job | unit | `pytest tests/test_briefing_scheduler.py -x` | ❌ Wave 0 |
| BRIEF-03 | Email scoring formula produces correct rank ordering | unit | `pytest tests/test_briefing_ranker.py -x` | ❌ Wave 0 |
| BRIEF-04 | Calendar events fetched for 48h window; conflicts detected | unit | `pytest tests/test_briefing_context.py::test_calendar -x` | ❌ Wave 0 |
| BRIEF-05 | Slack messages with is_mention/is_dm flags are included | unit | `pytest tests/test_briefing_context.py::test_slack -x` | ❌ Wave 0 |
| BRIEF-06 | Narrative output is a non-empty string ≤350 words; raw body not in output | unit | `pytest tests/test_briefing_narrator.py -x` | ❌ Wave 0 |
| PERS-03 | VIP sender scores higher than non-VIP sender with same keywords | unit | `pytest tests/test_briefing_ranker.py::test_vip_override -x` | ❌ Wave 0 |
| SEC-02 | Credential patterns are stripped from summarised bodies | unit | `pytest tests/test_briefing_redactor.py -x` | ❌ Wave 0 |
| SEC-05 | Pipeline output is `{ "narrative": "..." }` — no tool calls or credentials in output | unit | `pytest tests/test_briefing_narrator.py::test_output_structure -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_briefing_cache.py` — covers BRIEF-01 (use fakeredis or mock)
- [ ] `tests/test_briefing_scheduler.py` — covers BRIEF-02 (mock APScheduler `reschedule_job`)
- [ ] `tests/test_briefing_ranker.py` — covers BRIEF-03, PERS-03 (pure function, no mocks needed)
- [ ] `tests/test_briefing_redactor.py` — covers SEC-02 (mock OpenAI client)
- [ ] `tests/test_briefing_narrator.py` — covers BRIEF-06, SEC-05 (mock OpenAI client)
- [ ] `tests/test_briefing_context.py` — covers BRIEF-04, BRIEF-05 (mock adapters)
- [ ] `fakeredis` package — for testing Redis operations without a live Redis instance: `uv add --dev fakeredis`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — pipeline runs server-side, no user auth in pipeline itself |
| V3 Session Management | No | N/A — batch pipeline, no sessions |
| V4 Access Control | No | N/A — single-user M1 |
| V5 Input Validation | Yes | SEC-02: regex pattern strip + per-item LLM summarise before narrator LLM |
| V6 Cryptography | Inherited from Phase 1 | vault/crypto.py AES-256-GCM decryption — existing, not modified |

### Known Threat Patterns for LLM Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via email body | Tampering | Pre-summarisation step reduces raw content before it reaches narrator; narrative prompt uses system/user separation |
| Credential leakage in LLM context | Information Disclosure | Regex strip of `password:`, `token:`, `Authorization:`, `api_key=` patterns before LLM context assembly (D-09) |
| Raw body stored in Postgres | Information Disclosure | SEC-04 already enforced in Phase 1 models — `BriefingContext` is in-memory only, never persisted |
| Redis cache poisoning | Tampering | Redis is local only in M1; no external write path to briefing cache |
| LLM instructed to call external APIs | Elevation of Privilege | Narrator uses `response_format=json_object` + no tools registered — LLM cannot make API calls (D-11, SEC-05) |

---

## Sources

### Primary (HIGH confidence)
- PyPI registry — verified current versions: apscheduler 3.11.2 (3.10.4 in project venv), redis 7.4.0, openai 2.30.0 [VERIFIED: PyPI 2026-04-05]
- PyPI registry — confirmed APScheduler 4.x is alpha-only (4.0.0a1–a6) [VERIFIED: PyPI 2026-04-05]
- Phase 1 codebase — `base.py`, `models.py`, `db/models.py`, `config.py`, `pyproject.toml`, `docker-compose.yml` [VERIFIED: file reads]
- CONTEXT.md — all locked decisions D-01 through D-16 [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- APScheduler 3.x docs — SQLAlchemyJobStore sync-only requirement, AsyncIOScheduler + CronTrigger + reschedule_job [CITED: apscheduler.readthedocs.io/en/3.x]
- GitHub agronholm/apscheduler issue #499 — AsyncIOScheduler + SQLAlchemyJobStore OperationalError with asyncpg URL [CITED: github.com/agronholm/apscheduler/issues/499]
- redis-py asyncio examples — `redis.asyncio.Redis`, `decode_responses`, `aclose()` [CITED: redis.readthedocs.io/en/stable/examples/asyncio_examples.html]
- OpenAI API docs — `response_format={"type": "json_object"}`, `chat.completions.create`, async client [CITED: platform.openai.com/docs/models/gpt-4.1]
- WebSearch — APScheduler FastAPI lifespan pattern (multiple community sources confirming pattern) [MEDIUM: verified consistent across 3+ sources]

### Tertiary (LOW confidence)
- Heuristic weight constants (WEIGHT_VIP=40 etc.) — chosen based on relative importance intuition, not benchmarked [ASSUMED — A1]
- Regex credential patterns sufficient for M1 scope — based on CONTEXT.md guidance, not tested against real email corpora [ASSUMED — extension of D-09]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI registry
- Architecture: HIGH — based on Phase 1 codebase inspection + verified library patterns
- Pitfalls: HIGH — APScheduler async/sync gotcha verified via official GitHub issues; Redis decode_responses is documented behaviour
- Heuristic weights: LOW — assumed values, tunable in implementation

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (stable libraries; APScheduler 4.x status may change)
