# SECURITY.md

**Phase:** 03 — Orchestrator
**ASVS Level:** 1
**Audited:** 2026-04-10

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-03-01 | Tampering | mitigate | CLOSED | `src/daily/profile/models.py:39-40` — `tone: Literal["formal", "casual", "conversational"]` and `briefing_length: Literal["concise", "standard", "detailed"]` on `UserPreferences`; Pydantic `model_validate()` rejects unknown values at read time |
| T-03-02 | Information Disclosure | accept | CLOSED | Single-user Phase 3; `signal_log.metadata_json` is system-generated only per `src/daily/profile/signals.py:48`; accepted risk logged here |
| T-03-03 | Spoofing | mitigate | CLOSED | `src/daily/orchestrator/models.py:34` — `action: Literal["answer", "summarise_thread", "skip", "clarify"]`; Pydantic raises `ValidationError` for any other value |
| T-03-04 | Information Disclosure | mitigate | CLOSED | `src/daily/orchestrator/session.py:69` — `f"user-{user_id}-{d.isoformat()}"` produces per-user-per-day scoped thread_id; `user_id` is system-assigned |
| T-03-05 | Tampering | mitigate | CLOSED | `src/daily/orchestrator/nodes.py:161` — `redacted_content = await summarise_and_redact(raw_body, client)` called before `raw_body` is used in any LLM prompt; raw body never reaches LLM unredacted |
| T-03-06 | Elevation of Privilege | mitigate | CLOSED | `src/daily/orchestrator/nodes.py:88-96` and `164-178` — both LLM calls use `response_format={"type": "json_object"}` with no `tools=` parameter; `OrchestratorIntent.model_validate_json()` called at lines 98 and 180 |
| T-03-07 | Information Disclosure | mitigate | CLOSED | `src/daily/orchestrator/nodes.py:156-161` — `raw_body` declared as local variable, passed to `summarise_and_redact()` returning `redacted_content`; `raw_body` never assigned to any state field; only `AIMessage(content=intent.narrative)` enters state |
| T-03-08 | Denial of Service | accept | CLOSED | Single-user Phase 3; `summarise_and_redact` semaphore and `max_tokens=200` constraint in redactor accepted at this scale |
| T-03-09 | Tampering | mitigate | CLOSED | `src/daily/cli.py:56-59` — explicit string membership checks before DB write: `value not in ("formal", "casual", "conversational")` for tone; `value not in ("concise", "standard", "detailed")` for briefing_length; error returned without calling `upsert_preference` |
| T-03-10 | Tampering | accept | CLOSED | `category_order` values come from a controlled set of section names in PREFERENCE_PREAMBLE; single-user Phase 3; accepted risk logged here |
| T-03-11 | Spoofing | accept | CLOSED | `user_id=1` hardcoded in CLI; single-user Phase 3; multi-user auth deferred to Phase 4+; accepted risk logged here |
| T-03-12 | Information Disclosure | mitigate | CLOSED | `src/daily/cli.py:466` — `decrypted = decrypt_token(token.encrypted_access_token, vault_key)` result stored in local variable `decrypted`, passed directly to adapter constructor; no logging of decrypted value; follows scheduler.py pattern |

---

## Accepted Risks Log

| Threat ID | Acceptance Rationale |
|-----------|----------------------|
| T-03-02 | `signal_log.metadata_json` is system-generated (not user-supplied). No PII risk in single-user Phase 3. Re-evaluate at Phase 4 when multi-user scope is introduced. |
| T-03-08 | `summarise_and_redact` semaphore (3 concurrent) and `max_tokens=200` provide adequate DoS surface reduction for single-user Phase 3. Re-evaluate at Phase 5 multi-tenant deployment. |
| T-03-10 | `category_order` is a comma-separated list of known section names (emails, calendar, slack) injected into a system prompt. Values originate from a small controlled set, not free-form user text. Single-user Phase 3 — no cross-user injection surface. Re-evaluate if user-defined section names are introduced. |
| T-03-11 | `user_id=1` hardcoded across all CLI commands. Consistent with existing CLI design. Multi-user authentication is a Phase 4+ requirement. |

---

## Unregistered Threat Flags

None. All SUMMARY.md `## Threat Flags` sections reported no new threat surface beyond the declared threat register.

---

## Transfer Documentation

None required for Phase 3 (no transferred threats in register).
