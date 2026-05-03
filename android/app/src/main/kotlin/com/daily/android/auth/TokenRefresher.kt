package com.daily.android.auth

import java.time.Duration
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Proactively refreshes the access token before it expires.
 *
 * Checks the stored expiry timestamp and calls [AuthService.refresh] if the
 * token will expire within [earlyRefresh] (default 5 minutes).
 *
 * Called at app startup and before any API call that requires a valid token.
 */
class TokenRefresher(
    private val auth: AuthService,
    private val tokenStore: TokenStore,
    private val earlyRefresh: Duration = Duration.ofSeconds(300),
) {
    suspend fun refreshIfNeeded() {
        val expiryStr = tokenStore.load("access_token_expires_at")
        val expiry = expiryStr?.let {
            try {
                Instant.from(DateTimeFormatter.ISO_INSTANT.parse(it))
            } catch (_: Exception) {
                null
            }
        }
        // Refresh if no expiry stored, or if expiry is within earlyRefresh window
        if (expiry == null || Instant.now().plus(earlyRefresh).isAfter(expiry)) {
            auth.refresh()
        }
    }
}
