# Roadmap: dAIly

## Milestones

- ✅ **v1.0 MVP** — Phases 1–6 (shipped 2026-04-14)
- 📋 **v1.1 Intelligence Layer** — Phases 7–11, 17 (in progress)
- 📋 **v1.2 Mobile Voice** — Phases 18–21 (planned)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–6) — SHIPPED 2026-04-14</summary>

- [x] Phase 1: Foundation (5/5 plans) — completed 2026-04-06
- [x] Phase 2: Briefing Pipeline (5/5 plans) — completed 2026-04-07
- [x] Phase 3: Orchestrator (4/4 plans) — completed 2026-04-10
- [x] Phase 4: Action Layer (3/3 plans) — completed 2026-04-12
- [x] Phase 5: Voice Interface (4/4 plans) — completed 2026-04-13
- [x] Phase 6: Wire Preferences to Briefing (1/1 plan) — completed 2026-04-14

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

### 📋 v1.1 Intelligence Layer (In Progress)

- [x] Phase 17: Voice Polish — barge-in reliability (Bugs A-D), streaming TTS, echo suppression (11/12 verified, structural AEC issue closed)
- [ ] Phase 7: Tech Debt Fixes — fix user_email="" stub (WEIGHT_DIRECT never fires), Slack pagination (single-page only), message_id stub in thread summarisation
- [ ] Phase 8: Memory System — persistent user memory via mem0 + pgvector; extract facts from interactions, retrieve at briefing/query time for personalisation
- [ ] Phase 9: Adaptive Prioritisation — context-aware ranking of briefing items using urgency signals, user history, sender importance, and memory
- [ ] Phase 10: Adaptive Tone — briefing style adjusts based on time of day, user mood signals, content gravity, and learned preferences
- [ ] Phase 11: Trusted Actions — auto-execute pre-approved action categories without confirmation; user-managed allowlist with audit trail

### 📋 v1.2 Mobile Voice (Planned)

- [ ] Phase 18: LiveKit Agents Backend Integration — wire LangGraph into LiveKit agent framework via livekit-plugins-langchain
- [ ] Phase 19: Native iOS App — Swift + LiveKit iOS SDK, AVAudioEngine AEC, minimal UI
- [ ] Phase 20: Native Android App — Kotlin + LiveKit Android SDK, Oboe AEC, minimal UI
- [ ] Phase 21: Desktop Web Fallback — LiveKit web SDK, replaces current sounddevice voice loop

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 5/5 | Complete | 2026-04-06 |
| 2. Briefing Pipeline | v1.0 | 5/5 | Complete | 2026-04-07 |
| 3. Orchestrator | v1.0 | 4/4 | Complete | 2026-04-10 |
| 4. Action Layer | v1.0 | 3/3 | Complete | 2026-04-12 |
| 5. Voice Interface | v1.0 | 4/4 | Complete | 2026-04-13 |
| 6. Wire Preferences | v1.0 | 1/1 | Complete | 2026-04-14 |
| 17. Voice Polish | v1.1 | 4/4 | Complete | 2026-04-27 |
| 7. Tech Debt Fixes | v1.1 | 0/0 | Not started | — |
| 8. Memory System | v1.1 | 0/0 | Not started | — |
| 9. Adaptive Prioritisation | v1.1 | 0/0 | Not started | — |
| 10. Adaptive Tone | v1.1 | 0/0 | Not started | — |
| 11. Trusted Actions | v1.1 | 0/0 | Not started | — |

## Backlog

### Phase 999.1: Voice-First Onboarding (BACKLOG)

**Goal:** Make the entire app setup/onboarding experience voice-driven (or offer it as an option). Instead of menus and clicking, the user has a conversation in the same style as the rest of dAIly — that conversation IS the setup. Covers connecting integrations, setting preferences, and configuring the briefing. Should feel like talking to the assistant from day one.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)

---

### Phase 999.2: Deep Customization (BACKLOG)

**Goal:** Everything needs to be highly customizable and easy to configure. Briefing length, data sources, news preferences, the three-tier privacy/security options, and as many other layers as possible. The customization surface must be discoverable and easy — not buried. May warrant its own milestone given scope.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)
