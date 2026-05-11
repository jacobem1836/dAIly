import XCTest
@testable import dAIly

/// Unit tests for AppState.rootRoute — the top-level screen routing property.
///
/// Verifies that each auth/onboarding state combination resolves to the
/// correct RootRoute case, and that transitions via signOut() and completion
/// produce the expected route changes.
@MainActor
final class AppStateRoutingTests: XCTestCase {

    private var keychain: KeychainStore!

    override func setUp() async throws {
        keychain = KeychainStore(service: "com.daily.ios.tests-routing")
        try keychain.clearAll()
    }

    override func tearDown() async throws {
        try? keychain.clearAll()
    }

    // MARK: - Helpers

    private func makeState(hasToken: Bool = false, hasOnboarding: Bool = false) throws -> AppState {
        if hasToken {
            try keychain.save(key: "access_token", value: "test-token")
        }
        if hasOnboarding {
            try keychain.save(key: "onboarding_complete", value: "true")
        }
        return AppState(keychain: keychain)
    }

    // MARK: - Tests

    // Test 1: No token → .pairing
    func test_no_token_routes_to_pairing() throws {
        let state = try makeState(hasToken: false, hasOnboarding: false)
        XCTAssertEqual(state.rootRoute, .pairing)
    }

    // Test 2: Has token but onboarding incomplete → .onboarding
    func test_token_but_onboarding_incomplete_routes_to_onboarding() throws {
        let state = try makeState(hasToken: true, hasOnboarding: false)
        XCTAssertEqual(state.rootRoute, .onboarding)
    }

    // Test 3: Has token and onboarding complete → .voice
    func test_token_and_onboarding_complete_routes_to_voice() throws {
        let state = try makeState(hasToken: true, hasOnboarding: true)
        XCTAssertEqual(state.rootRoute, .voice)
    }

    // Test 4: signOut() clears all tokens and routes back to .pairing
    func test_signed_out_clears_route_to_pairing() throws {
        let state = try makeState(hasToken: true, hasOnboarding: true)
        XCTAssertEqual(state.rootRoute, .voice)

        state.signOut()

        XCTAssertEqual(state.rootRoute, .pairing)
        XCTAssertFalse(state.hasAccessToken)
        XCTAssertFalse(state.hasCompletedOnboarding)
    }

    // Test 5: Setting hasAccessToken = false programmatically routes to .pairing
    func test_clearing_access_token_routes_to_pairing() throws {
        let state = try makeState(hasToken: true, hasOnboarding: true)
        state.hasAccessToken = false
        XCTAssertEqual(state.rootRoute, .pairing)
    }

    // Test 6: Completing onboarding marks hasCompletedOnboarding and advances route to .voice
    func test_completing_onboarding_advances_route_to_voice() throws {
        let state = try makeState(hasToken: true, hasOnboarding: false)
        XCTAssertEqual(state.rootRoute, .onboarding)

        state.hasCompletedOnboarding = true

        XCTAssertEqual(state.rootRoute, .voice)
    }
}
