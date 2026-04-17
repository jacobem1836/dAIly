---
phase: 07
slug: tech-debt-fixes
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-18
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Email metadata → ranker | Untrusted recipient field values from email providers | RFC 2822 address strings (non-sensitive metadata) |
| DB → scheduler | user_email read from UserProfile table | Internal email string (trusted boundary) |
| Slack API → adapter | Untrusted next_cursor and message data from Slack API | Pagination cursors, MessageMetadata (no bodies) |
| User message → _resolve_message_id | Untrusted user text used for substring matching | User query string vs email subject/sender metadata |
| email_context → _resolve_message_id | Email metadata populated during briefing session | Internal session state (trusted boundary) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Spoofing | `_is_direct_recipient` (ranker.py) | accept | `parseaddr()` handles malformed RFC 2822 input gracefully — returns empty string; empty user_email returns False, no false WEIGHT_DIRECT score | closed |
| T-07-02 | Information Disclosure | scheduler `user_email` | accept | `user_email` used only for scoring comparison (ranker call), never logged or passed to LLM layer | closed |
| T-07-03 | Denial of Service | `list_messages` pagination (adapter.py) | mitigate | Hard cap `_MAX_PAGES_PER_CHANNEL = 10` prevents infinite loop if Slack API always returns `has_more=True`; warning logged on cap hit | closed |
| T-07-04 | Information Disclosure | `list_messages` (adapter.py) | accept | Only `MessageMetadata` returned (no body text) — T-1-12 metadata-only contract preserved across pagination pages | closed |
| T-07-05 | Spoofing | `_resolve_message_id` (nodes.py) | accept | Substring matching against subject/sender metadata only; no security-sensitive action on match result — false match yields wrong email summary, not privilege escalation | closed |
| T-07-06 | Information Disclosure | `summarise_thread_node` (nodes.py) | accept | Raw email body still passes through `summarise_and_redact()` before any state write — SEC-04 boundary preserved; resolution logic does not bypass redaction | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-01 | `parseaddr` standard library behaviour is well-tested; malformed addresses silently dropped (no WEIGHT_DIRECT) — no exploitable outcome | Jacob Marriott | 2026-04-18 |
| AR-07-02 | T-07-02 | `user_email` is read from trusted internal DB, used only in scoring arithmetic, never surfaced externally | Jacob Marriott | 2026-04-18 |
| AR-07-04 | T-07-04 | MessageMetadata-only contract was established in Phase 01 (T-1-12); pagination does not change the data shape | Jacob Marriott | 2026-04-18 |
| AR-07-05 | T-07-05 | Worst-case outcome of a false match is an incorrect email summary displayed to the authenticated user — no privilege escalation path exists | Jacob Marriott | 2026-04-18 |
| AR-07-06 | T-07-06 | `summarise_and_redact()` boundary verified in code (nodes.py:292, 424); resolution path explicitly calls redactor before state write | Jacob Marriott | 2026-04-18 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-18 | 6 | 6 | 0 | gsd-security-auditor (automated) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-18
