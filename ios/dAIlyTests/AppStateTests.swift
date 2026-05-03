import XCTest
@testable import dAIly

@MainActor
final class AppStateTests: XCTestCase {

    private var keychain: KeychainStore!

    override func setUp() {
        super.setUp()
        keychain = KeychainStore(service: "com.daily.ios.tests-appstate")
        try? keychain.clearAll()
    }

    override func tearDown() {
        try? keychain.clearAll()
        super.tearDown()
    }

    // Test 1: Fresh keychain → hasCompletedOnboarding == false
    func testHasCompletedOnboardingFalseOnEmptyKeychain() {
        let state = AppState(keychain: keychain)
        XCTAssertFalse(state.hasCompletedOnboarding)
    }

    // Test 2: Keychain has onboarding_complete → hasCompletedOnboarding == true
    func testHasCompletedOnboardingTrueWhenKeychainKeyPresent() throws {
        try keychain.save(key: "onboarding_complete", value: "true")
        let state = AppState(keychain: keychain)
        XCTAssertTrue(state.hasCompletedOnboarding)
    }

    // Test 3: access_token present but no onboarding_complete → both flags respected
    func testHasAccessTokenStillRespected() throws {
        try keychain.save(key: "access_token", value: "at-xyz")
        let state = AppState(keychain: keychain)
        XCTAssertTrue(state.hasAccessToken)
        XCTAssertFalse(state.hasCompletedOnboarding)
    }
}
