import SwiftUI
import AVFoundation

/// Onboarding tab 5 — requests microphone permission (D-09).
/// `NSMicrophoneUsageDescription` must be set in Info.plist (already done).
///
/// On grant, `onGranted` advances the parent TabView. On denial the user
/// can tap "Open Settings" to go to system Settings; the Continue button
/// stays disabled until permission flips to .granted (e.g. user returns
/// from Settings).
struct PermissionsView: View {
    let onGranted: () -> Void

    @State private var status: AVAudioSession.RecordPermission =
        AVAudioSession.sharedInstance().recordPermission
    @State private var isRequesting: Bool = false

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "mic.fill")
                .font(.system(size: 56))
                .foregroundStyle(.primary)

            Text("Allow microphone access")
                .font(.title2)
                .fontWeight(.semibold)

            Text("dAIly needs your microphone to hear your voice during briefings and conversations.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Spacer()

            if status == .granted {
                Button("Continue", action: onGranted)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
            } else if status == .denied {
                VStack(spacing: 12) {
                    Text("Microphone access was denied. Open Settings to enable it.")
                        .foregroundStyle(.red)
                        .font(.caption)
                        .multilineTextAlignment(.center)
                    Button("Open Settings") {
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            UIApplication.shared.open(url)
                        }
                    }
                    .buttonStyle(.bordered)
                }
            } else {
                Button(isRequesting ? "Requesting…" : "Allow microphone") {
                    Task { await request() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(isRequesting)
            }
        }
        .padding()
        .padding(.bottom, 40)  // D-07: keep CTA above page-indicator dots
        .onAppear {
            // Re-read in case the user returned from Settings.
            status = AVAudioSession.sharedInstance().recordPermission
        }
    }

    private func request() async {
        isRequesting = true
        let granted: Bool = await withCheckedContinuation { cont in
            AVAudioSession.sharedInstance().requestRecordPermission { ok in
                cont.resume(returning: ok)
            }
        }
        isRequesting = false
        status = AVAudioSession.sharedInstance().recordPermission
        if granted { onGranted() }
    }
}
