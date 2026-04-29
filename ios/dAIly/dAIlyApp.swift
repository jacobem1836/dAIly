import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()

    // NOTE: Replace this placeholder with your actual backend URL before TestFlight.
    // For local development, use an HTTPS tunnel URL (e.g. ngrok or Cloudflare Tunnel).
    // See ios/README.md for setup instructions.
    private let auth = AuthService(baseURL: URL(string: "https://app.example.com")!)

    init() {
        FirstLaunchCleanup.runIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.hasAccessToken {
                    VoiceView(session: VoiceSession(
                        tokenSource: LiveKitTokenSource(
                            baseURL: URL(string: "https://app.example.com")!
                        ),
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
