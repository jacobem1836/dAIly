import Foundation
import Combine

final class AppState: ObservableObject {
    @Published var isAuthenticated: Bool = false

    /// True when an access token is currently stored in the Keychain.
    /// Used to decide whether to show PairingView or the main voice screen.
    @Published var hasAccessToken: Bool

    /// True when the user has completed the onboarding flow (welcome → pairing →
    /// integration connect → schedule). Persisted via Keychain key `onboarding_complete`
    /// (D-04). Drives root routing: hasAccessToken && hasCompletedOnboarding → VoiceView.
    @Published var hasCompletedOnboarding: Bool

    init(keychain: KeychainStore = .shared) {
        self.hasAccessToken = keychain.load(key: "access_token") != nil
        self.hasCompletedOnboarding = keychain.load(key: "onboarding_complete") != nil
    }
}
