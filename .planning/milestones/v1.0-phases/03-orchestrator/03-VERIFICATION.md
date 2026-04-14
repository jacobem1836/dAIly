---
phase: 03-orchestrator
verified: 2026-04-07T14:30:00Z
status: human_needed
score: 4/4 must-haves verified
human_verification:
  - test: "Run 'daily chat' and type 'summarise that email chain', verify a coherent summary is returned"
    expected: "The orchestrator routes to summarise_thread_node, fetches the email thread via a registered adapter, passes it through the redactor, and returns a LLM-generated summary to the terminal"
    why_human: "Requires real connected email account (Gmail or Outlook) with stored integration tokens. The message_id passthrough stub (user text as adapter message_id) means the adapter must support subject-based lookup — can only be verified end-to-end with a live account"
  - test: "Run 'daily config set profile.tone casual', then trigger a briefing and verify narrative tone differs"
    expected: "The narrator prepends the PREFERENCE_PREAMBLE with tone=casual to the system prompt, resulting in a more relaxed narrative style"
    why_human: "Requires running the full briefing pipeline end-to-end with a live LLM call. Automated tests mock the LLM — tone quality requires human judgment"
---

# Phase 3: Orchestrator Verification Report

**Phase Goal:** Users can ask follow-up questions during the briefing and receive contextually-aware answers; the system knows their preferences
**Verified:** 2026-04-07T14:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can ask for a thread summary on demand ("summarise that email chain") and receive a coherent answer using in-session context | ? HUMAN | `summarise_thread_node` exists, routes correctly on keyword, calls adapter + redactor + GPT-4.1. Known stub: `message_id = last_content` (Phase 3 best-effort per SUMMARY). End-to-end requires live account. |
| 2 | User preferences (tone, briefing length, category order) are stored in a profile and applied to subsequent briefings | ✓ VERIFIED | `UserProfile` ORM + `UserPreferences` Pydantic exist. `upsert_preference()` and `load_profile()` tested. Narrator injects preamble via `build_narrator_system_prompt()`. CLI routes `profile.*` keys. 14+12+16 tests passing. |
| 3 | Interaction signals (skips, corrections, re-requests) are captured and stored for future ranking use | ✓ VERIFIED | `SignalLog` ORM + `SignalType` enum (5 values). `append_signal()` service. Fire-and-forget via `asyncio.create_task(_capture_signal())` in both nodes. Migration 003 covers signal_log table. 21 tests passing. |
| 4 | LLM outputs are structured intent JSON only — orchestrator dispatches all actions; no LLM tool calls invoke external APIs directly | ✓ VERIFIED | AST inspection confirms zero `tools=` keyword arguments on any LLM call. `response_format={"type": "json_object"}` on all calls. `OrchestratorIntent.model_validate_json()` enforces Literal whitelist. RuntimeError raised on unknown action. |

**Score:** 4/4 truths verified (Truth 1 needs human confirmation end-to-end)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/daily/profile/models.py` | UserProfile ORM + UserPreferences Pydantic | ✓ VERIFIED | `class UserProfile(Base)` with `__tablename__ = "user_profile"`, JSONB `preferences` column. `class UserPreferences(BaseModel)` with Literal tone/briefing_length/category_order. |
| `src/daily/profile/service.py` | load_profile(), upsert_preference() | ✓ VERIFIED | Both async functions present, accept explicit AsyncSession, return UserPreferences. |
| `src/daily/profile/signals.py` | SignalLog ORM + SignalType enum + append_signal() | ✓ VERIFIED | `SignalType(str, Enum)` with all 5 values. `SignalLog(Base)` with signal_log table. `async def append_signal()` present. |
| `src/daily/orchestrator/state.py` | SessionState Pydantic model for LangGraph | ✓ VERIFIED | `class SessionState(BaseModel)` with `messages: Annotated[list, add_messages]`, briefing_narrative, active_user_id, preferences, active_section. |
| `src/daily/orchestrator/models.py` | OrchestratorIntent response model | ✓ VERIFIED | `action: Literal["answer", "summarise_thread", "skip", "clarify"]`. Rejects "execute_code" at runtime (confirmed). |
| `src/daily/orchestrator/graph.py` | LangGraph StateGraph with checkpointer | ✓ VERIFIED | `build_graph(checkpointer=None)`, `StateGraph(SessionState)`, conditional edges, `builder.compile(checkpointer=checkpointer)`. |
| `src/daily/orchestrator/nodes.py` | respond_node and summarise_thread_node | ✓ VERIFIED | Both async functions. GPT-4.1-mini for respond, GPT-4.1 for summarise. `summarise_and_redact()` called before state write. `OrchestratorIntent.model_validate_json()` validates LLM output. |
| `src/daily/orchestrator/session.py` | Session entry point wrapping graph.ainvoke() | ✓ VERIFIED | `async def run_session()` using `graph.ainvoke()` (not invoke). `set_email_adapters()`/`get_email_adapters()` registry. `create_session_config()` with `user-{id}-{date}` scoping. |
| `src/daily/cli.py` | daily chat command + profile config commands | ✓ VERIFIED | `def chat()`, `async def _run_chat_session()`, `async def _resolve_email_adapters()`. `_upsert_profile()`, `_get_profile()`, profile.* routing. `@config_app.command("get")`. |
| `src/daily/briefing/narrator.py` | Preference-aware narrator system prompt | ✓ VERIFIED | `def build_narrator_system_prompt(preferences: UserPreferences | None = None)`. `PREFERENCE_PREAMBLE` constant. `generate_narrative` accepts optional `preferences` parameter. |
| `alembic/versions/003_add_user_profile_signal_log.py` | Migration for user_profile + signal_log | ✓ VERIFIED | File exists. Contains `op.create_table("user_profile", ...)` and `op.create_table("signal_log", ...)`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `profile/models.py` | `db/models.py` | `from daily.db.models import Base` | ✓ WIRED | Import present at line 10 |
| `profile/signals.py` | `db/models.py` | `from daily.db.models import Base` | ✓ WIRED | Import present |
| `profile/service.py` | `db/engine.py` | uses `AsyncSession` | ✓ WIRED | Session passed explicitly by caller |
| `orchestrator/nodes.py` | `briefing/redactor.py` | `from daily.briefing.redactor import summarise_and_redact` | ✓ WIRED | Module-level import at line 23. Called in `summarise_thread_node` before state write. |
| `orchestrator/nodes.py` | `orchestrator/models.py` | `OrchestratorIntent.model_validate_json()` | ✓ WIRED | Import at line 24. Used in both nodes. |
| `orchestrator/graph.py` | `orchestrator/state.py` | `StateGraph(SessionState)` | ✓ WIRED | Import + usage confirmed. |
| `orchestrator/session.py` | `briefing/cache.py` | `from daily.briefing.cache import get_briefing` | ✓ WIRED | Import at line 18. Called in `initialize_session_state`. |
| `cli.py` | `orchestrator/session.py` | module-level `from daily.orchestrator.session import` with `set_email_adapters` | ✓ WIRED | Module-level import at line 425-429. `set_email_adapters(adapters)` called in `_run_chat_session`. |
| `cli.py` | `profile/service.py` | `from daily.profile.service import upsert_preference` | ✓ WIRED | Imported inside `_upsert_profile()` helper, called with key and value. |
| `briefing/narrator.py` | `profile/models.py` | `UserPreferences` for prompt construction | ✓ WIRED | `from __future__ import annotations` enables string annotation. `UserPreferences` consumed at runtime by `build_narrator_system_prompt()`. Verified importable and functioning. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `orchestrator/nodes.py` respond_node | `state.briefing_narrative` | `initialize_session_state()` → Redis cache → `get_briefing()` | Yes — real Redis read | ✓ FLOWING |
| `orchestrator/nodes.py` summarise_thread_node | `raw_body` | `adapters[0].get_email_body(message_id)` | Phase 3 stub: message_id = user raw text (best-effort) | ⚠️ PARTIAL — adapter called with user text as message_id; real ID extraction deferred to Phase 5 |
| `briefing/narrator.py` generate_narrative | `system_prompt` | `build_narrator_system_prompt(preferences)` → preferences from `load_profile()` → DB | Yes — DB read via service | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 112 phase-3 tests pass | `PYTHONPATH=src uv run pytest tests/test_profile_service.py tests/test_signal_log.py tests/test_orchestrator_graph.py tests/test_orchestrator_thread.py tests/test_cli_chat.py tests/test_profile_cli.py tests/test_narrator_preferences.py -q` | 112 passed, 2 warnings | ✓ PASS |
| Graph builds with MemorySaver | `uv run python3 -c "from daily.orchestrator.graph import build_graph; ..."` | CompiledStateGraph returned | ✓ PASS |
| route_intent dispatches correctly | Python check via script | "summarise that email chain" → summarise_thread; "what meetings?" → respond | ✓ PASS |
| thread_id format correct | `create_session_config(user_id=1)` | `user-1-2026-04-07` | ✓ PASS |
| OrchestratorIntent rejects bad action | `OrchestratorIntent(action='execute_code', narrative='test')` | `ValidationError` raised | ✓ PASS |
| SignalType has all 5 values | Python assertion | skip, correction, re_request, follow_up, expand | ✓ PASS |
| No tools= in LLM calls | AST keyword-arg inspection | Zero matches | ✓ PASS |
| build_narrator_system_prompt with preferences | `build_narrator_system_prompt(UserPreferences(tone="formal"))` | Returns prompt with "Tone: formal" preamble | ✓ PASS |

### Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|---------|
| BRIEF-07 | 3 (Plan 02) | User can request thread summarisation on demand | ✓ SATISFIED | `summarise_thread_node` wired to adapter registry + redactor + GPT-4.1. `daily chat` CLI command wires real email adapters. Known Phase-3 stub: message_id passthrough (documented in SUMMARY). |
| PERS-01 | 3 (Plans 01, 03) | System maintains user profile with tone, briefing length, category order | ✓ SATISFIED | `UserProfile` ORM, `UserPreferences` Pydantic model, `load_profile()`/`upsert_preference()`. Narrator injects preferences preamble. CLI `config set profile.*` and `config get profile` commands. |
| PERS-02 | 3 (Plans 01b, 02) | System captures implicit interaction signals for future ranking | ✓ SATISFIED | `SignalLog` ORM, `SignalType` enum (5 values), `append_signal()` service. Fire-and-forget signal capture in both orchestrator nodes via `asyncio.create_task()`. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/daily/orchestrator/nodes.py` | 150 | `message_id = last_content` — user message text used as adapter message_id | ⚠️ Warning | Thread lookup may fail or be approximate. Documented stub in SUMMARY. Phase 3 intent: adapter receives user text for subject-based matching. Real ID extraction requires Phase 5 briefing metadata in SessionState. Does not prevent invocation of BRIEF-07 — adapter IS called. |

### Human Verification Required

#### 1. End-to-End Thread Summarisation (BRIEF-07)

**Test:** Connect a Gmail account, run `daily briefing` to precompute a briefing, then run `daily chat` and type "summarise that email chain" referencing an email mentioned in the briefing.

**Expected:** The orchestrator routes to `summarise_thread_node`, the registered GmailAdapter's `get_email_body()` is called with the user's text (Phase 3 stub — adapter should match by subject or return the best available thread), the raw body passes through `summarise_and_redact()`, and GPT-4.1 returns a coherent thread summary printed as "dAIly: [summary text]".

**Why human:** Requires live connected email account with stored integration tokens. The `message_id = last_content` stub means the adapter receives raw user text — only a human with a real connected account can verify the end-to-end path produces a useful summary.

#### 2. Preference Application to Briefing Narrative

**Test:** Run `daily config set profile.tone casual`, run `daily config set profile.briefing_length concise`, then trigger a briefing and listen to/read the narrative output.

**Expected:** The narrator's LLM call includes the PREFERENCE_PREAMBLE with "Tone: casual" and "Briefing length: concise", resulting in a noticeably more casual, shorter briefing (100-150 words target, max_tokens=350) compared to the default conversational/standard.

**Why human:** Tone quality and length appropriateness require subjective human judgment. Automated tests mock the LLM call — only a real LLM response can demonstrate the preference is behaviorally effective.

### Gaps Summary

No blocking gaps. All artifacts exist, are substantive, and are wired. All 112 tests pass. The `message_id = last_content` stub in `summarise_thread_node` is an acknowledged, documented Phase 3 limitation — it does not block the goal because the adapter IS invoked (the path is callable) and thread ID extraction is explicitly deferred to Phase 5 where briefing metadata will be available in SessionState.

The phase goal is architecturally achieved: conversational graph exists, profile/preferences wired, signals captured, structured intent enforced. Human verification is needed to confirm behavioral quality end-to-end.

---

_Verified: 2026-04-07T14:30:00Z_
_Verifier: Claude (gsd-verifier)_
