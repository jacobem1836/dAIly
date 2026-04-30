import SwiftUI

/// Visual indicator for the current VoiceSessionState.
/// Renders a coloured circle with a label — minimal, functional, per D-10.
struct ConnectionIndicator: View {
    let state: VoiceSessionState

    var body: some View {
        VStack(spacing: 12) {
            Circle()
                .fill(circleColor)
                .frame(width: 72, height: 72)
                .overlay(
                    Circle()
                        .stroke(circleColor.opacity(0.3), lineWidth: 6)
                        .scaleEffect(pulseActive ? 1.4 : 1.0)
                        .animation(
                            pulseActive
                                ? .easeInOut(duration: 0.9).repeatForever(autoreverses: true)
                                : .default,
                            value: pulseActive
                        )
                )
            Text(label)
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 200)
        }
    }

    // MARK: - Derived Properties

    private var circleColor: Color {
        switch state {
        case .idle:         return Color(.systemGray4)
        case .connecting,
             .reconnecting: return .yellow
        case .listening:    return .green
        case .speaking:     return .blue
        case .error:        return .red
        }
    }

    private var label: String {
        switch state {
        case .idle:          return "Tap to start"
        case .connecting:    return "Connecting\u{2026}"
        case .reconnecting:  return "Reconnecting\u{2026}"
        case .listening:     return "Listening"
        case .speaking:      return "Speaking"
        case .error(let msg):
            let display = msg.count > 40 ? String(msg.prefix(40)) + "\u{2026}" : msg
            return "Error: \(display)\nTap Retry to reconnect."
        }
    }

    private var pulseActive: Bool {
        switch state {
        case .connecting, .reconnecting: return true
        default: return false
        }
    }
}
