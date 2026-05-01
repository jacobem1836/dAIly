# Phase 21: Per-User Onboarding - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

In-app signup flow, OAuth connect screens (Google, Microsoft, Slack), and briefing schedule setup — all from within the iOS app. Every new user independently connects their own accounts without developer CLI intervention. The existing CLI-based localhost:8080 OAuth flow is replaced by a backend-mediated mobile OAuth pattern.

</domain>

<decisions>
## Implementation Decisions

### OAuth Callback Architecture
- **D-01:** Backend-mediated OAuth flow. App opens ASWebAuthenticationSession → OAuth provider redirects to backend callback endpoint (`/integrations/{provider}/callback`) → backend stores encrypted tokens → backend issues a deep link (Universal Link) back to the iOS app signaling success.
- **D-02:** Tokens never pass through the iOS app — the backend callback handler is the sole recipient of the auth code and performs the exchange. Preserves the SEC-01 constraint.
- **D-03:** After backend callback stores tokens, the backend redirects to a Universal Link (e.g. `https://yourdomain.com/oauth/success?provider=google`). iOS intercepts it via Universal Links and resumes the onboarding flow. No polling required.
- **D-04:** New backend endpoints required per provider: `GET /integrations/{provider}/connect` (returns authorization URL) and `GET /integrations/{provider}/callback` (handles redirect, stores token, issues deep link). Providers: google, microsoft, slack.
- **D-05:** The existing `integrations/google/auth.py` localhost flow is CLI/dev tooling only — it is not touched. New mobile OAuth endpoints are added alongside it.

### Onboarding Flow & Sequencing
- **D-06:** Linear flow: Email (magic link pairing) → Integrations → Briefing Schedule → Voice experience. User completes steps in this order.
- **D-07:** At least one integration must be connected before the user can advance to schedule setup. The "Continue" CTA on the integrations step is disabled until at least one provider shows a checkmark. Slack, Google, and Microsoft are all offered; any one satisfies the requirement.
- **D-08:** Briefing schedule is configured in onboarding (not deferred to settings). It is the final step before the user reaches the voice experience for the first time.

### Integration Connect UX
- **D-09:** ASWebAuthenticationSession (not SFSafariViewController) — Apple's purpose-built OAuth API. Isolated cookie store, shows a system permission prompt, App Store recommended. No Safari cookie sharing.
- **D-10:** One screen per integration, shown sequentially: Google → Microsoft → Slack. Each screen explains what data will be accessed (Gmail, Calendar; Outlook, Teams; Slack channels and DMs) with a prominent Connect button and a Skip option.
- **D-11:** After a successful connection, the Connect button is replaced by a green checkmark and the connected account email (e.g. `jacob@gmail.com ✓`). Makes it clear which account was linked.
- **D-12:** User can skip individual integrations (except the rule that at least one must be connected before advancing). If a user has skipped all but one, the Skip option on the last unconnected integration is hidden until at least one is connected.

### Briefing Schedule Setup
- **D-13:** Onboarding shows a dedicated schedule screen with a time picker (iOS native `DatePicker` in `.hourAndMinute` mode). Default: 7:00 AM.
- **D-14:** Timezone: auto-detect from `TimeZone.current` on iOS and send to the backend with the schedule preference. No user-facing timezone picker in onboarding. Adjustable in settings later.
- **D-15:** Backend stores briefing schedule time and timezone on the user's preferences record (existing `UserPreference` model). The APScheduler cron job reads this per-user when scheduling overnight briefing precompute.

### Claude's Discretion
- Visual design, colors, animation details on onboarding screens — keep consistent with the existing iOS app aesthetic (Phase 19).
- Exact wording on integration permission descriptions.
- Error handling for failed OAuth flows (generic retry screen is fine).
- Success/completion animation on final onboarding screen.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth & Pairing (existing backend)
- `src/daily/auth/router.py` — Existing pairing endpoints (send-link, complete, token/refresh). New OAuth endpoints follow the same router pattern.
- `src/daily/auth/pairing.py` — Pairing code generation utilities.
- `.planning/phases/19-native-ios-app/19-CONTEXT.md` — iOS app auth decisions: Universal Links, Keychain storage, magic link flow. New onboarding screens extend this.

### Integrations (existing CLI-based OAuth, for reference only)
- `src/daily/integrations/google/auth.py` — Existing localhost OAuth flow. NOT used for mobile. Read to understand the token storage pattern (credentials → `encrypt_token` → `IntegrationToken` DB record).
- `src/daily/integrations/models.py` — `IntegrationToken` model. New mobile OAuth callback writes to the same table.

### Database models
- `src/daily/db/models.py` — `User`, `IntegrationToken`, `UserPreference` models. Schedule time and timezone added to `UserPreference`.

### Security constraints
- `.planning/PROJECT.md` §Constraints — SEC-01: tokens encrypted at rest (AES-256-GCM), never exposed to frontend/logs/LLM. Mobile OAuth must uphold this — token exchange happens in backend callback only.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/auth/router.py` — Router pattern, `_get_db()` dependency, `_get_settings()` dependency. New `/integrations/{provider}/connect` and `/integrations/{provider}/callback` endpoints follow the same structure.
- `src/daily/vault/crypto.py` — `encrypt_token` / `decrypt_token`. OAuth callback handler uses these before writing to `IntegrationToken`.
- `src/daily/email/resend_client.py` — Resend email (already used for magic links). No change needed.
- `ios/` — Existing Swift iOS app. Onboarding screens are new SwiftUI views added to this project.

### Established Patterns
- Auth: Bearer JWT in `Authorization` header for all authenticated endpoints. The `/integrations/{provider}/connect` endpoint is authenticated (user must be paired first).
- Token storage: `IntegrationToken` table with `user_id`, `provider` (string), `access_token` (encrypted), `refresh_token` (encrypted). Callback handler follows this pattern.
- Universal Links: `apple-app-site-association` endpoint already in place from Phase 19. The `/oauth/success` path needs to be added to the AASA paths list.

### Integration Points
- iOS onboarding flow → `GET /integrations/google/connect` (authenticated) → returns `{auth_url}`
- ASWebAuthenticationSession opens `auth_url` → Google OAuth consent → Google redirects to `https://yourdomain.com/integrations/google/callback?code=...&state=...`
- Backend callback → stores tokens → redirects to `https://yourdomain.com/oauth/success?provider=google`
- iOS Universal Link handler → dismisses ASWebAuthenticationSession → marks Google as connected in UI
- iOS schedule screen → `PUT /users/me/preferences` with `{briefing_time: "07:00", timezone: "Australia/Brisbane"}`

</code_context>

<specifics>
## Specific Ideas

- ASWebAuthenticationSession is the App Store-recommended OAuth approach for iOS — use it, not SFSafariViewController.
- The `state` parameter in OAuth must be validated on callback to prevent CSRF (backend generates state, stores in Redis/DB with TTL, validates on callback).
- Integration screens: Google first (most common), then Microsoft, then Slack — ordered by expected adoption.
- Default briefing time: 7:00 AM. Feels natural and is already the APScheduler default.

</specifics>

<deferred>
## Deferred Ideas

- Android onboarding — same pattern but Android OAuth uses Chrome Custom Tabs. Phase 20 follow-up.
- Reconnect / re-auth flow for expired integrations — settings screen, not onboarding.
- Adding integrations post-onboarding (e.g. adding Slack later) — settings screen.
- Incremental OAuth scope upgrades (e.g. requesting send permission later) — M2+ consideration.

</deferred>

---

*Phase: 21-per-user-onboarding*
*Context gathered: 2026-05-01*
