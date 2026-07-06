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
    @State private var isSendingLink: Bool = false
    @State private var sendLinkError: String? = nil

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
        .padding(.bottom, 40)
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

            if let sendLinkError {
                Text(sendLinkError)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
            }

            Button(isSendingLink ? "Sending\u{2026}" : "Send link") {
                Task { await sendLink() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!email.contains("@") || isSendingLink)
        }
    }

    private func sendLink() async {
        isSendingLink = true
        sendLinkError = nil
        do {
            try await auth.sendLink(email: email)
            state = .sent
        } catch {
            sendLinkError = "Couldn't send the link. Check your connection and try again."
        }
        isSendingLink = false
    }

    // MARK: - Sent state: confirmation + manual code entry

    private var sentView: some View {
        VStack(spacing: 16) {
            Image(systemName: "envelope.open")
                .font(.system(size: 56))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(.tint)

            Text("Check your email")
                .font(.title2)
                .fontWeight(.semibold)

            Text("We sent a link to \(email).\nTap the link or enter the 6-digit code below.")
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
                .onChange(of: code) { newValue in
                    if newValue.count == 6 {
                        UIApplication.shared.sendAction(
                            #selector(UIResponder.resignFirstResponder),
                            to: nil, from: nil, for: nil
                        )
                    }
                }

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
