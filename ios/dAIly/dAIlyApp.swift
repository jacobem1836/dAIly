import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()

    private let auth = AuthService(baseURL: Config.backendBaseURL)

    init() {
        FirstLaunchCleanup.runIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.hasAccessToken {
                    VoiceView(session: VoiceSession(
                        tokenSource: LiveKitTokenSource(baseURL: Config.backendBaseURL),
                        auth: auth
                    ))
                } else {
                    PairingView(auth: auth)
                }
            }
            .environmentObject(appState)
            .onOpenURL { url in
                guard let code = PairCodeURLParser.extractPairCode(from: url) else { return }
                Task { @MainActor in
                    do {
                        _ = try await auth.completePairing(code: code)
                        appState.hasAccessToken = true
                    } catch {
                        // Plan 05 wires a user-visible error alert; for now log only
                        print("[dAIly] pair complete failed: \(error)")
                    }
                }
            }
        }
    }
}
