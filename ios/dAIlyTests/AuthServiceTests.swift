import XCTest
@testable import dAIly

// MARK: - URL Protocol Stub

final class StubURLProtocol: URLProtocol {
    static var stubResponseData: Data = Data()
    static var stubStatusCode: Int = 200
    static var stubError: Error? = nil

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        if let error = StubURLProtocol.stubError {
            client?.urlProtocol(self, didFailWithError: error)
            return
        }
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: StubURLProtocol.stubStatusCode,
            httpVersion: nil,
            headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: StubURLProtocol.stubResponseData)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

// MARK: - AuthService Tests

@MainActor
final class AuthServiceTests: XCTestCase {
    private var auth: AuthService!
    private var keychain: KeychainStore!
    private var session: URLSession!

    override func setUp() async throws {
        keychain = KeychainStore(service: "com.daily.ios.tests-auth")
        try keychain.clearAll()

        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubURLProtocol.self]
        session = URLSession(configuration: config)

        auth = AuthService(
            baseURL: URL(string: "https://api.test.example.com")!,
            session: session,
            keychain: keychain
        )

        StubURLProtocol.stubError = nil
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = Data()
    }

    override func tearDown() async throws {
        try keychain.clearAll()
    }

    // Test 5: sendLink POSTs to the correct endpoint and returns on 204
    func testSendLinkSucceedsOn204() async throws {
        StubURLProtocol.stubStatusCode = 204
        StubURLProtocol.stubResponseData = Data()

        // Should not throw
        try await auth.sendLink(email: "u@e.com")
    }

    // Test 6: completePairing parses response and persists Keychain entries
    func testCompletePairingPersistsTokens() async throws {
        let responseBody = """
        {"access_token":"at-abc","refresh_token":"rt-xyz","expires_in":3600}
        """.data(using: .utf8)!
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = responseBody

        let result = try await auth.completePairing(code: "ABC")

        XCTAssertEqual(result.accessToken, "at-abc")
        XCTAssertEqual(result.refreshToken, "rt-xyz")
        XCTAssertTrue(result.expiresAt > Date())

        XCTAssertEqual(keychain.load(key: "access_token"), "at-abc")
        XCTAssertEqual(keychain.load(key: "refresh_token"), "rt-xyz")
        XCTAssertNotNil(keychain.load(key: "access_token_expires_at"))
    }

    // Test 7: refresh reads refresh_token from keychain and persists new access_token
    func testRefreshPersistsNewAccessToken() async throws {
        try keychain.save(key: "refresh_token", value: "rt-existing")

        let responseBody = """
        {"access_token":"at-new","expires_in":3600}
        """.data(using: .utf8)!
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = responseBody

        try await auth.refresh()

        XCTAssertEqual(keychain.load(key: "access_token"), "at-new")
        XCTAssertNotNil(keychain.load(key: "access_token_expires_at"))
    }

    // Test 8: 401 throws AuthError.unauthorized
    func testUnauthorizedStatusThrowsAuthError() async throws {
        StubURLProtocol.stubStatusCode = 401
        StubURLProtocol.stubResponseData = Data()

        do {
            try await auth.sendLink(email: "u@e.com")
            XCTFail("Expected AuthError.unauthorized")
        } catch AuthError.unauthorized {
            // expected
        }
    }

    // Test 9: Network error throws AuthError.network
    func testNetworkErrorThrowsAuthErrorNetwork() async throws {
        StubURLProtocol.stubError = URLError(.notConnectedToInternet)

        do {
            try await auth.sendLink(email: "u@e.com")
            XCTFail("Expected AuthError.network")
        } catch AuthError.network {
            // expected
        }
    }
}
