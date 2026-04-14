---
phase: 6
slug: wire-preferences-to-briefing
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-14
---

# Phase 6 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| DB → pipeline | User preferences loaded from Postgres via `load_profile()` | `UserPreferences` (tone, briefing_length, category_order) — non-sensitive display hints |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-06-01 | Tampering | UserPreferences from DB | accept | Preferences are non-security-critical display hints. Pydantic `Literal` types restrict values at parse time — invalid values raise `ValidationError` before they reach the pipeline. | closed |
| T-06-02 | Information Disclosure | Preferences in LLM prompt | accept | Preferences contain no PII or secrets — only `tone`/`length`/`order` enum strings. Validated by Pydantic `Literal` constraints before injection into LLM system prompt. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-01 | Preferences are display hints (tone/length/order), not security-sensitive. Pydantic Literal types enforce the allowed value set — no arbitrary values can propagate. Tampering with these values has no security consequence; it can only affect narrative style. | gsd-security-auditor | 2026-04-14 |
| AR-06-02 | T-06-02 | Preferences injected into the LLM system prompt contain no PII, credentials, or secrets. The only values possible are the Pydantic-validated Literal strings. No user data flows into the prompt via this path. | gsd-security-auditor | 2026-04-14 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-14 | 2 | 2 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-14
