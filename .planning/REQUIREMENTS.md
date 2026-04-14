# Requirements: dAIly

**Defined:** 2026-04-05
**Core Value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.

## v1.1 Requirements

Requirements for the Intelligence Layer milestone. Each maps to a roadmap phase.

### Intelligence

- [ ] **INTEL-01**: User receives briefing ranked by learned personal priorities, not static heuristics
- [ ] **INTEL-02**: System recalls facts from previous sessions when building each day's briefing context

### Memory

- [ ] **MEM-01**: User can ask "what do you know about me?" and hear a summary of stored facts (capped at 10, paginated verbally)
- [ ] **MEM-02**: User can delete a specific remembered fact by stating it
- [ ] **MEM-03**: User can disable memory learning or reset all stored facts

### Autonomy

- [ ] **ACT-07**: User can configure per-action-type autonomy level (suggest / approve / auto); high-impact actions (send email, external calendar invites) locked to approve regardless

### Conversation

- [ ] **CONV-01**: User can interrupt mid-briefing and resume from the same section without restarting
- [ ] **CONV-02**: User can switch fluidly between briefing, Q&A, and action modes in a single session
- [ ] **CONV-03**: System compresses verbosity when user signals time pressure ("I'm in a rush", "keep it short")

### Fixes

- [ ] **FIX-01**: Scheduler correctly scores direct-to-user emails at WEIGHT_DIRECT (10pts), not CC weight — unblocks accurate signal collection for INTEL-01
- [ ] **FIX-02**: Slack ingestion fetches all pages for large workspaces via cursor-based pagination
- [ ] **FIX-03**: Thread summarisation uses real message IDs extracted from briefing metadata, not `last_content` stub

## v2.0 Requirements (Deferred)

### Ecosystem Integrations

- **INTG-07**: Travel — flight bookings, hotel reservations, itinerary management
- **INTG-08**: Finance — bank transaction summaries, spending insights
- **INTG-09**: Health — sleep, steps, recovery metrics
- **INTG-10**: Smart home — lights, locks, appliances
- **INTG-11**: Document platforms — Google Drive, Notion

### Interface

- **DASH-01**: Web dashboard — memory inspection, permissions, action history
- **DASH-02**: Mobile app — iOS native interface
- **DASH-03**: Daily summary view — recap of briefing + actions taken

### Autonomy

- **ACT-08**: Full autonomous action sequences across multiple services (no per-action approval)

## Out of Scope

| Feature | Reason |
|---------|--------|
| mem0ai integration | Documented production issues (10k+ junk extractions); langmem + custom schema is the right approach |
| Proper ML ranking model (BPR, neural) | Insufficient training data at v1.1 scale (~20-50 examples); score-multiplier blend is correct |
| Inline memory field editing | Delete-and-restate is the production pattern (ChatGPT reference); inline edit adds UI complexity with no UX gain |
| Sentence-level briefing cursor | Section-level is sufficient for v1.1; sentence-level adds complexity for marginal UX improvement |
| Voice cloning | v2.0+ |
| Team/enterprise mode | v2.0+ |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FIX-01 | Phase 7 | Pending |
| FIX-02 | Phase 7 | Pending |
| FIX-03 | Phase 7 | Pending |
| INTEL-01 | Phase 8 | Pending |
| INTEL-02 | Phase 9 | Pending |
| MEM-01 | Phase 10 | Pending |
| MEM-02 | Phase 10 | Pending |
| MEM-03 | Phase 10 | Pending |
| ACT-07 | Phase 11 | Pending |
| CONV-01 | Phase 12 | Pending |
| CONV-02 | Phase 12 | Pending |
| CONV-03 | Phase 12 | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-05*
*Last updated: 2026-04-15 after v1.1 roadmap creation*
