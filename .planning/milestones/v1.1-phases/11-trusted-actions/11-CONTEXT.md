# Phase 11: Trusted Actions - Context

**Gathered:** 2026-04-18 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

User can configure specific action types to execute without per-action approval. High-impact actions (send-email, create-external-calendar-invite) remain permanently locked to the approval gate. All other action types are configurable via the `daily config set` command. The approve level (default) must behave identically to v1.0 — no regression. Changes take effect on the next session.

No suggest-mode behaviour, no web UI, no action execution from non-voice/CLI surfaces.
</domain>

<decisions>
## Implementation Decisions

### Action Type Classification
- **D-01:** Permanently blocked from auto-execution (regardless of user config): `compose_email` (send-without-draft) and any future `create_external_calendar_invite` type. These two action types always interrupt for approval.
- **D-02:** Configurable action types (can be set to `auto`): `draft_email`, `draft_message`, `schedule_event`, `reschedule_event`. Default is `approve` for all.

### Autonomy Storage
- **D-03:** New `autonomy_levels` field added to the existing `UserPreferences` Pydantic model in `src/daily/profile/models.py`. Type: `dict[str, str]` mapping action type name → `"approve"` | `"auto"`. Default: `{}` (treat all missing keys as `"approve"`).
- **D-04:** No new database migration needed — `UserPreferences` is stored as JSONB in `user_profile.preferences`. The new field is a Pydantic-level addition, same pattern as `memory_enabled`.

### Approval Gate Bypass
- **D-05:** `approval_node` in `src/daily/orchestrator/nodes.py` is modified to check autonomy before calling `interrupt()`. Logic: if `state.pending_action.action_type` is in the blocked list → always interrupt. Else if user's autonomy level for that type is `"auto"` → skip interrupt, return `{"approval_decision": "confirm"}` directly. Otherwise → interrupt as today.
- **D-06:** The bypass is implemented as a pre-check at the TOP of `approval_node`, before any other logic, so the existing approval path is 100% unchanged when autonomy is `"approve"`.

### Config Command Extension
- **D-07:** `daily config set profile.autonomy.<action_type>=<level>` — extend the existing dot-separated key parser in `cli.py`. Key `profile.autonomy.draft_email` resolves to setting `autonomy_levels["draft_email"]` in UserPreferences. Invalid action types or invalid levels produce a clear error.
- **D-08:** `daily config get profile.autonomy` returns the full current autonomy dict as a formatted table showing each configurable action type and its current level.

### Suggest Level Scope
- **D-09:** `suggest` level is treated as equivalent to `approve` in Phase 11 — user still sees the draft and must approve. Full suggest-mode behaviour (e.g., auto-execute with post-hoc notification) is deferred to a later phase. This keeps Phase 11 binary: auto or gated.

### Session Load
- **D-10:** Autonomy levels are loaded at session start as part of `UserPreferences` and stored in `state.preferences`. The approval_node reads `state.preferences.get("autonomy_levels", {})`. No per-action DB queries.

### Claude's Discretion
- Exact error message wording for invalid config keys/levels
- Whether to show a confirmation message when auto-executing an action (e.g. "Drafted email — auto-executed (trusted action)")
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Action layer
- `src/daily/actions/base.py` — ActionType enum, ActionRequest model, ActionResult model
- `src/daily/actions/models.py` — approval-related models if separate
- `src/daily/orchestrator/nodes.py` — `approval_node` (line ~595), `execute_node` — these are the core changes

### Preferences
- `src/daily/profile/models.py` — `UserPreferences` Pydantic model, `upsert_preference()` function
- `src/daily/orchestrator/state.py` — `SessionState` and how `preferences` dict is populated

### Config CLI
- `src/daily/cli.py` — `config set/get` command handler, `profile.*` key parsing pattern (lines ~190-213)

### Requirements
- `.planning/REQUIREMENTS.md` §ACT-07 — autonomy level spec (suggest / approve / auto)
- `.planning/ROADMAP.md` Phase 11 success criteria — all 4 criteria define the acceptance bar

### Prior phase patterns
- `.planning/phases/10-memory-transparency/10-CONTEXT.md` — established pattern for preferences-backed feature flags (`memory_enabled`)
- `.planning/phases/08-adaptive-ranker/08-CONTEXT.md` — `state.preferences` load pattern
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `UserPreferences` JSONB pattern + `upsert_preference()` — Phase 11 adds `autonomy_levels` dict exactly like `memory_enabled` bool was added in Phase 10
- `approval_node` in `nodes.py:~595` — single conditional pre-check added at top; rest of function unchanged
- `daily config set profile.*` CLI pattern — dot-separated key parser already exists, extend to handle nested key `profile.autonomy.<action_type>`

### Established Patterns
- All preference-backed features load at session start via `SessionState.preferences` dict — autonomy must follow the same path, not query per-action
- Blocked action types are a **compile-time constant**, not user-configurable — avoids a footgun where user accidentally unlocks high-impact actions

### Integration Points
- `approval_node` → `state.preferences["autonomy_levels"]` (new read)
- `cli.py config set` → `upsert_preference(autonomy_levels=...)` (new write path)
- `SessionState` initialisation → include `autonomy_levels` from loaded UserPreferences
</code_context>

<specifics>
## Specific Ideas

- The confirmation message on auto-execution (e.g. "Drafted email — executed automatically (trusted action)") is at Claude's discretion — just make sure the user gets some audible/logged acknowledgement
- `suggest` level is intentionally a no-op placeholder for now so the config command accepts all three levels; it just behaves as `approve`
</specifics>

<deferred>
## Deferred Ideas

- Full suggest-mode UX (auto-execute with post-hoc notification or undo window) — future phase
- Per-contact or per-domain autonomy rules (e.g., "auto-draft only for known contacts") — future phase

### Reviewed Todos (not folded)
None — no open todos matched this phase.
</deferred>

---

*Phase: 11-trusted-actions*
*Context gathered: 2026-04-18*
