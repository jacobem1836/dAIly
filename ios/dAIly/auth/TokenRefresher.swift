import Foundation

// MARK: - TokenRefresher

/// Proactively refreshes the access token before it expires.
/// Call `refreshIfNeeded()` on app foreground or before making authenticated requests.
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
    public func refreshIfNeeded() async throws {
        guard let expiryStr = keychain.load(key: "access_token_expires_at"),
              let expiry = ISO8601DateFormatter().date(from: expiryStr) else {
            // No expiry stored — refresh unconditionally
            try await auth.refresh()
            return
        }
        if expiry.timeIntervalSinceNow < earlyRefreshSeconds {
            try await auth.refresh()
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
