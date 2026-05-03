import XCTest
@testable import dAIly

final class OnboardingKeychainTests: XCTestCase {

    // Use an isolated service name so tests never touch production tokens
    private let store = KeychainStore(service: "com.daily.ios.tests-onboarding")

    override func setUp() {
        super.setUp()
        try? store.clearAll()
    }

    override func tearDown() {
        try? store.clearAll()
        super.tearDown()
    }

    // Test 1: write and read onboarding_complete key round-trip
    func testOnboardingCompleteWriteAndRead() throws {
        try store.save(key: "onboarding_complete", value: "true")
        let loaded = store.load(key: "onboarding_complete")
        XCTAssertEqual(loaded, "true")
    }

    // Test 2: clearAll removes onboarding_complete
    func testOnboardingCompleteClearedByClearAll() throws {
        try store.save(key: "onboarding_complete", value: "true")
        try store.clearAll()
        let loaded = store.load(key: "onboarding_complete")
        XCTAssertNil(loaded)
    }
}
