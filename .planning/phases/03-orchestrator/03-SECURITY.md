---
phase: 03
slug: orchestrator
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-10
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| User input -> profile service | Preference values from CLI validated before DB write | User-supplied strings (tone, briefing_length) |
| Signal metadata -> signal_log | Metadata dict could contain arbitrary data | System-generated JSON metadata |
| Email content -> LLM | Raw email bodies fetched on-demand must pass through summarise_and_redact() | Email body text (PII, credentials) |
| LLM response -> orchestrator | LLM output validated as OrchestratorIntent | JSON structured response |
| User input -> graph routing | route_intent uses keyword matching only | User chat input text |
| Session state -> checkpointer (Postgres) | Only summaries enter state; raw bodies are local variables only | Redacted summaries |
| Stored tokens -> adapter instantiation | Tokens decrypted in-memory only at adapter creation time, never logged | OAuth tokens (encrypted at rest) |
| CLI input -> profile service | User-supplied preference values validated before DB write | Preference enum values |
| Preferences -> LLM prompt | Preference values from controlled enum — no injection risk | Enum string values |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-01 | Tampering | UserPreferences validation | mitigate | Pydantic Literal types restrict tone to 3 values, briefing_length to 3 values — invalid values rejected at model_validate() | closed |
| T-03-02 | Information Disclosure | signal_log metadata_json | accept | Single-user Phase 3; metadata is system-generated, not user-supplied. No PII risk at this scale. | closed |
| T-03-03 | Spoofing | OrchestratorIntent.action | mitigate | Literal["answer", "summarise_thread", "skip", "clarify"] — Pydantic rejects unknown values | closed |
| T-03-04 | Information Disclosure | thread_id | mitigate | thread_id = f"user-{user_id}-{date}" — user_id is system-assigned, never user-supplied | closed |
| T-03-05 | Tampering | LLM prompt injection via email | mitigate | summarise_and_redact() runs before any email content enters LLM context | closed |
| T-03-06 | Elevation of Privilege | LLM tool calls | mitigate | No tools= parameter on any LLM call. response_format=json_object constrains output. OrchestratorIntent Literal validation rejects unknown actions | closed |
| T-03-07 | Information Disclosure | Raw email in SessionState | mitigate | Raw body is a local variable in summarise_thread_node — never assigned to state fields. Only redacted summary enters state via AIMessage | closed |
| T-03-08 | Denial of Service | Large email body to redactor | accept | summarise_and_redact has semaphore (3 concurrent) and max_tokens=200. Single-user Phase 3 — acceptable risk | closed |
| T-03-09 | Tampering | CLI profile.tone | mitigate | Validated against Literal values in CLI helper before calling upsert_preference. Invalid values rejected with error message | closed |
| T-03-10 | Tampering | category_order injection | accept | category_order values from small controlled set injected into system prompt. Single-user Phase 3 — accepted | closed |
| T-03-11 | Spoofing | CLI user_id hardcoded to 1 | accept | Single-user Phase 3. user_id=1 consistent with all existing CLI commands. Multi-user auth is Phase 4+ | closed |
| T-03-12 | Information Disclosure | Token decryption in CLI chat | mitigate | Tokens decrypted in-memory only for adapter instantiation. Local variable, never logged. Same pattern as scheduler.py | closed |

*Status: open / closed*
*Disposition: mitigate (implementation required) / accept (documented risk) / transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-03-02 | Single-user Phase 3; metadata is system-generated only. No PII risk at this scale. | gsd-security-auditor | 2026-04-10 |
| AR-02 | T-03-08 | Semaphore + max_tokens limit in place. Single-user scale — DoS risk is minimal. | gsd-security-auditor | 2026-04-10 |
| AR-03 | T-03-10 | category_order values are from a controlled set, not user-generated text. | gsd-security-auditor | 2026-04-10 |
| AR-04 | T-03-11 | user_id=1 hardcoded is consistent with all Phase 3 CLI commands. Multi-user auth deferred to Phase 4+. | gsd-security-auditor | 2026-04-10 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-10 | 12 | 12 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-10
