---
status: awaiting_human_verify
trigger: "Multiple issues found during UAT of the dAIly chat action layer. The edit loop in approval flow is broken, action_log table is missing, and Gmail adapters don't load in chat despite successful OAuth connect."
created: 2026-04-11T00:00:00Z
updated: 2026-04-11T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — four distinct root causes identified (see Evidence)
test: apply fixes in priority order
expecting: all four issues resolved
next_action: fix edit loop routing in graph.py and execute_node in nodes.py

## Symptoms

expected: 
1. During approval prompt, typing "make it more formal" should re-draft (edit loop). User can edit unlimited times before confirm/reject.
2. "confirm" should execute the send via Gmail and return "Done. Sent (ID: ...)"
3. action_log table should exist and log all actions
4. After `daily connect gmail`, `daily chat` should show email adapters connected

actual:
1. First "make it more formal" triggered "Action cancelled" instead of re-drafting
2. After the failed edit, "confirm" just echoed text back as normal chat (graph lost draft state)
3. action_log table doesn't exist: `relation "action_log" does not exist`
4. Chat says "No email adapters connected" despite successful `daily connect gmail`

errors:
- `_log_action: failed to write action log: relation "action_log" does not exist`
- Deserialization warnings: `Deserializing unregistered type daily.actions.base.ActionType from checkpoint`

reproduction: 
1. `PYTHONPATH=src uv run daily connect gmail` (succeeds)
2. `PYTHONPATH=src uv run daily chat`
3. Type "draft a reply to dev relations at ebay thanking them for acceptance"
4. Draft card renders correctly
5. Type "make it more formal" — gets "Action cancelled" instead of re-draft
6. Type "confirm" — just echoes text, doesn't execute

started: First time testing these flows end-to-end

## Eliminated

## Evidence

- timestamp: 2026-04-11T00:01
  checked: nodes.py execute_node lines 676-683
  found: `if state.approval_decision != "confirm"` treats ALL non-confirm as rejection. "edit:make it more formal" hits this branch and returns "Action cancelled."
  implication: ROOT CAUSE for Issue 1a — execute_node doesn't distinguish edit from reject

- timestamp: 2026-04-11T00:01
  checked: graph.py lines 129-131
  found: Linear edges `draft -> approval -> execute -> END`. No conditional routing after approval. Even if execute_node handled "edit:*", there's no edge back to draft_node for re-drafting.
  implication: ROOT CAUSE for Issue 1b — graph topology doesn't support edit loop

- timestamp: 2026-04-11T00:01
  checked: cli.py _handle_approval_flow lines 580-586
  found: CLI resumes graph with Command(resume=decision) where decision="edit:...". After graph finishes (execute cancels), CLI tries to re-invoke draft via run_session(). But by then pending_action is cleared (execute_node sets it to None on line 682), so re-draft works but loses context. Also the re-draft loop in CLI (lines 724-743) only handles ONE edit round, not unlimited.
  implication: ROOT CAUSE for Issue 1c — CLI edit re-entry is single-shot and loses state

- timestamp: 2026-04-11T00:02
  checked: alembic/versions/004_action_log.py
  found: Migration file exists but error "relation action_log does not exist" means it was never run against the database
  implication: ROOT CAUSE for Issue 2 — migration not applied

- timestamp: 2026-04-11T00:02
  checked: cli.py _resolve_email_adapters lines 589-631
  found: Function queries IntegrationToken, decrypts, creates GmailAdapter(credentials=decrypted). Need to verify GmailAdapter constructor signature matches.
  implication: Need to check GmailAdapter constructor

- timestamp: 2026-04-11T00:02
  checked: graph.py build_graph — no custom serialization config
  found: No custom_types or allowed modules configured for ActionType/ActionDraft
  implication: ROOT CAUSE for Issue 4 — deserialization warnings

## Resolution

root_cause: |
  Four distinct issues:
  1. Edit loop: graph.py had linear edges draft->approval->execute->END with no conditional routing. execute_node treated all non-"confirm" as rejection. No way to loop back to draft on edit.
  2. action_log table: migration 004 existed but was never run against the database.
  3. Gmail adapter: _resolve_email_adapters passed raw decrypted token string to GmailAdapter(credentials=str) but GmailAdapter expects a google.oauth2.credentials.Credentials object. OutlookAdapter was called with wrong kwarg name (credentials= instead of access_token=).
  4. Deserialization: SessionState.pending_action was typed as Any, causing msgpack serializer to emit warnings for ActionDraft/ActionType.
fix: |
  1. Added route_after_approval() conditional edge in graph.py: edit decisions route back to draft, confirm/reject route to execute. Updated draft_node to detect edit:* in approval_decision and re-draft with original body + edit instruction. Updated CLI _run_chat_session to loop unlimited approval rounds.
  2. Ran `alembic upgrade head` — migration 004 now applied.
  3. Fixed _resolve_email_adapters: wrap decrypted token in google.oauth2.credentials.Credentials(token=decrypted) for Google, use access_token= kwarg for OutlookAdapter.
  4. Changed SessionState.pending_action from Any to ActionDraft | None with proper import.
verification: |
  - All 228 orchestrator/action/CLI tests pass (0 failures)
  - Graph compiles with new conditional edges
  - Imports verify clean (no circular imports)
  - Pre-existing failures (test_briefing_ranker 2.py, test_briefing_scheduler slack_sdk) are unrelated
files_changed:
  - src/daily/orchestrator/graph.py
  - src/daily/orchestrator/nodes.py
  - src/daily/orchestrator/state.py
  - src/daily/cli.py
