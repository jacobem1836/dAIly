# dAIly

## What This Is

A voice-first AI personal assistant that proactively synthesises a user's digital life into an intelligent daily briefing. It acts as a semi-autonomous operator for communication, scheduling, and decision support — combining executive briefing, conversational assistant, and action-taking agent. Built backend-first, targeting busy professionals and operators who want their life to brief them rather than manually checking multiple apps.

## Core Value

The briefing always delivers: every morning, the user gets a prioritised, conversational summary of what matters — without touching a single app.

## Milestone Plan

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M1 — Core Backend** | Agent orchestrator, integrations (email/calendar/messaging), briefing pipeline, action layer, voice interface | Active |
| **M2 — Intelligence Layer** | Adaptive prioritisation, deeper memory system, trusted actions, improved conversation flow | Planned |
| **M3 — Ecosystem Expansion** | Travel, finance, health, smart home, document platforms | Planned |
| **M4 — Autonomy** | Proactive decision-making, multi-step task execution, predictive assistance | Planned |

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Briefing Pipeline**
- [ ] Pull and rank data from email, calendar, and messaging integrations
- [ ] Generate structured briefing narrative via LLM
- [ ] Deliver briefing via voice (TTS)
- [ ] Support briefing interruption and follow-up questions

**Integrations**
- [ ] OAuth 2.0 authentication for Google (Gmail, Calendar) and Microsoft (Outlook, Teams)
- [ ] Email ingestion pipeline (last 24h, ranked by priority)
- [ ] Calendar ingestion (today + next 24–48h with contextual insights)
- [ ] Messaging ingestion (mentions, DMs, priority channels — Slack)

**Action Layer**
- [ ] Draft email/message replies
- [ ] Schedule and reschedule calendar events
- [ ] Summarise threads on demand
- [ ] Approval flow for all external-facing actions
- [ ] Action log (every action recorded with timestamp, type, approval status)

**Personalisation**
- [ ] Basic user profile (preferences, tone, briefing structure)
- [ ] Signals captured from interactions (skips, corrections, re-requests)

**Voice Interface**
- [ ] Speech-to-text (STT) pipeline
- [ ] Text-to-speech (TTS) response streaming
- [ ] Low-latency voice interaction loop

**Privacy & Security**
- [ ] OAuth tokens encrypted at rest
- [ ] No raw data passed to LLM (pre-filter/redaction layer)
- [ ] Local-first sensitive memory storage

### Out of Scope (M1)

- Mobile/iOS app — backend-first; UI comes in M2+
- Web dashboard — deferred to M2
- News integration — not in M1 integrations
- Travel, finance, health, smart home — M3+
- Trusted auto-actions (no approval required) — M2 after trust is established
- Fully local LLM — GPT-class cloud model required for M1 quality

## Context

- PRD and architecture notes live in `daily-prompt.txt` at project root
- Architecture: `[Voice/UI] → [Orchestrator] → [Context Builder] → [LLM] → [Action Engine] → [Integrations]`
- LLM is NOT permitted to call APIs directly — all execution goes through the backend
- Precomputed briefing strategy: fetch + summarise before user wakes, cache locally for instant delivery
- Target stack: Python/Node backend, Whisper-class STT, neural TTS, encrypted PostgreSQL, OAuth 2.0
- Multi-model strategy: large model for reasoning/briefing, smaller/local for quick responses

## Constraints

- **Architecture**: LLM must not directly access APIs or hold credentials — backend mediates everything
- **Privacy**: Raw email/message bodies must not be stored long-term — only summaries and metadata
- **Latency**: Voice responses must feel instant — precompute briefings, stream TTS
- **Security**: OAuth tokens encrypted at rest (AES-256), stored in secure vault (never frontend)
- **Autonomy**: All external-facing actions require user approval in M1 — auto-actions are M2+

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend-first for M1 | Validates core agent loop before investing in UI | — Pending |
| Cloud LLM (not on-device) | GPT-class reasoning required for M1 quality; local LLM insufficient | — Pending |
| Orchestrator pattern (LLM ≠ executor) | Security + reliability — LLM plans, backend executes | — Pending |
| Approval-required for all M1 actions | Build user trust before enabling autonomy | — Pending |
| Precomputed briefing cache | Eliminates voice latency at delivery time | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-05 after initialization*
