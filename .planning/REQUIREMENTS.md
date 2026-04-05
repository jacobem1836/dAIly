# Requirements: dAIly

**Defined:** 2026-04-05
**Core Value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.

---

## v1 Requirements

### Briefing Pipeline

- [ ] **BRIEF-01**: System precomputes a morning briefing overnight (default 5am), caching the result for instant voice delivery on user request
- [ ] **BRIEF-02**: User can configure the briefing precompute schedule time
- [ ] **BRIEF-03**: System ingests last 24h of email from connected accounts, ranks by heuristic priority (sender weight, deadline keywords, thread activity)
- [ ] **BRIEF-04**: System ingests today's and next 48h of calendar events, including conflict detection and meeting prep context
- [ ] **BRIEF-05**: System ingests Slack mentions, DMs, and priority channels from connected workspace
- [ ] **BRIEF-06**: Briefing narrative is generated via LLM from pre-ranked, pre-summarised context (raw data never passed directly to LLM)
- [ ] **BRIEF-07**: User can request thread summarisation on demand during briefing ("summarise that email chain")

### Voice Interface

- [ ] **VOICE-01**: System streams TTS output sentence-by-sentence (Cartesia Sonic-3 or equivalent), beginning playback before full response is generated
- [ ] **VOICE-02**: System streams STT input with interim results (Deepgram Nova-3 or equivalent) to minimise perceived latency
- [ ] **VOICE-03**: End-to-end voice response latency is under 1.5s for follow-up turns; briefing delivery begins within 1s of user request (from cache)
- [ ] **VOICE-04**: User can interrupt the briefing mid-sentence to redirect or ask a follow-up (VAD-based barge-in detection)
- [ ] **VOICE-05**: User can ask follow-up questions during the briefing and receive contextually-aware answers (session context maintained in-memory)

### Integrations

- [ ] **INTG-01**: User can connect a Gmail account via OAuth 2.0 with minimum required scopes (read email, draft/send replies)
- [ ] **INTG-02**: User can connect a Google Calendar account via OAuth 2.0 (read events, create/update events)
- [ ] **INTG-03**: User can connect a Microsoft Outlook account via OAuth 2.0 / Microsoft Graph (read email, draft/send replies, read/write Exchange calendar)
- [ ] **INTG-04**: User can connect a Slack workspace via OAuth 2.0, registered as an internal custom app (≥50 req/min rate limit tier)
- [ ] **INTG-05**: OAuth access tokens are refreshed proactively in a background process before scheduled briefing jobs run (not inline)

### Action Layer

- [ ] **ACT-01**: System can draft an email reply based on user instruction during briefing
- [ ] **ACT-02**: System can draft a Slack message reply based on user instruction during briefing
- [ ] **ACT-03**: System can create or reschedule a calendar event based on user instruction
- [ ] **ACT-04**: All external-facing actions require explicit user approval (confirm/reject) before execution — no bypass path exists in code
- [ ] **ACT-05**: Every action attempt is logged with: timestamp, action type, target, content summary, approval status, and outcome
- [ ] **ACT-06**: Action executor validates recipient, content type, and scope against a whitelist before dispatch (action sandboxing)

### Personalisation

- [ ] **PERS-01**: System maintains a user profile storing preferences: tone, briefing length, category order, notification preferences
- [ ] **PERS-02**: System captures implicit interaction signals: skips, corrections, re-requests, and follow-up patterns — stored for future ranking use
- [ ] **PERS-03**: Briefing priority ranking uses heuristic defaults at cold start: sender importance score, deadline keyword detection, thread activity recency

### Security

- [ ] **SEC-01**: OAuth tokens are encrypted at rest (AES-256) and stored in a secrets vault — never exposed to frontend, logs, or LLM context
- [ ] **SEC-02**: A pre-filter/redaction layer sanitises all external data (email bodies, messages) before passing to LLM — removes credentials, PII patterns, and potential injection payloads
- [ ] **SEC-03**: Each integration requests only the minimum OAuth scopes required for its function; no broad permissions
- [ ] **SEC-04**: Raw email and message bodies are not stored long-term — only summaries and metadata are persisted after processing
- [ ] **SEC-05**: All LLM tool-call outputs are treated as intents only; the backend orchestrator validates and dispatches — LLM never holds credentials or calls external APIs directly

---

## v2 Requirements

### Intelligence

- **INTEL-01**: Priority ranking engine learns from M1 signal data to replace heuristic defaults with personalised scoring
- **INTEL-02**: Cross-session conversational memory persists context across days (pgvector + structured user profile extraction)

### Autonomy

- **AUTO-01**: Staged autonomy model — user can grant trusted auto-action permissions for specific contacts or action types (no approval required for trusted actions)

### Dashboard

- **DASH-01**: Web dashboard for memory/profile inspection and editing
- **DASH-02**: Web dashboard for permissions management per integration
- **DASH-03**: Web dashboard for action log review and undo where possible

### Integrations

- **INTG-06**: Apple Mail integration via IMAP/SMTP with app-specific password auth (iCloud accounts)
- **INTG-07**: Apple Calendar integration via CalDAV

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Always-on ambient listening | Privacy exposure, battery drain, accidental triggers — not viable in M1 |
| Auto-send without approval | One wrong send destroys user trust permanently — earn trust first in M2 |
| News / web content briefing | Separate curation problem; risks diluting personal signal quality |
| Mobile / iOS app | Backend-first; UI investment deferred until core loop validated |
| Web dashboard | M2 after core loop validated — frontend burns time before value proven |
| Real-time push webhooks | Complexity spike with no user benefit for a batch-briefing product; polling sufficient |
| Smart home / IoT integration | Different product category entirely |
| Fully local LLM | GPT-class reasoning quality required; local models insufficient in 2026 |
| Voice biometrics / speaker ID | High complexity, fragile edge cases; OAuth session auth sufficient for M1 |
| Social media integration | Low signal-to-noise; not actionable content |
| Travel / finance / health integrations | M3+ after product-market fit established |
| Multi-user / team briefings | Different product category; separate persona research required |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BRIEF-01 | TBD | Pending |
| BRIEF-02 | TBD | Pending |
| BRIEF-03 | TBD | Pending |
| BRIEF-04 | TBD | Pending |
| BRIEF-05 | TBD | Pending |
| BRIEF-06 | TBD | Pending |
| BRIEF-07 | TBD | Pending |
| VOICE-01 | TBD | Pending |
| VOICE-02 | TBD | Pending |
| VOICE-03 | TBD | Pending |
| VOICE-04 | TBD | Pending |
| VOICE-05 | TBD | Pending |
| INTG-01 | TBD | Pending |
| INTG-02 | TBD | Pending |
| INTG-03 | TBD | Pending |
| INTG-04 | TBD | Pending |
| INTG-05 | TBD | Pending |
| ACT-01 | TBD | Pending |
| ACT-02 | TBD | Pending |
| ACT-03 | TBD | Pending |
| ACT-04 | TBD | Pending |
| ACT-05 | TBD | Pending |
| ACT-06 | TBD | Pending |
| PERS-01 | TBD | Pending |
| PERS-02 | TBD | Pending |
| PERS-03 | TBD | Pending |
| SEC-01 | TBD | Pending |
| SEC-02 | TBD | Pending |
| SEC-03 | TBD | Pending |
| SEC-04 | TBD | Pending |
| SEC-05 | TBD | Pending |

**Coverage:**
- v1 requirements: 31 total
- Mapped to phases: 0 (populated during roadmap creation)
- Unmapped: 31 ⚠️

---
*Requirements defined: 2026-04-05*
*Last updated: 2026-04-05 after initial definition*
