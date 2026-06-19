import SwiftUI

/// Main voice interaction screen.
///
/// Auto VAD only (D-06) — the server drives turn detection. No PTT button in UI.
/// Debug mic mute lives behind `#if DEBUG && DebugFlags.pttEnabled` in VoiceSession (D-07).
struct VoiceView: View {
    @ObservedObject var session: VoiceSession

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
            } else if case .retryable(let msg) = session.state {
                errorMessage(msg)
            }
            actionButton
            Spacer()
        }
        .padding()
    }

    // MARK: - Error Message

    private func errorMessage(_ msg: String) -> some View {
        Text(String(msg.prefix(60)))
            .font(.caption)
            .foregroundColor(.red)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 280)
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

        case .error:
            Button("Retry") {
                Task { try? await session.connect() }
            }
            .buttonStyle(.borderedProminent)
            .tint(.red)

        case .retryable:
            Button("Retry") {
                Task { await session.retry() }
            }
            .buttonStyle(.borderedProminent)

        case .connecting, .listening, .speaking, .reconnecting:
            Button("End") {
                Task { await session.disconnect() }
            }
            .buttonStyle(.bordered)
        }
    }
}
