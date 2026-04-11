---
phase: 04-action-layer
plan: "02"
subsystem: orchestrator-draft-cli
tags: [draft-node, llm-drafting, style-matching, cli-approval, langgraph-interrupt]
dependency_graph:
  requires: ["04-01"]
  provides: ["draft-node-full", "cli-approval-flow"]
  affects: ["04-03"]
tech_stack:
  added: []
  patterns:
    - "GPT-4.1 for drafting; GPT-4.1-mini for quick responses (D-02)"
    - "summarise_and_redact() gating all sent-email bodies before LLM prompt (T-04-07)"
    - "Command(resume=decision) for LangGraph interrupt/resume pattern"
    - "TDD Red-Green per task with per-commit discipline"
key_files:
  created:
    - tests/test_action_draft.py
    - tests/test_cli_approval.py
  modified:
    - src/daily/orchestrator/nodes.py
    - src/daily/cli.py
    - tests/test_action_approval.py
    - tests/test_cli_chat.py
decisions:
  - "draft_node infers ActionType from keyword matching (reply/email -> draft_email, schedule/book -> schedule_event, slack/message -> draft_message) — avoids round-trip LLM classification"
  - "Style examples capped at 5 sent emails (D-06) to keep prompt size bounded"
  - "Edit re-entry loop implemented inline in _run_chat_session (1 nested level) rather than recursive to avoid deep call stacks"
  - "aget_state() called after every turn to detect interrupt — adds one async call per turn but keeps approval flow detection simple and reliable"
metrics:
  duration_minutes: 47
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_modified: 6
---

# Phase 04 Plan 02: LLM Draft Node and CLI Approval Flow Summary

**One-liner:** Full GPT-4.1 draft generation with redacted sent-email style matching wired into an interactive CLI confirm/reject/edit approval loop via LangGraph Command(resume=).

## What Was Built

### Task 1: Full draft_node implementation (TDD)

Replaced the Plan 01 stub `draft_node` with a complete implementation:

- `DRAFT_SYSTEM_PROMPT` constant with slots for action_type, style_examples, tone, instruction, briefing_narrative
- `_infer_action_type(instruction)`: keyword-based ActionType inference (reschedule > schedule > slack/message > email)
- `_fetch_style_examples(client)`: fetches up to 5 recent sent emails via registered adapters, passes each body through `summarise_and_redact()` (T-04-07), returns formatted redacted excerpts
- `draft_node(state)`: calls GPT-4.1 with `response_format={"type": "json_object"}` and NO `tools=` parameter (T-04-09/SEC-05), parses JSON to `ActionDraft`, returns `{"pending_action": draft, "messages": [...]}`
- Graceful error handling: adapter failures skip style examples; LLM failures return user-friendly error message

### Task 2: CLI approval flow (TDD)

Extended `src/daily/cli.py` with the full approval interaction loop:

- `_parse_approval_decision(user_input)`: maps confirm synonyms to `"confirm"`, reject synonyms to `"reject"`, anything else to `"edit:{text}"`
- `_display_draft_card(draft)`: renders structured card with `DRAFT: {action_type}` header, separator lines, `card_text()`, and approval prompt
- `_display_cancellation_message(rejection_behaviour)`: shows "Action cancelled." for both ask_why and discard modes
- `_handle_approval_flow(graph, state, config)`: extracts interrupt payload, displays card, reads input, resumes graph with `Command(resume=decision)`, returns result with optional `edit_instruction`
- `_run_chat_session`: calls `graph.aget_state(config)` after each turn; if `state.next` is set (interrupted), delegates to `_handle_approval_flow`; edit decisions re-enter the draft loop automatically (D-01 unlimited rounds)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_action_approval.py integration tests broke after draft_node gained real LLM calls**
- **Found during:** Task 2 full test suite run
- **Issue:** `TestApprovalGateInterrupt` tests invoked the graph without mocking OpenAI. The stub draft_node (Plan 01) was a pass-through; the new draft_node calls `AsyncOpenAI()` which fails without `OPENAI_API_KEY` in test environments.
- **Fix:** Added `AsyncOpenAI` and `get_email_adapters` mocks to the three integration tests in `test_action_approval.py`. Added `import json` and mock imports.
- **Files modified:** `tests/test_action_approval.py`
- **Commit:** `4b9d89e`

**2. [Rule 1 - Bug] test_cli_chat.py approval flow detection triggered on normal responses**
- **Found during:** Task 2 full test suite run
- **Issue:** `_run_chat_session` now calls `graph.aget_state(config)` after every turn. The existing mock graph in `_make_mock_graph()` returned an `AsyncMock()` for `aget_state`, whose `.next` attribute was also an `AsyncMock` — truthy — causing the approval branch to fire for all normal responses.
- **Fix:** Updated `_make_mock_graph()` to set `mock_state.next = []` and `mock_state.tasks = []` so the approval branch is skipped in existing tests.
- **Files modified:** `tests/test_cli_chat.py`
- **Commit:** `4b9d89e`

## Known Stubs

None. The draft_node is fully implemented. The execute_node remains a stub (Plan 01 decision — real executor dispatch is Plan 03). This does not prevent Plan 02's goal: the draft -> preview -> confirm/reject/edit flow works end-to-end.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. All new LLM calls follow established patterns (no tools=, response_format=json_object). Sent email bodies continue to flow through `summarise_and_redact()` before any LLM prompt inclusion (T-04-07 mitigated as planned).

## Self-Check: PASSED

- FOUND: `src/daily/orchestrator/nodes.py` (contains DRAFT_SYSTEM_PROMPT, draft_node with gpt-4.1, summarise_and_redact)
- FOUND: `src/daily/cli.py` (contains Command(resume=, state.next, DRAFT:, edit:, Confirm, reject, or describe changes)
- FOUND: `tests/test_action_draft.py` (19 tests, all passing)
- FOUND: `tests/test_cli_approval.py` (41 tests, all passing)
- All commits verified: 688b76d, 9a5b308, ebd16df, 4b9d89e
- Full suite: 409 passed, 0 failed (excluding UAT integration tests)
