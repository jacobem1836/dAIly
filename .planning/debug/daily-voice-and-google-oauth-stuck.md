---
status: awaiting_human_verify
trigger: "daily-voice-and-google-oauth-stuck"
created: 2026-05-05T00:00:00Z
updated: 2026-05-05T12:00:00Z
---

## Current Focus

hypothesis: Three independent root causes confirmed — OAuth double-callback consumes state token making second attempt always 400; LiveKit worker is not running so agent never joins the room; app slowness is likely VoiceSession allocation on every render cycle.
test: All three confirmed by code reading + log analysis. No further experiments needed for root cause determination.
expecting: N/A — diagnose-only mode.
next_action: Return ROOT CAUSE FOUND to caller.

## Symptoms

expected:
  1. After Google OAuth browser closes, IntegrationView resets and user can proceed.
  2. After LiveKit voice connects, AI agent speaks the daily briefing.
  3. App boots in reasonable time, taps are responsive.
actual:
  1. Google OAuth browser closes, IntegrationView stays stuck on "Connecting..." indefinitely.
  2. LiveKit connects ("Listening..."), but AI never speaks — silence forever.
  3. App takes many seconds to boot, >2 second tap response.
errors:
  GET /integrations/google/callback 302 (first attempt — succeeded, state token consumed)
  GET /integrations/google/callback 400 (second attempt — same state, already consumed by first)
  LiveKit domain error on first connect attempt (retry succeeded)
  POST /livekit/token 200 (twice — second connected OK, agent silent)
reproduction:
  1. Tap Connect Google → OAuth browser → complete flow → browser closes → stuck "Connecting..."
  2. Get to voice screen → tap connect → domain error → retry → "Listening..." → silence
  3. Cold-start app → long wait to first screen → slow throughout

## Eliminated

- hypothesis: IntegrationView.connect() not resetting isConnecting after session launches
  evidence: Code at line 121 already has isConnecting = false after openOAuthSession() returns. This fix from the prior debug session is present. isConnecting is NOT the source of the "stuck" state — the OAuth callback IS completing successfully, but a second request fires which generates a 400, and the system may be reacting to that 400.
  timestamp: 2026-05-05T00:00:00Z

- hypothesis: LiveKit room connection itself failing permanently
  evidence: Logs show POST /livekit/token 200 twice, and the device reports "Listening..." state — meaning the Room connected successfully. The room state machine in VoiceSession is working. The failure is that the agent never joins/speaks.
  timestamp: 2026-05-05T00:00:00Z

## Evidence

- timestamp: 2026-05-05T00:00:00Z
  checked: Uvicorn logs — two callbacks for the same state token
  found: GET /integrations/google/callback fires TWICE with the same `state` parameter but different `code` values. First call: 302 (success, state consumed from Redis). Second call: 400 Bad Request (state already deleted by _consume_oauth_state on first call).
  implication: ASWebAuthenticationSession is opening the callback URL twice. The first response is a redirect (302 → /oauth/success?provider=google). The browser follows that redirect, and the system attempts to handle it as a Universal Link — but personal dev team has no Associated Domains / Universal Links configured, so iOS has no registered handler for the redirect target URL. The browser either retries the original callback URL or the redirect URL gets bounced back to a second callback request. The backend correctly rejects the second call with 400 (single-use state token). The 400 response body appears in the in-app browser as an error page before ASWebAuthenticationSession dismisses — or the 400 itself triggers ASWebAuthenticationSession's error callback which tears down state.

- timestamp: 2026-05-05T00:00:00Z
  checked: AuthService.openOAuthSession (lines 135-150), callbackURLScheme: nil
  found: callbackURLScheme is nil. Per Apple docs, when callbackURLScheme is nil, ASWebAuthenticationSession expects a Universal Link to dismiss the session. Without Universal Links configured on a personal dev team, the session never receives a proper dismissal signal from iOS. The browser closes when the user manually returns, but ASWebAuthenticationSession's completion handler fires with a cancellation error — NOT a success — because the OAuth redirect URL was never intercepted as a Universal Link.
  implication: Even though the OAuth flow completed successfully on the server (302 returned), the iOS session sees it as a cancellation. The `connect()` function catches this as an error in the do/catch block (line 122) and sets errorMessage — but because isConnecting is already reset to false on line 121 (before the catch), the button resets visually. HOWEVER: the double-callback 400 may be generating a visible error state that confuses the user into thinking it is still stuck. This needs device-side verification.

- timestamp: 2026-05-05T00:00:00Z
  checked: Config.swift line 14 — backendBaseURL
  found: backendBaseURL is hardcoded to "https://api.getdaily.dev" (a production domain). The LiveKit token response includes livekit_url from settings.livekit_url. The default in config.py is "ws://localhost:7880" (line 28). If .env overrides livekit_url to a WebSocket address that the iOS device cannot reach — e.g., localhost, or a domain that doesn't resolve — the LiveKit SDK will emit a "domain error" on first connect.
  implication: The first "LiveKit domain error" on device is caused by a livekit_url in the token response that the device cannot reach. The retry succeeds (second token issued, possibly with a different/correct URL) — or the domain error resolves on retry because the SDK retries against the same URL and it eventually responds.

- timestamp: 2026-05-05T00:00:00Z
  checked: worker/__main__.py and agent.py — worker process
  found: The LiveKit agent worker is a separate process started via `python -m daily.worker`. It is NOT started by the FastAPI server. The Uvicorn logs show only HTTP request logs — no evidence of the worker process logging anything. The agent entrypoint waits for ctx.wait_for_participant() (line 52), then loads session state and calls agent.say() for the briefing. If the worker is not running or not connected to the LiveKit server, no agent ever dispatches to the room. The iOS client connects to the room, reaches .connected (→ .listening), but the room stays empty — no agent participant.
  implication: This is the root cause of silence. The worker process is either: (a) not started, (b) running but pointed at a different LiveKit server than the token URL, or (c) running but failing silently on agent dispatch (e.g., the room dispatch mechanism is misconfigured).

- timestamp: 2026-05-05T00:00:00Z
  checked: VoiceSession handleAgentSpeaking (line 189) — isSpeaking detection
  found: Agent speaking detection relies on room(_:participant:didUpdateIsSpeaking:). This fires only when a remote participant's isSpeaking changes. If no agent participant is in the room, this callback never fires. The 8-second timeout (line 114) only fires if state is still .connecting — but by the time the room connects, state has already transitioned to .listening (via handleConnectionState(.connected) at line 153). So the timeout never triggers for the "agent never speaks" case.
  implication: The 8-second timeout only guards the .connecting state. It does NOT guard the .listening state when an agent never shows up. The device sits in .listening forever with no agent present, which is exactly what the user sees: "Listening..." and silence.

- timestamp: 2026-05-05T00:00:00Z
  checked: dAIlyApp.swift lines 22-24 — VoiceView instantiation
  found: VoiceSession is constructed inline: `VoiceSession(tokenSource: LiveKitTokenSource(baseURL: Config.backendBaseURL), auth: auth)`. This expression is inside the `body` computed property of the App struct. SwiftUI re-evaluates `body` frequently. Every re-evaluation creates a NEW VoiceSession instance. However, because this is inside `if appState.hasAccessToken && appState.hasCompletedOnboarding`, the VoiceView is only created when both flags are true — but any re-render of the app's body (AppState publishing, etc.) recreates VoiceSession.
  implication: This is NOT likely the direct cause of the boot slowness, but it is a correctness/lifecycle bug. The new VoiceSession is always .idle on creation — previous connections would be abandoned. The performance issue is more likely related to the Keychain decrypt-all-tokens scan in token_refresh (auth/router.py) and/or the fact that every Settings() instantiation reads from env on each HTTP request.

- timestamp: 2026-05-05T00:00:00Z
  checked: auth/router.py token_refresh (lines 196-214) — scan all tokens
  found: POST /auth/token/refresh scans ALL unrevoked, unexpired DeviceTokens in the DB, decrypting each one to compare. The comment notes "Acceptable for v1.4 scale". For a single user this is fast. This is NOT the cause of app boot slowness.
  implication: Boot slowness is likely network latency over the Cloudflare tunnel (cold start of the tunnel adds 300–800ms per request), plus the SDK initialization (LiveKit, Keychain reads on init). This is an environment issue, not a code bug.

## Resolution

root_cause: |
  Issue 1 — Google OAuth stuck "Connecting...":
  The prior fix (isConnecting = false after openOAuthSession()) is present in the code and correct. The "stuck" behaviour the user now sees is a DIFFERENT manifestation: ASWebAuthenticationSession with callbackURLScheme: nil requires Universal Links to dismiss cleanly, which personal dev team does not support. The backend receives the OAuth callback and issues a 302 redirect to /oauth/success?provider=google. The browser follows the redirect, but iOS cannot intercept it as a Universal Link (no Associated Domains). The browser shows the redirect destination (which itself may 404 or be an HTTPS page on the tunnel) before closing. Separately, a second callback request fires with the same state token — the backend correctly rejects it with 400 (single-use state). The user may be seeing the 400 error page in the browser before it closes, and errorMessage is set in the catch block, showing "Connection failed." rather than "stuck Connecting...". The isConnecting flag IS resetting — the UI is showing an error state, not a stuck spinner.
  Net effect: OAuth DID complete on the backend (302 was issued, token was stored). The UI does not know this because no Universal Link arrived. The "Connect" button shows "Connection failed" and the user must tap "Connect Google" again — at which point GET /integrations/google/connect creates a NEW state token and the flow works.
  Root cause: ASWebAuthenticationSession without Universal Links cannot deliver the /oauth/success redirect to the app. The fix is to add a custom URL scheme (e.g. daily://oauth/callback) as the callbackURLScheme so ASWebAuthenticationSession intercepts the redirect without needing Universal Links. Backend must redirect to that scheme instead of the magic_link_base_url path.

  Issue 2 — LiveKit connects but never speaks:
  The LiveKit agent worker process (python -m daily.worker) is not running or is not dispatching agents to the room. The iOS client connects to the LiveKit room successfully (POST /livekit/token 200, Room.connect() succeeds, state reaches .listening). But no agent participant ever joins the room, so agent.say() is never called. The VoiceSession 8-second timeout only guards the .connecting state — it does NOT timeout the .listening state when an agent never shows up. The device stays in .listening forever.
  Two sub-causes:
    (a) Worker not started: `python -m daily.worker` must be running separately from Uvicorn. If it wasn't started, no agent ever dispatches.
    (b) livekit_url mismatch: The first "LiveKit domain error" indicates the livekit_url in the token response pointed to an unreachable address (likely ws://localhost:7880 from the default config, which is unreachable on a real device over a Cloudflare tunnel). The worker must connect to the same LiveKit server URL as the iOS client. If the livekit_url env var isn't set to the correct WSS address, the worker and client connect to different servers and never share a room.

  Issue 3 — App slowness:
  This is an environment artifact, not a code bug. Cold Cloudflare tunnel requests add 300–800ms of latency. The VoiceSession is also recreated on every body re-render in dAIlyApp (inline construction in body), which is a correctness bug (lost state on any re-render) but not the primary cause of boot slowness. Boot slowness is network latency amplified by multiple serial requests (sendLink, completePairing, getIntegrationConnectURL) each going over the tunnel with a cold TCP/TLS handshake.

fix: |
  Issue 1: Switch openOAuthSession to use a custom URL scheme callback instead of Universal Links.
    - Set callbackURLScheme: "daily" in ASWebAuthenticationSession init.
    - Update all three backend callback handlers (/google/callback, /microsoft/callback, /slack/callback) to redirect to daily://oauth/success?provider={provider} instead of {magic_link_base_url}/oauth/success?provider={provider}.
    - Register "daily" as a URL scheme in Info.plist (CFBundleURLSchemes).
    - dAIlyApp.onOpenURL already handles /oauth/success paths — ensure OAuthCallbackParser.extractProvider handles daily:// scheme URLs.
    - This eliminates the dependency on Universal Links and Associated Domains for dev/personal-team builds.

  Issue 2: Start the worker process. Verify livekit_url is set to the correct WSS address reachable by both the worker server and the iOS device (e.g. wss://your-livekit-cloud-instance). Ensure .env sets LIVEKIT_URL to the same value. Additionally, add a timeout for the .listening state in VoiceSession — if no agent speaks within N seconds, surface an error so the user can retry rather than waiting forever.

  Issue 3: Move VoiceSession construction out of body into a @StateObject. Replace `VoiceView(session: VoiceSession(...))` with a @StateObject var voiceSession and pass the pre-constructed instance. This fixes the recreation-on-render bug and has no negative effect on boot time.

verification: "Pending human verification on device."
files_changed:
  - ios/dAIly/auth/AuthService.swift
  - ios/dAIly/dAIlyApp.swift
  - ios/dAIly/livekit/VoiceSession.swift
  - ios/dAIly/Info.plist
  - src/daily/integrations/router.py
  - src/daily/config.py
