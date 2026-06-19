import Foundation

// MARK: - RefreshBackoff

/// Exponential-backoff constants and retry logic for token refresh.
///
/// Retry schedule (3 attempts):
///   Attempt 1 — immediate
///   Attempt 2 — wait 0.5 s
///   Attempt 3 — wait 1.0 s
///   (terminal failure after attempt 3)
///
/// Total worst-case wait before declaring transient failure: ~1.5 s.
/// Hard 401 (invalid refresh token) throws immediately without retrying.
public enum RefreshBackoff {
    /// Delays in nanoseconds before each retry attempt (not including the first immediate attempt).
    /// Index 0 = delay before attempt 2, index 1 = delay before attempt 3.
    public static let retryDelaysNs: [UInt64] = [
        500_000_000,   // 0.5 s
        1_000_000_000  // 1.0 s
    ]

    /// Maximum number of attempts (1 initial + retryDelaysNs.count retries).
    public static let maxAttempts: Int = retryDelaysNs.count + 1  // 3

    /// Retry `auth.refresh()` with exponential backoff.
    ///
    /// - Throws `AuthError.unauthorized` immediately when the refresh token itself is
    ///   invalid (hard 401). Callers should treat this as a terminal failure requiring re-pair.
    /// - Throws the last transient error when all attempts are exhausted. Callers should
    ///   offer a user-facing retry affordance rather than treating this as terminal.
    public static func refreshWithBackoff(_ auth: AuthService) async throws {
        var lastError: Error?
        for attempt in 0..<maxAttempts {
            do {
                try await auth.refresh()
                return  // success
            } catch AuthError.unauthorized {
                // Hard 401: refresh token is invalid — escalate immediately, no retries.
                throw AuthError.unauthorized
            } catch {
                lastError = error
                // Not the last attempt — wait before retrying
                if attempt < maxAttempts - 1 {
                    try? await Task.sleep(nanoseconds: retryDelaysNs[attempt])
                }
            }
        }
        throw lastError ?? AuthError.network("refresh_backoff_exhausted")
    }
}

// MARK: - TokenRefresher

/// Proactively refreshes the access token before it expires.
/// Call `refreshIfNeeded()` on app foreground or before making authenticated requests.
/// Uses `RefreshBackoff.refreshWithBackoff` for resilience against transient network failures.
@MainActor
public final class TokenRefresher {
    private let auth: AuthService
    private let keychain: KeychainStore
    private let earlyRefreshSeconds: TimeInterval

    public init(auth: AuthService,
                keychain: KeychainStore = .shared,
                earlyRefreshSeconds: TimeInterval = 300) {
        self.auth = auth
        self.keychain = keychain
        self.earlyRefreshSeconds = earlyRefreshSeconds
    }

    /// Refresh the access token if it is missing or within `earlyRefreshSeconds` of expiry.
    /// Uses exponential backoff — see `RefreshBackoff`.
    public func refreshIfNeeded() async throws {
        guard let expiryStr = keychain.load(key: "access_token_expires_at"),
              let expiry = ISO8601DateFormatter().date(from: expiryStr) else {
            // No expiry stored — refresh unconditionally
            try await RefreshBackoff.refreshWithBackoff(auth)
            return
        }
        if expiry.timeIntervalSinceNow < earlyRefreshSeconds {
            try await RefreshBackoff.refreshWithBackoff(auth)
        }
    }
}

// MARK: - First-Launch Keychain Cleanup

/// Clears Keychain tokens on the first launch after a fresh install.
/// Prevents stale tokens from a previous install being reused (T-19-15).
public enum FirstLaunchCleanup {
    private static let hasLaunchedKey = "com.daily.ios.hasLaunchedBefore"

    public static func runIfNeeded(keychain: KeychainStore = .shared,
                                   defaults: UserDefaults = .standard) {
        if !defaults.bool(forKey: hasLaunchedKey) {
            try? keychain.clearAll()
            defaults.set(true, forKey: hasLaunchedKey)
        }
    }
}
