import SwiftUI

/// Tabs 2–4 of the onboarding TabView — one instance per provider (D-09):
/// Google, Microsoft, Slack. Shows provider name + data description + Connect
/// button + Skip option (D-10). On successful connection (signalled via
/// IntegrationState.markConnected from dAIlyApp.onOpenURL), the Connect
/// button is replaced with a green checkmark and a Continue button (D-11).
///
/// Skip visibility (D-12): on the last integration page (Slack), Skip is
/// hidden until at least one provider has connected — the user must connect
/// at least one before advancing past Slack.
struct IntegrationView: View {
    let provider: IntegrationProvider
    let auth: AuthService
    @ObservedObject var integrationState: IntegrationState
    let isLastIntegrationPage: Bool
    let onContinue: () -> Void

    @State private var isConnecting: Bool = false
    @State private var errorMessage: String? = nil

    private var isConnected: Bool {
        integrationState.isConnected(provider)
    }

    /// D-12: Skip is always available except on the last integration page
    /// (Slack), where it is hidden until at least one provider is connected.
    private var canSkip: Bool {
        !isLastIntegrationPage || integrationState.atLeastOneConnected
    }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: provider.icon)
                .font(.system(size: 56))
                .foregroundStyle(.primary)

            Text("Connect \(provider.displayName)")
                .font(.title2)
                .fontWeight(.semibold)

            Text(provider.description)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            if isConnected {
                connectedSection
            } else {
                disconnectedSection
            }

            Spacer()
        }
        .padding()
        .padding(.bottom, 40)
        // When a deep link (/oauth/success) arrives, dAIlyApp.onOpenURL calls
        // integrationState.markConnected, which fires this observer. Clear any
        // residual isConnecting state and error so the connected UI renders.
        // Uses single-argument onChange for iOS 16 deployment target compatibility.
        .onChange(of: integrationState.connectedProviders) { newValue in
            if newValue.contains(provider.rawValue) {
                isConnecting = false
                errorMessage = nil
            }
        }
    }

    @ViewBuilder
    private var connectedSection: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
            Text("Connected")
                .foregroundStyle(.secondary)
        }
        .font(.body)

        Button("Continue", action: onContinue)
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
    }

    @ViewBuilder
    private var disconnectedSection: some View {
        if let error = errorMessage {
            Text(error)
                .foregroundStyle(.red)
                .font(.caption)
                .multilineTextAlignment(.center)
        }

        Button(isConnecting ? "Connecting…" : "Connect \(provider.displayName)") {
            Task { await connect() }
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(isConnecting)

        if canSkip {
            Button("Skip", action: onContinue)
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
        }
    }

    @MainActor
    private func connect() async {
        isConnecting = true
        errorMessage = nil
        do {
            let authURL = try await auth.getIntegrationConnectURL(provider: provider.rawValue)
            try auth.openOAuthSession(url: authURL)
            // Reset isConnecting after the session launches. If a deep link
            // arrives (/oauth/success), the .onChange on connectedProviders
            // handles marking the provider connected. If no deep link arrives
            // (e.g. personal dev team with no Universal Links configured), the
            // button resets so the user can retry or tap Skip.
            isConnecting = false
        } catch {
            errorMessage = "Connection failed. Please try again."
            isConnecting = false
        }
    }
}

#Preview {
    IntegrationView(
        provider: .google,
        auth: AuthService(baseURL: URL(string: "https://example.com")!),
        integrationState: IntegrationState(),
        isLastIntegrationPage: false,
        onContinue: {}
    )
}
