import SwiftUI

/// Root onboarding carousel (D-01): TabView with .page style. Hosts 7 tabs:
/// Welcome → Pairing → Google → Microsoft → Slack → Schedule → Completion.
///
/// Gate semantics (D-02): forward swipe is clamped via .onChange — the user
/// can only advance past a tab when its gate condition is met. Back-swipe
/// (lower selection) is always allowed (D-03).
///
/// State injection: AppState comes from @EnvironmentObject (provided by
/// dAIlyApp). IntegrationState is also @EnvironmentObject so dAIlyApp's
/// onOpenURL can mutate it for /oauth/success deep links (21.1-RESEARCH
/// §Pattern 2).
struct OnboardingView: View {
    let auth: AuthService

    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var integrationState: IntegrationState

    @State private var currentTab: Int = 0
    @State private var briefingTime: Date =
        Calendar.current.date(bySettingHour: 7, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var scheduleSaved: Bool = false

    /// Highest tab index the user is allowed to reach right now.
    /// (Pitfall 3 mitigation: returns dynamically based on @Published state,
    /// so SwiftUI re-evaluates whenever hasAccessToken or
    /// integrationState.connectedProviders change.)
    private var allowedMaxTab: Int {
        if !appState.hasAccessToken { return 1 }       // Locked at Pairing
        if !integrationState.atLeastOneConnected { return 4 } // Locked at Slack (D-12)
        if !scheduleSaved { return 5 }                  // Locked at Schedule
        return 6                                        // Completion reachable
    }

    var body: some View {
        TabView(selection: $currentTab) {
            WelcomeView(onContinue: { advance() })
                .tag(0)

            PairingView(auth: auth, onComplete: { advance() })
                .tag(1)

            IntegrationView(
                provider: .google,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: false,
                onContinue: { advance() }
            )
            .tag(2)

            IntegrationView(
                provider: .microsoft,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: false,
                onContinue: { advance() }
            )
            .tag(3)

            IntegrationView(
                provider: .slack,
                auth: auth,
                integrationState: integrationState,
                isLastIntegrationPage: true,
                onContinue: { advance() }
            )
            .tag(4)

            ScheduleView(
                auth: auth,
                onComplete: { savedTime in
                    briefingTime = savedTime
                    scheduleSaved = true
                    advance()
                }
            )
            .tag(5)

            CompletionView(
                integrationState: integrationState,
                briefingTime: briefingTime,
                onFinish: {
                    // D-18: flip the published flag — dAIlyApp routing
                    // observes this and switches the root to VoiceView.
                    appState.hasCompletedOnboarding = true
                }
            )
            .tag(6)
        }
        .tabViewStyle(.page)
        .indexViewStyle(.page(backgroundDisplayMode: .always))
        // Auto-advance on appear if already authenticated from a prior session.
        // .onChange won't fire if hasAccessToken starts as true (no value change),
        // so we also check on task launch.
        .task {
            if appState.hasAccessToken && currentTab == 1 {
                withAnimation { currentTab = 2 }
            }
        }
        // Forward-only gate (D-02). Clamp on every selection change.
        // Single-argument form required for iOS 16 deployment target compatibility.
        .onChange(of: currentTab) { newValue in
            if newValue > allowedMaxTab {
                currentTab = allowedMaxTab
            }
        }
        // Auto-advance after pairing succeeds (Pattern 4).
        .onChange(of: appState.hasAccessToken) { newValue in
            if newValue && currentTab == 1 {
                withAnimation { currentTab = 2 }
            }
        }
    }

    /// Advance one tab if the current tab's gate allows it.
    private func advance() {
        let next = currentTab + 1
        if next <= allowedMaxTab {
            withAnimation { currentTab = next }
        }
    }
}
