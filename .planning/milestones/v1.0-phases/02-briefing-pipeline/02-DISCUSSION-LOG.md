# Phase 2: Briefing Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-04-05
**Phase:** 02-briefing-pipeline
**Mode:** discuss
**Areas discussed:** Content retrieval, Briefing structure, Email priority ranking, Redaction layer depth

---

## Areas Discussed

### Content Retrieval
| Question | Answer |
|----------|--------|
| How does Phase 2 get email/message bodies? | Extend adapters — add get_email_body / get_message_text methods |
| Rationale | User deferred to production best practice — colocating body-fetch in provider adapters avoids duplicating auth/retry logic |

### Briefing Structure
| Question | Answer |
|----------|--------|
| Narrative format | Flowing narrative (spoken-English paragraphs, TTS-optimised) |
| Briefing length | Concise (90–120s target) |
| Adaptive length? | Deferred — noted as todo for a future phase |

### Email Priority Ranking
| Question | Answer |
|----------|--------|
| Sender weight cold-start | Both heuristics AND optional VIP list (`daily vip add`) |
| Rationale | User: "Both, this is best considering a production interface for the product" |
| Email scope | List all 24h metadata, rank all, fetch bodies for user-configured top-N |
| Rationale | User: "user chooses top n to brief (choice is in setup of the system)" |

### Redaction Layer Depth
| Question | Answer |
|----------|--------|
| Redaction approach | Summarise + strip credentials (option 1) |
| User question | Asked whether option 1 is significantly less secure than full PII detection (presidio) |
| Claude response | No — pre-summarisation naturally strips credential strings; presidio is enterprise compliance tooling, overkill for M1 personal assistant |
| Summarisation model | Claude's discretion |

---

## Corrections Made

None — all decisions were confirmed by user selections or user deferred to Claude's judgement.

---

## Deferred Todos Captured

- Adaptive briefing length (user requested as GSD todo)
