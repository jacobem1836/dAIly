import SwiftUI

/// Two-state pairing view: email entry → "check your email" confirmation.
struct PairingView: View {
    private enum PairingState {
        case idle
        case sent
    }

    private let auth: AuthService
    private let onComplete: () -> Void
    @EnvironmentObject private var appState: AppState
    @State private var email: String = ""
    @State private var state: PairingState = .idle
    @State private var code: String = ""
    @State private var errorMessage: String? = nil
    @State private var isVerifying: Bool = false

    init(auth: AuthService, onComplete: @escaping () -> Void) {
        self.auth = auth
        self.onComplete = onComplete
    }

    var body: some View {
        VStack(spacing: 24) {
            switch state {
            case .idle:
                idleView
            case .sent:
                sentView
            }
        }
        .padding()
    }

    // MARK: - Idle state: email entry + send button

    private var idleView: some View {
        VStack(spacing: 16) {
            Text("Sign in to dAIly")
                .font(.title2)
                .fontWeight(.semibold)

            TextField("Email", text: $email)
                .keyboardType(.emailAddress)
                .autocapitalization(.none)
                .textContentType(.emailAddress)
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(10)

            Button("Send magic link") {
                Task {
                    try? await auth.sendLink(email: email)
                    state = .sent
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!email.contains("@"))
        }
    }

    // MARK: - Sent state: confirmation + manual code entry

    private var sentView: some View {
        VStack(spacing: 16) {
            Image(systemName: "envelope.open")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("Check your email")
                .font(.title2)
                .fontWeight(.semibold)

            Text("We sent a magic link to \(email).\nTap the link or enter the 6-digit code below.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            TextField("6-digit code", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .multilineTextAlignment(.center)
                .font(.title.monospacedDigit())
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(10)

            if let error = errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
            }

            Button(isVerifying ? "Verifying…" : "Verify code") {
                Task { await verifyCode() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(code.count != 6 || isVerifying)

            Button("Use a different email") {
                email = ""
                code = ""
                errorMessage = nil
                state = .idle
            }
            .buttonStyle(.borderless)
        }
    }

    private func verifyCode() async {
        isVerifying = true
        errorMessage = nil
        do {
            _ = try await auth.completePairing(code: code)
            appState.hasAccessToken = true
            isVerifying = false
            onComplete()
        } catch {
            errorMessage = "Invalid or expired code. Try again."
            isVerifying = false
        }
    }
}
