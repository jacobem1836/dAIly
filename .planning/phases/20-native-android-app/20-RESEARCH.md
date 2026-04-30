# Phase 20: Native Android App - Research

**Researched:** 2026-04-30
**Domain:** Android (Kotlin + Jetpack Compose + LiveKit Android SDK)
**Confidence:** MEDIUM-HIGH (SDK API verified; min SDK and AEC nuances LOW)

---

## Summary

Phase 20 mirrors the iOS app (Phase 19) in Kotlin. The Python backend already provides all required endpoints (pair/send-link, pair/complete, token/refresh, livekit/token). The Android app is a thin LiveKit room participant — STT, LLM, and TTS all happen server-side. The primary Android-specific work is: (1) Android project scaffold with Gradle + LiveKit Android SDK, (2) EncryptedSharedPreferences replacement (Tink + DataStore — ESP is now deprecated), (3) App Links / assetlinks.json backend endpoint (parallel to the existing AASA endpoint), (4) hardware AEC via `AudioOptions.javaAudioDeviceModuleCustomizer`, and (5) Jetpack Compose voice UI matching iOS's state machine.

The LiveKit Android SDK uses Kotlin coroutines and StateFlow — the pattern is structurally identical to iOS's ObservableObject + @Published. The main gotcha is that `EncryptedSharedPreferences` is deprecated in 2026; the replacement stack is `androidx.datastore:datastore-preferences` + Google Tink. A secondary gotcha is that hardware AEC via `javaAudioDeviceModuleCustomizer` has known device-fragmentation issues — the SDK's default WebRTC software AEC works reliably and is appropriate for a voice-first app.

**Primary recommendation:** Use Jetpack Compose (not XML). Use DataStore + Tink for secure token storage. Use LiveKit's default audio configuration (do NOT override javaAudioDeviceModuleCustomizer) for reliable AEC, matching the iOS pattern of letting the SDK manage audio session automatically.

---

## User Constraints

*(No CONTEXT.md exists for Phase 20 yet — this section will be populated by discuss-phase. The iOS decisions in 19-CONTEXT.md are the closest analogs and should be mirrored unless explicitly changed.)*

### iOS Decisions to Mirror (from 19-CONTEXT.md)
- **D-06:** Auto VAD is the only production voice mode (push-to-talk debug-flag only)
- **D-07:** PTT exists in code behind `BuildConfig.DEBUG` flag, not surfaced in production UI
- **D-08:** STT/TTS happen server-side — no Deepgram or Cartesia SDKs in the Android client
- **D-09:** Client-direct STT/TTS deferred to M2
- **D-10:** Minimal voice UI: connection state indicator + session controls

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LiveKit Android SDK | 2.25.1 | LiveKit room transport + WebRTC | Official SDK, Maven Central + JitPack, Kotlin coroutines native [VERIFIED: Maven Central + GitHub 2026-04-29] |
| Jetpack Compose | BOM 2025.01+ | UI toolkit | Google's official modern Android UI; recommended for all new apps 2025 [CITED: developer.android.com] |
| Kotlin | 1.9+ | Language | Coroutines, StateFlow, sealed classes for state machine |
| androidx.datastore:datastore-preferences | 1.1.x | Secure token storage | Async, coroutine-native replacement for SharedPreferences [CITED: developer.android.com] |
| Google Tink (via datastore-tink) | latest | Encryption for DataStore | Official AES-GCM encryption; replaces EncryptedSharedPreferences [CITED: developer.android.com] |
| OkHttp3 MockWebServer | 4.x | HTTP mocking in unit tests | Analog of iOS StubURLProtocol; well-established Android pattern [CITED: square.github.io/okhttp] |
| MockK | 1.13+ | Kotlin mocking framework | Native Kotlin support, coroutine-aware (coEvery/coVerify) [CITED: mockk.io] |
| JUnit 4 / JUnit 5 | 4.13 / 5.x | Test runner | Standard Android test runner |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| LiveKit Components Android | matches SDK | Jetpack Compose UI primitives for LiveKit | Optional — provides pre-built composables; use if ConnectionIndicator is complex |
| kotlinx-coroutines-test | 1.7+ | Testing coroutines | Required for testing StateFlow and suspend functions |
| androidx.lifecycle:lifecycle-viewmodel-compose | 2.7+ | ViewModel integration with Compose | Compose ViewModel scoping |
| androidx.activity:activity-compose | 1.8+ | ComponentActivity + setContent | Entry point for Compose apps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DataStore + Tink | EncryptedSharedPreferences | ESP is deprecated as of security-crypto 1.1.0-alpha07 — do NOT use it for new code [CITED: developer.android.com/jetpack/androidx/releases/security] |
| Jetpack Compose | XML layouts | XML is legacy; Compose recommended for all new apps in 2025 per Google [CITED: developer.android.com] |
| LiveKit default AEC | javaAudioDeviceModuleCustomizer override | Custom AEC override is unreliable across devices (open GitHub issues #600, #673); default WebRTC AEC works correctly [CITED: github.com/livekit/client-sdk-android/issues/600] |
| MockWebServer | MockK HTTP mocking | MockWebServer exercises the full HTTP stack at the socket level; more realistic than function mocking for network layer |

### Installation (app/build.gradle.kts)

```kotlin
dependencies {
    val livekit_version = "2.25.1"
    implementation("io.livekit:livekit-android:$livekit_version")

    // Jetpack Compose
    implementation(platform("androidx.compose:compose-bom:2025.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.runtime:runtime")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")

    // Secure token storage (replaces EncryptedSharedPreferences)
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("com.google.crypto.tink:tink-android:1.14.0")

    // Tests
    testImplementation("junit:junit:4.13.2")
    testImplementation("io.mockk:mockk:1.13.10")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
}
```

### settings.gradle.kts (JitPack required for LiveKit)

```kotlin
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven("https://jitpack.io")  // Required by LiveKit Android SDK
    }
}
```

**Version verification:**
- `io.livekit:livekit-android` 2.25.1 — verified via Maven Central [VERIFIED: central.sonatype.com, 2026-04-28]
- `@livekit/client` npm 2.18.2 — not relevant (JS SDK, not Android)
- `EncryptedSharedPreferences` deprecated in `security-crypto:1.1.0-alpha07` [VERIFIED: WebSearch, developer.android.com]

---

## Architecture Patterns

### Recommended Project Structure

```
android/
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   └── kotlin/com/daily/android/
│       │       ├── DailyApp.kt          # Application subclass
│       │       ├── MainActivity.kt      # Single activity, Compose host
│       │       ├── Config.kt            # Equivalent of iOS Config.swift
│       │       ├── auth/
│       │       │   ├── TokenStore.kt    # DataStore + Tink (equiv: KeychainStore)
│       │       │   ├── AuthService.kt   # sendLink, completePairing, refresh
│       │       │   ├── TokenRefresher.kt
│       │       │   └── PairCodeUriParser.kt
│       │       ├── livekit/
│       │       │   ├── LiveKitTokenSource.kt
│       │       │   ├── VoiceSession.kt  # StateFlow state machine
│       │       │   └── DebugFlags.kt
│       │       └── ui/
│       │           ├── PairingScreen.kt
│       │           ├── VoiceScreen.kt
│       │           └── ConnectionIndicator.kt
│       └── test/
│           └── kotlin/com/daily/android/
│               ├── auth/
│               │   ├── TokenStoreTest.kt
│               │   ├── AuthServiceTest.kt
│               │   └── PairCodeUriParserTest.kt
│               └── livekit/
│                   └── VoiceSessionTest.kt
├── build.gradle.kts
└── settings.gradle.kts
```

### Pattern 1: VoiceSession as ViewModel with StateFlow

The iOS `VoiceSession: ObservableObject` maps directly to Android `VoiceSession: ViewModel` with `StateFlow`:

```kotlin
// Source: iOS VoiceSession.swift pattern, adapted to Android/Kotlin
class VoiceSession(
    private val tokenSource: LiveKitTokenSource,
    private val auth: AuthService,
    private val tokenStore: TokenStore,
    application: Application,
) : AndroidViewModel(application) {

    sealed class State {
        object Idle : State()
        object Connecting : State()
        object Listening : State()
        object Speaking : State()
        object Reconnecting : State()
        data class Error(val message: String) : State()
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    private var room: Room? = null

    fun connect() {
        viewModelScope.launch {
            _state.value = State.Connecting
            val jwt = tokenStore.loadAccessToken()
                ?: run { _state.value = State.Error("not_authenticated"); return@launch }
            // ... fetch LiveKit token, connect room, set up event collection
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            room?.disconnect()
            room = null
            _state.value = State.Idle
        }
    }
}
```

### Pattern 2: Room Events via StateFlow (LiveKit Android SDK)

LiveKit Android SDK uses Kotlin Flows — no delegate pattern needed (unlike iOS):

```kotlin
// Source: LiveKit Android SDK docs — room.events + @FlowObservable properties
viewModelScope.launch {
    room.events.collect { event ->
        when (event) {
            is RoomEvent.Connected -> _state.value = State.Listening
            is RoomEvent.Reconnecting -> _state.value = State.Reconnecting
            is RoomEvent.Disconnected -> _state.value = State.Idle
            is RoomEvent.ParticipantSpeakingChanged -> {
                val speaking = event.participant.isSpeaking
                if (speaking) _state.value = State.Speaking
                else if (_state.value == State.Speaking) _state.value = State.Listening
            }
            else -> {}
        }
    }
}
```

### Pattern 3: Room Creation (default AEC — recommended)

```kotlin
// Source: LiveKit Android SDK README [VERIFIED: github.com/livekit/client-sdk-android]
// Do NOT override AudioOptions — let the SDK manage audio session automatically.
// This gives hardware AEC on devices that support it, software AEC as fallback.
val room = LiveKit.create(applicationContext)
room.connect(url = lkToken.url, token = lkToken.token)
room.localParticipant.setMicrophoneEnabled(true)
```

### Pattern 4: Token Storage — DataStore + Tink

```kotlin
// Source: [CITED: developer.android.com/topic/libraries/architecture/datastore]
// Replaces iOS KeychainStore. AES-256-GCM via Tink.
class TokenStore(context: Context) {
    private val dataStore = context.createDataStore(
        fileName = "tokens.pb",
        serializer = EncryptedSerializer(context)  // Tink-backed
    )

    suspend fun saveAccessToken(token: String) {
        dataStore.edit { prefs -> prefs[ACCESS_TOKEN_KEY] = token }
    }

    suspend fun loadAccessToken(): String? {
        return dataStore.data.first()[ACCESS_TOKEN_KEY]
    }
}
```

### Pattern 5: App Links — AndroidManifest Intent Filter

```xml
<!-- AndroidManifest.xml — equivalent of iOS Universal Link entitlement -->
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="yourdomain.com"
              android:pathPrefix="/pair" />
    </intent-filter>
</activity>
```

```kotlin
// MainActivity.kt — receive deep link in onCreate / onNewIntent
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    handleIntent(intent)
}

override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    handleIntent(intent)
}

private fun handleIntent(intent: Intent) {
    val uri = intent.data ?: return
    val code = PairCodeUriParser.extractCode(uri) ?: return
    // Launch coroutine to complete pairing
}
```

### Anti-Patterns to Avoid

- **Using EncryptedSharedPreferences:** Deprecated since `security-crypto:1.1.0-alpha07`. Use DataStore + Tink.
- **Overriding javaAudioDeviceModuleCustomizer:** `setUseHardwareAcousticEchoCanceler(true)` has known issues (GitHub #600, #673) — device fragmentation means this may amplify noise on some hardware. Let LiveKit's default manage AEC.
- **Blocking the main thread with SharedPreferences:** DataStore is async — always access via coroutines.
- **Using `android.intent.scheme` custom URL scheme:** Use App Links (HTTPS scheme) with autoVerify — not hijackable by other apps (mirrors iOS Universal Links decision D-03).
- **Launching the Activity for single instance:** The `/pair` deep link should use `launchMode="singleTop"` and handle the intent in `onNewIntent` to avoid re-creating the activity if it's already running.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AES-256 token encryption | Custom Cipher code | Google Tink | Tink is Google's vetted crypto library; handles key rotation, nonce management automatically |
| WebSocket/WebRTC audio transport | Custom WebRTC integration | LiveKit Android SDK | LiveKit wraps WebRTC with reconnection, ICE, TURN, etc. |
| HTTP server for unit tests | Manual request/response stubs | OkHttp MockWebServer | Exercises full HTTP stack; analogous to iOS StubURLProtocol |
| Echo cancellation DSP | Custom Oboe integration | LiveKit default AudioOptions | SDK manages AVAudioSession equivalent automatically; custom Oboe brings fragmentation risk |
| Kotlin Flow from scratch | Custom EventBus | LiveKit `room.events` Flow | SDK emits typed RoomEvents as a Kotlin Flow |

**Key insight:** The iOS app deliberately avoided overriding AVAudioSession configuration (`isAutomaticConfigurationEnabled` left at default). Apply the same discipline on Android — do NOT override `javaAudioDeviceModuleCustomizer`. The SDK's default achieves hardware AEC on supported devices and gracefully falls back to software AEC.

---

## Backend Changes Required

### New Endpoint: `GET /.well-known/assetlinks.json`

The backend already has `GET /.well-known/apple-app-site-association` (Plan 19-01). Android App Links require a parallel endpoint:

```
GET /.well-known/assetlinks.json
Content-Type: application/json
```

Required JSON structure:
```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.daily.android",
    "sha256_cert_fingerprints": ["AA:BB:CC:..."]
  }
}]
```

**Key differences from AASA:**
- AASA contains Team ID + Bundle ID → Android needs package name + SHA-256 signing cert fingerprint
- The SHA-256 fingerprint is from the app's signing keystore — changes between debug and release
- Must be served with `Content-Type: application/json` and no redirects (same requirement as AASA)
- Must be reachable over HTTPS from Android's verification service

**New Settings fields needed in `src/daily/config.py`:**
- `android_package_name: str` (e.g., `"com.daily.android"`)
- `android_sha256_fingerprint: str` (e.g., `"AA:BB:CC:..."`)

**FastAPI route addition in `src/daily/main.py`** (parallel to apple_app_site_association):
```python
@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def asset_links() -> JSONResponse:
    settings = Settings()
    return JSONResponse(
        content=[{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": settings.android_package_name,
                "sha256_cert_fingerprints": [settings.android_sha256_fingerprint]
            }
        }],
        media_type="application/json",
    )
```

---

## Common Pitfalls

### Pitfall 1: EncryptedSharedPreferences Is Deprecated

**What goes wrong:** Developer adds `androidx.security:security-crypto` and uses `EncryptedSharedPreferences` — this compiles and works but uses a deprecated API heading toward removal.
**Why it happens:** Training data and many blog posts still recommend ESP. The deprecation landed in `1.1.0-alpha07`.
**How to avoid:** Use `androidx.datastore:datastore-preferences` + `tink-android`. Do not add `security-crypto` to dependencies at all.
**Warning signs:** Any import of `androidx.security.crypto.EncryptedSharedPreferences`.

### Pitfall 2: Hardware AEC Override Breaks on Some Devices

**What goes wrong:** Calling `builder.setUseHardwareAcousticEchoCanceler(true)` in `javaAudioDeviceModuleCustomizer` causes echo amplification or audio distortion on some Android OEMs.
**Why it happens:** The `JavaAudioDeviceModule` customizer overrides LiveKit's tested defaults. Device-specific audio hardware varies wildly on Android.
**How to avoid:** Do not override `javaAudioDeviceModuleCustomizer`. LiveKit's default uses WebRTC's built-in acoustic processing, which includes AEC on devices that support it. Open GitHub issues #600 and #673 document failures with the override approach.
**Warning signs:** Any `javaAudioDeviceModuleCustomizer` usage in `LiveKit.create()`.

### Pitfall 3: App Links Verification Fails Without Correct SHA-256

**What goes wrong:** App installs but tapping the magic link opens a browser chooser instead of the app directly.
**Why it happens:** Android verifies App Links at install time by fetching `/.well-known/assetlinks.json` and matching the SHA-256 against the installed APK's signing certificate. Debug vs release keystores have different SHA-256 fingerprints.
**How to avoid:** The `assetlinks.json` should include BOTH the debug and release SHA-256 fingerprints during development. Use `keytool -printcert -jarfile app.apk | grep SHA256` to get the fingerprint.
**Warning signs:** Opening the `/pair?code=XXX` URL from email goes to browser, not app.

### Pitfall 4: Deep Link Arrives in Already-Running Activity

**What goes wrong:** User taps magic link while app is already open — `onCreate` is not called, so the code handling the deep link never runs.
**Why it happens:** Default `launchMode` creates a new task/activity. With `singleTop` or `singleTask`, `onNewIntent` is called instead.
**How to avoid:** Set `android:launchMode="singleTop"` on `MainActivity` and implement `onNewIntent` to handle the deep link URI alongside `onCreate`.
**Warning signs:** Deep link works on cold launch but silently fails when app is already in foreground.

### Pitfall 5: JitPack Required for LiveKit (Not Maven Central Alone)

**What goes wrong:** Gradle sync fails with "Could not resolve io.livekit:livekit-android:2.25.1".
**Why it happens:** LiveKit Android SDK depends on JitPack-hosted transitive dependencies — Maven Central alone is insufficient.
**How to avoid:** Add `maven("https://jitpack.io")` to `settings.gradle.kts` `dependencyResolutionManagement.repositories`.
**Warning signs:** Gradle sync error mentioning resolution failure despite Maven Central being listed.

### Pitfall 6: DataStore Is Async — No Blocking Read

**What goes wrong:** Calling `runBlocking { dataStore.data.first()[key] }` on the main thread causes ANR on slow devices.
**Why it happens:** DataStore is intentionally async-only. There is no synchronous read path.
**How to avoid:** Always read/write DataStore inside a coroutine (`viewModelScope.launch`, `lifecycleScope.launch`). Initialize the ViewModel with token presence check as a Flow.
**Warning signs:** `runBlocking` used anywhere with DataStore; token read in `Application.onCreate`.

### Pitfall 7: Room Events vs RoomDelegate (iOS vs Android API Difference)

**What goes wrong:** Developer tries to implement `RoomDelegate` callbacks (iOS pattern) on Android.
**Why it happens:** The iOS SDK uses a delegate pattern; the Android SDK uses Kotlin Flows.
**How to avoid:** Collect `room.events` as a Flow in a coroutine scope. Use `room::activeSpeakers.flow.collectLatest` for speaking state. There is no `RoomDelegate` protocol on Android.
**Warning signs:** Searching for "RoomDelegate" in Android SDK docs — it does not exist.

---

## Code Examples

### Room Connection (Standard Pattern)

```kotlin
// Source: github.com/livekit/client-sdk-android README [VERIFIED]
val room = LiveKit.create(applicationContext)

// Connect with token from /livekit/token backend endpoint
room.connect(url = lkToken.livekit_url, token = lkToken.token)

// Enable mic for voice input (auto-VAD mode — D-06 mirror)
room.localParticipant.setMicrophoneEnabled(true)
```

### Collecting Room State Events

```kotlin
// Source: LiveKit Android SDK @FlowObservable pattern [CITED: docs.livekit.io]
viewModelScope.launch {
    room.events.collect { event ->
        when (event) {
            is RoomEvent.Connected -> _state.value = VoiceState.Listening
            is RoomEvent.Reconnecting -> _state.value = VoiceState.Reconnecting
            is RoomEvent.Disconnected -> {
                if (event.error != null) _state.value = VoiceState.Error(event.error.message)
                else _state.value = VoiceState.Idle
            }
            else -> Unit
        }
    }
}

// Speaking state via @FlowObservable property
viewModelScope.launch {
    room::activeSpeakers.flow.collectLatest { speakers ->
        val agentSpeaking = speakers.any { it.identity != room.localParticipant.identity }
        if (agentSpeaking) _state.value = VoiceState.Speaking
        else if (_state.value == VoiceState.Speaking) _state.value = VoiceState.Listening
    }
}
```

### AuthService (HTTP pattern mirrors iOS)

```kotlin
// Mirrors ios/dAIly/auth/AuthService.swift — same endpoints, same error types
class AuthService(
    private val baseUrl: String,
    private val client: OkHttpClient = OkHttpClient(),
    private val tokenStore: TokenStore,
) {
    suspend fun sendLink(email: String) = withContext(Dispatchers.IO) {
        val body = """{"email":"$email"}"""
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$baseUrl/auth/pair/send-link")
            .post(body)
            .build()
        client.newCall(request).execute().use { resp ->
            if (resp.code != 204) throw AuthError.Server(resp.code)
        }
    }

    suspend fun completePairing(code: String): PairingResult = withContext(Dispatchers.IO) {
        // POST /auth/pair/complete, parse {access_token, refresh_token, expires_in}
        // Persist to TokenStore
    }
}
```

### PairCodeUriParser (mirrors iOS PairCodeURLParser)

```kotlin
object PairCodeUriParser {
    fun extractCode(uri: Uri): String? {
        if (uri.path != "/pair") return null
        return uri.getQueryParameter("code")
    }
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| EncryptedSharedPreferences | DataStore + Tink | Late 2024 (security-crypto 1.1.0-alpha07) | New projects must use DataStore + Tink |
| XML layouts | Jetpack Compose | Compose stable since 2021, standard 2023+ | New apps should not use XML |
| LiveKit SDK v1 (Java) | LiveKit SDK v2 (Kotlin-first) | v2 launched 2023 | v2 uses Flows, not callbacks |
| Custom Oboe AEC | LiveKit default WebRTC AEC | N/A | Let the SDK manage AEC |
| RoomDelegate callbacks | room.events Flow | LiveKit Android v2 | Idiomatic Kotlin — collect events as Flow |

**Deprecated/outdated:**
- `EncryptedSharedPreferences`: deprecated, avoid
- LiveKit Android SDK v1: migration guide at docs.livekit.io/reference/migration-guides/migrate-from-v1
- `android:usesCleartextTraffic="true"`: never needed — all traffic is HTTPS

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Java / JDK | Gradle build | ✓ | OpenJDK 25.0.2 | — |
| Android SDK / adb | Build & deploy | ✗ | — | Developer machine (same constraint as iOS) |
| Gradle | Build tool | ✗ (system) | — | Gradle wrapper (gradlew) in project — no system install needed |
| Kotlin | Language | ✗ (system) | — | Gradle plugin pulls Kotlin compiler |
| Android Studio | IDE | ✗ | — | Build/test deferred to developer machine (same as iOS) |

**Missing dependencies with fallback:**
- Android SDK, adb, Android Studio: same pattern as iOS Phase 19 — all code artifacts created correctly on this machine, build verification deferred to developer machine where Android Studio is installed.

**Note:** Java 25 is present (`/usr/bin/java`). Gradle wrapper (`gradlew`) is self-bootstrapping — no system Gradle install needed. Android SDK tools (adb, emulator, sdkmanager) are not installed but are only needed for device/emulator testing.

---

## Validation Architecture

Tests follow the same TDD pattern as Phase 19 iOS tests. Android unit tests run on JVM (no emulator needed for pure Kotlin tests). Instrumented tests require a device/emulator — same constraint as iOS `xcodebuild test`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | JUnit 4 + MockK + OkHttp MockWebServer |
| Config file | `android/app/build.gradle.kts` (testImplementation deps) |
| Quick run (JVM only) | `./gradlew test` |
| Full suite (with instrumented) | `./gradlew connectedAndroidTest` (requires device/emulator) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| MOB-02.1 | LiveKit room connects with token | unit | `./gradlew test --tests "*.VoiceSessionTest"` | MockWebServer for /livekit/token |
| MOB-02.2 | PTT / auto VAD modes | unit | `./gradlew test --tests "*.VoiceSessionTest"` | StateFlow state machine test |
| MOB-02.3 | Hardware AEC eliminates echo | manual | Physical device test | Cannot be unit tested |
| MOB-02.4 | Daily briefing playback end-to-end | manual | Physical device test | Requires LiveKit + backend running |

### Wave 0 Gaps

- [ ] `android/app/src/test/kotlin/.../auth/TokenStoreTest.kt` — covers secure storage
- [ ] `android/app/src/test/kotlin/.../auth/AuthServiceTest.kt` — covers sendLink, completePairing, refresh
- [ ] `android/app/src/test/kotlin/.../auth/PairCodeUriParserTest.kt` — covers deep link extraction
- [ ] `android/app/src/test/kotlin/.../livekit/VoiceSessionTest.kt` — covers state machine
- [ ] `android/app/src/test/kotlin/.../livekit/LiveKitTokenSourceTest.kt` — covers /livekit/token fetch

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Magic link (email + pair code) — mirrors iOS |
| V3 Session Management | yes | DataStore + Tink for access/refresh token storage |
| V4 Access Control | yes | Bearer JWT on all authenticated endpoints |
| V5 Input Validation | yes | URI parsing in PairCodeUriParser — strict path + param check |
| V6 Cryptography | yes | Google Tink (AES-256-GCM) for token encryption — never hand-roll |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Custom URL scheme hijacking | Spoofing | Use App Links (HTTPS + autoVerify), not custom schemes |
| Stale token after reinstall | Tampering | Clear DataStore on first launch (same as iOS FirstLaunchCleanup) |
| Pair code replay | Tampering | Backend enforces single-use TTL — no client-side change needed |
| Deep link code parameter tampering | Tampering | PairCodeUriParser: strict path `/pair` + `code` param required |
| Token in logs | Info Disclosure | Never log access_token or refresh_token strings |
| SHA-256 mismatch in assetlinks.json | Spoofing | Serve both debug and release fingerprints during dev |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | LiveKit Android SDK v2 uses `room.events` Flow (not delegate callbacks) | Architecture Patterns | Low — verified in GitHub README, but exact RoomEvent class names need confirming against SDK source before implementation |
| A2 | `activeSpeakers` Flow correctly identifies agent speaking vs local participant | Code Examples | Medium — agent may need identity filtering; test needed |
| A3 | LiveKit's default AudioOptions achieves hardware AEC automatically on Android (analogous to iOS SDK managing AVAudioSession) | Don't Hand-Roll | Medium — unverified; default may only use software AEC on Android. Manual device test required. |
| A4 | DataStore + Tink API surface is stable in `datastore-preferences:1.1.1` (not alpha/beta) | Standard Stack | Low — DataStore 1.1 is stable; Tink 1.14 is stable |
| A5 | `io.livekit:livekit-android:2.25.1` compiles against minSdk 21 or lower (enabling Android 5+ coverage) | Standard Stack | Low — WebRTC libraries typically require minSdk 21; if higher, adjust |

---

## Open Questions

1. **Exact RoomEvent class names in LiveKit Android SDK v2.25.1**
   - What we know: `room.events` Flow emits typed events; README shows `RoomEvent.Connected`, `RoomEvent.Disconnected`
   - What's unclear: Exact sealed class hierarchy for disconnect-with-error vs clean disconnect; whether `ParticipantSpeakingChanged` is the correct event name
   - Recommendation: Read SDK source at `github.com/livekit/client-sdk-android` during Plan 02 before writing event collection code

2. **Minimum SDK version for LiveKit Android SDK**
   - What we know: Not documented in README, docs, or Maven Central page
   - What's unclear: Whether minSdk 21 (Android 5.0, 2014) or higher is required
   - Recommendation: Check `livekit/build.gradle` in the SDK GitHub repository during Plan 01

3. **Hardware AEC on Android: default vs override**
   - What we know: Custom `javaAudioDeviceModuleCustomizer` override has known issues (issues #600, #673); LiveKit default uses WebRTC AEC
   - What's unclear: Whether LiveKit default AudioOptions activates hardware AEC (via `AudioType.CallAudioType()`) on supported devices, or only software WebRTC AEC
   - Recommendation: Start with default. If echo is observed on device test, try `AudioType.CallAudioType()` which sets the audio stream to `STREAM_VOICE_CALL`, which Android routes through hardware AEC if available

4. **DataStore + Tink: exact encryption API**
   - What we know: `androidx.datastore:datastore-tink` artifact exists; `AeadSerializer` class provides Tink-backed encryption
   - What's unclear: Whether `datastore-tink` artifact is stable (may be alpha); exact API surface for `AeadSerializer`
   - Recommendation: If `datastore-tink` is still alpha/beta, use `EncryptedFile` from `security-crypto` for the token file instead (it wraps Tink under the hood). Alternatively, implement manual Tink AEAD encryption wrapping a plain DataStore.

---

## Sources

### Primary (HIGH confidence)
- [github.com/livekit/client-sdk-android](https://github.com/livekit/client-sdk-android) — SDK version, Gradle setup, room connect API, permissions, AudioOptions
- [central.sonatype.com/artifact/io.livekit/livekit-android](https://central.sonatype.com/artifact/io.livekit/livekit-android) — confirmed v2.25.1 latest (2026-04-28)
- [developer.android.com/training/app-links/add-applinks](https://developer.android.com/training/app-links/add-applinks) — App Links intent filter, autoVerify, assetlinks.json
- [developer.android.com/jetpack/androidx/releases/security](https://developer.android.com/jetpack/androidx/releases/security) — EncryptedSharedPreferences deprecation
- [developers.google.com/digital-asset-links](https://developers.google.com/digital-asset-links/v1/statements) — assetlinks.json format

### Secondary (MEDIUM confidence)
- [docs.livekit.io/transport/sdk-platforms/android/](https://docs.livekit.io/transport/sdk-platforms/android/) — quickstart, permissions, room connect pattern
- [docs.livekit.io/reference/client-sdk-android](https://docs.livekit.io/reference/client-sdk-android/livekit-android-sdk/io.livekit.android/-audio-options/index.html) — AudioOptions fields
- [docs.livekit.io/transport/media/noise-cancellation/](https://docs.livekit.io/transport/media/noise-cancellation/) — AEC/noise options (Krisp vs WebRTC default)
- [github.com/livekit/client-sdk-android/issues/600](https://github.com/livekit/client-sdk-android/issues/600) — hardware AEC override issues
- [proandroiddev.com — EncryptedSharedPreferences 2026 migration guide](https://proandroiddev.com/goodbye-encryptedsharedpreferences-a-2026-migration-guide-4b819b4a537a) — Tink + DataStore replacement pattern
- [mockk.io](https://mockk.io/) — MockK coroutine-aware mocking

### Tertiary (LOW confidence — flag for validation)
- WebSearch results on `javaAudioDeviceModuleCustomizer` — some example code found but not from official LiveKit docs
- AEC effectiveness on Android defaults — [ASSUMED] that default SDK behavior matches documentation intent

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — LiveKit version verified via Maven Central; DataStore + Tink deprecation verified via official Android docs
- Architecture: MEDIUM — Room Events Flow API pattern inferred from README; exact sealed class names need SDK source verification
- Pitfalls: HIGH — AEC override issues verified via open GitHub issues; deprecation verified via official docs
- Backend changes: HIGH — assetlinks.json format verified via Google Digital Asset Links docs

**Research date:** 2026-04-30
**Valid until:** 2026-05-30 (LiveKit SDK releases frequently; verify version before implementation)
