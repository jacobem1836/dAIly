import SwiftUI

/// Tab 0 of the onboarding TabView — branded entry point shown before
/// email/magic-link auth (D-07). Tapping "Get started" advances the parent
/// TabView selection to tab 1 via the onContinue callback (D-08).
struct WelcomeView: View {
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: "waveform")
                .font(.system(size: 64))
                .foregroundStyle(.primary)

            Text("dAIly")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("Your AI daily briefing, every morning.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Spacer()

            Button("Get started", action: onContinue)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding()
    }
}

#Preview {
    WelcomeView(onContinue: {})
}
