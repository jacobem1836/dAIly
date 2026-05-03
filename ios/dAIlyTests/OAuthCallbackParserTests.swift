import XCTest
@testable import dAIly

final class OAuthCallbackParserTests: XCTestCase {

    // Test 1: Extracts "google" from /oauth/success?provider=google
    func testExtractsGoogleProvider() {
        let url = URL(string: "https://example.com/oauth/success?provider=google")!
        XCTAssertEqual(OAuthCallbackParser.extractProvider(from: url), "google")
    }

    // Test 2: Extracts "microsoft" from /oauth/success?provider=microsoft
    func testExtractsMicrosoftProvider() {
        let url = URL(string: "https://example.com/oauth/success?provider=microsoft")!
        XCTAssertEqual(OAuthCallbackParser.extractProvider(from: url), "microsoft")
    }

    // Test 3: Extracts "slack" from /oauth/success?provider=slack
    func testExtractsSlackProvider() {
        let url = URL(string: "https://example.com/oauth/success?provider=slack")!
        XCTAssertEqual(OAuthCallbackParser.extractProvider(from: url), "slack")
    }

    // Test 4: Returns nil for wrong path (/pair)
    func testReturnsNilForPairPath() {
        let url = URL(string: "https://example.com/pair?code=ABC")!
        XCTAssertNil(OAuthCallbackParser.extractProvider(from: url))
    }

    // Test 5: Returns nil when query is missing
    func testReturnsNilWhenQueryMissing() {
        let url = URL(string: "https://example.com/oauth/success")!
        XCTAssertNil(OAuthCallbackParser.extractProvider(from: url))
    }

    // Test 6: Returns nil for empty provider value
    func testReturnsNilForEmptyProviderValue() {
        let url = URL(string: "https://example.com/oauth/success?provider=")!
        XCTAssertNil(OAuthCallbackParser.extractProvider(from: url))
    }

    // Test 7: Passes through unknown provider values (caller validates)
    func testPassesThroughUnknownProvider() {
        let url = URL(string: "https://example.com/oauth/success?provider=unknown")!
        XCTAssertEqual(OAuthCallbackParser.extractProvider(from: url), "unknown")
    }

    // Test 8: hasSuffix matches paths with leading segments
    func testHandlesPathWithLeadingSegments() {
        let url = URL(string: "https://example.com/api/oauth/success?provider=google")!
        XCTAssertEqual(OAuthCallbackParser.extractProvider(from: url), "google")
    }
}
