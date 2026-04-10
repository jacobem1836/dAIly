# Phase 4: Action Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-10
**Phase:** 04-action-layer
**Mode:** discuss (interactive)
**Areas discussed:** Approval flow UX, Draft presentation, Action sandboxing & validation, Adapter write methods

## Approval Flow UX

| Question | Options Presented | User Choice |
|----------|-------------------|-------------|
| How should the user confirm or reject a proposed action? | Simple confirm/reject; Preview-edit-confirm; Auto-queue batch | Preview-edit-confirm |
| How many edit rounds before final decision? | Unlimited; Cap at 3; You decide | Unlimited until user confirms |
| What happens when user rejects an action? | Discard and move on; Ask why and offer alternatives; You decide | Default "ask why", configurable to "discard" via profile setting |
| Approval gate implementation? | LangGraph interrupt; CLI/voice loop confirm; You decide | LangGraph human-in-the-loop interrupt |
| Should pending actions survive restarts? | Survive restarts; Session-scoped only; You decide | Survive restarts (AsyncPostgresSaver) |

## Draft Presentation

| Question | Options Presented | User Choice |
|----------|-------------------|-------------|
| How should drafts be presented before approval? | Full content; Summary with expand; Structured card | User was unsure re: voice-first; agreed to structured card for CLI with voice adaptation in Phase 5 |
| Who generates draft content? | LLM generates draft; LLM extracts intent + executor templates; You decide | LLM generates full draft |
| (User addition) | — | Use sent email history as style reference for LLM drafting |

## Action Sandboxing & Validation

| Question | Options Presented | User Choice |
|----------|-------------------|-------------|
| Recipient whitelist strategy? | Known contacts only; Allow all + blocklist; No restrictions; You decide | Known contacts only |
| Supported action types in M1? | Email replies; Slack messages; Calendar create/reschedule; New email composition | All four selected |
| Sandbox rejection UX? | Explain + offer override; Hard block; You decide | Explain why and offer override |
| Action log content depth? | Summary + content hash; Full content; Summary only; You decide | Summary + SHA-256 content hash |

## Adapter Write Methods

| Question | Options Presented | User Choice |
|----------|-------------------|-------------|
| How to add write capabilities? | Extend existing ABCs; Separate ActionExecutor classes; You decide | Separate ActionExecutor classes — user preferred production best practice (modular, secure, SRP) |
| OAuth scope upgrade strategy? | Write scopes upfront; Incremental grants; You decide | Write scopes upfront at connection time |

## Corrections Made

No corrections — all decisions were first-pass selections or user-provided additions.

## User-Provided Additions

- Draft generation should use sent email history as style reference (few-shot examples)
- Rejection behaviour should be configurable in user profile (default: ask why)
