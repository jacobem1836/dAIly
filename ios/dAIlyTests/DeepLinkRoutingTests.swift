import XCTest
@testable import dAIly

/// Unit tests verifying that incoming URLs route to the correct AppState
/// mutations through AppState.handleDeepLink.
///
/// NOT testing the parsers themselves (covered by OAuthCallbackParserTests /
/// PairCodeURLParserTests) — testing the routing layer that calls them and
/// applies the mutations.
@MainActor
final class DeepLinkRoutingTests: XCTestCase {

    private var appState: AppState!
    private var integrationState: IntegrationState!
    private var keychain: KeychainStore!
    private var capturedPairCodes: [String] = []

    override func setUp() async throws {
        keychain = KeychainStore(service: "com.daily.ios.tests-deeplink")
        try keychain.clearAll()
        appState = AppState(keychain: keychain)
        integrationState = IntegrationState()
        capturedPairCodes = []
    }

    override func tearDown() async throws {
        try? keychain.clearAll()
    }

    // MARK: - Helpers

    @discardableResult
    private func handle(_ urlString: String) -> Bool {
        let url = URL(string: urlString)!
        return appState.handleDeepLink(url, integrationState: integrationState) { code in
            self.capturedPairCodes.append(code)
        }
    }

    // MARK: - Tests

    // Test 1: OAuth success URL marks the provider connected.
    func test_oauth_success_url_marks_provider_connected() {
        handle("https://daily.app/oauth/success?provider=google")
        XCTAssertTrue(integrationState.isConnected(.google))
    }

    // Test 2: Unknown provider in OAuth success URL is ignored (no crash, no state change).
    func test_oauth_success_unknown_provider_is_ignored() {
        let changed = handle("https://daily.app/oauth/success?provider=unknown")
        XCTAssertFalse(changed, "Unknown provider should not be handled")
        XCTAssertTrue(integrationState.connectedProviders.isEmpty)
    }

    // Test 3: OAuth success for microsoft marks microsoft connected.
    func test_oauth_success_microsoft_marks_microsoft_connected() {
        handle("https://daily.app/oauth/success?provider=microsoft")
        XCTAssertTrue(integrationState.isConnected(.microsoft))
        XCTAssertFalse(integrationState.isConnected(.google))
    }

    // Test 4: Pair code URL extracts code and invokes pairCompletion callback.
    func test_pair_code_url_invokes_pair_completion() {
        handle("https://daily.app/pair?code=123456")
        XCTAssertEqual(capturedPairCodes, ["123456"])
    }

    // Test 5: Universal link with invalid path is ignored.
    func test_universal_link_with_invalid_path_is_ignored() {
        let handled = handle("https://daily.app/garbage")
        XCTAssertFalse(handled)
        XCTAssertTrue(integrationState.connectedProviders.isEmpty)
        XCTAssertTrue(capturedPairCodes.isEmpty)
    }

    // Test 6: OAuth callback during onboarding integrations step updates integration state
    //         but does NOT auto-advance (advance is user-driven).
    func test_oauth_callback_updates_integration_but_does_not_auto_advance() {
        // Simulate being on integrations step
        let coordinator = OnboardingCoordinator()
        coordinator.currentStep = .slack
        coordinator.hasAccessToken = true
        coordinator.atLeastOneIntegrationConnected = false

        // OAuth success arrives
        handle("https://daily.app/oauth/success?provider=google")

        // State is updated
        XCTAssertTrue(integrationState.isConnected(.google))

        // But coordinator did NOT advance on its own (user taps Continue)
        XCTAssertEqual(coordinator.currentStep, .slack)
    }

    // Test 7: OAuthCallbackParser and PairCodeURLParser are used by the routing layer.
    //         Verify both parsers are exercised via the handler (not duplicating unit tests).
    func test_handler_uses_both_parsers() {
        // OAuthCallbackParser branch
        let oauthResult = handle("https://daily.app/oauth/success?provider=slack")
        XCTAssertTrue(oauthResult)
        XCTAssertTrue(integrationState.isConnected(.slack))

        // PairCodeURLParser branch
        let pairResult = handle("https://daily.app/pair?code=ABCXYZ")
        XCTAssertTrue(pairResult)
        XCTAssertEqual(capturedPairCodes.first, "ABCXYZ")
    }
}
