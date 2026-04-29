import SwiftUI

/// Main voice interaction screen.
///
/// Auto VAD only (D-06) — the server drives turn detection. No PTT button in UI.
/// Debug mic mute lives behind `#if DEBUG && DebugFlags.pttEnabled` in VoiceSession (D-07).
struct VoiceView: View {
    @ObservedObject var session: VoiceSession

    var body: some View {
        VStack(spacing: 32) {
            Spacer()
            ConnectionIndicator(state: session.state)
            actionButton
            Spacer()
        }
        .padding()
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

        case .connecting, .listening, .speaking, .reconnecting:
            Button("End") {
                Task { await session.disconnect() }
            }
            .buttonStyle(.bordered)
        }
    }
}
