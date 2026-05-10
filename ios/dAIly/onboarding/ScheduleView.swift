import SwiftUI

/// Tab 5 of the onboarding TabView — daily briefing time picker (D-14).
/// Default 7:00 AM. Timezone auto-detected from TimeZone.current.identifier
/// (D-15) — no user-facing picker. Save calls AuthService.savePreferences
/// then writes onboarding_complete to Keychain (D-16) before invoking
/// onComplete which advances the TabView to CompletionView.
///
/// Critical: write onboarding_complete only AFTER savePreferences succeeds.
/// (T-21.1-03-01 mitigation; 21.1-RESEARCH.md §Threat patterns).
struct ScheduleView: View {
    let auth: AuthService
    let onComplete: (Date) -> Void

    @State private var briefingTime: Date =
        Calendar.current.date(bySettingHour: 7, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var isSaving: Bool = false
    @State private var errorMessage: String? = nil

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Image(systemName: "alarm")
                .font(.system(size: 56))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(.tint)

            Text("When should we brief you?")
                .font(.title2)
                .fontWeight(.semibold)

            DatePicker(
                "Briefing time",
                selection: $briefingTime,
                displayedComponents: .hourAndMinute
            )
            .datePickerStyle(.wheel)
            .labelsHidden()

            if let error = errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
            }

            Button(isSaving ? "Saving…" : "Save and continue") {
                Task { await save() }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(isSaving)

            Spacer()
        }
        .padding()
        .padding(.bottom, 40)
    }

    @MainActor
    private func save() async {
        isSaving = true
        errorMessage = nil

        let timezone = TimeZone.current.identifier
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        let timeString = formatter.string(from: briefingTime)

        do {
            try await auth.savePreferences(briefingTime: timeString, timezone: timezone)
            // Only persist onboarding_complete AFTER backend save succeeds (D-16).
            try KeychainStore.shared.save(key: "onboarding_complete", value: "true")
            onComplete(briefingTime)
        } catch {
            errorMessage = "Failed to save. Please try again."
            isSaving = false
        }
    }
}
