import Foundation
import Combine

// MARK: - RootRoute

/// Top-level screen the app should display.
/// Computed from auth and onboarding state.
enum RootRoute: Equatable {
    case pairing
    case onboarding
    case voice
}

// MARK: - AppState

@MainActor
final class AppState: ObservableObject {
    @Published var isAuthenticated: Bool = false

    /// True when an access token is currently stored in the Keychain.
    /// Used to decide whether to show PairingView or the main voice screen.
    @Published var hasAccessToken: Bool

    /// True when the user has completed the onboarding flow (welcome → pairing →
    /// integration connect → schedule). Persisted via Keychain key `onboarding_complete`
    /// (D-04). Drives root routing: hasAccessToken && hasCompletedOnboarding → VoiceView.
    @Published var hasCompletedOnboarding: Bool

    private let keychain: KeychainStore

    init(keychain: KeychainStore = .shared) {
        self.keychain = keychain
        self.hasAccessToken = keychain.load(key: "access_token") != nil
        self.hasCompletedOnboarding = keychain.load(key: "onboarding_complete") != nil
    }

    // MARK: - Root Route

    /// Resolves which root screen should be shown based on current state.
    var rootRoute: RootRoute {
        guard hasAccessToken else { return .pairing }
        guard hasCompletedOnboarding else { return .onboarding }
        return .voice
    }

    // MARK: - Deep Link Handling

    /// Handles Universal Links and custom-scheme URLs.
    /// Two shapes are supported:
    ///   - /pair?code=...           → pair-code completion (delegates to auth)
    ///   - /oauth/success?provider= → integration connect success
    ///
    /// Returns true if the URL was handled, false if it was not recognised.
    @discardableResult
    func handleDeepLink(
        _ url: URL,
        integrationState: IntegrationState,
        pairCompletion: ((String) -> Void)? = nil
    ) -> Bool {
        // Branch 1: pair code
        if let code = PairCodeURLParser.extractPairCode(from: url) {
            pairCompletion?(code)
            return true
        }

        // Branch 2: OAuth success — validate provider against IntegrationProvider
        if let providerRaw = OAuthCallbackParser.extractProvider(from: url),
           IntegrationProvider(rawValue: providerRaw) != nil {
            integrationState.markConnected(provider: providerRaw)
            return true
        }

        return false
    }

    // MARK: - Sign Out

    /// Clears all auth tokens and resets auth state.
    func signOut() {
        try? keychain.delete(key: "access_token")
        try? keychain.delete(key: "refresh_token")
        try? keychain.delete(key: "access_token_expires_at")
        try? keychain.delete(key: "onboarding_complete")
        hasAccessToken = false
        hasCompletedOnboarding = false
    }
}
