---
phase: 11-trusted-actions
plan: "01"
subsystem: orchestrator/action-autonomy
tags: [trusted-actions, autonomy, approval-gate, security]
dependency_graph:
  requires: []
  provides: [BLOCKED_ACTION_TYPES, CONFIGURABLE_ACTION_TYPES, autonomy_levels, auto_executed]
  affects: [approval_node, SessionState, UserPreferences]
tech_stack:
  added: []
  patterns: [frozenset-constants, JSONB-schema-evolution, langgraph-interrupt-bypass]
key_files:
  created: []
  modified:
    - src/daily/actions/base.py
    - src/daily/profile/models.py
    - src/daily/orchestrator/nodes.py
    - src/daily/orchestrator/state.py
decisions:
  - "BLOCKED_ACTION_TYPES is a frozenset constant — user config cannot bypass it (T-11-01)"
  - "autonomy_levels uses dict[str, str] stored in JSONB — no DB migration needed (D-04)"
  - "'suggest' level falls through to interrupt() same as 'approve' in Phase 11 (D-09)"
  - "auto_executed field added to SessionState to distinguish bypass from user-confirmed"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-04-18"
  tasks_completed: 2
  files_modified: 4
requirements_satisfied: [ACT-07]
---

# Phase 11 Plan 01: Autonomy Type System Summary

JWT auth with refresh rotation using jose library — no, this plan: **Compile-time blocked action list plus user-configurable autonomy levels wired into the LangGraph approval gate.**

## What Was Built

Two tasks delivered the full autonomy type system for Phase 11 Trusted Actions:

**Task 1 — Constants and preferences field:**
- Added `BLOCKED_ACTION_TYPES: frozenset[ActionType]` to `base.py` — currently contains `compose_email`. This is a frozenset (immutable) ensuring no user config can bypass it (T-11-01).
- Added `CONFIGURABLE_ACTION_TYPES: frozenset[ActionType]` to `base.py` — contains `draft_email`, `draft_message`, `schedule_event`, `reschedule_event`. These four types are the ones a user may configure to `"auto"`.
- Added `autonomy_levels: dict[str, str] = Field(default_factory=dict)` to `UserPreferences` in `models.py`. Stored in the existing JSONB `preferences` blob — no DB migration needed. Defaults to empty dict (all types default to `"approve"`).

**Task 2 — Approval gate bypass:**
- Updated `from daily.actions.base import` in `nodes.py` to include `BLOCKED_ACTION_TYPES`.
- Rewrote `approval_node` to add a pre-check before `interrupt()`:
  1. If `action_type in BLOCKED_ACTION_TYPES` → skip pre-check, always call `interrupt()` (compose_email always requires approval).
  2. Else look up `autonomy_levels.get(action_type.value, "approve")` from `state.preferences`.
  3. If level is `"auto"` → return `{"approval_decision": "confirm", "auto_executed": True}` immediately, bypassing `interrupt()`.
  4. If level is `"suggest"` or `"approve"` (or missing) → fall through to existing `interrupt()` call unchanged.
- Added `auto_executed: bool = False` field to `SessionState` so downstream nodes and logging can distinguish auto-executed from user-confirmed actions.

## Decisions Made

1. **BLOCKED_ACTION_TYPES as frozenset constant:** Immutability at the Python level prevents any runtime modification — no config path can add/remove from it. compose_email always requires human approval (T-11-01).

2. **autonomy_levels in JSONB:** Adding a new dict field to `UserPreferences` requires zero DB schema changes because preferences are stored as a JSONB blob. Invalid values (unknown strings) default to `"approve"` at lookup time — worst-case degradation, never escalation (T-11-02).

3. **"suggest" = "approve" in Phase 11:** The `suggest` autonomy level is reserved for M2+ behaviour (preview-only, no approval prompt). In Phase 11 it falls through to `interrupt()` identically to `"approve"`. Documented as D-09 in CONTEXT.md.

4. **auto_executed field on SessionState:** Provides observability for the bypass path. The execute_node and audit log (Phase 11 Plan 02) will use this flag to mark auto-executed entries distinctly from user-confirmed ones.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — all new surface is covered by the plan's threat model (T-11-01, T-11-02, T-11-03).

## Self-Check: PASSED

Files exist and verified:
- `src/daily/actions/base.py` — BLOCKED_ACTION_TYPES and CONFIGURABLE_ACTION_TYPES present
- `src/daily/profile/models.py` — autonomy_levels field present
- `src/daily/orchestrator/nodes.py` — approval_node contains pre-check, autonomy_levels lookup, and interrupt()
- `src/daily/orchestrator/state.py` — auto_executed field present

Commits verified:
- `296006a` — feat(11-01): define BLOCKED_ACTION_TYPES, CONFIGURABLE_ACTION_TYPES, and autonomy_levels field
- `8224121` — feat(11-01): wire autonomy pre-check into approval_node

All plan verification checks passed (4/4).

Pre-existing test failure `test_draft_node_fetches_sent_emails_from_adapter` confirmed pre-existing (failing before this plan's changes — unrelated to approval_node or autonomy system).
