import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()
    var body: some Scene {
        WindowGroup {
            Text("dAIly")
                .environmentObject(appState)
                .onOpenURL { url in
                    // Universal Link handler implemented in Plan 03
                    print("[dAIly] received URL: \(url)")
                }
        }
    }
}
