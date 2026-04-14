---
phase: quick-260412-gak
plan: 01
subsystem: orchestrator
tags: [draft-node, email-context, threading, action-layer]
dependency_graph:
  requires: [phase-04-plan-02-draft-node]
  provides: [draft_node-email-context, draft_node-thread-population]
  affects: [SessionState, draft_node, initialize_session_state]
tech_stack:
  added: []
  patterns: [email-metadata-as-dict, langgraph-state-plain-dict, llm-output-mapping]
key_files:
  created: []
  modified:
    - src/daily/orchestrator/state.py
    - src/daily/orchestrator/session.py
    - src/daily/orchestrator/nodes.py
decisions:
  - "Store email_context as list[dict] (not list[EmailMetadata]) for clean LangGraph state serialisation"
  - "Fallback live fetch in draft_node for sessions where email_context was not pre-loaded"
  - "LLM outputs message_id; ActionDraft stores it as thread_message_id (RFC 2822 In-Reply-To mapping)"
metrics:
  duration: ~10 minutes
  completed: "2026-04-12T12:32:00Z"
  tasks_completed: 2
  files_modified: 3
---

# Quick Task 260412-gak: Fix Null Recipient in draft_node — Pass Email Metadata to LLM Prompt

**One-liner:** Structured email metadata (sender, subject, thread_id, message_id) is now passed to the draft_node LLM prompt, fixing null recipient and enabling reply threading via ActionDraft.thread_id and thread_message_id.

## What Was Done

### Task 1 — Add email_context to SessionState and populate during session init

- Added `email_context: list[dict]` field to `SessionState` (plain dicts for LangGraph serialisation compatibility; only metadata stored per SEC-04).
- `initialize_session_state()` in `session.py` now fetches last 7 days of email metadata from the first registered adapter after loading briefing/preferences. Failure is non-fatal (warning log only).
- Added `import logging` and module-level `logger` to `session.py`.

**Commit:** `1ad8d28`

### Task 2 — Wire email metadata into DRAFT_SYSTEM_PROMPT and populate ActionDraft threading fields

- Updated `DRAFT_SYSTEM_PROMPT` to include `{email_context}` section with reply-matching instructions and extended LLM output schema to include `thread_id` and `message_id` fields.
- Added `_format_email_context(email_context: list[dict]) -> str` helper that renders metadata as a numbered list for the LLM prompt.
- `draft_node` now injects `state.email_context` into the prompt via `_format_email_context`. If `state.email_context` is empty (non-briefing session), falls back to a live adapter fetch.
- `ActionDraft` construction updated to populate `thread_id` and `thread_message_id` from LLM output (`parsed["thread_id"]` and `parsed["message_id"]` respectively).

**Commit:** `60975dd`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints or auth paths introduced. Email metadata (not bodies) is the only addition to SessionState, consistent with SEC-04. LLM output thread_id/message_id values pass through GmailExecutor API validation before use (T-QK-02).

## Self-Check: PASSED

- `src/daily/orchestrator/state.py` — modified, `email_context` field present
- `src/daily/orchestrator/session.py` — modified, `email_context` populated in `initialize_session_state`
- `src/daily/orchestrator/nodes.py` — modified, `_format_email_context` and `DRAFT_SYSTEM_PROMPT` updated
- Commit `1ad8d28` — exists
- Commit `60975dd` — exists
