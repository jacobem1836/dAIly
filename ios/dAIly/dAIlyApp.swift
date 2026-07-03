import SwiftUI
import LiveKit
import os

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var integrationState = IntegrationState()
    @StateObject private var voiceSession = VoiceSession(
        tokenSource: LiveKitTokenSource(baseURL: Config.backendBaseURL),
        auth: AuthService(baseURL: Config.backendBaseURL)
    )

    private let auth = AuthService(baseURL: Config.backendBaseURL)
    private let tokenRefresher: TokenRefresher

    @Environment(\.scenePhase) private var scenePhase

    private static let logger = Logger(subsystem: "com.jacobmarriott.daily", category: "app")

    init() {
        FirstLaunchCleanup.runIfNeeded()
        tokenRefresher = TokenRefresher(auth: auth)
        MetricsReporter.shared.start()
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
        // Proactively refresh the access token whenever the app returns to the
        // foreground, so a returning user pays the (cheap) proactive refresh
        // path instead of the full reactive backoff on their first tap.
        .onChange(of: scenePhase) { newPhase in
            guard newPhase == .active else { return }
            Task { @MainActor in
                do {
                    try await tokenRefresher.refreshIfNeeded()
                } catch {
                    Self.logger.notice("Proactive token refresh skipped/failed: \(String(describing: error), privacy: .public)")
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
                    Self.logger.error("Pair complete failed: \(String(describing: error), privacy: .public)")
                }
            }
        }
    }
}
