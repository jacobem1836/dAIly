import SwiftUI

/// Main voice interaction screen.
///
/// Auto VAD only (D-06) — the server drives turn detection. No PTT button in UI.
/// Debug mic mute lives behind `#if DEBUG && DebugFlags.pttEnabled` in VoiceSession (D-07).
struct VoiceView: View {
    @ObservedObject var session: VoiceSession
    @EnvironmentObject private var appState: AppState

    /// Sentinel error value VoiceSession sets when a 401 can only be resolved
    /// by re-pairing (refresh token rejected, or the refreshed token is still
    /// unauthorized). See VoiceSession.connect() doc comment.
    private static let rePairRequiredError = "re_pair_required"

    var body: some View {
        VStack(spacing: 32) {
            Text("dAIly")
                .font(.title3.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Spacer()
            ConnectionIndicator(state: session.state)
            if case .error(let msg) = session.state {
                errorMessage(msg)
            }
            actionButton
            Spacer()
        }
        .padding()
        // Dead-end fix: a re_pair_required error means Retry can never succeed
        // (the refresh token itself is invalid) — sign the user out so the app
        // root recomputes back to PairingView instead of leaving them stuck.
        .onChange(of: session.state) { newState in
            if case .error(let msg) = newState, msg == Self.rePairRequiredError {
                appState.signOut()
            }
        }
    }

    // MARK: - Error Message

    private func errorMessage(_ msg: String) -> some View {
        Text(displayText(for: msg))
            .font(.caption)
            .foregroundColor(.red)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 280)
    }

    private func displayText(for msg: String) -> String {
        if msg == Self.rePairRequiredError {
            return "Your session expired. Signing you out\u{2026}"
        }
        return String(msg.prefix(60))
    }

    // MARK: - Action Button

    @ViewBuilder
    private var actionButton: some View {
        switch session.state {
        case .idle:
            Button("Start") {
                Task { try? await session.connect() }
            }
            .buttonStyle(.borderedProminent)

        case .error(let msg) where msg == Self.rePairRequiredError:
            // No Retry here — retrying would fail forever since the refresh
            // token itself was rejected. onChange above already triggers
            // sign-out; show progress instead of a dead-end button.
            ProgressView()

        case .error:
            Button("Retry") {
                Task { try? await session.connect() }
            }
            .buttonStyle(.borderedProminent)
            .tint(.red)

        case .connecting, .listening, .speaking, .reconnecting:
            Button("End") {
                Task { await session.disconnect() }
            }
            .buttonStyle(.bordered)
        }
    }
}
