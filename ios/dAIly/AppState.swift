import Foundation
import Combine

final class AppState: ObservableObject {
    @Published var isAuthenticated: Bool = false

    /// True when an access token is currently stored in the Keychain.
    /// Used to decide whether to show PairingView or the main voice screen.
    @Published var hasAccessToken: Bool

    init(keychain: KeychainStore = .shared) {
        self.hasAccessToken = keychain.load(key: "access_token") != nil
    }
}
