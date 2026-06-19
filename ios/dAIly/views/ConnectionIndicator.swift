import SwiftUI

/// Visual indicator for the current VoiceSessionState.
/// Renders a layered circle indicator with a label — 21.3 visual polish.
struct ConnectionIndicator: View {
    let state: VoiceSessionState

    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                // Ambient outer ring — always present, faint, adds depth.
                Circle()
                    .stroke(circleColor.opacity(0.12), lineWidth: 2)
                    .frame(width: 144, height: 144)

                // Pulse ring — animates outward when connecting/reconnecting.
                Circle()
                    .stroke(circleColor.opacity(0.28), lineWidth: 8)
                    .frame(width: 96, height: 96)
                    .scaleEffect(pulseActive ? 1.4 : 1.0)
                    .animation(
                        pulseActive
                            ? .easeInOut(duration: 0.9).repeatForever(autoreverses: true)
                            : .default,
                        value: pulseActive
                    )

                // Main circle.
                Circle()
                    .fill(circleColor)
                    .frame(width: 96, height: 96)
            }

            Text(label)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 240)
        }
    }

    // MARK: - Derived Properties

    private var circleColor: Color {
        switch state {
        case .idle:         return Color.accentColor.opacity(0.6)
        case .connecting,
             .reconnecting: return Color.yellow
        case .listening:    return Color.green
        case .speaking:     return Color.blue
        case .retryable:    return Color.orange
        case .error:        return Color.red
        }
    }

    private var label: String {
        switch state {
        case .idle:          return "Tap to start"
        case .connecting:    return "Connecting\u{2026}"
        case .reconnecting:  return "Reconnecting\u{2026}"
        case .listening:     return "Listening"
        case .speaking:      return "Speaking"
        case .retryable(let msg):
            let display = msg.count > 40 ? String(msg.prefix(40)) + "\u{2026}" : msg
            return "Connection lost: \(display)\nTap Retry to reconnect."
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
