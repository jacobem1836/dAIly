# Phase 4: Action Layer - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can instruct the system to draft replies (email, Slack) and calendar changes, approve them through a preview-edit-confirm flow, and see a full audit trail. All external-facing actions require explicit user approval before execution. No voice interface (Phase 5) — interaction surface is CLI text. No trusted auto-actions (M2+).

Requirements in scope: ACT-01, ACT-02, ACT-03, ACT-04, ACT-05, ACT-06

</domain>

<decisions>
## Implementation Decisions

### Approval Flow
- **D-01:** Preview-edit-confirm flow. System presents draft, user can request edits ("make it shorter", "change the time to 3pm"), then explicitly confirm or reject. Unlimited edit rounds until user confirms — no cap on revisions.
- **D-02:** LangGraph human-in-the-loop interrupt for the approval gate. Graph pauses at the approval node, persists state via AsyncPostgresSaver checkpointer, resumes on user input. Pending actions survive app restarts.
- **D-03:** On rejection, default behaviour is "ask why and offer alternatives" — system asks what the user would prefer instead and reworks the draft. This is configurable in user profile (`rejection_behaviour: ask_why | discard`). Rejected actions logged with status `rejected` in action_log.

### Draft Presentation
- **D-04:** Structured card format in CLI — labelled key-value pairs (To, Subject, Body preview, Time, Attendees, etc.). Draft data model stores all fields; presentation layer adapts per surface. Phase 5 will add voice readout adaptation.
- **D-05:** LLM generates full draft content (email body, message text) using user's tone preference from profile. Not template-based — natural, personalised output.
- **D-06:** Draft generation uses the user's sent email history as style reference. Fetch recent sent emails via existing adapters, pass through redactor, include as few-shot examples in the LLM drafting prompt to match writing style.

### Action Sandboxing & Validation (ACT-06)
- **D-07:** Known-contacts-only recipient whitelist. Only allow sending to addresses the user has previously emailed or received email from. New/unknown recipients trigger an explanation + explicit override prompt ("X isn't in your contacts. Add them and retry, or cancel?").
- **D-08:** Supported action types in M1: email replies (ACT-01), new email composition (to known contacts), Slack message replies (ACT-02), calendar create/reschedule (ACT-03).
- **D-09:** Action log stores: timestamp, action type, target (recipient/event), content summary (first 200 chars), SHA-256 hash of full body, approval status, outcome. Append-only table. Satisfies ACT-05 without storing full PII long-term (aligned with SEC-04).

### Adapter Write Methods
- **D-10:** Separate `ActionExecutor` ABC with concrete implementations per provider (GmailExecutor, OutlookExecutor, SlackExecutor, GoogleCalendarExecutor). Read adapters stay read-only. Write path has separate security profile: extra validation, audit logging, approval gate. Single responsibility, independently auditable write paths.
- **D-11:** Write scopes requested upfront at OAuth connection time. No incremental scope grants — user grants read+write when connecting an account. Avoids mid-session re-auth complexity.

### Claude's Discretion
- Exact OrchestratorIntent action type extensions for Phase 4 (draft_email, draft_message, schedule_event, etc.)
- Internal module structure for the action layer package
- Action executor error handling and retry strategy
- How sent-email style examples are selected and formatted in the drafting prompt
- Contact whitelist storage mechanism (DB table vs in-memory from recent emails)
- Exact action_log table schema field names

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — ACT-01 through ACT-06 (action layer requirements), SEC-04 (no raw bodies long-term), SEC-05 (LLM is intent-only)
- `.planning/ROADMAP.md` §Phase 4 — Success criteria (5 items) and phase dependencies

### Product & Architecture
- `CLAUDE.md` §Technology Stack — LangGraph human-in-the-loop interrupts, Google API client, Slack SDK, Microsoft Graph SDK
- `CLAUDE.md` §Constraints — LLM never holds credentials, orchestrator dispatches all actions, all external actions require approval in M1
- `CLAUDE.md` §Stack Patterns — "Human-in-the-Loop Approval" variant: LangGraph interrupt holds execution pending user approval

### Phase 3 — Orchestrator (upstream)
- `src/daily/orchestrator/models.py` — OrchestratorIntent with Literal action whitelist (Phase 4 extends this with new action types)
- `src/daily/orchestrator/graph.py` — LangGraph StateGraph, route_intent(), build_graph() (Phase 4 adds approval node and action executor nodes)
- `src/daily/orchestrator/nodes.py` — respond_node, summarise_thread_node (Phase 4 adds draft and execute nodes)
- `src/daily/orchestrator/state.py` — SessionState (Phase 4 extends with pending action state)
- `src/daily/profile/signals.py` — SignalType enum, append_signal() (Phase 4 adds action-related signal types)

### Phase 1 — Foundation (upstream)
- `src/daily/integrations/base.py` — EmailAdapter, CalendarAdapter, MessageAdapter ABCs (Phase 4 creates parallel ActionExecutor ABCs)
- `src/daily/integrations/google/` — Gmail and Calendar concrete adapters (reference for creating executor implementations)
- `src/daily/integrations/slack/` — Slack adapter (reference for SlackExecutor)
- `src/daily/integrations/microsoft/` — Outlook adapter (reference for OutlookExecutor)
- `src/daily/db/models.py` — Existing ORM models (Phase 4 adds action_log table)
- `src/daily/db/engine.py` — Async SQLAlchemy engine (reused for action_log)

### Phase 2 — Briefing Pipeline (upstream)
- `src/daily/briefing/redactor.py` — summarise_and_redact() pattern (reused for redacting sent email style examples)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/orchestrator/graph.py` — LangGraph StateGraph with checkpointer. Phase 4 extends with approval and executor nodes.
- `src/daily/orchestrator/models.py` — OrchestratorIntent Literal validation pattern. Phase 4 extends the action whitelist.
- `src/daily/briefing/redactor.py` — summarise_and_redact(). Reuse for sent email style extraction.
- `src/daily/db/engine.py` — Async SQLAlchemy engine. Reused for action_log table.
- `src/daily/profile/` — User profile with preferences. Phase 4 adds `rejection_behaviour` preference.
- `src/daily/integrations/base.py` — ABC pattern for adapters. Reference for ActionExecutor ABC design.

### Established Patterns
- LLM outputs as structured intent JSON (SEC-05). Phase 4 adds new intent types but follows the same validation pattern.
- Append-only logging (signal_log in Phase 3). action_log follows the same pattern.
- Async-first throughout. ActionExecutors are async.
- Pydantic models at all data boundaries.
- Fire-and-forget for non-blocking writes (signal capture pattern from Phase 3).

### Integration Points
- Phase 4 extends: LangGraph graph (adds approval gate + executor nodes), OrchestratorIntent (adds action types), SessionState (adds pending action)
- Phase 4 reads from: existing adapters (sent email history for style), user profile (tone, rejection_behaviour)
- Phase 4 writes to: external APIs via ActionExecutors, action_log table, signal_log (action signals)
- Phase 5 connects to: approval flow via voice (confirm/reject/edit by speech)

</code_context>

<specifics>
## Specific Ideas

- Sent email style matching: fetch 5-10 recent sent emails, redact, include as few-shot examples in the LLM drafting prompt so generated emails sound like the user
- Contact whitelist derived from email history — no separate "contacts" feature needed, just check if address appears in sent/received
- Action executor separate from read adapters — different security surface, independently auditable
- Approval flow should feel conversational: "Here's what I'd send: [card]. Want to change anything, or should I send it?"

</specifics>

<deferred>
## Deferred Ideas

- **Trusted auto-actions (M2+)** — Staged autonomy model where user grants auto-send permissions for specific contacts or action types. Out of scope per M1 constraints.
- **Undo/recall sent messages** — After-the-fact undo for recently sent emails (Gmail supports recall within 30s). Useful but adds complexity beyond M1 scope.
- **Rich text email composition** — M1 drafts are plain text. HTML formatting and attachments deferred.
- **Action templates/macros** — Predefined action templates ("decline meeting with reason") for common patterns. Future enhancement.
- **Batch actions** — "Reply to all three of those saying I'll be there" — multiple actions from one instruction. Future enhancement.

</deferred>

---

*Phase: 04-action-layer*
*Context gathered: 2026-04-10*
