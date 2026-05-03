import SwiftUI

/// Tab 6 of the onboarding TabView — final confirmation screen (D-17).
/// Summarises briefing time + connected providers. Tapping "Start talking
/// to dAIly" calls onFinish, which sets appState.hasCompletedOnboarding
/// = true in the parent OnboardingView, transitioning the app root to
/// VoiceView (D-18).
struct CompletionView: View {
    @ObservedObject var integrationState: IntegrationState
    let briefingTime: Date
    let onFinish: () -> Void

    private var formattedTime: String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter.string(from: briefingTime)
    }

    /// Sorted list of connected provider display names so the order in the
    /// summary is stable across renders (Set iteration order is undefined).
    private var connectedProvidersDisplay: [String] {
        IntegrationProvider.allCases
            .filter { integrationState.isConnected($0) }
            .map(\.displayName)
    }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 72))
                .foregroundStyle(.green)

            Text("You're all set")
                .font(.largeTitle)
                .fontWeight(.bold)

            VStack(alignment: .leading, spacing: 12) {
                Label("Briefing at \(formattedTime)", systemImage: "alarm")

                ForEach(connectedProvidersDisplay, id: \.self) { name in
                    Label("\(name) connected", systemImage: "checkmark.circle")
                }
            }
            .font(.body)
            .foregroundStyle(.secondary)

            Spacer()

            Button("Start talking to dAIly", action: onFinish)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding()
    }
}

#Preview {
    let state = IntegrationState()
    state.markConnected(provider: "google")
    return CompletionView(
        integrationState: state,
        briefingTime: Calendar.current.date(bySettingHour: 7, minute: 0, second: 0, of: Date())!,
        onFinish: {}
    )
}
