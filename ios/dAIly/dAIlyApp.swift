import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var integrationState = IntegrationState()

    private let auth = AuthService(baseURL: Config.backendBaseURL)

    init() {
        FirstLaunchCleanup.runIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                // D-05: only route to VoiceView once both auth AND onboarding
                // are complete. Any other state shows the OnboardingView,
                // which itself starts at the correct tab via its gate logic
                // (tab 0 always; PairingView at tab 1 if not authed yet).
                if appState.hasAccessToken && appState.hasCompletedOnboarding {
                    VoiceView(session: VoiceSession(
                        tokenSource: LiveKitTokenSource(baseURL: Config.backendBaseURL),
                        auth: auth
                    ))
                } else {
                    OnboardingView(auth: auth)
                }
            }
            .environmentObject(appState)
            .environmentObject(integrationState)
            .onOpenURL { url in
                handleDeepLink(url)
            }
        }
    }

    /// Handles Universal Links delivered to the app while running.
    /// Two shapes are supported:
    ///   - /pair?code=...           → pair-code completion (existing)
    ///   - /oauth/success?provider= → integration connect success (new, D-13)
    @MainActor
    private func handleDeepLink(_ url: URL) {
        // Branch 1: pair code (existing behavior preserved verbatim).
        if let code = PairCodeURLParser.extractPairCode(from: url) {
            Task { @MainActor in
                do {
                    _ = try await auth.completePairing(code: code)
                    appState.hasAccessToken = true
                } catch {
                    print("[dAIly] pair complete failed: \(error)")
                }
            }
            return
        }

        // Branch 2: OAuth success (new). Validate the provider rawValue
        // against IntegrationProvider so a malformed query string can't
        // mark an arbitrary string as "connected" (T-21.1-04-01).
        if let providerRaw = OAuthCallbackParser.extractProvider(from: url),
           IntegrationProvider(rawValue: providerRaw) != nil {
            integrationState.markConnected(provider: providerRaw)
        }
    }
}
