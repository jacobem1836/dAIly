# dAIly — Technical Due-Diligence & Integration-Friction Review

**Date:** 2026-06-19
**Reviewer role:** Principal Engineer / Systems Architect / Integration Specialist
**Branch reviewed:** `gsd/phase-21.4-test-coverage`
**Verdict in one line:** The product is not over-built in size (9.4k backend LOC) — it is **half-migrated**. A mobile-first/LiveKit architecture was layered on top of the original CLI/local-voice architecture without retiring the old one. Most friction is the cost of carrying two of everything across a 5+ service boundary that no test exercises.

---

## 1. Executive Summary

dAIly works in pieces. The reason it *feels* hard to finish is structural, not volumetric:

1. **Two parallel voice architectures.** A 1,316-LOC local CLI audio pipeline (`src/daily/voice/`) reimplements STT/TTS/barge-in that the production path (`worker/` via the `livekit-agents` library) gets for free. Both converge on the same LangGraph orchestrator but through different checkpointers (`MemorySaver` vs `AsyncPostgresSaver`). Every voice behaviour change can require editing both paths.
2. **The remaining 20% is the E2E integration path** — `mobile → /livekit/token → LiveKit room → worker agent → LangGraph → approval interrupt → external API` — which crosses ~7 boundaries and 5 services. The test suite is large (16.9k LOC, 1.8:1 vs source) but **unit-level**, so these failures only appear in live sessions. Result: the recent commit history is whack-a-mole bug-fixing (`fix: resolve 4 live-session bugs`, `fix: resolve 5 LiveKit voice issues`), and velocity collapsed from ~150 commits/week (week 15) to ~30/week (week 19).
3. **The actual product value isn't built yet.** Phase 21.5 (Adaptive Learning & Memory — the "it learns you" promise) has not started. The team is spending its energy on plumbing reliability *before* reaching the differentiator. Building 21.5 on top of the dual-path architecture would double its cost.
4. **Two mobile clients at uneven parity.** iOS ≈ 85% ready; Android ≈ 50% (no onboarding, integration, or permissions UI). Maintaining parity is a tax paid before either is validated with real users.

**Highest-ROI move:** delete the legacy voice path, unify on `livekit-agents`, ship **iOS-only** to TestFlight behind **one** E2E smoke test, and fix config drift. This removes ~1,300 LOC and most of the duplicated blast radius without removing a single user-facing feature.

---

## 2. Research Findings (external → principles)

Sources: Ponytail (DietrichGebert/ponytail), 12-Factor Agents, Anthropic "Building Effective Agents", voice-AI production post-mortems.

**Principles extracted (kept only the ones this repo violates):**

| # | Principle | Source | dAIly status |
|---|-----------|--------|--------------|
| P1 | Don't write what a dependency already does. | Ponytail | ❌ `voice/` reimplements `livekit-agents` |
| P2 | Control flow lives in deterministic code; the LLM emits a decision and stops. | 12-Factor | ◑ LangGraph does this, but with ceremony |
| P3 | One source of session truth, not scattered across context+Redis+DB+client. | 12-Factor | ❌ split across 4 layers |
| P4 | Start with one LLM call + retrieval; add agent complexity only after the simple thing fails. | Anthropic | ◑ 5-node graph for a near-linear flow |
| P5 | Human-in-the-loop is a day-one primitive, not a retrofit. | 12-Factor | ✅ done well (interrupt gate) |
| P6 | Structured tracing across services, or every voice incident is multi-hour archaeology. | Voice-AI | ❌ no E2E tracing → whack-a-mole |
| P7 | Own what runs under the framework before shipping. | Anthropic | ◑ LangGraph + livekit-agents magic |
| P8 | Pick one platform/path; compose narrow, don't widen. | 12-Factor / Anthropic | ❌ 2 voice paths, 2 clients |

**Integration-hell root causes for voice + mobile + multi-service (and where dAIly hits them):**
- Brittle connectors, not LLM failures (OAuth token refresh races) — **hits** `IntegrationToken` decrypt path.
- State scattered across layers (briefing in Redis, session in Postgres checkpointer, UI state on device) — **hits** the "briefing context lost on follow-up" bug class.
- Latency budget exhausted by serial hops — **hits** the STT/verbosity/latency debug sessions.
- Mobile lifecycle edge cases found last (backgrounding, network drop, mid-session permission denial) — **hits** `ios-mic-permissions-stuck`, reconnect-timeout bugs.
- Graph creep — **partially**; the graph is still small (5 nodes) but already dual-checkpointer'd.

---

## 3. Repository Understanding (map)

```
dAIly/
├── src/daily/                      9,372 LOC Python (the product backend)
│   ├── orchestrator/   1,443  LangGraph: respond/summarise/draft/approval/execute  (nodes.py 868)
│   ├── briefing/       1,376  APScheduler cron → ingest → rank → summarise → Redis cache
│   ├── voice/          1,316  ⚠ LEGACY local mic→Deepgram→graph→Cartesia→speaker (CLI only)
│   ├── (root) cli.py     817  ⚠ LEGACY original interface, now a test harness
│   ├── integrations/     575  google/microsoft/slack adapters + OAuth router (419)
│   ├── worker/           500  ✅ PRODUCTION voice: livekit-agents VoicePipelineAgent + graph bridge
│   ├── auth/             331  magic-link → JWT pairing
│   ├── actions/          327  approval-gated email/calendar actions
│   ├── vault/            304  AES-256-GCM OAuth token store + proactive refresh (NOT memory)
│   ├── profile/users/db  ~457
│   └── livekit/           63  ✅ ephemeral room JWT minting
├── ios/                3,183 LOC Swift   ✅ ~85% ready (auth, voice, onboarding, integrations)
├── android/            1,378 LOC Kotlin  ◑ ~50% ready (voice+auth only; no onboarding UI)
├── tests/             16,904 LOC, 107 files  (unit-heavy; thin E2E)
├── alembic/ docker-compose*.yml livekit.yaml turnserver.conf
├── automation/ (git submodule), landing/ marketing/ content/ graphify-out/   ← not the product
└── .planning/  233 files (GSD workflow)
```

**Services to run:** postgres, redis, **self-hosted LiveKit**, **coturn (TURN)**, api, worker = 6 containers, plus external Deepgram + Cartesia + OpenAI + Google/Microsoft/Slack OAuth + Resend.

**Two entrypoints into the same brain:**
- `cli.py` → `voice/loop.py` → `build_graph(MemorySaver())` (ephemeral) — legacy/dev.
- `worker/__main__.py` → LiveKit job → `voice_pipeline` → `build_graph(AsyncPostgresSaver)` (persistent) — production/mobile.

---

## 4. Dependency Map & Coupling Hotspots

**Bottleneck modules (high fan-in):**
- `config.py` Settings singleton — referenced by ~30 files. Single boot dependency; also where the `.env`/`.env.example` drift bites.
- `db/models.py::IntegrationToken` — the convergence table. Every briefing, voice session, and action decrypts tokens from it at runtime (no cache, by security design). Touched by scheduler, orchestrator/session, worker/state, integrations/router, vault/refresh, cli.
- `vault/crypto.py` (encrypt/decrypt) — scheduler, vault/refresh, integrations/router.
- `integrations/base.py` (adapter interfaces) — scheduler, context_builder, orchestrator, worker, cli.
- `orchestrator/` — imported by 14 files; the shared brain both voice paths route through.

**Circular / duplicated responsibility:** `voice/stt.py + voice/tts.py + voice/barge_in.py` (1,316 LOC, raw WebSocket Deepgram/Cartesia + barge-in) vs `worker/voice_pipeline.py` (127 LOC delegating the identical pipeline to `livekit-agents`). Same job, two implementations.

---

## 5. Integration Friction Audit

Scores 1–10 (higher = worse for burden columns; MVP value higher = more user value).

| Subsystem | Complexity | MVP value | Integration burden | Maintenance burden | Verdict |
|---|---|---|---|---|---|
| Briefing pipeline | 6 | **10** | 5 | 5 | **Keep** |
| Worker + LiveKit (prod voice) | 6 | **9** | 7 | 5 | **Keep / consolidate** |
| Integrations + adapters + vault crypto | 6 | 9 | 6 | 5 | **Keep** |
| iOS client | 6 | **10** | 6 | 5 | **Keep** |
| LangGraph orchestrator | 7 | 7 | 7 | 6 | **Simplify** (keep interrupt, drop ceremony) |
| Vault token refresh | 4 | 7 | 4 | 3 | **Keep** |
| `cli.py` | 5 | 3 | 6 | 5 | **Simplify** (shrink to thin harness) |
| **`voice/` local pipeline** | **8** | **2** | **8** | **8** | **Remove** |
| Android client | 6 | 4* | 6 | 7 | **Defer/freeze** (*for MVP; high later) |
| Self-host LiveKit + coturn | 7 | 6 | 6 | **8** | **Replace** (LiveKit Cloud for MVP) |
| api + worker 2-container split | 5 | 5 | 5 | 5 | **Consolidate** (evaluate) |
| landing/marketing/content/automation in product repo | 3 | 1 | 4 | 4 | **Remove** from product repo |

**Integration cost per user flow** (systems / boundaries / files / external svcs / state transitions):

| Flow | Sys | Bound | Files | Ext | Transitions | Cost |
|---|---|---|---|---|---|---|
| **Mobile voice interaction** | 6 | ~7 | 15+ | 4 | many (async) | **Highest** |
| Daily briefing generation | 6 | 4 | 12+ | 4 | 7 | High |
| Approval workflow | 4 | 3 | 8 | 1–3 | 4 (×2 paths) | High (dual) |
| Mobile startup/auth | 4 | 3 hops | 8 | 2 | 5 async | High |
| Email ingestion | 5 | 3 | 6 | 3 | 4 | Medium |
| OAuth onboarding | 4 | 3 | 6 | 3 | 4 | Medium |
| Memory retrieval | — | — | — | — | — | Not built (21.5) |

**Change blast radius:**
- **Voice change** → potentially `voice/` *and* `worker/voice_pipeline` + `livekit/` + iOS `VoiceSession` + Android `VoiceSession` + `orchestrator/session`. Largest blast radius, driven by duality.
- **Auth change** → `auth/router` + `users` + iOS `AuthService` + Android `AuthService` + `livekit/tokens` + vault. Spans backend + 2 clients.
- **Briefing change** → scheduler + context_builder + narrator + Redis + config. Contained.
- **Memory change** → greenfield (nothing to break, but nothing to build on).

---

## 6. Mobile Readiness Audit (severity-ranked)

**CRITICAL**
1. Token-refresh assumes the network always works — single 401 → one retry → unrecoverable `auth_refresh_failed`, no backoff, no retry UI (`ios/.../VoiceSession.swift:71-89`, `AuthService.swift:67-82`).
2. Hardcoded 8s "agent unreachable" timeout fires on a slow backend token issue and surfaces a misleading error (`VoiceSession.swift:113-123`).

**HIGH**
3. 60s agent-join timeout: if the worker crashes post-connect, user waits a full minute.
4. 30s reconnect timeout, no backoff: a >30s WiFi glitch silently kills the session.
5. iOS has no `scenePhase` lifecycle observer → backgrounding may silently drop the LiveKit connection.

**MEDIUM**
6. Onboarding gate state not persisted → force-quit mid-onboarding resets progress.
7. Magic-link always returns 204 (anti-enumeration) → user can't distinguish "no email" from "Resend failed."
8. **Android onboarding/integration/permissions UI entirely missing** → Android cannot complete first-run.

**Desktop/CLI assumptions that break on mobile:** synchronous startup (no "connecting…" state on cold start), persistent WebSocket (mobile networks churn), server-local mic (the entire reason `voice/` is legacy), inline synchronous token refresh, no background-processing model.

---

## 7. Complexity Audit (cost vs benefit)

| Finding | Why it exists | Current benefit | Current cost | Action |
|---|---|---|---|---|
| Legacy `voice/` pipeline kept after LiveKit adoption | Built first (Phases 5/17), worked, never deleted | CLI voice demo | 1,316 LOC + dual STT/TTS + dual checkpointer + 2× voice blast radius | **Remove** |
| Self-hosted LiveKit + coturn | Avoid vendor cost / full control | Control | 2 extra services, TURN/NAT ops, harder local+prod parity | **Replace** w/ LiveKit Cloud for MVP |
| Two native clients to parity | Wanted both stores at launch | Reach | Every feature/bug paid twice; Android half-done | **Freeze Android** until iOS validated |
| LangGraph for a ~5-node near-linear flow | HITL interrupt requirement (real) | Approval gate safety + observability | StateGraph/checkpointer ceremony; dual saver | **Simplify**, keep interrupt |
| `.env` 25 vars vs `.env.example` 10 | Drift as integrations were added | — | New env can't boot from example; silent misconfig | **Fix** (regenerate example) |
| 199 `* 2.*` duplicate files | iCloud sync conflicts | none | Noise, confusion, accidental edits to wrong file | **Remove** + move repo off iCloud-synced path |
| marketing/content/landing/automation submodule in product repo | GTM lived alongside code | convenience | Conflates product with go-to-market; clutter | **Extract** to separate repo |
| Unit-heavy tests, no E2E smoke | TDD habit at unit level | regression safety on units | Doesn't catch the only failures that ship | **Add 1 E2E smoke** |

---

## 8. Keep / Simplify / Consolidate / Replace / Remove

- **Keep:** briefing pipeline, worker+LiveKit production voice, integrations+adapters+vault, iOS client, approval interrupt.
- **Simplify:** LangGraph (retain `interrupt()`+`Command(resume)`, drop unused graph machinery / one checkpointer), `cli.py` (shrink to a thin text harness over `worker/llm_bridge.py`).
- **Consolidate:** the two STT/TTS pipelines → one (`livekit-agents`); evaluate folding `api`+`worker` deployment; single checkpointer (`AsyncPostgresSaver`).
- **Replace:** self-hosted LiveKit+coturn → LiveKit Cloud (MVP); `.env.example` → generated-from-actual.
- **Remove:** `src/daily/voice/`, the CLI voice command path, 199 duplicate `* 2.*` files, marketing/content from the product repo (extract, don't delete).

> No user-facing feature is removed. Briefing, voice, email/calendar, approvals, memory all stay. The cuts are duplicated *implementations* and premature infra.

---

## 9. Alternative Architectures

### Option A — Minimal-risk evolution (recommended first step)
- Delete `voice/` + CLI voice command; unify on `livekit-agents`. Single checkpointer.
- Regenerate `.env.example`; add one E2E smoke test (pair → token → room → agent greeting → one approval round-trip).
- Freeze Android; ship iOS to TestFlight.
- **Infra unchanged.** Effort: low–moderate. Benefit: removes ~1,300 LOC and the largest blast radius. Risk: low (legacy path isn't in the prod flow).

### Option B — Balanced simplification (recommended target)
- Everything in A, plus: LiveKit Cloud (drop self-host LiveKit + coturn), flatten LangGraph ceremony, extract marketing/content/automation to its own repo, decide api/worker consolidation.
- Effort: moderate. Benefit: 6 services → 3–4; local==prod parity; cleaner repo. Risk: moderate (LiveKit Cloud migration + env wiring).

### Option C — Aggressive (ship fastest)
- iOS + one backend process only. Replace LangGraph with a plain async function holding one approval `await` point (graph is 5 nodes). LiveKit Cloud + `livekit-agents` for STT/LLM/TTS. Briefing = cron → summarise → cache. Drop Android, coturn, self-host LiveKit, CLI, in-repo marketing. Defer adaptive learning to post-launch.
- Effort: higher up-front rewrite of orchestrator. Benefit: smallest possible surface (1 deploy + LiveKit Cloud + Postgres + Redis). Risk: rewriting the working approval brain is the one thing currently solid — **don't, unless A/B prove insufficient.**

**Recommendation:** Sequence **A → B**. A is also a prerequisite for B. Reserve C's "replace LangGraph" idea only if the graph later creeps.

---

## 10. ADR Ledger

| ADR | Current | Proposed | Rationale | Alternatives | Trade-off | Confidence |
|---|---|---|---|---|---|---|
| 001 | Dual voice (local `voice/` + LiveKit) | Single `livekit-agents` path | Removes 1,316 LOC + dual checkpointer; kills largest blast radius | Keep both behind a flag | Lose CLI mic demo (low value) | **High** |
| 002 | Self-host LiveKit + coturn | LiveKit Cloud (MVP) | −2 services, managed TURN, local==prod | Stay self-hosted | Vendor cost + lock-in | Medium |
| 003 | iOS + Android to parity | iOS-first; freeze Android | Stop paying every cost twice pre-validation | Ship both | Delays Android launch | **High** |
| 004 | LangGraph 5-node graph, 2 checkpointers | Keep interrupt, 1 checkpointer, trim ceremony | Keep HITL safety, drop overhead | Hand-rolled state machine (Option C) | Some refactor risk | Medium |
| 005 | `.env.example` drift (10 of 25) | Generate from actual | Bootable, fewer silent misconfigs | Manual doc | one-time chore | **High** |
| 006 | Unit-only tests | +1 E2E smoke on voice path | Catches the only class that ships | Manual QA | smoke maintenance | **High** |
| 007 | Marketing/content in product repo | Extract to own repo | De-clutter; clearer boundary | Leave it | migration chore | Medium |
| 008 | api + worker split | Evaluate consolidation | Fewer deploy units if worker can host scheduler | Keep split | scaling ceiling later | Low |

---

## 11. Prioritised Roadmap (by ROI)

| # | Task | Complexity | Risk | Benefit | Depends on | Validation |
|---|---|---|---|---|---|---|
| 1 | Delete `voice/` + CLI voice cmd; unify on `livekit-agents`; single checkpointer | Med | Low | **Highest** (−1.3k LOC, −1 blast radius) | — | E2E smoke + existing worker tests green |
| 2 | Add 1 E2E smoke (pair→token→room→agent→approval) | Med | Low | High (kills whack-a-mole) | 1 | CI runs it; fails on regression |
| 3 | Regenerate `.env.example`; doc required vars; startup-validate | Low | Low | High (boot reliability) | — | Fresh clone boots from example |
| 4 | iOS lifecycle + token-refresh backoff + retry UI | Med | Low | High (mobile stability) | — | Backgrounding/network-drop test on device |
| 5 | Freeze Android; mark iOS-only for TestFlight | Low | Low | High (halves surface) | — | Decision recorded in ROADMAP |
| 6 | Move LiveKit → Cloud; drop coturn + self-host | Med | Med | Med (−2 services) | 1 | Voice works on Cloud creds end-to-end |
| 7 | Remove 199 `* 2.*` dups; move repo off iCloud path | Low | Low | Med (noise) | — | `find * 2.*` returns 0 |
| 8 | Extract marketing/content/automation to own repo | Low | Low | Med (clarity) | — | Product repo builds without them |
| 9 | Trim LangGraph ceremony (keep interrupt) | Med | Med | Med | 1,2 | Approval round-trips still pass |
| 10 | **Then** Phase 21.5 Adaptive Learning on the clean base | High | Med | Product diff | 1–4 | New UAT for learning |

**Priority order honoured:** integration (1,2) → mobile readiness (4,5) → reliability (3,6,7) → maintainability (8,9) → new functionality (10).

---

## 12. Highest-ROI Changes (the 20% → 80%)

1. **Delete the legacy `voice/` path and unify on `livekit-agents`.** Single biggest friction remover.
2. **One E2E smoke test** on the mobile voice path. Converts live whack-a-mole into CI signal.
3. **iOS-only for TestFlight; freeze Android.** Stops double-paying.
4. **Fix `.env.example` drift + startup validation.** Removes a class of silent misconfig.

These four are mostly *deletion and consolidation*, low-risk, and unblock Phase 21.5 (the real value) on a clean base.

---

## 13. Risks & Unknowns

- **Does anything still rely on the CLI voice path in practice?** Evidence says no (CLI uses `MemorySaver`, not in prod flow) — confirm before deleting.
- **LiveKit Cloud cost/latency** vs self-host at expected volume — needs a quick check before ADR-002.
- **api/worker consolidation** (ADR-008) is low-confidence; the worker carries heavy audio libs and is long-lived — may be correct to keep split. Validate, don't assume.
- **Trimming LangGraph** risks the one solid subsystem (approval). Do it only after the E2E smoke exists.
- **mem0/adaptive learning (21.5)** is unbuilt; its real integration cost is still unknown and should be scoped on the consolidated base, not the current dual one.

---

## 14. Root-Cause Answers

**Why does it feel hard to integrate?** Because the same capability exists twice. The mobile-first/LiveKit architecture was added on top of the CLI/local-voice architecture without retiring it, so voice, the checkpointer, and the client all exist in duplicate, and session truth is scattered across context + Redis + Postgres + device.

**Why does it slow near the finish?** The last 20% is cross-service E2E integration (mobile↔LiveKit↔worker↔graph↔approval↔API) — exactly the path the unit-heavy test suite doesn't cover — so failures surface only in live sessions, and every fix is paid twice (two voice paths, two clients).

**Which decisions contribute most?** (1) keeping legacy `voice/` after adopting `livekit-agents`; (2) self-hosting LiveKit + coturn; (3) building Android to parity before iOS was validated; (4) LangGraph ceremony + dual checkpointer; (5) config drift; (6) no E2E smoke.

**The 20% that removes 80% of friction:** delete legacy voice + unify on `livekit-agents`, one E2E smoke, iOS-only TestFlight, fix env drift — then build 21.5 on the clean base.
