package com.daily.android

object Config {
    /// Single source of truth for the backend host.
    /// Local dev: HTTPS tunnel (cloudflared / ngrok).
    /// Production: deployed FastAPI URL before Play Store.
    const val backendBaseURL: String = "https://app.example.com"

    /// Hostname for App Links autoVerify. Must match the host in
    /// AndroidManifest.xml `<data android:host="..."/>` AND the host
    /// serving /.well-known/assetlinks.json (Plan 20-01).
    const val appLinksHost: String = "app.example.com"
}
