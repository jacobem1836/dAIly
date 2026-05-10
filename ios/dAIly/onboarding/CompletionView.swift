import SwiftUI

/// Tab 6 of the onboarding TabView — final confirmation screen (D-17).
/// Summarises briefing time + connected providers. Tapping "Start talking
/// to dAIly" triggers on-demand briefing generation (D-04) via
/// AuthService.triggerBriefing(), then calls onFinish which sets
/// appState.hasCompletedOnboarding = true in OnboardingView, transitioning
/// the app root to VoiceView (D-18).
struct CompletionView: View {
    let auth: AuthService
    @ObservedObject var integrationState: IntegrationState
    let briefingTime: Date
    let onFinish: () -> Void

    @State private var isGeneratingBriefing: Bool = false
    @State private var briefingError: String? = nil

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

            if isGeneratingBriefing {
                ProgressView("Generating your first briefing...")
                    .progressViewStyle(.circular)
                    .controlSize(.large)
            } else {
                Button("Start talking to dAIly") {
                    Task {
                        isGeneratingBriefing = true
                        briefingError = nil
                        do {
                            try await auth.triggerBriefing()
                            onFinish()
                        } catch {
                            briefingError = "Couldn't generate your first briefing. Tap to try again."
                            isGeneratingBriefing = false
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }

            if let errorMessage = briefingError {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
        .padding(.bottom, 40)
    }
}

#Preview {
    CompletionView(
        auth: AuthService(baseURL: URL(string: "http://localhost:8000")!),
        integrationState: IntegrationState(),
        briefingTime: Calendar.current.date(bySettingHour: 7, minute: 0, second: 0, of: Date())!,
        onFinish: {}
    )
}
