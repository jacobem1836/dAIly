# Requirements: dAIly

**Defined:** 2026-04-18
**Core Value:** The briefing always delivers — every morning, the user gets a prioritised, conversational summary of what matters without touching a single app.

## v1.2 Requirements

Requirements for the Deployability Layer milestone. Each maps to roadmap phases.

### Signal Capture

- [ ] **SIG-01**: User can generate `skip` signals (pausing/dismissing a briefing item) that are captured and stored in the signal table
- [ ] **SIG-02**: User can generate `re_request` signals (asking to repeat or clarify an item) that are captured and stored in the signal table
- [ ] **SIG-03**: Adaptive ranker ingests `skip` and `re_request` signals alongside `expand` when computing decay scores

### Observability

- [ ] **OBS-01**: All modules emit structured JSON logs with consistent fields (timestamp, level, module, message, context)
- [ ] **OBS-02**: Log level is configurable via environment variable without code changes
- [ ] **OBS-03**: Health check endpoint (`GET /health`) returns service status including DB, Redis, and scheduler state
- [ ] **OBS-04**: Key metrics are tracked and queryable: briefing generation latency, signal counts by type, memory store size

### Deployment

- [ ] **DEPLOY-01**: Docker Compose file defines the full stack (app + Postgres + Redis) and starts cleanly from a fresh clone
- [ ] **DEPLOY-02**: `.env.example` documents all required environment variables with descriptions; no secrets committed
- [ ] **DEPLOY-03**: Production configuration guide covers single-host VPS deployment (systemd or Docker, reverse proxy, TLS)

## Future Requirements

Tracked but not in current roadmap.

### Ecosystem Expansion (v2.0)

- **DASH-01**: Web dashboard — briefing history, preference management, memory browser
- **DASH-02**: Mobile companion app (iOS)
- **INTG-06**: Apple Mail (IMAP/SMTP) integration
- **INTG-07**: Travel integration (flights, hotels, itinerary)
- **INTG-08**: Finance integration (transactions, balances, alerts)
- **INTG-09**: Health integration (calendar-aware fitness/wellbeing)
- **INTG-10**: Smart home integration

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Distributed tracing (Jaeger/Zipkin) | Overkill for single-process single-host v1.2; revisit if multi-service |
| Cloud-managed Postgres / Redis | Self-hosted deployment is the target; managed services deferred to v2.0+ |
| CI/CD pipeline | Not in scope until the project has collaborators or automated deploys |
| Grafana dashboard | Queryable metrics are sufficient for v1.2; visual dashboarding deferred to v2.0 web UI |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SIG-01 | Phase 13 | Pending |
| SIG-02 | Phase 13 | Pending |
| SIG-03 | Phase 13 | Pending |
| OBS-01 | Phase 14 | Pending |
| OBS-02 | Phase 14 | Pending |
| OBS-03 | Phase 14 | Pending |
| OBS-04 | Phase 14 | Pending |
| DEPLOY-01 | Phase 15 | Pending |
| DEPLOY-02 | Phase 15 | Pending |
| DEPLOY-03 | Phase 15 | Pending |

**Coverage:**
- v1.2 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-18*
*Last updated: 2026-04-18 after v1.2 roadmap creation*
