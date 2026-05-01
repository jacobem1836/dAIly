# Phase 21: Per-User Onboarding - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-01
**Phase:** 21-per-user-onboarding
**Areas discussed:** OAuth callback architecture, Onboarding flow & sequencing, Integration connect UX, Briefing schedule setup

---

## OAuth Callback Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Backend-mediated | App opens ASWebAuthenticationSession → provider redirects to backend callback → backend stores token → deep link back to app | ✓ |
| App-receives auth code | OAuth redirect → Universal Link opens iOS app → app sends code to backend | |
| Polling after browser | Backend callback stores token → app polls status endpoint | |

**User's choice:** Backend-mediated
**Notes:** Tokens never pass through the iOS app — cleanest security posture, upholds SEC-01.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Backend sends deep link | Backend redirects to Universal Link → iOS resumes onboarding | ✓ |
| App polls status endpoint | App polls GET /integrations/status every 2s | |
| User taps Done manually | Success page shown in browser, user returns manually | |

**User's choice:** Backend sends deep link
**Notes:** No polling complexity, clean UX handoff.

---

## Onboarding Flow & Sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Email → Integrations → Schedule | Linear guided flow, nothing skippable in order | ✓ |
| Email → Schedule → Integrations | Schedule first, then accounts | |
| Email only → everything else in settings | Minimal onboarding, integration setup deferred | |

**User's choice:** Email → Integrations → Schedule

---

| Option | Description | Selected |
|--------|-------------|----------|
| At least one integration required | Must connect one of Google/Microsoft/Slack before advancing | ✓ |
| All optional — skip allowed | User can skip all, briefing tells them to connect later | |
| Google required, others optional | Google is minimum | |

**User's choice:** At least one required
**Notes:** No integration = no briefing content; requiring at least one prevents an empty first experience.

---

## Integration Connect UX

| Option | Description | Selected |
|--------|-------------|----------|
| ASWebAuthenticationSession | Apple's purpose-built OAuth API, isolated cookies, system prompt | ✓ |
| SFSafariViewController | In-app browser sheet, shares Safari cookies | |

**User's choice:** ASWebAuthenticationSession
**Notes:** App Store recommended, more secure, isolated cookie store.

---

| Option | Description | Selected |
|--------|-------------|----------|
| One screen per integration (sequential) | Google → Microsoft → Slack, each with description + Connect + Skip | ✓ |
| Single screen, all three shown | Checklist layout, user connects whichever they want | |

**User's choice:** One screen per integration

---

| Option | Description | Selected |
|--------|-------------|----------|
| Checkmark + account email | `jacob@gmail.com ✓` — shows which account was linked | ✓ |
| Checkmark only | Button becomes checkmark, no email | |
| Provider name + Connected badge | `Google — Connected` badge | |

**User's choice:** Checkmark + account email

---

## Briefing Schedule Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Onboarding step with time picker | Dedicated screen, iOS DatePicker, default 7:00 AM | ✓ |
| Settings only | No schedule setup in onboarding, deferred to settings | |
| First-briefing prompt | End of onboarding shows "Your first briefing is at 7:00 AM tomorrow" | |

**User's choice:** Onboarding step with time picker

---

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect device timezone | `TimeZone.current` sent to backend, no user interaction | ✓ |
| User picks from a list | Explicit timezone picker in onboarding | |
| UTC stored, convert on display | Store in UTC, client handles conversion | |

**User's choice:** Auto-detect device timezone

---

## Claude's Discretion

- Visual design, animation details — consistent with Phase 19 iOS app aesthetic
- Exact permission description wording on integration screens
- Error handling for failed OAuth flows
- Success/completion animation on final onboarding screen

## Deferred Ideas

- Android onboarding (Chrome Custom Tabs pattern) — Phase 20 follow-up
- Post-onboarding reconnect/re-auth flow — settings screen
- Adding integrations after onboarding — settings screen
- Incremental OAuth scope upgrades — M2+
