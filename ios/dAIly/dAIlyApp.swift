import SwiftUI
import LiveKit

@main
struct dAIlyApp: App {
    @StateObject private var appState = AppState()

    init() {
        FirstLaunchCleanup.runIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            Text("dAIly")
                .environmentObject(appState)
                .onOpenURL { url in
                    // Universal Link handler implemented in Task 3 (Plan 03)
                    print("[dAIly] received URL: \(url)")
                }
        }
    }
}
