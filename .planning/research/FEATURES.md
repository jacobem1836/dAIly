# Feature Research

**Domain:** Voice-first AI personal assistant (proactive briefing + action layer)
**Researched:** 2026-04-05
**Confidence:** HIGH (verified against ChatGPT Pulse, Google CC, Alfred_, Lindy, competitor landscape)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Daily briefing delivery | The core promise: synthesise overnight, deliver proactively on wake | MEDIUM | Precomputed briefing cache is required — real-time generation feels slow |
| Email ingestion + triage | Users expect every communication assistant to handle email | MEDIUM | Gmail + Outlook OAuth. Classify: urgent / needs-reply / FYI / noise |
| Calendar ingestion | Expected alongside email in every EA/briefing product | LOW | Today + next 24–48h. Conflict detection, meeting prep context |
| Voice output (TTS) | Voice-first means the briefing is spoken, not read | MEDIUM | ElevenLabs or similar — sub-150ms synthesis latency is now standard |
| Voice input (STT) | Users want to ask follow-ups by voice, not type | MEDIUM | Whisper or Deepgram. Streaming STT with interim results to cut LLM wait |
| Low-latency response loop | Humans expect 300–800ms conversational responses — anything above 1.5s breaks immersion | HIGH | WebRTC > PSTN. Pipeline: STT interim → LLM → TTS streaming. Sub-1s is achievable |
| Action drafting (email/message reply) | Briefing products without draft output feel read-only and passive | MEDIUM | Draft, don't send. Human-in-the-loop approval gates all sends in M1 |
| Approval flow for all external actions | Non-negotiable trust contract with users — no unsanctioned sends | LOW | Simple confirm/reject. Action log maintained. Critical for user trust baseline |
| Interruption handling | Voice-only interaction demands the ability to interrupt and redirect | MEDIUM | Barge-in detection (VAD). Redirect briefing mid-sentence is expected |
| Follow-up questions during briefing | Users will ask "tell me more about that email" — this is expected | MEDIUM | Conversational context window maintained across briefing session |
| OAuth integration (Google + Microsoft) | Standard auth for email/calendar integrations | MEDIUM | Gmail, Google Calendar, Outlook, Exchange. Tokens encrypted at rest |
| Action log | Transparency on what the assistant has done or attempted | LOW | Timestamped, type-tagged, approval-status per entry |

### Differentiators (Competitive Advantage)

Features that set dAIly apart. Not universally expected, but high leverage for the target market.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Proactive, precomputed briefing (not on-demand) | "Your life briefs you" — no prompt needed. ChatGPT Pulse and Google CC both moved here in late 2025, validating demand | HIGH | Fetch + summarise before user wakes. Cache for instant voice delivery. Key differentiator vs reactive assistants |
| Priority ranking engine | Not "here are 20 emails" — "here are the 3 that matter" | HIGH | Learned from skip/re-request signals. Requires a scoring model tuned to user behaviour over time |
| Messaging integration (Slack) | Most briefing tools cover email + calendar but skip async messaging | HIGH | Mentions, DMs, priority channels. High signal density for target market (professionals) |
| Conversational memory across sessions | Single-session assistants feel dumb after first use. Persistent memory = compounding value | HIGH | Not just "preferences" — contextual memory (e.g. "Jacob mentioned a deadline last Tuesday"). ChromaDB or pgvector |
| Signal capture from interaction behaviour | Skips, corrections, re-requests as implicit feedback loop | MEDIUM | Drives priority ranking improvement without explicit user effort |
| Multi-turn follow-up with action dispatch | "Reply to that Slack message" mid-briefing — briefing becomes a command interface | HIGH | Requires tight integration between briefing context and action engine |
| Staged autonomy model (approve → trust → auto) | Users want to grant more authority over time without a cliff edge | MEDIUM | M1: approve all. M2: trusted actions (auto-send to flagged contacts). Explicit trust levels per action type |
| Thread summarisation on demand | "Summarise that email chain" as a natural follow-up | LOW | Single retrieval + LLM summarise. High perceived intelligence, low complexity |
| Structured action log with audit trail | Professional users want to know exactly what was done | LOW | Differentiator vs consumer assistants that hide actions. Audit-first design |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem obviously good but create meaningful problems in MVP.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-send without approval | "More efficient, I trust it" | One wrong send to the wrong person destroys trust immediately. Trust has to be earned incrementally. | Staged autonomy — require approval in M1, gate auto-send behind explicit trust grants in M2 |
| Always-on ambient listening | Feels like a true voice-first experience | Privacy land mines, battery drain, accidental trigger edge cases. WAF/legal exposure. "Helpful until it interjects uninvited" | Wake-word + push-to-talk hybrid. On-device wake word detection (Picovoice/Porcupine) to maintain privacy |
| News / web content in M1 briefing | "Complete morning briefing" expectation | Unlimited scope. News curation is a separate hard problem. Dilutes the core signal (YOUR data, not the world's) | Explicitly out of scope in M1. Add in M3 as a channel, not core |
| Web dashboard / UI in M1 | Users want to see things visually | Frontend development burns time. Core value is voice-first. A bad UI shipped early creates design debt | Backend-first. CLI or minimal API surface for M1. Dashboard is M2+ |
| Real-time inbox sync (push webhooks) | Feels more responsive | Complexity spike — webhook management, failure handling, exactly-once delivery. No user benefit in a briefing product that batch-processes overnight | Scheduled pull (cron-style). Simpler, more reliable, sufficient for briefing use case |
| Smart home / IoT integration | "Alexa replacement" vision | Completely different domain. Different device layer, different latency model, different user context. Scope dilution | Out of scope permanently unless product pivots. Not this product's job |
| Fully local LLM | Privacy appeal | GPT-class reasoning quality is necessary for coherent briefing narratives. Local models produce noticeably worse summaries at current capability levels | Cloud LLM (GPT-4o class) with pre-filter/redaction layer. Raw data never leaves backend |
| Voice biometrics / speaker ID | Security appeal | High implementation complexity. Edge cases (illness, noise) cause false rejections. Not warranted at MVP scale | OAuth session auth is sufficient for M1. Add biometrics as optional enhancement in M3+ |
| Proactive interruptions / push notifications during day | "Assistant should alert me" | Without strong signal quality, proactive interruptions become noise. Users will disable them | Deliver one high-quality briefing per day. Let users pull additional queries. Earn proactive trust first |
| Social media integration | "Full digital life" | Low signal-to-noise. Content volume vastly exceeds actionable items. Personalization quality degrades | Not in M1–M3. If added, treat as opt-in low-priority channel only |

---

## Feature Dependencies

```
Voice Interface (STT)
    └──requires──> Low-Latency Pipeline (WebRTC, streaming)
                       └──requires──> TTS Streaming

Proactive Briefing
    └──requires──> Email Ingestion
    └──requires──> Calendar Ingestion
    └──requires──> LLM Summarisation
    └──requires──> Briefing Cache (precompute)

Action Layer (Draft/Schedule)
    └──requires──> Approval Flow
    └──requires──> Action Log
    └──requires──> OAuth Integrations

Personalisation Engine
    └──requires──> Signal Capture (skip/correction events)
    └──requires──> User Profile Store
    └──enhances──> Priority Ranking Engine

Conversational Memory
    └──requires──> Session Context Store
    └──enhances──> Multi-Turn Follow-Up
    └──enhances──> Personalisation Engine

Priority Ranking Engine
    └──requires──> Signal Capture
    └──enhances──> Proactive Briefing (what leads vs what buries)

Staged Autonomy (M2)
    └──requires──> Action Log (evidence base for trust)
    └──requires──> Approval Flow (trust scoring input)
    └──enhances──> Action Layer
```

### Dependency Notes

- **Proactive briefing requires all three data sources (email, calendar, messaging):** A briefing without messaging is incomplete for the target market (professionals on Slack). But messaging can be added after email/calendar without breaking anything — phase accordingly.
- **Approval flow must exist before action drafting ships:** Drafting without approval gates = unsanctioned send risk. Build the gate first, draft second.
- **Conversational memory enhances almost everything but blocks nothing:** Can be shipped incrementally. Session memory (in-session context) is low complexity and ships in M1. Cross-session memory is M2.
- **Priority ranking requires signal data:** Cold start problem — ranking can't be personalised without prior interactions. Use heuristic defaults (sender importance, keywords, deadlines) until signal data accumulates.
- **Staged autonomy conflicts with M1 all-approval:** These are not in conflict — M1 approval flow IS the foundation for M2 trust scoring. Don't shortcut it.

---

## MVP Definition

### Launch With (v1 — M1)

Minimum to validate the core value proposition: "Your life briefs you every morning."

- [ ] Daily proactive briefing — precomputed from email + calendar, delivered via TTS on request
- [ ] Email ingestion + triage (Gmail, Outlook OAuth) — last 24h, ranked by heuristic priority
- [ ] Calendar ingestion — today + 48h, conflict detection, meeting prep context
- [ ] Slack messaging ingestion — mentions, DMs, priority channels
- [ ] Voice output (TTS streaming) — ElevenLabs or equivalent, sub-150ms synthesis
- [ ] Voice input (STT streaming) — Whisper/Deepgram, interim results to cut perceived latency
- [ ] Interruption + follow-up question handling — barge-in, mid-briefing redirect
- [ ] Action drafting (email reply, Slack reply, calendar event) — draft only, never auto-send
- [ ] Approval flow — confirm/reject gate on all external-facing actions
- [ ] Action log — timestamped record of all actions and approval status
- [ ] Basic user profile + preference store — tone, briefing structure preferences
- [ ] Signal capture — skips, corrections, re-requests logged for future use

### Add After Validation (v1.x — M2)

Features to add once core briefing loop is working and users are returning.

- [ ] Priority ranking engine — move from heuristic to learned prioritisation using M1 signal data
- [ ] Cross-session conversational memory — persist context across days, not just sessions
- [ ] Staged autonomy — trusted auto-actions for flagged contacts/patterns after explicit user grant
- [ ] Web dashboard — visual companion to the voice interface, action log review, preference management

### Future Consideration (v2+ — M3/M4)

Defer until product-market fit is established and user base is active.

- [ ] Travel integration (flights, hotels, itineraries) — high complexity, niche signal
- [ ] Finance integration (bank feeds, expense tracking) — regulatory exposure, separate trust domain
- [ ] Health integration (calendar-aware energy/focus) — requires health data access, privacy-sensitive
- [ ] News/content briefing layer — separate curation problem, risks diluting personal signal quality
- [ ] On-device LLM (fallback or privacy mode) — model quality insufficient in 2026, revisit 2027+
- [ ] Multi-user / team briefings — different product category; requires separate personas research

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Proactive daily briefing (precomputed) | HIGH | HIGH | P1 |
| Email ingestion + triage | HIGH | MEDIUM | P1 |
| Calendar ingestion | HIGH | LOW | P1 |
| Voice output (TTS streaming) | HIGH | MEDIUM | P1 |
| Voice input (STT + interruption) | HIGH | MEDIUM | P1 |
| Approval flow + action log | HIGH | LOW | P1 |
| Action drafting (email/message/calendar) | HIGH | MEDIUM | P1 |
| Slack messaging ingestion | HIGH | MEDIUM | P1 |
| Follow-up question handling | HIGH | MEDIUM | P1 |
| Basic user profile | MEDIUM | LOW | P1 |
| Signal capture (implicit feedback) | MEDIUM | LOW | P1 |
| Priority ranking engine (learned) | HIGH | HIGH | P2 |
| Cross-session memory | HIGH | HIGH | P2 |
| Staged autonomy / trusted actions | MEDIUM | HIGH | P2 |
| Web dashboard | MEDIUM | HIGH | P2 |
| Thread summarisation on demand | MEDIUM | LOW | P2 |
| Travel/finance integrations | MEDIUM | HIGH | P3 |
| News briefing layer | LOW | HIGH | P3 |
| Voice biometrics / speaker ID | LOW | HIGH | P3 |
| Always-on ambient listening | LOW | HIGH | NEVER (M1) |

**Priority key:**
- P1: Must have for M1 launch
- P2: Should have, add in M2 after validation
- P3: Nice to have, future milestone
- NEVER (M1): Explicitly excluded from M1 for stated reasons

---

## Competitor Feature Analysis

| Feature | ChatGPT Pulse (OpenAI) | Alfred_ | Google CC | dAIly Approach |
|---------|------------------------|---------|-----------|----------------|
| Proactive morning briefing | Yes — card-based, overnight | Yes — email to inbox | Yes — "Your Day Ahead" email | Voice-first delivery, not inbox/card |
| Email integration | Gmail, Outlook (Connectors) | Gmail, Outlook | Gmail | Same |
| Calendar integration | Google Calendar | Google Calendar | Google Calendar | Same + Exchange/Outlook |
| Messaging integration | Not documented | Not documented | Not documented | Slack in M1 — differentiated |
| Voice delivery | No — text/card only | No — email/notification | No — email only | Yes — core differentiator |
| Conversational follow-up | Limited (ChatGPT chat) | No | No | Yes — barge-in, multi-turn |
| Action layer (send/schedule) | Draft in ChatGPT | Yes — drafts | Not documented | Yes — approval-gated |
| Personalisation / memory | ChatGPT Memory feature | Learns implicitly | Not documented | Explicit signal capture + user profile |
| Approval flow | Not explicit | Not explicit | Not applicable | Explicit — audit log per action |
| Availability | Pro tier ($200/mo) | $24.99/mo | Free (Google users) | TBD — targeting prosumer/professional |

**Key insight:** No competitor delivers the briefing via voice with conversational follow-up. ChatGPT Pulse, Alfred_, and Google CC all deliver to inbox or app card. dAIly's voice-first delivery with interruption handling is a genuine gap in the market.

---

## Sources

- [OpenAI ChatGPT Pulse launch — TechCrunch](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/)
- [What Is an AI Daily Briefing — Alfred_](https://get-alfred.ai/blog/what-is-ai-daily-briefing)
- [AI Executive Assistants in 2026 — Sliq](https://www.trysliq.com/blog/ai-executive-assistant)
- [Voice AI Pipeline: STT, LLM, TTS and the 300ms Budget — Chanl](https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget)
- [Best AI Voice Assistants 2026 — Lindy](https://www.lindy.ai/blog/best-ai-voice-assistants)
- [Why Action-Level Approvals Matter — Hoop.dev](https://hoop.dev/blog/why-action-level-approvals-matter-for-ai-agent-security-ai-trust-and-safety)
- [Proactive AI in 2026: Moving Beyond the Prompt — AlphaSense](https://www.alpha-sense.com/resources/research-articles/proactive-ai/)
- [Solving Voice AI Latency — Medium](https://medium.com/@reveorai/solving-voice-ai-latency-from-5-seconds-to-sub-1-second-responses-d0065e520799)
- [Why Skipping the Wake Word is a Mistake — Sensory](https://sensory.com/skipping-wake-words-conversational-ai/)
- [Agentic AI Trends 2026 — EMA](https://www.ema.co/additional-blogs/addition-blogs/agentic-ai-trends-predictions-2025)

---
*Feature research for: voice-first AI personal assistant (dAIly)*
*Researched: 2026-04-05*
