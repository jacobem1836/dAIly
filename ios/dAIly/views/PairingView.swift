import SwiftUI

/// Two-state pairing view: email entry → "check your email" confirmation.
struct PairingView: View {
    private enum PairingState {
        case idle
        case sent
    }

    private let auth: AuthService
    @State private var email: String = ""
    @State private var state: PairingState = .idle

    init(auth: AuthService) {
        self.auth = auth
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

    // MARK: - Sent state: confirmation + reset option

    private var sentView: some View {
        VStack(spacing: 16) {
            Image(systemName: "envelope.open")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("Check your email")
                .font(.title2)
                .fontWeight(.semibold)

            Text("We sent a magic link to \(email).\nTap the link in your email to continue.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            Button("Use a different email") {
                email = ""
                state = .idle
            }
            .buttonStyle(.borderless)
        }
    }
}
