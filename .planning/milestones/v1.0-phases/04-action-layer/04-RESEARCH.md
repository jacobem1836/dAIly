# Phase 4: Action Layer - Research

**Researched:** 2026-04-10
**Domain:** Human-in-the-loop approval flows, write-side integration adapters, append-only audit logging
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Preview-edit-confirm flow. System presents draft, user can request edits ("make it shorter", "change the time to 3pm"), then explicitly confirm or reject. Unlimited edit rounds until user confirms — no cap on revisions.
- **D-02:** LangGraph human-in-the-loop interrupt for the approval gate. Graph pauses at the approval node, persists state via AsyncPostgresSaver checkpointer, resumes on user input. Pending actions survive app restarts.
- **D-03:** On rejection, default behaviour is "ask why and offer alternatives" — system asks what the user would prefer instead and reworks the draft. This is configurable in user profile (`rejection_behaviour: ask_why | discard`). Rejected actions logged with status `rejected` in action_log.
- **D-04:** Structured card format in CLI — labelled key-value pairs (To, Subject, Body preview, Time, Attendees, etc.). Draft data model stores all fields; presentation layer adapts per surface. Phase 5 will add voice readout adaptation.
- **D-05:** LLM generates full draft content (email body, message text) using user's tone preference from profile. Not template-based — natural, personalised output.
- **D-06:** Draft generation uses the user's sent email history as style reference. Fetch recent sent emails via existing adapters, pass through redactor, include as few-shot examples in the LLM drafting prompt to match writing style.
- **D-07:** Known-contacts-only recipient whitelist. Only allow sending to addresses the user has previously emailed or received email from. New/unknown recipients trigger an explanation + explicit override prompt.
- **D-08:** Supported action types in M1: email replies (ACT-01), new email composition (to known contacts), Slack message replies (ACT-02), calendar create/reschedule (ACT-03).
- **D-09:** Action log stores: timestamp, action type, target (recipient/event), content summary (first 200 chars), SHA-256 hash of full body, approval status, outcome. Append-only table. Satisfies ACT-05 without storing full PII long-term (aligned with SEC-04).
- **D-10:** Separate `ActionExecutor` ABC with concrete implementations per provider (GmailExecutor, OutlookExecutor, SlackExecutor, GoogleCalendarExecutor). Read adapters stay read-only. Write path has separate security profile: extra validation, audit logging, approval gate. Single responsibility, independently auditable write paths.
- **D-11:** Write scopes requested upfront at OAuth connection time. No incremental scope grants — user grants read+write when connecting an account. Avoids mid-session re-auth complexity.

### Claude's Discretion

- Exact OrchestratorIntent action type extensions for Phase 4 (draft_email, draft_message, schedule_event, etc.)
- Internal module structure for the action layer package
- Action executor error handling and retry strategy
- How sent-email style examples are selected and formatted in the drafting prompt
- Contact whitelist storage mechanism (DB table vs in-memory from recent emails)
- Exact action_log table schema field names

### Deferred Ideas (OUT OF SCOPE)

- **Trusted auto-actions (M2+)** — Staged autonomy model where user grants auto-send permissions for specific contacts or action types. Out of scope per M1 constraints.
- **Undo/recall sent messages** — After-the-fact undo for recently sent emails (Gmail supports recall within 30s). Useful but adds complexity beyond M1 scope.
- **Rich text email composition** — M1 drafts are plain text. HTML formatting and attachments deferred.
- **Action templates/macros** — Predefined action templates ("decline meeting with reason") for common patterns. Future enhancement.
- **Batch actions** — "Reply to all three of those saying I'll be there" — multiple actions from one instruction. Future enhancement.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACT-01 | System can draft an email reply based on user instruction during briefing | GmailExecutor write pattern; Gmail API messages.send with In-Reply-To/References headers; LLM drafting node |
| ACT-02 | System can draft a Slack message reply based on user instruction during briefing | SlackExecutor write pattern; Slack SDK chat_postMessage with thread_ts; LLM drafting node |
| ACT-03 | System can create or reschedule a calendar event based on user instruction | GoogleCalendarExecutor; Calendar API events.insert + events.patch; LLM drafting node |
| ACT-04 | All external-facing actions require explicit user approval before execution — no bypass path exists in code | LangGraph interrupt() pattern; approval node in graph; Command(resume=...) for confirm/reject |
| ACT-05 | Every action attempt is logged with timestamp, action type, target, content summary, approval status, and outcome | action_log ORM model; append_action_log() service; fire-and-forget via asyncio.create_task() |
| ACT-06 | Action executor validates recipient, content type, and scope against a whitelist before dispatch | contact whitelist check in ActionExecutor.validate(); Pydantic models at all action boundaries |
</phase_requirements>

---

## Summary

Phase 4 adds a write-capable action layer on top of the existing read-only orchestrator. The three technical pillars are: (1) LangGraph `interrupt()` for the human-in-the-loop approval gate, (2) a new `ActionExecutor` ABC hierarchy parallel to the read adapters, and (3) an append-only `action_log` table for audit compliance.

The LangGraph interrupt pattern is well-understood and production-ready at version 1.1.6 (already locked in the project). `interrupt()` raises a special exception that the runtime catches, saves state to the `AsyncPostgresSaver` checkpointer, and suspends — surviving process restarts. `Command(resume=value)` resumes execution with the user's decision. The critical constraint is that `interrupt()` must not be wrapped in a bare `try/except` — doing so catches the internal exception and silently breaks the pause/resume lifecycle.

The write-side API patterns are straightforward extensions of patterns already established in Phase 1. Gmail replies require RFC 2822 MIME encoding plus `In-Reply-To`/`References` threading headers. Slack message replies use `chat_postMessage` with `thread_ts` as a string (not float — a known SDK gotcha). Google Calendar rescheduling uses `events.patch` for partial updates rather than full `events.update`.

**Primary recommendation:** Implement the approval gate first as a pure LangGraph node test with `MemorySaver`, then wire `ActionExecutor` implementations and the `action_log` table. The graph topology changes (approval node + executor nodes) are the highest-complexity piece; the write API calls themselves are low-risk.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.6 | Human-in-the-loop interrupt + state graph | Already in project; `interrupt()` is the canonical HITL primitive |
| langgraph-checkpoint-postgres | 3.0.5 | AsyncPostgresSaver — persist interrupted state across restarts | Already in project; required for D-02 |
| google-api-python-client | >=2.100.0 | Gmail + Google Calendar write API | Already in project; used by GmailAdapter, reference for GmailExecutor |
| slack-sdk | >=3.41.0 | Slack `chat_postMessage` | Already in project; used by SlackAdapter, reference for SlackExecutor |
| msgraph-sdk + msal | >=1.55.0 / >=1.35.0 | Microsoft Graph — Outlook send | Already in project |
| sqlalchemy | >=2.0.49 | ORM for action_log | Already in project; established async pattern |
| pydantic | 2.x | Draft models + action validation | Already in project; all data boundaries |
| cryptography | >=42.0.0 | AES-256-GCM token decrypt for executor auth | Already in project (SEC-01) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hashlib (stdlib) | — | SHA-256 hash of full draft body for action_log | Always — D-09 requires hash, not full body |
| asyncio (stdlib) | — | create_task for fire-and-forget audit log writes | Always — established pattern from Phase 3 |
| email.message (stdlib) | — | MIME message construction for Gmail send | Always — required for Gmail API RFC 2822 encoding |
| base64 (stdlib) | — | base64url encoding of MIME messages | Always — Gmail API requires this encoding |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LangGraph interrupt() | Custom state machine with DB polling | Custom approach loses restart-durability and requires building what LangGraph already provides |
| action_log append-only table | signal_log reuse | action_log has different schema (outcome, content_hash) — a separate table is cleaner |

**Installation:** No new packages required. All dependencies already in `pyproject.toml`.

---

## Architecture Patterns

### Recommended Module Structure

```
src/daily/
├── actions/
│   ├── __init__.py
│   ├── base.py          # ActionExecutor ABC + ActionDraft model + ActionResult model
│   ├── models.py        # ActionLog ORM model, ActionType enum, ApprovalStatus enum
│   ├── log.py           # append_action_log() service (parallel to profile/signals.py)
│   ├── whitelist.py     # contact whitelist check logic
│   ├── google/
│   │   ├── __init__.py
│   │   ├── email.py     # GmailExecutor(ActionExecutor)
│   │   └── calendar.py  # GoogleCalendarExecutor(ActionExecutor)
│   ├── slack/
│   │   └── executor.py  # SlackExecutor(ActionExecutor)
│   └── microsoft/
│       └── executor.py  # OutlookExecutor(ActionExecutor)
└── orchestrator/
    ├── graph.py         # EXTENDED: approval node + executor dispatch nodes
    ├── models.py        # EXTENDED: new Literal action types
    ├── nodes.py         # EXTENDED: draft_node, approval_node, execute_node
    └── state.py         # EXTENDED: pending_action field added
```

### Pattern 1: LangGraph interrupt() Approval Gate

**What:** A graph node calls `interrupt(payload)` to pause execution. The runtime saves state, returns control to the CLI, and waits. The CLI calls `graph.ainvoke(Command(resume=decision), config=config)` with the user's confirm/reject input. The graph resumes from the exact point it paused.

**When to use:** Every external-facing action — no exceptions. This is the only code path to execution (ACT-04).

**Example:**
```python
# Source: https://docs.langchain.com/oss/python/langgraph/interrupts
from langgraph.types import interrupt, Command
from typing import Literal

async def approval_node(state: SessionState) -> dict:
    """Pause execution and present draft to user for approval.

    CRITICAL: Do NOT wrap interrupt() in a bare try/except — it raises
    a special internal exception that must propagate to the LangGraph runtime.
    """
    draft = state.pending_action  # ActionDraft Pydantic model
    # interrupt() pauses here; state is checkpointed by AsyncPostgresSaver
    decision = interrupt({
        "draft_type": draft.action_type,
        "preview": draft.card_text(),  # structured CLI card
    })
    # Resumes here when Command(resume=decision) is invoked
    return {"approval_decision": decision}  # "confirm" | "reject" | "edit:<instruction>"

# CLI layer — after graph pauses:
# result = await graph.ainvoke(Command(resume="confirm"), config=config)
```

**Critical constraint:** `interrupt()` must not be wrapped in a bare `try/except`. The interrupt mechanism works by raising a special exception internally; catching it breaks the pause/resume lifecycle. [VERIFIED: docs.langchain.com/oss/python/langgraph/interrupts]

### Pattern 2: ActionExecutor ABC

**What:** Abstract base class for write operations, parallel to the existing read adapter ABCs in `src/daily/integrations/base.py`. Each executor has a `validate()` method (contact whitelist + scope check) and an `execute()` method that calls the external API.

**When to use:** All write operations route through an executor, never direct API calls from graph nodes.

```python
# Source: modelled on src/daily/integrations/base.py pattern
from abc import ABC, abstractmethod
from daily.actions.base import ActionDraft, ActionResult

class ActionExecutor(ABC):
    @abstractmethod
    async def validate(self, draft: ActionDraft) -> None:
        """Raise ValueError if draft fails whitelist/scope check (ACT-06)."""
        ...

    @abstractmethod
    async def execute(self, draft: ActionDraft) -> ActionResult:
        """Execute the approved action via external API. Returns outcome."""
        ...
```

### Pattern 3: Gmail Reply Execution

**What:** RFC 2822 MIME construction + base64url encoding + Gmail API `messages.send`. Threading requires `In-Reply-To` and `References` headers set to the original message's RFC 2822 message-id (the `<...@...>` form, not Gmail's internal ID).

```python
# Source: https://developers.google.com/workspace/gmail/api/guides/sending
import asyncio
import base64
from email.message import EmailMessage

async def _send_reply(self, draft: EmailDraft) -> str:
    def _build_and_send() -> str:
        msg = EmailMessage()
        msg.set_content(draft.body)
        msg["To"] = draft.recipient
        msg["Subject"] = f"Re: {draft.subject}"
        msg["In-Reply-To"] = draft.thread_message_id   # RFC 2822 message-id
        msg["References"] = draft.thread_message_id
        encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = (
            self._service.users()
            .messages()
            .send(userId="me", body={"raw": encoded, "threadId": draft.gmail_thread_id})
            .execute()
        )
        return result["id"]
    return await asyncio.to_thread(_build_and_send)
```

### Pattern 4: Slack Reply Execution

**What:** `chat_postMessage` with `thread_ts` as a string (must be string, not float). The `thread_ts` is the timestamp of the parent message.

```python
# Source: https://docs.slack.dev/reference/methods/chat.postMessage/
async def execute(self, draft: SlackDraft) -> ActionResult:
    # thread_ts MUST be a string — float causes silent failure (known SDK bug)
    response = await asyncio.to_thread(
        self._client.chat_postMessage,
        channel=draft.channel_id,
        text=draft.body,
        thread_ts=str(draft.thread_ts),  # CRITICAL: str(), not float
    )
    return ActionResult(success=response["ok"], message_ts=response["ts"])
```

### Pattern 5: Google Calendar Create/Reschedule

**What:** `events.insert` for new events; `events.patch` for partial updates (time changes only). Prefer `patch` over `update` for reschedules — update replaces the full resource and risks clobbering attendees, location, etc.

```python
# Source: https://developers.google.com/workspace/calendar/api/v3/reference/events/update
# Create
def _create_event(self, draft: CalendarDraft) -> str:
    body = {
        "summary": draft.title,
        "start": {"dateTime": draft.start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": draft.end_dt.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": a} for a in draft.attendees],
    }
    result = self._service.events().insert(calendarId="primary", body=body).execute()
    return result["id"]

# Reschedule — patch only the changed fields
def _reschedule_event(self, event_id: str, new_start, new_end) -> None:
    self._service.events().patch(
        calendarId="primary",
        eventId=event_id,
        body={
            "start": {"dateTime": new_start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": new_end.isoformat(), "timeZone": "UTC"},
        },
    ).execute()
```

### Pattern 6: AsyncPostgresSaver Setup

**What:** Required for D-02. `setup()` creates the checkpoint tables on first run. Connection must use `autocommit=True` and `row_factory=dict_row`.

```python
# Source: https://pypi.org/project/langgraph-checkpoint-postgres/
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def build_production_graph(db_uri: str):
    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        await checkpointer.setup()  # idempotent — safe to call on every startup
        graph = build_graph(checkpointer=checkpointer)
        return graph
```

### Pattern 7: action_log Append-Only Write

**What:** Parallel to `signal_log` from Phase 3. Fire-and-forget via `asyncio.create_task()` so audit writes never block the approval flow. SHA-256 hash of the draft body replaces the raw body (SEC-04 compliance).

```python
# Source: modelled on src/daily/profile/signals.py pattern [VERIFIED: codebase]
import hashlib

async def append_action_log(
    user_id: int,
    action_type: str,
    target: str,
    content_summary: str,   # first 200 chars
    full_body: str,          # hashed, not stored
    approval_status: str,    # "pending" | "approved" | "rejected"
    outcome: str | None,     # "sent" | "failed" | None
    session: AsyncSession,
) -> None:
    body_hash = hashlib.sha256(full_body.encode()).hexdigest()
    row = ActionLog(
        user_id=user_id,
        action_type=action_type,
        target=target,
        content_summary=content_summary[:200],
        body_hash=body_hash,
        approval_status=approval_status,
        outcome=outcome,
    )
    session.add(row)
    await session.commit()
```

### Pattern 8: OrchestratorIntent Extension

**What:** Phase 4 adds new Literal action types to `OrchestratorIntent.action`. All new types must be whitelisted here — Pydantic ValidationError blocks any LLM-injected unknown string (SEC-05).

```python
# src/daily/orchestrator/models.py — EXTENDED for Phase 4
action: Literal[
    "answer",
    "summarise_thread",
    "skip",
    "clarify",
    # Phase 4 additions:
    "draft_email",
    "draft_message",
    "schedule_event",
    "reschedule_event",
]
```

### Anti-Patterns to Avoid

- **Bare try/except around interrupt():** Catches the LangGraph internal exception and breaks pause/resume. Catch `Exception` only *outside* the node call, never inside.
- **thread_ts as float in Slack:** `chat_postMessage` silently succeeds but creates no thread. Always cast to `str()`.
- **Calling events.update instead of events.patch for reschedules:** `update` replaces the full event resource, clobbering attendees and metadata not included in the update body. Use `patch` for partial updates.
- **LLM calling executor directly:** SEC-05 enforces that the LLM produces intents only. The graph node reads the intent, validates it, routes to the executor. No `tools=` parameter in any LLM call.
- **Raw body in action_log:** Store `content_summary[:200]` and `sha256(full_body)` only. Never the full body (SEC-04/D-09).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph pause/resume with restart durability | Custom DB polling loop | LangGraph `interrupt()` + AsyncPostgresSaver | Checkpointing, versioning, and thread_id management already implemented; restart durability is non-trivial |
| MIME email construction | Manual string concatenation | `email.message.EmailMessage` (stdlib) | RFC 2822 compliance, header encoding, multi-part — many edge cases |
| Contact whitelist population | Separate "contacts" table | Derived from email metadata already ingested by GmailAdapter/OutlookAdapter | No new data fetch needed; already available from Phase 1/2 adapters |
| Audit log integrity | Custom log with editable rows | Append-only table (insert only, no update/delete on action_log) | Pattern already established by signal_log; append-only is the correct audit primitive |
| SHA-256 body fingerprint | Rolling hash or custom scheme | `hashlib.sha256` (stdlib) | Standard, no dependencies, sufficient for content integrity without storing PII |

**Key insight:** The approval flow and audit log are the novel pieces. The actual write API calls are straightforward — the complexity is in the state machine wrapping them, not in the Gmail/Calendar/Slack calls themselves.

---

## Common Pitfalls

### Pitfall 1: interrupt() Bare try/except Swallows the Pause Signal

**What goes wrong:** Node wraps `interrupt()` in `try/except Exception`, catches the internal `GraphInterrupt` exception, graph never actually pauses.
**Why it happens:** Developers instinctively catch all exceptions for safety.
**How to avoid:** Never wrap `interrupt()` in a bare `try/except`. Catch exceptions only outside the node at the graph invocation layer.
**Warning signs:** `graph.ainvoke()` returns normally instead of returning an interrupted state; `Command(resume=...)` invocations have no effect.

### Pitfall 2: Slack thread_ts Float vs String

**What goes wrong:** `chat_postMessage` returns `{'ok': True}` but no thread is created. The message appears as a top-level channel message instead.
**Why it happens:** Python slack-sdk accepts both float and string for `thread_ts` without raising an error, but only string creates the thread.
**How to avoid:** Always pass `thread_ts=str(original_ts)`.
**Warning signs:** Reply shows up as a new message in the channel rather than a thread reply.

### Pitfall 3: Gmail Reply Missing Thread Link

**What goes wrong:** Reply is sent successfully but appears as a separate conversation in Gmail, not threaded under the original.
**Why it happens:** Missing `In-Reply-To` and `References` headers, or using Gmail's internal message ID instead of the RFC 2822 message-id from the `Message-ID` header.
**How to avoid:** Fetch the original message's `Message-ID` header (the `<...@...>` form) and set both `In-Reply-To` and `References` to that value. The `threadId` parameter in the send body handles Gmail's internal threading.
**Warning signs:** Email delivered but shows as new conversation; no thread indicator in Gmail UI.

### Pitfall 4: AsyncPostgresSaver Missing setup()

**What goes wrong:** `AsyncPostgresSaver` raises `psycopg.errors.UndefinedTable` on first checkpoint write because the tables don't exist.
**Why it happens:** `setup()` is not idempotent by default — must be called explicitly on first run.
**How to avoid:** Call `await checkpointer.setup()` on application startup before compiling the graph. It is safe to call every startup.
**Warning signs:** `UndefinedTable` or `psycopg.errors.InvalidSqlStatementName` on first interrupt.

### Pitfall 5: Calendar events.update Clobbers Event Data

**What goes wrong:** Rescheduling an event removes attendees, location, and description that were not included in the update body.
**Why it happens:** `events.update` replaces the full resource — any fields omitted from the body are cleared.
**How to avoid:** Use `events.patch` for all partial updates (time changes, title changes). Only use `events.update` when replacing the full event body intentionally.
**Warning signs:** Attendees disappear from rescheduled meetings; description fields become blank.

### Pitfall 6: Pending Action State Lost on Restart Without Checkpointer

**What goes wrong:** User approves an action, process restarts before execution, action is lost with no audit record.
**Why it happens:** `MemorySaver` (used in tests) is in-process only. Production must use `AsyncPostgresSaver`.
**How to avoid:** Production graph always compiled with `AsyncPostgresSaver`. Tests use `MemorySaver`. The distinction is enforced by passing the checkpointer at graph construction time (existing pattern from Phase 3).
**Warning signs:** Interrupted state disappears after process restart.

---

## Code Examples

### Full Approval Flow in Graph

```python
# Source: modelled on graph.py pattern [VERIFIED: codebase] +
#         interrupt() docs [CITED: docs.langchain.com/oss/python/langgraph/interrupts]

from langgraph.types import interrupt, Command
from langgraph.graph import END, START, StateGraph
from daily.orchestrator.state import SessionState

async def draft_node(state: SessionState) -> dict:
    """Generate draft content via LLM (GPT-4.1), store in pending_action."""
    # ... LLM call, build ActionDraft, set state.pending_action ...
    return {"pending_action": draft}

async def approval_node(state: SessionState) -> dict:
    """Pause for user confirm/reject/edit. State persisted by checkpointer."""
    decision = interrupt({
        "preview": state.pending_action.card_text(),
        "action_type": state.pending_action.action_type,
    })
    return {"approval_decision": decision}

async def execute_node(state: SessionState) -> dict:
    """Execute approved action via ActionExecutor."""
    if state.approval_decision != "confirm":
        return {"messages": [AIMessage(content="Action cancelled.")]}
    executor = get_executor(state.pending_action)
    await executor.validate(state.pending_action)  # ACT-06
    result = await executor.execute(state.pending_action)
    asyncio.create_task(_log_action(state, "approved", result.outcome))
    return {"messages": [AIMessage(content=f"Done. {result.summary}")]}

def build_graph(checkpointer=None):
    builder = StateGraph(SessionState)
    builder.add_node("respond", respond_node)
    builder.add_node("summarise_thread", summarise_thread_node)
    builder.add_node("draft", draft_node)         # Phase 4 new
    builder.add_node("approval", approval_node)   # Phase 4 new
    builder.add_node("execute", execute_node)     # Phase 4 new
    # ... edges ...
    builder.add_edge("draft", "approval")
    builder.add_edge("approval", "execute")
    return builder.compile(checkpointer=checkpointer)
```

### SessionState Extension

```python
# src/daily/orchestrator/state.py — EXTENDED
from daily.actions.base import ActionDraft  # new

class SessionState(BaseModel):
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    briefing_narrative: str = ""
    active_user_id: int = 0
    preferences: dict = Field(default_factory=dict)
    active_section: str = ""
    # Phase 4 additions:
    pending_action: ActionDraft | None = None
    approval_decision: str | None = None  # "confirm" | "reject" | "edit:<instruction>"
```

### UserPreferences Extension

```python
# src/daily/profile/models.py — EXTENDED
class UserPreferences(BaseModel):
    tone: Literal["formal", "casual", "conversational"] = "conversational"
    briefing_length: Literal["concise", "standard", "detailed"] = "standard"
    category_order: list[str] = ["emails", "calendar", "slack"]
    # Phase 4 addition (D-03):
    rejection_behaviour: Literal["ask_why", "discard"] = "ask_why"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `interrupt_before` / `interrupt_after` on graph compile | `interrupt()` function inside node body | LangGraph 0.2+ | More precise interrupt placement; value returned at interrupt site; cleaner approval flow |
| `LangChain chains` for HITL | `LangGraph` with checkpointer | 2024 | LangGraph adds state persistence and restart durability |
| `events.update` for calendar changes | `events.patch` preferred for partial updates | Calendar API v3 (stable) | Avoids clobbering non-updated fields |
| python-jose for token handling | authlib | 2025 | python-jose near-abandoned; CLAUDE.md explicitly forbids it |

**Deprecated/outdated:**
- `interrupt_before`/`interrupt_after` as compile-time flags: These still work but `interrupt()` inside the node body is the modern pattern — more flexible, allows dynamic interrupt with arbitrary payload.
- `python-jose`: Explicitly banned in CLAUDE.md and CLAUDE.md stack notes. Authlib handles OAuth token storage.

---

## Runtime State Inventory

Phase 4 is not a rename/refactor phase. No existing runtime state needs migration.

New state introduced by Phase 4:
- `action_log` DB table (created via Alembic migration — no existing data to migrate)
- `AsyncPostgresSaver` checkpoint tables (created by `checkpointer.setup()` on first run — idempotent)
- `rejection_behaviour` preference key in `user_profile.preferences` JSONB (schema-less JSONB — defaults applied at read time via Pydantic, no migration needed)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | AsyncPostgresSaver checkpointer, action_log | via docker-compose | 15+ | MemorySaver (tests only) |
| LangGraph | interrupt() + graph | ✓ (pyproject.toml) | 1.1.6 | — |
| langgraph-checkpoint-postgres | AsyncPostgresSaver | ✓ (pyproject.toml) | 3.0.5 | — |
| google-api-python-client | GmailExecutor, CalendarExecutor | ✓ (pyproject.toml) | >=2.100.0 | — |
| slack-sdk | SlackExecutor | ✓ (pyproject.toml) | >=3.41.0 | — |
| msgraph-sdk | OutlookExecutor | ✓ (pyproject.toml) | >=1.55.0 | — |

**Missing dependencies with no fallback:** None. All required packages are already in `pyproject.toml`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml (existing) |
| Quick run command | `uv run pytest tests/test_action_*.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACT-01 | Draft email reply generation via LLM | unit (mock LLM + mock executor) | `uv run pytest tests/test_action_executor.py::test_gmail_draft -x` | Wave 0 |
| ACT-01 | GmailExecutor.execute() sends with correct threading headers | unit (mock Gmail service) | `uv run pytest tests/test_action_executor.py::test_gmail_send_headers -x` | Wave 0 |
| ACT-02 | SlackExecutor.execute() calls chat_postMessage with thread_ts as string | unit (mock Slack client) | `uv run pytest tests/test_action_executor.py::test_slack_thread_ts_string -x` | Wave 0 |
| ACT-03 | CalendarExecutor creates event with correct body | unit (mock Calendar service) | `uv run pytest tests/test_action_executor.py::test_calendar_create -x` | Wave 0 |
| ACT-03 | CalendarExecutor reschedules via patch not update | unit (mock Calendar service) | `uv run pytest tests/test_action_executor.py::test_calendar_reschedule_uses_patch -x` | Wave 0 |
| ACT-04 | Approval node pauses graph (interrupt fires) | unit (MemorySaver graph) | `uv run pytest tests/test_action_approval.py::test_interrupt_fires -x` | Wave 0 |
| ACT-04 | Graph resumes on Command(resume="confirm") | unit (MemorySaver graph) | `uv run pytest tests/test_action_approval.py::test_confirm_resumes -x` | Wave 0 |
| ACT-04 | Graph routes to cancelled path on Command(resume="reject") | unit (MemorySaver graph) | `uv run pytest tests/test_action_approval.py::test_reject_cancels -x` | Wave 0 |
| ACT-05 | append_action_log writes correct fields | unit (async_session fixture) | `uv run pytest tests/test_action_log.py::test_append_action_log -x` | Wave 0 |
| ACT-05 | action_log body_hash is SHA-256 of full body | unit | `uv run pytest tests/test_action_log.py::test_body_hash -x` | Wave 0 |
| ACT-06 | validate() rejects unknown recipient | unit | `uv run pytest tests/test_action_executor.py::test_unknown_recipient_rejected -x` | Wave 0 |
| ACT-06 | validate() passes known contact | unit | `uv run pytest tests/test_action_executor.py::test_known_contact_passes -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_action_*.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_action_executor.py` — covers ACT-01, ACT-02, ACT-03, ACT-06
- [ ] `tests/test_action_approval.py` — covers ACT-04
- [ ] `tests/test_action_log.py` — covers ACT-05

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | OAuth tokens from Phase 1; executors reuse decrypted credentials |
| V3 Session Management | yes | LangGraph thread_id scoping; checkpointed state tied to user session |
| V4 Access Control | yes | Contact whitelist (ACT-06); action type whitelist (OrchestratorIntent Literal) |
| V5 Input Validation | yes | Pydantic at all draft/action model boundaries; OrchestratorIntent Literal rejects unknown action types |
| V6 Cryptography | yes | cryptography lib AES-256-GCM for token decrypt; hashlib SHA-256 for body fingerprint |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM prompt injection targeting action types | Tampering | OrchestratorIntent Literal whitelist — ValidationError blocks unknown strings (SEC-05) |
| Executor called without approval gate | Elevation of Privilege | Executor nodes only reachable via approval_node in graph topology; no direct call path |
| PII stored in action_log full body | Information Disclosure | Store `content_summary[:200]` + `sha256(body)` only (D-09 / SEC-04) |
| Unknown/external recipient email | Tampering | Contact whitelist in `validate()` (ACT-06 / D-07) |
| Credential leakage via draft body | Information Disclosure | Draft body passes through `summarise_and_redact()` before LLM style-matching (D-06) |
| Stale interrupted state from another user's session | Spoofing | `thread_id` includes `user_id` + date (established pattern from Phase 3 `session.py`) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sent email style examples from Gmail can be fetched via existing `GmailAdapter.list_emails()` + `get_email_body()` — no new Gmail API scope needed | Standard Stack | If "sent" folder requires `SENT` label filter beyond current scope, need to verify scope grants |
| A2 | Microsoft Outlook/Exchange write (send email) is available via msgraph-sdk with the scopes already requested in D-11 (read+write at connect time) | Standard Stack | If Outlook send requires a different Graph API scope, OAuth flow needs updating |
| A3 | `AsyncPostgresSaver.setup()` is idempotent and safe to call on every application startup | Architecture Patterns | If setup() is not idempotent, it must be guarded (e.g., env flag or migration table check) |

**Notes on A1:** The CONTEXT.md (D-06) describes fetching sent emails for style matching. The Gmail API `list_emails()` uses `q=after:{epoch}` — to filter sent emails specifically, the query should be `q=in:sent after:{epoch}`. This is a minor implementation detail within the existing scope. [ASSUMED — not verified against Gmail API docs in this session]

---

## Open Questions

1. **Outlook send scope confirmation**
   - What we know: CLAUDE.md lists `msgraph-sdk` and `msal` for Microsoft integration. D-11 locks write scopes to be requested at connect time.
   - What's unclear: Whether the exact Graph API scope for sending mail (`Mail.Send`) is already included in the Phase 1 OAuth flow or needs adding.
   - Recommendation: Verify `src/daily/integrations/microsoft/` OAuth scope list before implementing OutlookExecutor. Low risk — easy to add scope if missing.

2. **Contact whitelist population source**
   - What we know: CONTEXT.md (D-07) says whitelist is derived from email history — addresses the user has sent to or received from.
   - What's unclear: Claude's discretion on whether this is a DB table populated during briefing pipeline runs or a dynamic query against email metadata at action time.
   - Recommendation: DB table (`known_contacts`) populated/updated each time the briefing pipeline runs (email metadata already available). Avoids a real-time adapter call during the approval flow.

---

## Sources

### Primary (HIGH confidence)

- LangGraph interrupt() docs — [docs.langchain.com/oss/python/langgraph/interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — interrupt/Command/resume pattern
- Gmail API sending guide — [developers.google.com/workspace/gmail/api/guides/sending](https://developers.google.com/workspace/gmail/api/guides/sending) — MIME encoding, threading headers, drafts
- Google Calendar API events reference — [developers.google.com/workspace/calendar/api/v3/reference/events/update](https://developers.google.com/workspace/calendar/api/v3/reference/events/update) — patch vs update semantics
- Slack chat.postMessage docs — [docs.slack.dev/reference/methods/chat.postMessage/](https://docs.slack.dev/reference/methods/chat.postMessage/) — thread_ts parameter
- langgraph-checkpoint-postgres PyPI — [pypi.org/project/langgraph-checkpoint-postgres/](https://pypi.org/project/langgraph-checkpoint-postgres/) — AsyncPostgresSaver setup pattern
- Codebase: `src/daily/integrations/base.py`, `src/daily/orchestrator/graph.py`, `src/daily/orchestrator/state.py`, `src/daily/orchestrator/nodes.py`, `src/daily/profile/signals.py`, `src/daily/profile/models.py`, `src/daily/db/models.py`

### Secondary (MEDIUM confidence)

- LangGraph best practices blog — [sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025](https://sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025) — checkpointer production patterns
- Slack SDK GitHub issue #840 — [github.com/slackapi/python-slack-sdk/issues/840](https://github.com/slackapi/python-slack-sdk/issues/840) — thread_ts float vs string bug confirmation

### Tertiary (LOW confidence)

- None. All critical claims verified against official sources or codebase.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already in project; no new dependencies
- Architecture (LangGraph interrupt): HIGH — verified against official docs
- Architecture (write API patterns): HIGH — verified against official API docs
- Pitfalls: HIGH — verified against official docs and SDK issue tracker
- Contact whitelist design: MEDIUM — Claude's discretion; open question documented

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (LangGraph, Gmail/Calendar/Slack APIs are stable; interrupt API unlikely to change)
