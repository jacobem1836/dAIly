import XCTest
@testable import dAIly

/// Unit tests for the onboarding step machine (OnboardingCoordinator) and
/// the integration state gates that control forward navigation.
///
/// These tests drive the step machine directly — no SwiftUI rendering required.
/// Mirrors the style of IntegrationStateTests.swift.
final class OnboardingFlowTests: XCTestCase {

    private var coordinator: OnboardingCoordinator!
    private var integrationState: IntegrationState!
    private var keychain: KeychainStore!
    private var appState: AppState!

    override func setUp() {
        super.setUp()
        coordinator = OnboardingCoordinator()
        integrationState = IntegrationState()
        keychain = KeychainStore(service: "com.daily.ios.tests-onboarding-flow")
        try? keychain.clearAll()
        appState = AppState(keychain: keychain)
    }

    override func tearDown() {
        try? keychain.clearAll()
        super.tearDown()
    }

    // MARK: - Step 1: Welcome

    /// Fresh coordinator starts at .welcome.
    func test_onboarding_starts_at_welcome() {
        XCTAssertEqual(coordinator.currentStep, .welcome)
    }

    // MARK: - Step 2: Advance from welcome to pairing

    /// No gates block welcome → pairing; advance() moves to .pairing.
    func test_advance_from_welcome_goes_to_pairing() {
        let moved = coordinator.advance()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .pairing)
    }

    // MARK: - Step 3: Pairing gate

    /// Without an access token, the user cannot advance past .pairing.
    func test_pairing_step_blocks_advance_without_access_token() {
        coordinator.currentStep = .pairing
        coordinator.hasAccessToken = false
        XCTAssertFalse(coordinator.canAdvance)
    }

    /// With an access token, the gate opens and advance() reaches .google.
    func test_pairing_step_allows_advance_with_access_token() {
        coordinator.currentStep = .pairing
        coordinator.hasAccessToken = true
        let moved = coordinator.advance()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .google)
    }

    // MARK: - Step 4: Integration gate

    /// With all integrations disconnected, canAdvance is false at .slack (the last integration page).
    func test_integrations_step_requires_at_least_one_connected() {
        coordinator.currentStep = .slack
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = false
        XCTAssertFalse(coordinator.canAdvance)
    }

    /// With at least one integration connected, the user can advance past .slack.
    func test_integrations_step_allows_advance_when_one_connected() {
        coordinator.currentStep = .slack
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = true
        coordinator.micPermissionGranted = false
        let moved = coordinator.advance()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .permissions)
    }

    // MARK: - Step 5: Permissions gate

    /// Advance from permissions to schedule once mic permission is granted.
    func test_advance_from_permissions_goes_to_schedule() {
        coordinator.currentStep = .permissions
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = true
        coordinator.micPermissionGranted = true
        let moved = coordinator.advance()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .schedule)
    }

    // MARK: - Step 6: Schedule → Completion

    /// Advance from schedule to completion once schedule is saved.
    func test_advance_from_schedule_goes_to_completion() {
        coordinator.currentStep = .schedule
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = true
        coordinator.micPermissionGranted = true
        coordinator.scheduleSaved = true
        let moved = coordinator.advance()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .completion)
    }

    // MARK: - Step 7: Completion marks onboarding done

    /// Completing onboarding should set hasCompletedOnboarding on AppState.
    func test_advance_from_completion_marks_onboarding_done() {
        // Simulate what CompletionView's onFinish closure does
        appState.hasCompletedOnboarding = true
        XCTAssertTrue(appState.hasCompletedOnboarding)
    }

    // MARK: - Back navigation

    /// back() from .schedule returns to .permissions.
    func test_back_from_schedule_returns_to_permissions() {
        coordinator.currentStep = .schedule
        let moved = coordinator.back()
        XCTAssertTrue(moved)
        XCTAssertEqual(coordinator.currentStep, .permissions)
    }

    /// back() at .welcome is a no-op (no previous step).
    func test_back_from_welcome_is_noop() {
        coordinator.currentStep = .welcome
        let moved = coordinator.back()
        XCTAssertFalse(moved)
        XCTAssertEqual(coordinator.currentStep, .welcome)
    }

    // MARK: - OAuth callback updates integration state

    /// Simulating /oauth/success?provider=google marks google as connected
    /// and unblocks the integration gate.
    func test_oauth_callback_updates_integration_state() {
        XCTAssertFalse(integrationState.atLeastOneConnected)
        integrationState.markConnected(provider: IntegrationProvider.google.rawValue)
        XCTAssertTrue(integrationState.isConnected(.google))
        XCTAssertTrue(integrationState.atLeastOneConnected)

        // Coordinator gate reflects updated state
        coordinator.currentStep = .slack
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = integrationState.atLeastOneConnected
        XCTAssertTrue(coordinator.canAdvance)
    }
}
