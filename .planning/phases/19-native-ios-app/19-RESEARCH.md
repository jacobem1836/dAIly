# Phase 19: Native iOS App — Research

**Researched:** 2026-04-30
**Domain:** Swift / SwiftUI / LiveKit iOS SDK / AVAudioEngine / iOS Auth
**Confidence:** HIGH (core stack verified via official sources and GitHub)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** iOS Xcode project lives at `ios/` in this repo (monorepo).
- **D-02:** First-launch pairing uses a magic link sent via Resend API. User enters email, backend generates pair code and sends `https://yourdomain.com/pair?code=XXXXXX` via email.
- **D-03:** Universal Links (HTTPS-based), not custom URL scheme. Requires `apple-app-site-association` served from the backend domain.
- **D-04:** Backend needs `POST /auth/pair/send-link` (new endpoint) accepting `{email}`, generating a pair code, sending via Resend. `POST /auth/pair/complete` is unchanged.
- **D-05:** After pairing, access JWT and refresh token stored in iOS Keychain (not UserDefaults).
- **D-06:** Auto VAD is the only production voice mode. App always listens; LiveKit turn detection determines when user is speaking.
- **D-07:** Push-to-talk exists in code (behind `DEBUG_PTT_ENABLED` build flag) but not surfaced in production UI.
- **D-08:** STT and TTS happen server-side via the Python LiveKit Agent. iOS app publishes audio track, subscribes to agent's audio track. No Deepgram or Cartesia SDKs in iOS client.
- **D-09:** MOB-05 (client-direct STT/TTS) is deferred.
- **D-10:** Visual design at Claude's discretion. Required: connection state indicator (Connecting / Listening / Speaking), session controls. Minimal by default.

### Claude's Discretion
- Visual design specifics

### Deferred Ideas (OUT OF SCOPE)
- MOB-05: Client-direct STT/TTS (Deepgram + Cartesia Swift SDKs)
- Visual design specifics
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MOB-01 | Native iOS (Swift) client with LiveKit SDK, AVAudioEngine AEC | LiveKit iOS SDK 2.13.0 verified; AVAudioEngine/voiceChat mode pattern documented; Room connection lifecycle researched |
</phase_requirements>

---

## Summary

Phase 19 builds a greenfield native iOS app in Swift that pairs with the existing FastAPI backend via a magic link email flow, then joins a LiveKit room for voice I/O. The iOS app is architecturally thin: it publishes a local audio track and subscribes to the server agent's audio track. All STT, LLM, and TTS processing stays on the Python backend. The app's complexity is in three areas: (1) the magic link pairing flow with Universal Links and Keychain storage, (2) correct AVAudioSession/AVAudioEngine configuration for hardware AEC, and (3) LiveKit room connection lifecycle management.

The canonical starting point is `livekit-examples/agent-starter-swift`, which provides the `Session` + `LocalMedia` observable architecture the planner should follow. Hardware AEC is activated by setting `AVAudioSession` to `.playAndRecord` category with `.voiceChat` mode — this is automatic when the LiveKit SDK manages the audio session (which is the default). The magic link backend work (Resend email, AASA endpoint) is new backend surface that must ship alongside the iOS app.

**Primary recommendation:** Model the app on `agent-starter-swift` (LiveKit's official Swift voice agent starter), replacing `SandboxTokenSource` with `EndpointTokenSource` that calls `POST /livekit/token`, and wire the pairing flow against the existing `POST /auth/pair/*` endpoints plus a new `POST /auth/pair/send-link` endpoint.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LiveKit Swift SDK | 2.13.0 [VERIFIED: github.com/livekit/client-sdk-swift/releases] | WebRTC room connection, audio track publish/subscribe | Official LiveKit client; handles AVAudioSession, AEC, reconnect |
| Swift | 6.0 [VERIFIED: github.com/livekit/client-sdk-swift README] | Language | SDK requires Swift 6.0 strict concurrency |
| SwiftUI | iOS 13+ [VERIFIED: Package.swift iOS 13.0 minimum] | UI framework | Standard declarative iOS UI; `@Observable` available iOS 17+ — use `ObservableObject` for broader compat |
| XCTest + Swift Testing | Xcode-bundled | Unit and integration tests | Apple standard; no third-party test framework needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| URLSession (stdlib) | — | Backend API calls (pairing, token fetch) | All HTTP to FastAPI backend; no third-party HTTP client needed |
| Security framework (stdlib) | — | Keychain storage of JWT + refresh token | kSecClassGenericPassword for token persistence |
| UserNotifications (stdlib) | — | Push notification groundwork | Out of scope for phase 19 but import to avoid later refactor |

### No Third-Party Auth/Networking Libraries Needed
The project uses direct `URLSession` async/await + Keychain (Security framework). No Alamofire, no Auth0 SDK, no third-party Keychain wrapper — keeps the dependency graph minimal and security surface explicit.

**Installation via SPM** — add to Xcode project (not Package.swift since this is an app, not a library):

In Xcode: File → Add Package Dependencies → `https://github.com/livekit/client-sdk-swift.git` → Up to Next Major: `2.13.0`

**Version verification:**
```
github.com/livekit/client-sdk-swift latest: 2.13.0 (released 2026-04-10) [VERIFIED: GitHub releases page]
iOS minimum: 13.0 [VERIFIED: Package.swift platforms array]
Swift requirement: 6.0 [VERIFIED: README + Package@swift-6.0.swift]
```

CocoaPods is deprecated for LiveKit (will go read-only in 2027). Use SPM only. [CITED: swiftpackageindex.com/livekit/client-sdk-swift]

---

## Key APIs & Patterns

### 1. LiveKit Room Connection

The SDK's high-level voice-agent pattern uses `Session` + `LocalMedia` as `@Observable` / `ObservableObject` objects (from the `agent-starter-swift` reference app). For audio-only, the lower-level `Room` API is also sufficient.

**High-level (agent-starter-swift pattern):**
```swift
// Source: github.com/livekit-examples/agent-starter-swift
let session = Session(
    tokenSource: EndpointTokenSource(url: URL(string: "https://api.example.com/livekit/token")!,
                                     bearerToken: keychainAccessToken),
    options: SessionOptions(preConnectAudio: true)
)
// Connect
try await session.connect()
// Disconnect
await session.disconnect()
```

**Lower-level (Room API — for reference):**
```swift
// Source: docs.livekit.io/home/quickstarts/swift/
let room = Room()
room.add(delegate: self)
try await room.connect(
    url: "wss://your-livekit-server.com",
    token: livekitJWT,
    connectOptions: ConnectOptions(enableMicrophone: true)
)
```

The planner should use the `Session`/`LocalMedia` high-level API from `agent-starter-swift` — it encapsulates reconnect, preConnectAudio, and agent state out of the box.

### 2. Token Source — Custom Endpoint

Replace `SandboxTokenSource` with `EndpointTokenSource` (or a custom implementation):

```swift
// Source: github.com/livekit-examples/agent-starter-swift docs
// EndpointTokenSource calls the URL, expects {"token": "...", "url": "..."}
// The FastAPI /livekit/token endpoint returns {token, room, livekit_url}
// which matches — livekit_url maps to "url"
```

The FastAPI response shape `{token, room, livekit_url}` maps to what `EndpointTokenSource` expects. [ASSUMED — verify exact field names expected by EndpointTokenSource against the LiveKit SDK source before implementing]

### 3. AVAudioEngine / Hardware AEC

LiveKit **automatically manages AVAudioSession** when connected. [VERIFIED: github.com/livekit/client-sdk-swift README]

- Default: `.playback` category (no mic)
- After `enableMicrophone: true`: switches to `.playAndRecord` with `.voiceChat` mode
- `.voiceChat` mode activates iOS hardware AEC, automatic gain control (AGC), and noise suppression [VERIFIED: Apple Developer docs via web search]

**No manual AVAudioSession configuration is needed** unless calling CallKit or needing custom routing. The SDK handles it.

**To force voiceChat mode explicitly** (if automatic fails or needs verification):
```swift
// Source: github.com/livekit/client-sdk-swift README (AudioManager section)
// Disable auto and set manually:
AudioManager.shared.audioSession.isAutomaticConfigurationEnabled = false
try AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .voiceChat, options: [])
try AVAudioSession.sharedInstance().setActive(true)
// Then re-enable or manage manually
```

**Prefer the automatic path** (leave `isAutomaticConfigurationEnabled = true`). Only override if a specific AEC failure is observed.

### 4. Push-to-Talk (Debug) vs. Auto VAD (Production)

**Auto VAD (production — D-06):**
The server-side LiveKit Agent uses Silero VAD for turn detection. The iOS client simply publishes audio continuously — no client-side VAD configuration required. The server drives all speaking/listening state transitions. [VERIFIED: docs.livekit.io/agents/build/turns/]

**Push-to-talk (debug — D-07):**
```swift
// Toggle mic mute for PTT
// Source: github.com/livekit/client-sdk-swift issues #140 and README
#if DEBUG
if pttEnabled {
    room.localParticipant.setMicrophone(enabled: isHolding)
}
#endif
```

Gate behind a compile-time flag: `#if DEBUG` + a `DEBUG_PTT_ENABLED` boolean in a debug settings bundle or hardcoded debug constant. Do not surface in UI.

Important: `setMicrophone(enabled: false)` mutes the track but keeps the audio session alive. [CITED: github.com/livekit/client-sdk-swift/issues/422 — "Mute without stopping audio recording"]

### 5. Pairing Flow (Magic Link)

The full pairing flow involves new backend work and iOS client handling:

**Backend new endpoint (from D-04):**
```
POST /auth/pair/send-link
Body: {"email": "user@example.com"}
Action: generate pair code, send https://domain.com/pair?code=XXXXXX via Resend
Response: 204 No Content (don't confirm email existence for security)
```

**iOS client flow:**
1. User enters email → `POST /auth/pair/send-link`
2. User taps link in email → iOS opens app via Universal Link
3. App's `onOpenURL` / scene delegate extracts `code` from URL
4. `POST /auth/pair/complete` with `{code}` → receives `{access_token, refresh_token}`
5. Store both tokens in Keychain

**AASA endpoint (backend, also new):**
```python
# FastAPI route needed in src/daily/main.py or a new router
@app.get("/.well-known/apple-app-site-association",
         response_class=JSONResponse)
async def apple_app_site_association():
    return {
        "applinks": {
            "apps": [],
            "details": [{
                "appID": "TEAMID.com.example.daily",
                "paths": ["/pair"]
            }]
        }
    }
```

Requirements: HTTPS only, no redirects, Content-Type: application/json, max 128KB. [VERIFIED: Apple Developer docs]

### 6. Keychain Storage Pattern

```swift
// Source: Apple Security framework + best practices (verified via web search)
// Use kSecClassGenericPassword with kSecAttrAccessibleWhenUnlocked
func saveToKeychain(key: String, value: String) throws {
    let data = value.data(using: .utf8)!
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrAccount: key,
        kSecValueData: data,
        kSecAttrAccessible: kSecAttrAccessibleWhenUnlocked
    ]
    SecItemDelete(query as CFDictionary) // delete old before adding new
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else { throw KeychainError.saveFailed(status) }
}
```

Clear Keychain on first launch (fresh install) to prevent stale tokens from a previous install. [CITED: multiple iOS Keychain best practice sources]

### 7. Connection State UI

The LiveKit `Session` object (or `Room.connectionState`) drives UI state:

| LiveKit State | UI Label | User-Visible |
|---------------|----------|--------------|
| `.connecting` | "Connecting..." | Loading indicator |
| `.connected` (no agent) | "Connecting..." | Loading indicator |
| `.connected` (agent listening) | "Listening" | Mic waveform |
| `.connected` (agent speaking) | "Speaking" | Speaker animation |
| `.reconnecting` | "Reconnecting..." | Warning indicator |
| `.disconnected` | Session ended | Dismiss/retry |

Agent state (`initializing` / `listening` / `thinking` / `speaking`) flows from LiveKit agent data channel metadata. The `Session` object exposes `agentState` directly. [CITED: github.com/livekit-examples/agent-starter-swift]

### 8. Reconnect Behavior

LiveKit Swift SDK automatically reconnects on network loss (WebSocket + ICE restart). [VERIFIED: docs.livekit.io/intro/basics/connect/]

**Known issues to handle defensively:**
- `connectionState` may remain `.connected` during early retry attempts — use `room(_:didUpdateConnectionState:from:)` delegate to track transitions [CITED: github.com/livekit/client-sdk-swift/issues/410]
- WebSocket connection can fail with `NSURLError -1005` in specific network conditions [CITED: github.com/livekit/client-sdk-swift/issues/863]
- Always implement `roomDidDisconnect(room:withError:)` to show user-visible error and offer reconnect

**Background audio:** Enable the "Audio, AirPlay, and Picture in Picture" background mode in Xcode Capabilities. Required for voice session to continue when app is backgrounded. [VERIFIED: docs.livekit.io/home/quickstarts/swift/]

### 9. Project Structure

```
ios/
├── dAIly.xcodeproj/               # Xcode project
├── dAIly/
│   ├── dAIlyApp.swift             # @main entry, scene/URL handling
│   ├── AppState.swift             # @Observable app-wide state
│   ├── auth/
│   │   ├── AuthService.swift      # POST /auth/pair/send-link, /pair/complete, /token/refresh
│   │   ├── KeychainStore.swift    # Token persistence
│   │   └── TokenRefresher.swift   # Proactive refresh logic
│   ├── livekit/
│   │   ├── VoiceSession.swift     # Session + LocalMedia wrappers, token source
│   │   └── AudioSessionConfig.swift # AVAudioSession helpers (if needed)
│   ├── views/
│   │   ├── PairingView.swift      # Email entry + "check your email" screen
│   │   ├── VoiceView.swift        # Main voice UI (state indicator + controls)
│   │   └── ConnectionIndicator.swift # Connecting/Listening/Speaking widget
│   └── Info.plist
└── dAIlyTests/
    ├── AuthServiceTests.swift
    ├── KeychainStoreTests.swift
    └── VoiceSessionTests.swift
```

---

## Implementation Approach

### Wave 0 — Project Scaffold + Backend Prerequisites
1. Create `ios/dAIly.xcodeproj` with SwiftUI app template, iOS 16+ deployment target (use 16 not 13 for `@Observable` and modern API ergonomics despite SDK minimum of 13)
2. Add LiveKit SPM dependency (2.13.0)
3. Configure Info.plist: `NSMicrophoneUsageDescription`, background modes (`audio`)
4. Enable Associated Domains capability: `applinks:yourdomain.com`
5. **Backend:** Add `POST /auth/pair/send-link` endpoint + Resend integration
6. **Backend:** Add `GET /.well-known/apple-app-site-association` endpoint
7. **Backend:** Add `POST /auth/pair/send-link` to existing auth router

### Wave 1 — Auth + Pairing Flow
1. `KeychainStore` — save/load/delete JWT + refresh token
2. `AuthService` — send-link, complete pairing, refresh token
3. `PairingView` — email input, "link sent" confirmation, Universal Link handler
4. `TokenRefresher` — check expiry, call refresh before token expires

### Wave 2 — Voice Session
1. `VoiceSession` — wraps LiveKit `Session` or `Room`, `EndpointTokenSource` calling `/livekit/token`
2. `VoiceView` — connection state indicator, disconnect button, debug PTT gate
3. Wire `agentState` → UI labels (Listening / Speaking)
4. Background audio mode verification

### Wave 3 — Polish + Testing
1. Reconnect handling (user-visible error, retry button)
2. First-launch Keychain cleanup
3. XCTest suite for `AuthService` and `KeychainStore`
4. Manual device testing (simulator cannot test audio or Universal Links reliably)

---

## Risks & Gotchas

### Pitfall 1: AVAudioSession Mode Race Condition
**What goes wrong:** If `setMicrophone(enabled: true)` is called before the audio session is active, the session switches modes mid-stream and audio artifacts / echo occurs.
**Why it happens:** LiveKit auto-configures AVAudioSession lazily when the first track is enabled.
**How to avoid:** Let the SDK manage it (default). Do not call `AVAudioSession.setCategory` before `room.connect()`. If you must configure manually, do it before connecting.

### Pitfall 2: Universal Link Fallback to Browser
**What goes wrong:** Apple fetches AASA from CDN during app install, not at link-click time. If the AASA isn't live when the app is installed, Universal Links silently fall back to Safari.
**Why it happens:** Apple CDN caches AASA aggressively [CITED: codestudy.net/blog/apple-app-site-association-file-is-not-fetched-from-server]
**How to avoid:** Deploy AASA endpoint before submitting TestFlight build. Test with `xcrun simctl openurl booted "https://domain.com/pair?code=test"`. Verify with Apple's AASA validator.

### Pitfall 3: Keychain Stale Tokens After Reinstall
**What goes wrong:** iOS Keychain persists across app installs. A freshly installed app may find a stale (expired) JWT from a previous install, skipping the pairing flow but then failing all API calls.
**How to avoid:** On `applicationDidFinishLaunching`, check a UserDefaults flag `hasLaunchedBefore`. If false, clear all Keychain items then set the flag.

### Pitfall 4: Simulator Cannot Test Audio or Universal Links
**What goes wrong:** AVAudioSession in the simulator does not support `.playAndRecord`. Real microphone capture requires a physical device.
**How to avoid:** All audio tests are manual-only on physical device. Unit test only the non-audio layers (auth, Keychain, URL parsing). Simulator can test UI and state machines.

### Pitfall 5: LiveKit ConnectionState Lag During Reconnect
**What goes wrong:** `room.connectionState` stays `.connected` while the SDK retries internally. UI shows "Connected" when user is actually disconnected.
**How to avoid:** Implement `roomIsReconnecting` delegate / `agentState` changes to drive UI rather than relying solely on `connectionState`. Add a timeout: if agent state doesn't reach `listening` within 8s of room joining, show a reconnect prompt.

### Pitfall 6: EndpointTokenSource Field Name Mismatch
**What goes wrong:** LiveKit's `EndpointTokenSource` may expect specific JSON field names from the token endpoint response that differ from the FastAPI `/livekit/token` response (`{token, room, livekit_url}`).
**Why it happens:** [ASSUMED — exact expected field names for EndpointTokenSource not confirmed against SDK source]
**How to avoid:** Before implementing, read `EndpointTokenSource.swift` in the SDK source to confirm expected JSON keys. If mismatched, implement a custom `TokenSource` conforming type instead.

### Pitfall 7: Swift 6 Strict Concurrency on Delegates
**What goes wrong:** LiveKit delegates are called on SDK's internal thread. Updating `@Observable` / `@Published` properties from delegates without `@MainActor` causes Swift 6 concurrency warnings (errors in strict mode).
**How to avoid:** Mark all UI-updating delegate callbacks with `await MainActor.run { }` or annotate the delegate conformance class with `@MainActor`.

### Pitfall 8: Resend API Key Must Not Be in iOS App
**What goes wrong:** The iOS app calls `POST /auth/pair/send-link` — the backend calls Resend. The Resend API key must stay in the backend `.env`, never in the iOS bundle.
**Architecture is correct** per D-04 (backend sends email). This is not a risk if the design is followed. Document explicitly so no shortcut is taken.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| WebRTC + audio transport | Custom WebRTC session | LiveKit Swift SDK |
| Echo cancellation DSP | Software AEC filter | AVAudioSession `.voiceChat` mode (hardware) |
| VAD on client | Custom audio classifier | Server-side Silero VAD via LiveKit Agents |
| JWT parsing | Custom JWT decoder | PyJWT is server-side; iOS only needs to store opaque token strings, not parse them |
| Keychain wrapper library | Third-party (KeychainAccess, etc.) | Security framework directly — fewer deps, no attack surface |
| HTTP client | Alamofire/Moya | URLSession async/await — sufficient, zero deps |

---

## Runtime State Inventory

Step 2.5: NOT APPLICABLE — this is a greenfield iOS app phase, no rename/refactor/migration.

The backend does get two new endpoints (`POST /auth/pair/send-link`, `GET /.well-known/apple-app-site-association`) but these are additions, not renames. No runtime state migration required.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Xcode | iOS app build | [ASSUMED] | Unknown | None — must have Xcode |
| macOS (for Xcode) | iOS build | Confirmed (Darwin 25.4.0) | macOS 26 | — |
| iOS physical device | Audio + Universal Link testing | [ASSUMED] | Unknown | Simulator for non-audio UI testing |
| LiveKit dev server | Room join testing | ✓ | v1.11.0 (Phase 18) | — |
| FastAPI backend | Token endpoint | ✓ | Phase 18 verified | — |
| Resend account | Magic link email | [ASSUMED] | Unknown — Jacob uses Resend | Fallback: pairing code display in app (temporary) |

**Missing dependencies with no fallback:**
- Xcode — required for all build/test tasks. Assumed present on developer machine.
- Physical iPhone — required for audio, AEC, and real Universal Link testing.

**Missing dependencies with fallback:**
- Resend credentials — if not configured, the send-link endpoint returns 500 but pairing can still be tested via direct `POST /auth/pair/complete` with a manually generated code.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | XCTest (Xcode-bundled) + Swift Testing (Xcode 16+) |
| Config file | Embedded in `dAIly.xcodeproj` (scheme → Test action) |
| Quick run command | `xcodebuild test -project ios/dAIly.xcodeproj -scheme dAIly -destination 'platform=iOS Simulator,name=iPhone 16'` |
| Full suite command | Same + physical device destination for audio tests (manual) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MOB-01 (auth) | `KeychainStore` saves/loads/deletes JWT | unit | `xcodebuild test ... -only-testing:dAIlyTests/KeychainStoreTests` | ❌ Wave 0 |
| MOB-01 (auth) | `AuthService.sendLink` calls correct endpoint | unit (mocked URLSession) | `xcodebuild test ... -only-testing:dAIlyTests/AuthServiceTests` | ❌ Wave 0 |
| MOB-01 (auth) | Universal Link URL parsed correctly | unit | `xcodebuild test ... -only-testing:dAIlyTests/AuthServiceTests/testPairCodeExtraction` | ❌ Wave 0 |
| MOB-01 (voice) | LiveKit room joins with valid token | manual | physical device — connect to dev LiveKit server | N/A |
| MOB-01 (AEC) | No echo during voice session | manual | physical device — AEC quality assessment | N/A |
| MOB-01 (VAD) | Agent responds after user speech | manual | physical device + running agent | N/A |
| MOB-01 (launch) | App connects in <3s | manual | stopwatch from launch to agent state=listening | N/A |

### Sampling Rate
- **Per task commit:** `xcodebuild build -project ios/dAIly.xcodeproj -scheme dAIly` (build succeeds)
- **Per wave merge:** Full unit test suite on simulator
- **Phase gate:** All unit tests green + manual device test of voice session + AEC before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `ios/dAIlyTests/KeychainStoreTests.swift` — covers MOB-01 auth/keychain
- [ ] `ios/dAIlyTests/AuthServiceTests.swift` — covers MOB-01 auth flow + URL parsing
- [ ] `ios/dAIlyTests/VoiceSessionTests.swift` — state machine unit tests (mock LiveKit connection)
- [ ] Xcode project itself at `ios/dAIly.xcodeproj` — must be created in Wave 0

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Keychain (kSecAttrAccessibleWhenUnlocked), JWT Bearer |
| V3 Session Management | yes | Short-lived access JWT (1h from Phase 18); refresh token rotation |
| V4 Access Control | no | Backend enforces; iOS client is consumer only |
| V5 Input Validation | yes | URL parsing for pair code extraction; email input validation before send |
| V6 Cryptography | no — iOS Keychain handles it | kSecAttrAccessibleWhenUnlocked uses device Secure Enclave |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Pair code interception | Info Disclosure | HTTPS Universal Link (not custom scheme — D-03); codes are single-use and 5-min TTL |
| Stale token replay after reinstall | Elevation of Privilege | Clear Keychain on first launch |
| URL scheme hijack | Spoofing | Universal Links cannot be claimed by another app (OS-verified AASA) |
| Resend API key exposure | Info Disclosure | Key stays in backend `.env`; iOS client never sees it (D-04 architecture) |
| JWT stored in UserDefaults | Tampering | Forbidden by D-05; use Keychain only |
| Man-in-the-middle on /livekit/token | Tampering | HTTPS enforced; never call over HTTP |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom URL schemes (`myapp://`) | Universal Links (`https://domain/path`) | iOS 9 / still evolving | More secure, no hijacking, cleaner UX |
| CocoaPods for LiveKit | Swift Package Manager | 2024 (CocoaPods deprecated by LiveKit) | SPM only — use `.upToNextMajor("2.13.0")` |
| Software AEC (WebRTC built-in) | iOS hardware AEC via `.voiceChat` mode | iOS 13+ | Eliminates echo without CPU overhead |
| Custom VAD on client | Server-side Silero VAD (LiveKit Agents) | 2024 (LiveKit Agents launch) | Simpler iOS client; better accuracy |
| ObservableObject + @Published | @Observable macro (iOS 17+) | iOS 17 | Better performance; but requires iOS 17 minimum — use ObservableObject if targeting iOS 16 |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `EndpointTokenSource` expects JSON fields compatible with FastAPI response `{token, room, livekit_url}` | Key APIs §2 | Token source fails silently; custom `TokenSource` implementation needed |
| A2 | Jacob has Xcode installed and an Apple Developer account for device testing | Environment | Phase cannot be executed without Xcode + paid account for physical device |
| A3 | Resend credentials are available for the backend send-link endpoint | Environment | Magic link flow cannot be tested end-to-end; fallback: manual pair code |
| A4 | The `Session` high-level API from `agent-starter-swift` works with custom `EndpointTokenSource` | Implementation Approach | May need to drop to lower-level `Room` API if `Session` is tightly coupled to LiveKit Cloud |
| A5 | iOS deployment target of 16 is appropriate (SDK minimum is 13 but `@Observable` is 17) | Project Scaffold | Using 16 blocks `@Observable`; use `ObservableObject` instead |

---

## Open Questions

1. **EndpointTokenSource JSON contract**
   - What we know: FastAPI returns `{token, room, livekit_url}`. SDK has an `EndpointTokenSource` type.
   - What's unclear: Exact JSON field names expected by `EndpointTokenSource` (especially whether it reads `url` or `livekit_url`).
   - Recommendation: Read `EndpointTokenSource.swift` in the SDK source before implementing. If mismatch, write a custom `TokenSource` struct — straightforward 20-line implementation.

2. **Apple Developer Team ID**
   - What we know: AASA file requires `TEAMID.bundleIdentifier` format.
   - What's unclear: Jacob's Apple Developer Team ID and intended bundle ID for the app.
   - Recommendation: Resolve in Wave 0 before creating the AASA endpoint. Use a placeholder that gets replaced.

3. **LiveKit dev server accessibility from iOS device**
   - What we know: LiveKit runs in Docker on localhost (Phase 18).
   - What's unclear: Can a physical iOS device reach the dev LiveKit server? Requires VPS or ngrok tunnel for real device testing.
   - Recommendation: Plan for ngrok or Cloudflare Tunnel for dev device testing; production uses the VPS LiveKit deployment.

4. **Resend email domain verification**
   - What we know: Resend requires domain DNS verification before sending.
   - What's unclear: Whether the domain used for the FastAPI backend is already verified with Resend.
   - Recommendation: Verify in Wave 0; if not set up, magic link email delivery will fail silently.

---

## Sources

### Primary (HIGH confidence)
- [github.com/livekit/client-sdk-swift](https://github.com/livekit/client-sdk-swift) — SDK version (2.13.0), iOS minimum (13.0), Swift 6.0 requirement, AVAudioSession patterns
- [github.com/livekit/client-sdk-swift releases](https://github.com/livekit/client-sdk-swift/releases) — latest version 2.13.0, released 2026-04-10
- [Package.swift (raw)](https://raw.githubusercontent.com/livekit/client-sdk-swift/main/Package.swift) — platforms: iOS 13.0, macOS 10.15, macCatalyst 14.0, tvOS 17.0
- [docs.livekit.io/home/quickstarts/swift/](https://docs.livekit.io/home/quickstarts/swift/) — Room connection API, Info.plist requirements, background mode
- [github.com/livekit-examples/agent-starter-swift](https://github.com/livekit-examples/agent-starter-swift) — Session + LocalMedia architecture, preConnectAudio, EndpointTokenSource
- [Apple Developer — AASA / Universal Links](https://developer.apple.com/documentation/xcode/supporting-associated-domains) — AASA requirements, no-redirect rule

### Secondary (MEDIUM confidence)
- [docs.livekit.io/agents/build/turns/](https://docs.livekit.io/agents/build/turns/) — server-side Silero VAD, turn detection architecture
- [github.com/livekit/client-sdk-swift/issues/410](https://github.com/livekit/client-sdk-swift/issues/410) — connectionState lag during reconnect (known issue)
- [github.com/livekit/client-sdk-swift/issues/863](https://github.com/livekit/client-sdk-swift/issues/863) — NSURLError -1005 WebSocket failure pattern
- [Apple voiceChat mode docs (via web search)](https://developer.apple.com/documentation/avfaudio/avaudiosession/mode-swift.struct/voicechat) — hardware AEC activation
- [codestudy.net — AASA CDN caching](https://www.codestudy.net/blog/apple-app-site-association-file-is-not-fetched-from-server-but-cached-at-apple/) — Apple CDN caches AASA at install time

### Tertiary (LOW confidence)
- Various iOS Keychain best practice articles — consistent with Apple documentation; no single authoritative source cited

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — SDK version and iOS minimum verified against GitHub/Package.swift
- Architecture patterns: HIGH — from official LiveKit starter app and documentation
- AVAudioSession/AEC: HIGH — Apple docs + LiveKit README confirm .voiceChat automatic activation
- Pitfalls: MEDIUM — reconnect issues from GitHub issues (real reports, not official docs)
- EndpointTokenSource field names: LOW — not verified against SDK source (A1 assumption)

**Research date:** 2026-04-30
**Valid until:** 2026-05-30 (LiveKit SDK releases frequently; check for updates beyond 2.13.0)
