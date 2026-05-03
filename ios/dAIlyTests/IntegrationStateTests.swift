import XCTest
@testable import dAIly

final class IntegrationStateTests: XCTestCase {

    // Test 1: Initial state is empty with no providers connected
    func testInitialStateIsEmpty() {
        let state = IntegrationState()
        XCTAssertTrue(state.connectedProviders.isEmpty)
        XCTAssertFalse(state.atLeastOneConnected)
    }

    // Test 2: markConnected adds provider and sets atLeastOneConnected
    func testMarkConnectedAddsProvider() {
        let state = IntegrationState()
        state.markConnected(provider: "google")
        XCTAssertEqual(state.connectedProviders, ["google"])
        XCTAssertTrue(state.atLeastOneConnected)
    }

    // Test 3: markConnected is idempotent — duplicate inserts keep Set deduplicated
    func testMarkConnectedIsIdempotent() {
        let state = IntegrationState()
        state.markConnected(provider: "google")
        state.markConnected(provider: "google")
        XCTAssertEqual(state.connectedProviders.count, 1)
    }

    // Test 4: All three providers can be connected
    func testAllThreeProvidersCanBeConnected() {
        let state = IntegrationState()
        state.markConnected(provider: "google")
        state.markConnected(provider: "microsoft")
        state.markConnected(provider: "slack")
        XCTAssertEqual(state.connectedProviders.count, 3)
    }

    // Test 5: isConnected helper works correctly
    func testIsConnectedHelper() {
        let state = IntegrationState()
        state.markConnected(provider: "google")
        XCTAssertTrue(state.isConnected(.google))
        XCTAssertFalse(state.isConnected(.microsoft))
    }

    // Test 6: IntegrationProvider raw values match expected strings
    func testProviderEnumRawValues() {
        XCTAssertEqual(IntegrationProvider.google.rawValue, "google")
        XCTAssertEqual(IntegrationProvider.microsoft.rawValue, "microsoft")
        XCTAssertEqual(IntegrationProvider.slack.rawValue, "slack")
    }

    // Test 7: IntegrationProvider.allCases returns providers in declared order
    func testProviderEnumAllCases() {
        let cases = IntegrationProvider.allCases
        XCTAssertEqual(cases, [.google, .microsoft, .slack])
    }
}
