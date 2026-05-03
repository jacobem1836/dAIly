import Foundation
import Combine

/// Ephemeral onboarding session state — tracks which OAuth providers have
/// successfully connected during this onboarding run (D-11, D-12).
///
/// Lifted into dAIlyApp as @StateObject and injected via .environmentObject so
/// that both OnboardingView and dAIlyApp.onOpenURL can mutate it (the deep-link
/// callback /oauth/success?provider= must call markConnected from the App level).
final class IntegrationState: ObservableObject {
    /// Set of provider raw values that have completed OAuth this session.
    /// Values: "google", "microsoft", "slack".
    @Published var connectedProviders: Set<String> = []

    /// D-12 gate: at least one provider must be connected before user can
    /// advance past the Slack page (last integration page).
    var atLeastOneConnected: Bool { !connectedProviders.isEmpty }

    /// Called by dAIlyApp.onOpenURL when /oauth/success?provider= is received.
    func markConnected(provider: String) {
        connectedProviders.insert(provider)
    }

    func isConnected(_ provider: IntegrationProvider) -> Bool {
        connectedProviders.contains(provider.rawValue)
    }
}
