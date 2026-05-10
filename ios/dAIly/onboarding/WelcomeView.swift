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
                .font(.system(size: 72))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(.tint)

            Text("dAIly")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("Your AI daily briefing, every morning.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)
                .padding(.horizontal)

            Spacer()

            Button("Get started", action: onContinue)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
        .padding()
        .padding(.bottom, 40)
    }
}

#Preview {
    WelcomeView(onContinue: {})
}
