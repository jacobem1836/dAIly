---
phase: 13
slug: signal-capture
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-18
---

# Phase 13 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| DB query → caller | `get_sender_multipliers` returns computed floats from DB data; caller trusts the values | float multipliers (no PII) |
| Pipeline → Redis | Item list written to Redis contains sender emails (from integration metadata, not user input) | sender emails (already in briefing context) |
| Redis → SessionState | Item list loaded into state — used internally by signal nodes | sender emails, item metadata |
| User voice transcript → route_intent | Untrusted text matched against keyword lists (no code execution) | raw transcript text |
| SessionState.briefing_items → signal target_id | Server-side item list (from Redis cache) used as signal target_id | sender identifier |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-13-01 | Tampering | adaptive_ranker.py | mitigate | `SignalLog.user_id == user_id` WHERE clause (lines 52–58). `user_id` sourced from `state.active_user_id` (system-assigned), never user input. | closed |
| T-13-02 | Information Disclosure | adaptive_ranker.py | accept | Multiplier values are internal ranking weights only — no PII in return dict. | closed |
| T-13-03 | Information Disclosure | items.py / Redis cache | accept | Sender emails already present in existing state fields. Redis access requires connection credentials. | closed |
| T-13-04 | Tampering | session.py item loading | mitigate | `_items` key built from `_cache_key(user_id, d) + "_items"` — both components system-controlled (lines 147–155). Payload deserialized with `json.loads()` only; no eval/pickle path. | closed |
| T-13-05 | Tampering | route_intent skip/re_request keywords | accept | Keyword matching is read-only routing. `user_id` for signal writes comes from `state.active_user_id` (system-assigned). | closed |
| T-13-06 | Tampering | _capture_signal target_id | mitigate | `sender`/`target_id` sourced exclusively from `state.briefing_items` (Redis-loaded server-side cache). No path from user transcript to `target_id`. | closed |
| T-13-07 | Denial of Service | Implicit skip flood | accept | Signal volume bounded by item count (5–15 items). 2s silence threshold (`implicit_skip_threshold = 2.0`) prevents rapid-fire. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-13-01 | T-13-02 | Multiplier values are internal ranking floats with no PII. Acceptable to expose within the calling layer. | Jacob Marriott | 2026-04-18 |
| AR-13-02 | T-13-03 | Sender emails in Redis item list are already present in `email_context` state field. No new exposure surface. Redis access gated by connection credentials. | Jacob Marriott | 2026-04-18 |
| AR-13-03 | T-13-05 | Keyword matching is read-only; no state mutations. Cross-user signal injection is impossible since `user_id` is system-assigned. | Jacob Marriott | 2026-04-18 |
| AR-13-04 | T-13-07 | Implicit skip flood risk is bounded by briefing item count and the 2s threshold. No rate-limiting beyond this is warranted at M1 scale. | Jacob Marriott | 2026-04-18 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-18 | 7 | 7 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
