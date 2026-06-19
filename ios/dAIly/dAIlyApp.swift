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
    // scenePhase: observe app lifecycle transitions for graceful session pause/reconnect.
    // handleBackground() tears down the LiveKit room and sets shouldResume = true.
    // handleForeground() reconnects (via connect() backoff path) if shouldResume is set.
    @Environment(\.scenePhase) private var scenePhase

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
        .onChange(of: scenePhase) { newPhase in
            switch newPhase {
            case .background:
                // Gracefully tear down the LiveKit room and record that a session was live.
                // Cancels in-flight reconnect timers so they cannot fire while suspended.
                Task { @MainActor in
                    await voiceSession.handleBackground()
                }
            case .active:
                // Reconnect if a session was live before backgrounding.
                // Delegates to the existing connect() path which includes backoff token refresh.
                Task { @MainActor in
                    await voiceSession.handleForeground()
                }
            case .inactive:
                // App is transitioning (e.g. lock screen overlay, notification drawer).
                // Do nothing — wait for .background or .active to be definitive.
                break
            @unknown default:
                break
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
