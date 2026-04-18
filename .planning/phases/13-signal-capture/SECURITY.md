# Security Audit — Phase 13: Signal Capture

**Audited:** 2026-04-18
**ASVS Level:** 1
**Threats Closed:** 7/7
**Threats Open:** 0/7

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-13-01 | Tampering | mitigate | CLOSED | `src/daily/profile/adaptive_ranker.py` lines 52–58: `SignalLog.user_id == user_id` WHERE clause in SQLAlchemy query filters all signal rows to the requesting user only. `user_id` parameter comes from caller (context_builder.py), which sources it from `state.active_user_id` (system-assigned). |
| T-13-02 | Information Disclosure | accept | CLOSED | Accepted: multiplier values are internal float weights (range ~0.5–2.0); no PII in the return dict. Documented here as accepted risk. |
| T-13-03 | Information Disclosure | accept | CLOSED | Accepted: sender emails in `BriefingItem.sender` are already present in `email_context` state and briefing context. Redis access requires connection credentials (not user-accessible). Documented here as accepted risk. |
| T-13-04 | Tampering | mitigate | CLOSED | `src/daily/orchestrator/session.py` lines 147–155: `_items` Redis key constructed as `_cache_key(user_id, d) + "_items"` — both components are system-controlled (user_id from function parameter, date from `date.today()`). Payload parsed with `json.loads()` (stdlib); no `eval` or `pickle` paths. |
| T-13-05 | Tampering | accept | CLOSED | Accepted: keyword routing is the established pattern (T-03-04). User voice transcript controls only routing intent, not signal attribution. `user_id` for signal writes comes from `state.active_user_id` (system-assigned). Documented here as accepted risk. |
| T-13-06 | Tampering | mitigate | CLOSED | `src/daily/voice/loop.py` lines 258–269: `sender` for implicit skip signal sourced from `briefing_items[current_item_idx]` (loaded from Redis via `initialize_session_state` at line 230), not from the user transcript. Explicit skip/re_request signals in `nodes.py` source sender from `state.briefing_items` via `_get_current_item_sender()`. No user-controlled path to `target_id`. |
| T-13-07 | Denial of Service | accept | CLOSED | Accepted: implicit skip bounded by briefing item count (5–15 items); 2s silence threshold (`implicit_skip_threshold = 2.0` at loop.py line 232) prevents rapid-fire. One DB row per signal, same as all other signal types. Documented here as accepted risk. |

---

## Accepted Risks Log

| Threat ID | Category | Rationale |
|-----------|----------|-----------|
| T-13-02 | Information Disclosure | Multiplier values are internal scoring weights, not user-facing PII. Return dict contains no credentials, emails, or message content. |
| T-13-03 | Information Disclosure | Sender emails already exist in briefing context and `email_context` state. BriefingItem adds no new PII surface. Redis requires connection credentials. |
| T-13-05 | Tampering | Keyword-list routing is read-only pattern established in Phase 3. User cannot inject signals for other users — `user_id` is system-assigned. |
| T-13-07 | Denial of Service | Signal volume naturally capped by briefing item count. 2s threshold + per-item-advance prevents flood. No amplification vector. |

---

## Unregistered Flags

None. All threat flags in SUMMARY.md files map to registered threats T-13-01 through T-13-07.
