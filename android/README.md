# dAIly Android

Native Android (Kotlin + Jetpack Compose) client for the dAIly voice assistant.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Android Studio | Iguana (2023.2.1+) | Required for Compose tooling |
| JDK | 17 | Must match `compileOptions` in `app/build.gradle.kts` |
| Android SDK | API 34 | `compileSdk = 34`; install via SDK Manager in Android Studio |
| Gradle | 8.7 | Fetched automatically by the wrapper on first run |

## Build Commands

```bash
# Assemble debug APK
cd android
./gradlew assembleDebug

# Run unit tests
./gradlew testDebugUnitTest

# Run TokenStore tests specifically
./gradlew testDebugUnitTest --tests "com.daily.android.auth.TokenStoreTest"
```

### Gradle Wrapper Bootstrap

The Gradle wrapper (`gradlew`) is committed with the project. If it is missing on a fresh clone, bootstrap it once:

```bash
cd android
gradle wrapper --gradle-version 8.7
```

### Planning Machine Limitation

The planning machine does not have an Android SDK or Gradle installed. Build and test verification is deferred to a developer machine with Android Studio installed. All grep-based acceptance criteria pass on the planning machine. This mirrors the iOS Plan 19-02 deviation pattern (Xcode absent on planning machine).

## Token Storage

Tokens (`access_token`, `refresh_token`, `access_token_expires_at`) are stored via `TokenStore`:

- Encrypted at rest using **AES-256-GCM** (Google Tink)
- Master key lives in the **Android Keystore** (`android-keystore://tokenstore_master_key`)
- Plaintext is never written to disk
- File location: `filesDir/datastore/tokens.enc`
- Tokens are never logged, never passed to the LLM layer

## Project Structure

```
android/
├── settings.gradle.kts          # Project-level Gradle settings + JitPack repo
├── build.gradle.kts             # Root plugin declarations
├── gradle.properties            # JVM args, AndroidX flag
└── app/
    ├── build.gradle.kts         # Module deps: LiveKit 2.25.1, Compose BOM 2025.01.00,
    │                            #   DataStore 1.1.1, Tink 1.14.0
    └── src/
        ├── main/
        │   ├── AndroidManifest.xml  # RECORD_AUDIO + INTERNET; MainActivity singleTop
        │   └── kotlin/com/daily/android/
        │       ├── DailyApp.kt      # Application class — Tink AeadConfig.register()
        │       ├── MainActivity.kt  # Entry point (voice UI wired in Plan 20-04)
        │       ├── AppState.kt      # Reactive auth state (hasAccessToken StateFlow)
        │       └── auth/
        │           └── TokenStore.kt  # AES-256-GCM token storage via DataStore + Tink
        └── test/
            └── kotlin/com/daily/android/
                └── auth/
                    └── TokenStoreTest.kt  # 6 unit tests (Robolectric)
```

## Configuration

All backend wiring lives in `Config.kt`. Edit `backendBaseURL` for tunnel/prod; edit `Config.appLinksHost` AND `AndroidManifest.xml`'s `<data android:host=...>` together.

> **Warning:** When changing the backend host, you MUST update `Config.appLinksHost` AND the
> `android:host` literal in `AndroidManifest.xml` together — Android's manifest does not
> interpolate Kotlin constants. If they drift, App Links verification fails silently and the
> magic link opens in a browser instead of the app.

## Local dev with cloudflared

1. `cloudflared tunnel --url http://localhost:8000`
2. Paste the HTTPS URL into `Config.backendBaseURL` (e.g. `"https://abc123.trycloudflare.com"`)
3. Paste the host (without scheme) into `Config.appLinksHost` (e.g. `"abc123.trycloudflare.com"`) AND into `AndroidManifest.xml`'s `<data android:host="..."/>` literal
4. `curl https://<tunnel>/.well-known/assetlinks.json` to verify the Plan 20-01 endpoint is reachable
5. Reinstall the debug APK so Android re-runs App Links verification: `adb uninstall com.daily.android && ./gradlew installDebug`

## App Links debug verification

After installing, verify App Links are working:

```bash
adb shell pm verify-app-links --re-verify com.daily.android
adb shell pm get-app-links com.daily.android
# Look for: 1024:com.daily.android (verified)
```

## Key Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| `io.livekit:livekit-android` | 2.25.1 | Voice transport via WebRTC |
| `androidx.compose:compose-bom` | 2025.01.00 | Jetpack Compose UI |
| `androidx.datastore:datastore-preferences` | 1.1.1 | Async persistent storage (replaces SharedPreferences) |
| `com.google.crypto.tink:tink-android` | 1.14.0 | AES-256-GCM encryption |
| `org.robolectric:robolectric` | 4.13 | Android context simulation in JVM unit tests |

Note: `EncryptedSharedPreferences` is deprecated and is **not** used anywhere in this project.
JitPack is declared in `settings.gradle.kts` as required by the LiveKit Android SDK distribution.
