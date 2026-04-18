# Phase 12: Conversational Flow - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

User can interrupt the briefing mid-delivery, switch fluidly between briefing / Q&A / action modes within one session, and receive tone-adapted responses — all without breaking session state.

In scope:
- Sentence-level briefing segmentation and position tracking
- Resume command (explicit keyword + auto-offer fallback)
- Session-scoped tone adaptation triggered by explicit phrases and implicit signals
- Verbal acknowledgement of context shifts (hybrid mode switching)

Out of scope:
- Persisting tone changes across sessions (session-only flag)
- New action types or integration changes
- Web/dashboard UI

</domain>

<decisions>
## Implementation Decisions

### Briefing Resume — Segmentation
- **D-01:** Split briefing narrative into sentences before speaking. Iterate sentence-by-sentence in `voice/loop.py`, tracking a `briefing_cursor: int` index. On each `turn_manager.speak(sentence)` call that returns `completed=False`, stop iterating and set `state.briefing_cursor` to the next unspoken sentence index.
- **D-02:** `briefing_cursor: int | None` added to `SessionState`. `None` means no briefing in progress or briefing fully delivered. A non-None value means an unfinished briefing exists at that sentence index.

### Briefing Resume — Trigger
- **D-03:** Primary resume path: explicit keywords ("continue my briefing", "resume briefing", "go back to the briefing") matched in `route_intent()` and routed to a new `resume_briefing` node. This node re-speaks sentences from `state.briefing_cursor` onward.
- **D-04:** Fallback resume path: after a Q&A or action turn completes and `state.briefing_cursor` is not None, the system proactively offers: "Want me to continue your briefing?" before returning to listen. This is a short verbal prompt — no interrupt, no approval gate.

### Mode Switching
- **D-05:** No explicit `session_mode` field. The `briefing_cursor` field is the only mode signal needed — non-None means "there is an unfinished briefing". All routing stays via `route_intent()`.
- **D-06:** When the briefing is interrupted (user barges in), the voice loop speaks a short verbal acknowledgement before processing the user's utterance: "Sure — I'll pick up your briefing after." This is spoken immediately after the interrupt is detected, before `run_session()` is called.

### Tone Adaptation — Triggers
- **D-07:** Tone compression is triggered by both explicit phrases and implicit signals:
  - **Explicit**: "I'm in a rush", "keep it brief", "quick version", "short version", "make it snappy", "I'm busy"
  - **Implicit**: User responses < 5 words for two consecutive turns (rapid/clipped responses signal time pressure)
- **D-08:** Detection happens in `respond_node` (or a pre-node check) before invoking the LLM — not via a separate LLM call. Explicit phrases: substring match. Implicit: message length check on the last two user messages.

### Tone Adaptation — Scope
- **D-09:** Compression is session-scoped only. A `tone_override: str | None` field is added to `SessionState`. When compression triggers, set `tone_override = "brief"`. All subsequent LLM calls in that session read `tone_override` and append a compression instruction to the system prompt. No write to `UserPreferences` / DB — resets when session ends.

### Claude's Discretion
- Exact wording of the context-shift verbal acknowledgement ("Sure — I'll pick up your briefing after" is a guide, not a fixed string)
- Exact wording of the auto-offer resume prompt
- Whether the implicit trigger (< 5 words, 2 consecutive turns) needs tuning — start with these values
- Sentence splitting strategy (split on `.`, `?`, `!` or use `nltk.sent_tokenize` — whichever fits project deps)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Voice pipeline
- `src/daily/voice/loop.py` — `run_voice_session()`: current monolithic briefing speak (line ~187), main voice loop, barge-in handling
- `src/daily/voice/barge_in.py` — `VoiceTurnManager.speak()`: returns `completed=False` on interrupt; `_stop_event` coordination

### Orchestrator
- `src/daily/orchestrator/graph.py` — `route_intent()`: keyword routing, node names, how to add resume_briefing route
- `src/daily/orchestrator/nodes.py` — `respond_node`: tone/length preference usage in LLM prompts (lines ~68-89, ~173-174, ~483-484)
- `src/daily/orchestrator/state.py` — `SessionState`: current fields including `briefing_narrative`; new fields `briefing_cursor` and `tone_override` go here

### Requirements
- `.planning/ROADMAP.md` Phase 12 — CONV-01, CONV-02, CONV-03 success criteria
- `.planning/REQUIREMENTS.md` §CONV-01, CONV-02, CONV-03

### Prior phase patterns
- `.planning/phases/11-trusted-actions/11-CONTEXT.md` — `approval_node` pre-check pattern (top-of-node bypass without touching existing path) — same pattern for tone_override injection
- `.planning/phases/10-memory-transparency/10-CONTEXT.md` — `route_intent()` keyword extension pattern (how to add new keyword groups and node routes)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `VoiceTurnManager.speak()` — already returns `bool` on completion; sentence iteration just wraps it in a loop with index tracking
- `route_intent()` keyword pattern — copy the memory_keywords block to add `resume_briefing_keywords`; already handles priority ordering
- `state.preferences.get("tone", "conversational")` in `respond_node` — `tone_override` can slot in as a higher-priority override of the same field

### Established Patterns
- Session-state flags (not DB writes) for in-session behaviour: `autonomy_levels` loads once at session start; `tone_override` follows the same pattern but is set mid-session
- Top-of-node bypass without touching existing path: `approval_node` pre-check (Phase 11 D-06) — same structure for injecting tone_override into LLM prompt
- `route_intent()` priority order: memory → summarise → draft → respond. `resume_briefing` should slot in between memory and summarise (high specificity)

### Integration Points
- `voice/loop.py` briefing speak block (step 6, line ~187) → convert to sentence iteration loop
- `orchestrator/state.py` → add `briefing_cursor: int | None = None` and `tone_override: str | None = None`
- `orchestrator/graph.py route_intent()` → add `resume_briefing_keywords` block + return `"resume_briefing"`
- `orchestrator/nodes.py respond_node` → read `state.tone_override` before building system prompt

</code_context>

<specifics>
## Specific Ideas

- Verbal context-shift acknowledgement: "Sure — I'll pick up your briefing after." (exact wording at Claude's discretion)
- Auto-offer fallback after a turn completes with unfinished briefing: "Want me to continue your briefing?" (short verbal prompt, no interrupt gate)
- Implicit tone trigger: < 5 words for 2 consecutive user turns — start here, tune if needed

</specifics>

<deferred>
## Deferred Ideas

- Persisting tone changes across sessions (user says "always be brief") — would write to UserPreferences, future phase
- Per-section awareness in briefing (knowing "we were on calendar events") — could be added later as section labels on top of sentence cursor

</deferred>

---

*Phase: 12-conversational-flow*
*Context gathered: 2026-04-18*
