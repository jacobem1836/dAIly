---
status: resolved
trigger: "fix-email-reading-sender-and-context"
created: 2026-04-13T00:00:00Z
updated: 2026-04-13T00:00:00Z
---

## Current Focus

hypothesis: Two confirmed bugs — (1) date object passed where datetime needed, (2) raw Gmail From header stored instead of bare email address
test: Read all known locations, confirmed both bugs in code
expecting: Fix both bugs and verify no remaining issues
next_action: Apply fixes to session.py and nodes.py

## Symptoms

expected: (1) email_context populated at session start with recent emails; (2) sender field contains parseable email address for LLM recipient matching
actual: (1) email_context always empty — initialize_session_state passes date object to list_emails which calls since.timestamp() — date has no timestamp() method; (2) Gmail From header stored raw as "Name <email@example.com>" — LLM may output bare email which won't match known_addresses
errors: exception swallowed silently in session.py:119 "could not load email context"; no visible error to user
reproduction: run `daily chat`, try to draft a reply — email_context is empty
started: introduced when email_context was wired up in Phase 4

## Eliminated

- hypothesis: bug might be elsewhere in pipeline
  evidence: confirmed in session.py:106 — `d` is a date object from `date.today()` or `session_date`, subtracted with timedelta gives another date object, and date has no .timestamp() method
  timestamp: 2026-04-13T00:00:00Z

## Evidence

- timestamp: 2026-04-13T00:00:00Z
  checked: session.py:96-120
  found: d = session_date or date.today() gives date, then d - timedelta(days=7) gives date; GmailAdapter.list_emails expects datetime and calls since.timestamp() at line 54
  implication: AttributeError on date.timestamp() — exception swallowed silently, email_context stays empty

- timestamp: 2026-04-13T00:00:00Z
  checked: adapter.py:105, nodes.py:633-634
  found: sender stored from header_map.get("From", "") which is raw Gmail From header ("Name <email@example.com>"); known_addresses built from {e.sender} — same raw strings; LLM outputs bare email addresses that won't match
  implication: recipient matching in draft_node and _build_executor_for_type will silently fail

- timestamp: 2026-04-13T00:00:00Z
  checked: nodes.py:429
  found: draft_node fallback uses datetime.now() - timedelta(days=7) — this is already correct (datetime, not date), so only session.py has Bug 1
  implication: Bug 1 is isolated to session.py:106

## Resolution

root_cause: |
  Bug 1: session.py line 106 — `d - timedelta(days=7)` produces a date object (not datetime) because d is `date.today()`. GmailAdapter.list_emails calls since.timestamp() which exists on datetime but not date. AttributeError is silently swallowed so email_context is always empty.
  Bug 2: Gmail From header value is the full RFC 2822 display-name format ("Name <email@example.com>"). This raw string is stored in email_context sender fields and added to known_addresses. LLM produces bare email addresses that won't match these raw strings.
fix: |
  Bug 1: In session.py initialize_session_state, replace `since = d - timedelta(days=7)` with `since = datetime.now(tz=timezone.utc) - timedelta(days=7)` using datetime (not date).
  Bug 2: Add _extract_email helper using regex to strip display name. Apply in session.py email_context build, in draft_node fallback build, and in _build_executor_for_type known_addresses build.
verification: |
  Code inspection confirms:
  - Bug 1 fixed: datetime.now(tz=timezone.utc) - timedelta(days=7) produces datetime; .timestamp() will succeed
  - Bug 2 fixed: _extract_email applied at all three sites — session.py email_context build, draft_node fallback build, _build_executor_for_type known_addresses build
  - Helper is defined in both modules independently (session.py and nodes.py) — no cross-module dependency needed
files_changed:
  - src/daily/orchestrator/session.py
  - src/daily/orchestrator/nodes.py
