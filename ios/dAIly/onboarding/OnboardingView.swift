import SwiftUI
import AVFoundation
import os

/// Root onboarding carousel (D-01): TabView with .page style. Hosts 8 tabs:
/// Welcome → Pairing → Google → Microsoft → Slack → Permissions → Schedule → Completion.
///
/// Gate semantics (D-02): forward swipe is clamped in the `currentTab` binding's
/// setter — the user can only advance past a tab when its gate condition is met.
/// Back-swipe (lower selection) is always allowed (D-03).
///
/// Single source of truth: OnboardingCoordinator owns the step + gate machine
/// (unit-tested by OnboardingFlowTests.swift). OnboardingView used to
/// reimplement an equivalent `currentTab`/`allowedMaxTab` pair inline — that
/// duplicate has been removed; this view now only drives the coordinator and
/// keeps its gate inputs (hasAccessToken, atLeastOneIntegrationConnected,
/// micPermissionGranted, scheduleSaved) in sync with AppState/IntegrationState.
///
/// State injection: AppState comes from @EnvironmentObject (provided by
/// dAIlyApp). IntegrationState is also @EnvironmentObject so dAIlyApp's
/// onOpenURL can mutate it for /oauth/success deep links (21.1-RESEARCH
/// §Pattern 2).
struct OnboardingView: View {
    let auth: AuthService

    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var integrationState: IntegrationState

    @StateObject private var coordinator = OnboardingCoordinator()

    @State private var briefingTime: Date =
        Calendar.current.date(bySettingHour: 7, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var micPermissionGranted: Bool = false

    private static let logger = Logger(subsystem: "com.jacobmarriott.daily", category: "onboarding")

    /// Bridges TabView's Int selection to the coordinator's OnboardingStep.
    /// The gate check happens directly in the setter — not in a separate
    /// .onChange — so there is no window where a stale gate value could be
    /// read between the write and the check; the clamp and the mutation are
    /// the same statement.
    private var currentTab: Binding<Int> {
        Binding(
            get: { coordinator.currentStep.rawValue },
            set: { requested in
                guard let step = OnboardingStep(rawValue: requested) else { return }
                let maxStep = coordinator.maximumReachableStep
                coordinator.currentStep = step.rawValue <= maxStep.rawValue ? step : maxStep
            }
        )
    }

    var body: some View {
        TabView(selection: currentTab) {
            WelcomeView(onContinue: { advance() })
                .tag(OnboardingStep.welcome.rawValue)

            PairingView(auth: auth, onComplete: { advance() })
                .tag(OnboardingStep.pairing.rawValue)

            IntegrationView(
                provider: .google,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: false,
                onContinue: { advance() }
            )
            .tag(OnboardingStep.google.rawValue)

            IntegrationView(
                provider: .microsoft,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: false,
                onContinue: { advance() }
            )
            .tag(OnboardingStep.microsoft.rawValue)

            IntegrationView(
                provider: .slack,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: true,
                onContinue: { advance() }
            )
            .tag(OnboardingStep.slack.rawValue)

            PermissionsView(onGranted: {
                micPermissionGranted = true
                coordinator.micPermissionGranted = true
                // ponytail: temporary instrumentation to diagnose an intermittent
                // stuck-at-Permissions repro. A prior session's root-cause theory
                // — that @State batching makes advance() read a stale gate value
                // — is almost certainly wrong (SwiftUI/Combine writes are visible
                // synchronously within the same frame, and PairingView.advance()
                // uses the identical pattern without the bug). Logging the real
                // gate inputs at the moment of this transition lets the actual
                // cause be captured from a device log instead of guessed at.
                // Remove once the repro is understood and fixed.
                logGateSnapshot(trigger: "permissions.onGranted")
                advance()
            })
            .tag(OnboardingStep.permissions.rawValue)

            ScheduleView(
                auth: auth,
                onComplete: { savedTime in
                    briefingTime = savedTime
                    coordinator.scheduleSaved = true
                    advance()
                }
            )
            .tag(OnboardingStep.schedule.rawValue)

            CompletionView(
                auth: auth,
                integrationState: integrationState,
                briefingTime: briefingTime,
                onFinish: {
                    // D-18: flip the published flag — dAIlyApp routing
                    // observes this and switches the root to VoiceView.
                    appState.hasCompletedOnboarding = true
                }
            )
            .tag(OnboardingStep.completion.rawValue)
        }
        .tabViewStyle(.page)
        .indexViewStyle(.page(backgroundDisplayMode: .always))
        // Auto-advance on appear if already authenticated from a prior session.
        // .onChange won't fire if hasAccessToken starts as true (no value change),
        // so we also check on task launch.
        .task {
            syncGates()
            if appState.hasAccessToken && coordinator.currentStep == .pairing {
                withAnimation { coordinator.currentStep = .google }
            }
            // Pre-grant: if the user already allowed mic in a previous session,
            // skip the gate so returning users don't re-see the Permissions tab.
            if AVAudioSession.sharedInstance().recordPermission == .granted {
                micPermissionGranted = true
                coordinator.micPermissionGranted = true
            }
        }
        // Auto-advance after pairing succeeds (Pattern 4). Also keeps the
        // coordinator's hasAccessToken gate input in sync.
        .onChange(of: appState.hasAccessToken) { newValue in
            coordinator.hasAccessToken = newValue
            if newValue && coordinator.currentStep == .pairing {
                withAnimation { coordinator.currentStep = .google }
            }
        }
        // Keeps the coordinator's integration gate input in sync whenever a
        // provider connects (e.g. via the /oauth/success deep link handled at
        // the App level).
        .onChange(of: integrationState.connectedProviders) { _ in
            coordinator.atLeastOneIntegrationConnected = integrationState.atLeastOneConnected
        }
    }

    /// Advance one tab if the coordinator's gate allows it.
    private func advance() {
        withAnimation { _ = coordinator.advance() }
    }

    /// Pushes the current AppState/IntegrationState/local gate inputs into the
    /// coordinator. Called once on .task; subsequent changes flow through the
    /// onChange handlers and the closures above.
    private func syncGates() {
        coordinator.hasAccessToken = appState.hasAccessToken
        coordinator.atLeastOneIntegrationConnected = integrationState.atLeastOneConnected
        coordinator.micPermissionGranted = micPermissionGranted
    }

    // ponytail: diagnostic logging for the stuck-at-Permissions repro — see
    // the comment on PermissionsView's onGranted closure above. Logs every
    // input maximumReachableStep depends on at the moment of the transition.
    private func logGateSnapshot(trigger: String) {
        Self.logger.debug("""
        onboarding gate snapshot [\(trigger, privacy: .public)]: \
        currentStep=\(coordinator.currentStep.label, privacy: .public) \
        hasAccessToken=\(coordinator.hasAccessToken, privacy: .public) \
        atLeastOneIntegrationConnected=\(coordinator.atLeastOneIntegrationConnected, privacy: .public) \
        micPermissionGranted=\(coordinator.micPermissionGranted, privacy: .public) \
        scheduleSaved=\(coordinator.scheduleSaved, privacy: .public) \
        maximumReachableStep=\(coordinator.maximumReachableStep.label, privacy: .public)
        """)
    }
}
