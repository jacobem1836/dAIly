import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var integrationState = IntegrationState()
    @StateObject private var voiceSession = VoiceSession(
        tokenSource: LiveKitTokenSource(baseURL: Config.backendBaseURL),
        auth: AuthService(baseURL: Config.backendBaseURL)
    )

    private let auth = AuthService(baseURL: Config.backendBaseURL)

    init() {
        FirstLaunchCleanup.runIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                // D-05: use rootRoute computed property on AppState for clean routing.
                // hasAccessToken && hasCompletedOnboarding → VoiceView; else OnboardingView.
                switch appState.rootRoute {
                case .voice:
                    VoiceView(session: voiceSession)
                case .pairing, .onboarding:
                    OnboardingView(auth: auth)
                }
            }
            .environmentObject(appState)
            .environmentObject(integrationState)
            .onOpenURL { url in
                handleDeepLink(url)
            }
            .onReceive(NotificationCenter.default.publisher(for: .oauthCallbackReceived)) { notification in
                if let url = notification.object as? URL {
                    handleDeepLink(url)
                }
            }
        }
    }

    /// Handles Universal Links delivered to the app while running.
    /// Delegates to AppState.handleDeepLink for testability.
    @MainActor
    private func handleDeepLink(_ url: URL) {
        appState.handleDeepLink(url, integrationState: integrationState) { code in
            Task { @MainActor in
                do {
                    _ = try await auth.completePairing(code: code)
                    appState.hasAccessToken = true
                    UIApplication.shared.sendAction(
                        #selector(UIResponder.resignFirstResponder),
                        to: nil, from: nil, for: nil
                    )
                } catch {
                    print("[dAIly] pair complete failed: \(error)")
                }
            }
        }
    }
}
