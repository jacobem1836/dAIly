# Phase 19: Native iOS App - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a native iOS app in Swift using the LiveKit iOS SDK. The app authenticates via a magic link email flow, joins a LiveKit room, and handles real-time voice I/O. STT, LLM orchestration, and TTS all happen server-side via the Python LiveKit Agent — the iOS app is a thin room participant. Push-to-talk and voice activity detection modes both exist in code; only VAD is exposed in the production UI.

</domain>

<decisions>
## Implementation Decisions

### App Location
- **D-01:** iOS Xcode project lives at `ios/` in this repo (monorepo). Keeps backend and client changes in sync.

### Authentication — Magic Link Flow
- **D-02:** First-launch pairing uses a magic link sent via Resend API. User enters their email, backend generates a pair code and sends `https://yourdomain.com/pair?code=XXXXXX` via email.
- **D-03:** Universal Links (HTTPS-based), not a custom URL scheme (`daily://`). Requires `apple-app-site-association` served from the backend domain. Apple-preferred, can't be hijacked by another app.
- **D-04:** Backend needs a new endpoint `POST /auth/pair/send-link` that accepts `{email}`, generates a pair code (reusing Phase 18 mechanism), and sends the magic link via Resend. The pair code redemption (`POST /auth/pair/complete`) is unchanged.
- **D-05:** After pairing, the access JWT and refresh token are stored in iOS Keychain (not UserDefaults).

### Voice Mode
- **D-06:** Auto VAD is the only production voice mode. The app always listens; LiveKit turn detection determines when the user is speaking.
- **D-07:** Push-to-talk exists in code (behind a developer/debug flag) but is not surfaced in the production UI. Useful for testing in noisy environments.

### STT/TTS Architecture
- **D-08:** STT and TTS happen server-side via the Python LiveKit Agent. The iOS app publishes an audio track to the LiveKit room and subscribes to the agent's audio track. No Deepgram or Cartesia SDKs in the iOS client.
- **D-09:** MOB-05 (client-direct STT/TTS) is deferred — it becomes relevant only if server-side latency proves insufficient at production scale.

### Voice UI
- **D-10:** Claude's discretion on visual design. Functional requirements: connection state indicator (Connecting / Listening / Speaking), session controls. Minimal by default.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### LiveKit backend (Phase 18)
- `.planning/phases/18-livekit-infrastructure/18-01-SUMMARY.md` — LiveKit dev stack, settings fields (livekit_url, livekit_api_key, livekit_api_secret)
- `.planning/phases/18-livekit-infrastructure/18-02-SUMMARY.md` — Device pairing auth flow (pair/initiate, pair/complete, token/refresh)
- `.planning/phases/18-livekit-infrastructure/18-03-SUMMARY.md` — POST /livekit/token endpoint, LiveKit JWT shape (room, identity, TTL)
- `.planning/phases/18-livekit-infrastructure/18-VERIFICATION.md` — Verified API contracts

### Requirements
- `.planning/PROJECT.md` — MOB-01 requirement, mobile-first architecture decision, security constraints (AES-256-GCM, tokens never in frontend/logs/LLM)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/daily/auth/router.py` — Existing pair/initiate, pair/complete, token/refresh endpoints. The `POST /auth/pair/send-link` endpoint is new but shares the pair code generation logic.
- `src/daily/livekit/router.py` — POST /livekit/token returns `{token, room, livekit_url}`. This is what the iOS app calls after pairing to get a LiveKit room token.
- `src/daily/livekit/tokens.py` — LiveKit JWT creation. Room name format: `session-{user_id}-{unix_timestamp}`.
- `src/daily/config.py` — Settings expose `livekit_url`, `livekit_api_key`, `livekit_api_secret` via env.

### Established Patterns
- Auth: Bearer JWT in Authorization header for all authenticated endpoints.
- Refresh: `POST /auth/token/refresh` exchanges refresh token for new access JWT.
- No existing iOS/Swift code — greenfield project at `ios/`.

### Integration Points
- iOS app → `POST /auth/pair/send-link` (new) → triggers Resend email
- iOS app (Universal Link handler) → `POST /auth/pair/complete` → receives access JWT + refresh token
- iOS app → `POST /livekit/token` (with Bearer JWT) → receives LiveKit room token
- iOS app → LiveKit room join (WebSocket to `livekit_url`) → publishes audio track, subscribes to agent audio track
- Backend `apple-app-site-association` endpoint needed to enable Universal Links

</code_context>

<specifics>
## Specific Ideas

- Magic link delivery via Resend API (Jacob already uses/knows Resend).
- Universal Links require serving `/.well-known/apple-app-site-association` from the FastAPI backend — a small new route.
- PTT mode kept in code, not in UI — gated by a `DEBUG_PTT_ENABLED` env/build flag.

</specifics>

<deferred>
## Deferred Ideas

- MOB-05: Client-direct STT/TTS (Deepgram + Cartesia Swift SDKs) — deferred until server-side latency is measurable and insufficient.
- Visual design specifics — left to Claude's discretion during planning.

</deferred>

---

*Phase: 19-native-ios-app*
*Context gathered: 2026-04-30*
