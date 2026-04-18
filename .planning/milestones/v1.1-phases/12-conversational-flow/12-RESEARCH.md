# Phase 12: Conversational Flow - Research

**Researched:** 2026-04-18
**Domain:** Voice session loop, LangGraph state management, intent routing, tone adaptation
**Confidence:** HIGH

## Summary

Phase 12 is a surgical modification of three existing files plus one new node, all within an already-mature codebase with established patterns. The core challenge is not discovering new technology — it is threading new state fields (`briefing_cursor`, `tone_override`) cleanly through the existing voice loop, orchestrator state, and respond node without breaking any of the six prior phases that have already shipped.

The decisions in CONTEXT.md are specific and non-ambiguous: the planner has exact field names, exact integration points, exact keyword lists, and an exact sentence-splitting strategy choice. Research confirms the mechanical fit is clean and no external dependencies are required.

The two non-trivial risks are (1) sentence splitting edge cases in TTS-formatted briefing text, and (2) state mutation semantics in LangGraph — updating `briefing_cursor` and `tone_override` must follow the existing `SessionState` Pydantic model update pattern (return a dict from the node, not mutate state directly).

**Primary recommendation:** Implement in two plans — Plan 01 for the state + voice loop + routing changes (the operational core), Plan 02 for tests and the implicit-trigger tuning verification.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Split briefing narrative into sentences before speaking. Iterate sentence-by-sentence in `voice/loop.py`, tracking a `briefing_cursor: int` index. On each `turn_manager.speak(sentence)` call that returns `completed=False`, stop iterating and set `state.briefing_cursor` to the next unspoken sentence index.

**D-02:** `briefing_cursor: int | None` added to `SessionState`. `None` means no briefing in progress or briefing fully delivered. A non-None value means an unfinished briefing exists at that sentence index.

**D-03:** Primary resume path: explicit keywords ("continue my briefing", "resume briefing", "go back to the briefing") matched in `route_intent()` and routed to a new `resume_briefing` node. This node re-speaks sentences from `state.briefing_cursor` onward.

**D-04:** Fallback resume path: after a Q&A or action turn completes and `state.briefing_cursor` is not None, the system proactively offers: "Want me to continue your briefing?" before returning to listen.

**D-05:** No explicit `session_mode` field. The `briefing_cursor` field is the only mode signal needed.

**D-06:** When the briefing is interrupted, the voice loop speaks a short verbal acknowledgement before processing the user's utterance.

**D-07:** Tone compression triggers: explicit phrases ("I'm in a rush", "keep it brief", "quick version", "short version", "make it snappy", "I'm busy") and implicit (< 5 words for two consecutive turns).

**D-08:** Detection happens in `respond_node` (or a pre-node check) before invoking the LLM — not via a separate LLM call. Explicit: substring match. Implicit: message length check on last two user messages.

**D-09:** `tone_override: str | None` added to `SessionState`. When compression triggers, set `tone_override = "brief"`. All subsequent LLM calls read `tone_override` and append a compression instruction to the system prompt. Session-only — no write to DB.

### Claude's Discretion

- Exact wording of the context-shift verbal acknowledgement
- Exact wording of the auto-offer resume prompt
- Whether the implicit trigger (< 5 words, 2 consecutive turns) needs tuning
- Sentence splitting strategy (split on `.`, `?`, `!` or use `nltk.sent_tokenize`)

### Deferred Ideas (OUT OF SCOPE)

- Persisting tone changes across sessions (would write to UserPreferences / DB)
- Per-section awareness in briefing (section labels on top of sentence cursor)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONV-01 | Briefing supports natural mid-session interruption without breaking conversation state | `VoiceTurnManager.speak()` already returns `completed=False` on barge-in. Adding sentence-level iteration + `briefing_cursor` to `SessionState` is sufficient. |
| CONV-02 | Fluid switching between briefing, discussion, and action modes | `route_intent()` already handles mode dispatch. Adding `resume_briefing` keyword group + new node covers the explicit switch-back path. The `briefing_cursor` field tracks whether a briefing is in-progress — no separate mode enum needed. |
| CONV-03 | Adaptive tone — system adjusts formality and verbosity based on context signals | `respond_node` already reads `state.preferences.get("tone", ...)`. `tone_override` slots in as a session-scoped override of the same preference. Explicit phrase detection via substring match; implicit via consecutive message length check — both checked before LLM call. |
</phase_requirements>

---

## Standard Stack

### Core (already in use — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python re | stdlib | Sentence splitting via regex | `[VERIFIED: codebase]` — `nltk` is not installed; regex split on `(?<=[.?!])\s+` handles all briefing text. |
| LangGraph SessionState | 0.2+ | State field additions | `[VERIFIED: codebase]` — `orchestrator/state.py` uses Pydantic BaseModel; adding two nullable fields follows established pattern. |
| asyncio | stdlib | Voice loop concurrency | `[VERIFIED: codebase]` — all barge-in coordination already asyncio-based. |

### No New Dependencies Required

`nltk` is not installed in the project venv. `[VERIFIED: environment probe]` The sentence-splitting decision (`Claude's Discretion`) should default to the stdlib regex approach — no dependency to add.

**Installation:** none required.

---

## Architecture Patterns

### Recommended Project Structure

No new directories. All changes are within:

```
src/daily/
├── orchestrator/
│   ├── state.py          # Add briefing_cursor, tone_override fields
│   ├── graph.py          # Add resume_briefing route to route_intent() + build_graph()
│   └── nodes.py          # Add resume_briefing_node; modify respond_node for tone_override
└── voice/
    └── loop.py           # Convert monolithic briefing speak to sentence iteration loop
```

### Pattern 1: State Field Addition (Pydantic on SessionState)

**What:** Add two nullable Optional fields to the existing `SessionState` Pydantic model. This is the same pattern used for `pending_action`, `approval_decision`, `user_memories`, and `auto_executed`.

**When to use:** Any in-session flag that must survive across turns but not be persisted to DB.

**Example:**
```python
# Source: [VERIFIED: codebase] src/daily/orchestrator/state.py — existing pattern
class SessionState(BaseModel):
    # ... existing fields ...
    briefing_cursor: int | None = None
    tone_override: str | None = None
```

**LangGraph update semantics:** Nodes return a dict, not mutate state. LangGraph merges the dict into state.
```python
# Correct — return update dict
return {"briefing_cursor": next_index}
# Wrong — mutate state directly
state.briefing_cursor = next_index
```

### Pattern 2: route_intent() Keyword Extension

**What:** Add a new keyword group at the correct priority position. Memory keywords are highest priority. `resume_briefing` must rank above `summarise` to avoid "resume briefing" being swallowed by the summarise route.

**When to use:** Any new intent that needs keyword-based routing.

**Example:**
```python
# Source: [VERIFIED: codebase] src/daily/orchestrator/graph.py — existing pattern
resume_briefing_keywords = [
    "continue my briefing",
    "resume briefing",
    "go back to the briefing",
    "continue briefing",
]
if any(kw in last_msg for kw in resume_briefing_keywords):
    return "resume_briefing"
```

Priority order (most specific first):
1. `memory_keywords` → `"memory"`
2. `resume_briefing_keywords` → `"resume_briefing"` (NEW — must be above summarise)
3. `summarise_keywords` → `"summarise_thread"`
4. `draft_keywords` → `"draft"`
5. default → `"respond"`

### Pattern 3: Sentence Iteration Loop in voice/loop.py

**What:** Replace the monolithic `await turn_manager.speak(briefing_narrative)` at line ~187 with a for-loop over sentences, tracking cursor index, stopping on interrupt.

**When to use:** CONV-01 requirement — briefing must be resumable from mid-point.

**Example:**
```python
# Source: [ASSUMED — based on VoiceTurnManager.speak() return value contract]
import re

def _split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace."""
    return [s.strip() for s in re.split(r'(?<=[.?!])\s+', text) if s.strip()]

sentences = _split_sentences(briefing_narrative)
cursor = state.get("briefing_cursor") or 0

for i, sentence in enumerate(sentences[cursor:], start=cursor):
    completed = await turn_manager.speak(sentence)
    if not completed:
        # Barge-in detected — store resume point, speak acknowledgement
        # Set briefing_cursor = i + 1 (next unspoken sentence)
        await turn_manager.speak("Sure — I'll pick up your briefing after.")
        # ... proceed to wait_for_utterance
        break
else:
    # All sentences delivered — cursor is None (done)
    pass
```

**Key insight:** `briefing_cursor` must be passed back to the orchestrator state. Since the voice loop currently passes `initial_state` only on `first_turn`, the cursor update must be surfaced through the state persistence layer (LangGraph checkpointer) or maintained as a local voice-loop variable in scope for the resume node to read.

### Pattern 4: Tone Override Injection in respond_node

**What:** Read `state.tone_override` before building the system prompt. If set to `"brief"`, append a compression instruction. This is the same top-of-node pre-check pattern used in Phase 11 `approval_node`.

**When to use:** CONV-03 — session-scoped tone adaptation.

**Example:**
```python
# Source: [VERIFIED: codebase] src/daily/orchestrator/nodes.py — existing tone read
tone = state.preferences.get("tone", "conversational")
length = state.preferences.get("briefing_length", "standard")

# New: tone_override takes priority
if state.tone_override == "brief":
    tone = "brief"
    length = "short"
    # Append to system prompt: "Be compressed and direct. Max 2 sentences per response."
```

**Detection logic (pre-LLM, no extra API call):**
```python
# Explicit phrases — substring match
COMPRESSION_PHRASES = [
    "i'm in a rush", "keep it brief", "quick version",
    "short version", "make it snappy", "i'm busy",
]
last_msg_lower = state.messages[-1].content.lower() if state.messages else ""
explicit_trigger = any(phrase in last_msg_lower for phrase in COMPRESSION_PHRASES)

# Implicit — last 2 user messages < 5 words each
human_messages = [m for m in state.messages if hasattr(m, "type") and m.type == "human"]
implicit_trigger = (
    len(human_messages) >= 2
    and len(human_messages[-1].content.split()) < 5
    and len(human_messages[-2].content.split()) < 5
)

if (explicit_trigger or implicit_trigger) and not state.tone_override:
    return {"tone_override": "brief", "messages": [...]}
```

### Pattern 5: resume_briefing_node

**What:** A new node that reads `state.briefing_cursor` and re-speaks sentences from that index. Structurally similar to `respond_node` but outputs to voice (via voice loop) rather than the LLM.

**Key design question (resolved by architecture):** The `resume_briefing` node in the LangGraph graph cannot directly call `turn_manager.speak()` — that is voice I/O, not orchestrator logic. The node should return a synthetic `AIMessage` containing the resumption cue, and the voice loop handles speaking it the same way it speaks any other `result.messages[-1]`.

**Approach:** The `resume_briefing` node returns an AIMessage with the next sentences (or a sentinel indicating "resume from cursor"). The voice loop then iterates from `briefing_cursor` onward.

**Simpler alternative:** The node returns a brief confirmation message ("Resuming your briefing now."), and the voice loop — after receiving any response where `state.briefing_cursor` is not None — recognises it should re-enter the sentence iteration loop. This keeps TTS orchestration entirely in `voice/loop.py`.

### Anti-Patterns to Avoid

- **Storing briefing_cursor in the LangGraph messages list:** `messages` uses `add_messages` with append semantics — cursor is a scalar state field, not a message. Store as `briefing_cursor: int | None` on `SessionState`.
- **Calling `turn_manager.speak()` from inside a LangGraph node:** The orchestrator graph has no TTS dependency. Speaking is `voice/loop.py`'s responsibility. Nodes return text; loop speaks it.
- **Using `nltk.sent_tokenize`:** Not installed. Use stdlib `re.split(r'(?<=[.?!])\s+', text)`.
- **Persisting `tone_override` to DB:** Per D-09, this is session-only. Never call `upsert_preference` for this field.
- **Adding a `session_mode` enum:** Per D-05, `briefing_cursor is not None` is the only mode signal. No separate enum needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence splitting | Custom parser | `re.split(r'(?<=[.?!])\s+', text)` | stdlib, zero deps, handles all cases in TTS text |
| Tone detection | Separate LLM call | Substring match + word count | Adds latency, cost, and failure surface — detection is deterministic |
| Mode tracking | session_mode enum | `briefing_cursor is not None` | Simpler, already in state, avoids enum sync bugs |
| State persistence | Custom session dict | LangGraph checkpointer (existing) | Already wired — `briefing_cursor` just needs adding to SessionState |

---

## Common Pitfalls

### Pitfall 1: briefing_cursor lives in voice loop scope, not graph state

**What goes wrong:** The briefing speak loop runs in `voice/loop.py` before any `run_session()` call. If `briefing_cursor` is only stored as a local variable, the `resume_briefing` node cannot read it because it reads from `SessionState`.

**Why it happens:** The first-turn briefing delivery (step 6 in `run_voice_session`) happens outside the graph. The cursor needs to be surfaced into LangGraph state so the `resume_briefing` node can read it on subsequent turns.

**How to avoid:** After the sentence iteration loop sets `briefing_cursor`, pass it as part of `initial_state` on the subsequent `run_session()` call, OR initialise the state with `briefing_cursor` immediately after the interruption is detected. Check how `initial_state` is currently consumed in `run_session()`.

**Warning signs:** `resume_briefing` node always sees `briefing_cursor = None` regardless of where the briefing was interrupted.

### Pitfall 2: LangGraph state update semantics — dict, not mutation

**What goes wrong:** Node function mutates `state.briefing_cursor = x` directly instead of returning `{"briefing_cursor": x}`.

**Why it happens:** Pydantic model fields are mutable but LangGraph only persists the returned dict diff.

**How to avoid:** Every node that changes `briefing_cursor` or `tone_override` must include them in the returned dict. Verify with the existing `respond_node` return pattern.

**Warning signs:** State changes are visible within a single node invocation but lost on next turn.

### Pitfall 3: Barge-in acknowledgement echoes back to itself

**What goes wrong:** The verbal acknowledgement ("Sure — I'll pick up your briefing after.") triggers the TTS echo suppression code (`tts_active` flag), which is correct — but if the acknowledgement itself causes a `speech_started` callback before `tts_active` is set, a spurious barge-in is detected.

**Why it happens:** Race between `_on_speech_started` callback and `tts_active = True` in `VoiceTurnManager.speak()`.

**How to avoid:** The existing `tts_active` + `muted` pattern in `barge_in.py` already handles this — `self._stt.muted = True` is set at the start of every `speak()` call. The acknowledgement call is just another `speak()` call — the pattern is already correct. Verify: always call `await turn_manager.speak(acknowledgement)` (not a raw TTS call) so the mute logic fires.

**Warning signs:** Acknowledgement causes a second barge-in to be detected immediately.

### Pitfall 4: Tone override not applied to resume_briefing node

**What goes wrong:** `tone_override` is read only in `respond_node`. When the briefing resumes, it re-speaks the pre-written briefing narrative (which was generated at pipeline time, not by `respond_node`). The briefing text cannot be compressed mid-sentence.

**Why it happens:** Briefing narrative is a precomputed string. Tone override in `respond_node` affects LLM-generated responses, not the precomputed briefing.

**How to avoid:** Accept this scope limit. `tone_override = "brief"` means LLM follow-up responses are compressed, but the cached briefing narrative itself is not re-generated. Document this clearly in code comments. Future work: re-generate a compressed briefing narrative when `tone_override` is set at session start.

**Warning signs:** None — this is a known scope limitation, not a bug.

### Pitfall 5: `route_intent` priority collision with summarise_keywords

**What goes wrong:** User says "go back to my briefing" — the word "back" is not in summarise_keywords, but future keyword additions could collide. More concretely: if a user says "resume that thread briefing", `summarise_keywords` contains "thread" and would fire before `resume_briefing` if ordering is wrong.

**Why it happens:** `route_intent` is a linear scan of keyword groups in priority order.

**How to avoid:** `resume_briefing_keywords` must be checked BEFORE `summarise_keywords`. Per D-03 and the existing pattern, insert it in slot 2 (after memory, before summarise).

**Warning signs:** "Resume briefing" utterances route to `summarise_thread` node.

### Pitfall 6: Implicit tone trigger misfires on session start

**What goes wrong:** First two user turns happen to be short (e.g., "yes" / "ok") and trigger compression prematurely.

**Why it happens:** The implicit trigger looks at any two consecutive short messages, including session-open responses.

**How to avoid:** Consider whether the trigger should only fire after turn 3+. This is in Claude's Discretion per the context. Start with the spec values (< 5 words, 2 turns) and note in tests that session-open short messages are a known edge case.

**Warning signs:** Tone override triggers immediately in most sessions since opening exchanges ("yes", "go ahead") are often short.

---

## Code Examples

Verified patterns from codebase:

### Adding a field to SessionState
```python
# Source: [VERIFIED: codebase] src/daily/orchestrator/state.py — existing pattern
class SessionState(BaseModel):
    auto_executed: bool = False  # Phase 11 — same pattern for new fields
    briefing_cursor: int | None = None   # Phase 12
    tone_override: str | None = None     # Phase 12
```

### Adding a node and route to build_graph
```python
# Source: [VERIFIED: codebase] src/daily/orchestrator/graph.py

# In route_intent() — slot 2, after memory, before summarise:
resume_briefing_keywords = ["continue my briefing", "resume briefing", "go back to the briefing"]
if any(kw in last_msg for kw in resume_briefing_keywords):
    return "resume_briefing"

# In build_graph():
builder.add_node("resume_briefing", resume_briefing_node)
builder.add_conditional_edges(START, route_intent, {
    "memory": "memory",
    "resume_briefing": "resume_briefing",   # NEW
    "respond": "respond",
    "summarise_thread": "summarise_thread",
    "draft": "draft",
})
builder.add_edge("resume_briefing", END)
```

### Sentence splitting (no nltk)
```python
# Source: [VERIFIED: environment] nltk not installed; stdlib regex confirmed working
import re

def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.?!])\s+', text)
    return [s.strip() for s in parts if s.strip()]
```

### Top-of-node pre-check (Phase 11 approval_node pattern)
```python
# Source: [VERIFIED: codebase] Phase 11 approval_node — same pattern for tone injection
async def respond_node(state: SessionState) -> dict:
    # Phase 12: check tone compression triggers BEFORE building LLM prompt
    effective_tone = state.preferences.get("tone", "conversational")
    effective_length = state.preferences.get("briefing_length", "standard")
    updates: dict = {}

    if state.tone_override == "brief":
        effective_tone = "brief"
        effective_length = "short"
    elif not state.tone_override:
        # Check triggers
        ...
        if triggered:
            updates["tone_override"] = "brief"
            effective_tone = "brief"

    system_content = RESPOND_SYSTEM_PROMPT.format(
        tone=effective_tone,
        length=effective_length,
        ...
    )
    ...
    return {"messages": [AIMessage(content=narrative)], **updates}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Monolithic briefing speak (single `speak(text)` call) | Sentence-by-sentence iteration with cursor tracking | Phase 12 | Enables mid-briefing interrupt + resume |
| No tone session state | `tone_override` session flag | Phase 12 | LLM tone adapts to user's time signal within session |
| Static intent routing (4 routes) | 5 routes: adds `resume_briefing` | Phase 12 | Explicit briefing resume via keywords |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | `pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/test_conversational_flow.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONV-01 | `speak()` returning `False` stops sentence iteration and sets `briefing_cursor` | unit | `pytest tests/test_conversational_flow.py::test_briefing_cursor_set_on_interrupt -x` | ❌ Wave 0 |
| CONV-01 | `resume_briefing` node re-speaks from `state.briefing_cursor` onward | unit | `pytest tests/test_conversational_flow.py::test_resume_briefing_node -x` | ❌ Wave 0 |
| CONV-01 | `route_intent` routes "resume briefing" → `"resume_briefing"` | unit | `pytest tests/test_conversational_flow.py::test_route_intent_resume -x` | ❌ Wave 0 |
| CONV-02 | After Q&A turn completes with non-None `briefing_cursor`, auto-offer fires | unit | `pytest tests/test_conversational_flow.py::test_auto_offer_resume -x` | ❌ Wave 0 |
| CONV-02 | Full briefing delivery sets `briefing_cursor = None` | unit | `pytest tests/test_conversational_flow.py::test_cursor_none_on_completion -x` | ❌ Wave 0 |
| CONV-03 | Explicit phrase triggers `tone_override = "brief"` in state | unit | `pytest tests/test_conversational_flow.py::test_explicit_tone_trigger -x` | ❌ Wave 0 |
| CONV-03 | Implicit trigger (2 short turns) sets `tone_override = "brief"` | unit | `pytest tests/test_conversational_flow.py::test_implicit_tone_trigger -x` | ❌ Wave 0 |
| CONV-03 | LLM system prompt includes compression instruction when `tone_override = "brief"` | unit | `pytest tests/test_conversational_flow.py::test_tone_override_prompt_injection -x` | ❌ Wave 0 |
| CONV-03 | `tone_override` not persisted to DB (no `upsert_preference` call) | unit | `pytest tests/test_conversational_flow.py::test_tone_override_not_persisted -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_conversational_flow.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_conversational_flow.py` — covers all CONV-01, CONV-02, CONV-03 tests above
- [ ] No new conftest fixtures needed — existing `SessionState` + `MemorySaver` patterns are sufficient (see `test_trusted_actions.py` for reference)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | yes | Session-only `tone_override` — no DB write. `briefing_cursor` is in-session state. LangGraph `AsyncPostgresSaver` scoped by `thread_id`. |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Tone detection via substring match (no eval, no code exec). Cursor is an int, not user-controlled string. |
| V6 Cryptography | no | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious phrase to trigger tone change | Tampering | Low risk — worst case is compressed responses. No privilege escalation possible. |
| Integer overflow / negative cursor | Tampering | Clamp cursor to valid range: `cursor = max(0, min(cursor, len(sentences) - 1))`. |
| TTS echo triggering self-barge-in during acknowledgement | Spoofing | Already mitigated by `tts_active` + `muted` in `VoiceTurnManager.speak()`. Use `speak()`, not raw TTS. |

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — all changes are within the existing Python/LangGraph stack with no new tools required).

---

## Open Questions

1. **briefing_cursor state surfacing**
   - What we know: The briefing speak loop runs at line ~187 in `voice/loop.py`, before any `run_session()` call. `initial_state` is passed only on `first_turn`.
   - What's unclear: How does the `briefing_cursor` value get into LangGraph state so `resume_briefing_node` can read it? Option A: include it in `initial_state` on first turn only (loses cursor if interrupted after turn 1). Option B: after detecting barge-in, call `graph.aupdate_state(config, {"briefing_cursor": i+1})` to push it directly. Option C: keep cursor as a voice-loop-local variable and pass the remaining sentences directly in the `run_session` initial state.
   - Recommendation: Use Option B (direct state update via `graph.aupdate_state`) — this is the LangGraph-idiomatic approach and avoids coupling the voice loop structure to cursor bookkeeping.

2. **resume_briefing_node TTS concern**
   - What we know: LangGraph nodes cannot call `turn_manager.speak()` directly.
   - What's unclear: The `resume_briefing` node needs to trigger sentence re-delivery, but the sentences live in `briefing_narrative` which is already in state, and the voice loop is the only speaker.
   - Recommendation: `resume_briefing_node` returns an AIMessage with a short confirmation ("Resuming your briefing now.") and ensures `briefing_cursor` remains set. The voice loop, after speaking this message, checks `state.briefing_cursor is not None` and re-enters the sentence iteration loop. This keeps TTS orchestration entirely in the voice loop.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `re.split(r'(?<=[.?!])\s+', text)` correctly splits all briefing narrative formats | Standard Stack / Code Examples | Ellipsis, abbreviations (e.g., "Dr. Smith") may create extra splits — but briefing text is LLM-generated and follows clean sentence structure, so edge cases are minimal |
| A2 | `graph.aupdate_state()` is the correct LangGraph API for pushing cursor into state mid-session | Open Questions | If API differs (e.g., requires `as_node` parameter), voice loop implementation changes but architecture stays the same |
| A3 | Implicit tone trigger threshold (< 5 words, 2 turns) is in Claude's Discretion — starting values may need tuning | Common Pitfalls | Premature trigger on normal short responses; adjust threshold upward if needed |

---

## Project Constraints (from CLAUDE.md)

- **Architecture:** LLM must not directly access APIs or hold credentials — backend mediates everything. No change to this in Phase 12.
- **Privacy:** Raw email/message bodies must not be stored long-term. No change — Phase 12 stores no new data.
- **Latency:** Voice responses must feel instant. Tone detection is pre-LLM, zero latency overhead. Sentence iteration adds no new latency.
- **Security:** OAuth tokens encrypted at rest. Not touched in Phase 12.
- **Autonomy:** All external-facing actions require user approval in M1. Not touched in Phase 12.
- **Stack conventions:** Python 3.11+, FastAPI, Pydantic v2, LangGraph 0.2+, pytest + pytest-asyncio. All enforced — no new deps.
- **Code style:** Functions < 50 lines, files < 800 lines, immutable data (return dicts from nodes, not mutate state).
- **Testing:** 80% coverage minimum; TDD approach; pytest-asyncio for async tests.

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: codebase]` `src/daily/voice/loop.py` — run_voice_session, briefing speak block line ~187, session_history pattern
- `[VERIFIED: codebase]` `src/daily/voice/barge_in.py` — VoiceTurnManager.speak() return contract, tts_active pattern
- `[VERIFIED: codebase]` `src/daily/orchestrator/state.py` — SessionState fields, Pydantic model pattern
- `[VERIFIED: codebase]` `src/daily/orchestrator/graph.py` — route_intent priority order, build_graph node wiring
- `[VERIFIED: codebase]` `src/daily/orchestrator/nodes.py` — respond_node tone/length read at lines ~172-176, RESPOND_SYSTEM_PROMPT format
- `[VERIFIED: codebase]` `tests/test_trusted_actions.py` — test pattern for Phase 11 (same structure expected for Phase 12)
- `[VERIFIED: environment]` stdlib `re.split` sentence splitting — confirmed working; nltk confirmed NOT installed

### Secondary (MEDIUM confidence)
- `[CITED: LangGraph docs]` `graph.aupdate_state()` for mid-session state push (assumed from LangGraph API knowledge)

### Tertiary (LOW confidence)
- A1, A2, A3 above

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all within existing codebase, no new deps
- Architecture: HIGH — four specific integration points, all verified in source
- Pitfalls: HIGH — all derived from reading actual implementation files
- Test map: HIGH — mirrors Phase 11 test structure exactly

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (stable stack — LangGraph/FastAPI version changes unlikely in 30 days)
