import XCTest
@testable import dAIly

final class PairCodeURLParserTests: XCTestCase {

    // Test 1: Valid pair URL returns code
    func testExtractPairCodeReturnsCodeFromValidURL() {
        let url = URL(string: "https://app.example.com/pair?code=ABC123")!
        let result = PairCodeURLParser.extractPairCode(from: url)
        XCTAssertEqual(result, "ABC123")
    }

    // Test 2: Missing code param returns nil
    func testExtractPairCodeReturnNilWhenCodeParamAbsent() {
        let url = URL(string: "https://app.example.com/pair?other=xx")!
        let result = PairCodeURLParser.extractPairCode(from: url)
        XCTAssertNil(result)
    }

    // Test 3: Wrong path returns nil
    func testExtractPairCodeReturnNilForWrongPath() {
        let url = URL(string: "https://app.example.com/notpair?code=ABC")!
        let result = PairCodeURLParser.extractPairCode(from: url)
        XCTAssertNil(result)
    }

    // Test 4: Mixed-case path returns nil (strict match)
    func testExtractPairCodeReturnNilForMixedCasePath() {
        let url = URL(string: "https://app.example.com/Pair?code=ABC")!
        let result = PairCodeURLParser.extractPairCode(from: url)
        XCTAssertNil(result)
    }
}
