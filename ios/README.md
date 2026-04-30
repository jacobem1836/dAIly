# dAIly iOS App

Native iOS client for dAIly — a voice-first AI personal assistant.

## Prerequisites

- macOS with Xcode 15+ installed
- Apple Developer account (free or paid)
- iOS 16+ device or simulator for testing
- Running dAIly FastAPI backend

## Initial Setup

### 1. Set Apple Team ID and Bundle ID

After cloning, open `ios/dAIly.xcodeproj` in Xcode:

1. Select the **dAIly** target in the project navigator
2. Go to **Signing & Capabilities**
3. Set your **Team** (Apple Developer account)
4. The Bundle Identifier is `com.daily.ios` — change this to match your Apple Developer account (must be unique)

Or update `ios/project.yml` and regenerate:

```yaml
settings:
  base:
    PRODUCT_BUNDLE_IDENTIFIER: com.yourname.daily.ios   # change this
```

Then run: `cd ios && xcodegen generate`

### 2. Replace the Universal Link Domain

The entitlement file at `ios/dAIly/dAIly.entitlements` contains a placeholder domain:

```xml
<string>applinks:app.example.com</string>
```

Replace `app.example.com` with your production domain (the domain where the FastAPI backend is deployed). The backend must serve `/.well-known/apple-app-site-association` from this domain.

### 3. Resolve SPM Dependencies

SPM packages (LiveKit 2.13.0) are declared in `project.pbxproj`. On first open in Xcode, SPM will automatically resolve and download the packages. The `Package.resolved` file in this repo contains version pins — Xcode will use them.

## Building

### Generate the Xcode project (if project.yml was changed)

```bash
cd ios
xcodegen generate
```

### Build for iOS Simulator

```bash
cd ios
xcodebuild \
  -project dAIly.xcodeproj \
  -scheme dAIly \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

### Run Tests on iOS Simulator

```bash
cd ios
xcodebuild test \
  -project dAIly.xcodeproj \
  -scheme dAIly \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGNING_ALLOWED=NO
```

## Architecture

The app is architecturally thin — all STT, LLM, and TTS processing happen server-side via the Python LiveKit Agent.

```
iOS App                         Backend (FastAPI)
  |                                 |
  |-- POST /auth/pair/send-link --> | (new in Phase 19)
  |                                 |-- Sends magic link via Resend
  |
  |<-- Universal Link tap ----------|
  |
  |-- POST /auth/pair/complete ---> |
  |<-- {access_token, refresh_token}|
  |
  |-- Store tokens in Keychain -----|
  |
  |-- POST /livekit/token --------> |
  |<-- {token, room, livekit_url} --|
  |
  |-- Join LiveKit room ----------> | LiveKit Server
  |-- Publish audio track --------> |
  |<-- Subscribe agent audio -------|
```

## Security Notes

- JWT and refresh tokens are stored in iOS Keychain with `kSecAttrAccessibleWhenUnlocked`
- Tokens are never stored in UserDefaults
- The Resend API key lives only in the backend `.env` — never in the iOS bundle
- Universal Links (HTTPS-based) are used for magic link handling — custom URL schemes are explicitly rejected

## Local Dev with ngrok / Cloudflare Tunnel

The iOS app requires HTTPS even during local development. Use a tunnel to expose your local backend:

### Option A: Cloudflare Tunnel (recommended — no account needed for one-time URLs)

```bash
cloudflared tunnel --url http://localhost:8000
# Note the printed HTTPS URL, e.g. https://abcd-1234.trycloudflare.com
```

### Option B: ngrok

```bash
ngrok http 8000
# Note the Forwarding HTTPS URL, e.g. https://abcd1234.ngrok.io
```

### Wire the tunnel URL into the app

1. Open `ios/dAIly/Config.swift` and replace the `backendBaseURL` value:

   ```swift
   public static let backendBaseURL: URL = URL(string: "https://abcd-1234.trycloudflare.com")!
   ```

2. Update the `applinks:` entry in `ios/dAIly/dAIly.entitlements` to match the tunnel host:

   ```xml
   <string>applinks:abcd-1234.trycloudflare.com</string>
   ```

3. Re-run `xcodegen generate` if `project.yml` changed, then rebuild.

4. Verify AASA is reachable from the tunnel:

   ```bash
   curl https://abcd-1234.trycloudflare.com/.well-known/apple-app-site-association
   ```

> **Note:** Tunnel URLs rotate on each restart. Update `Config.swift` and `dAIly.entitlements` each time.

## Backend URL Configuration

`ios/dAIly/Config.swift` is the single source of truth for the backend URL:

```swift
public static let backendBaseURL: URL = URL(string: "https://app.example.com")!
```

Replace `https://app.example.com` with your actual backend URL:
- **Local development:** Use an HTTPS tunnel URL (see "Local Dev with ngrok" above)
- **Production/TestFlight:** Use your deployed FastAPI backend URL

## Entitlements Checklist

Before shipping to TestFlight:

- [ ] Replace `app.example.com` with your production domain in `dAIly.entitlements`
- [ ] Replace `https://app.example.com` baseURL in `dAIlyApp.swift` with real backend URL
- [ ] Set correct Apple Team ID in Xcode Signing & Capabilities
- [ ] Verify `/.well-known/apple-app-site-association` is live on your domain
- [ ] Verify AASA contains correct `TEAMID.com.your.bundleid` format
- [ ] Test Universal Link with: `xcrun simctl openurl booted "https://yourdomain.com/pair?code=test"`
