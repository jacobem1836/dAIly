import XCTest
@testable import dAIly

// MARK: - URL Protocol Stub

final class StubURLProtocol: URLProtocol {
    static var stubResponseData: Data = Data()
    static var stubStatusCode: Int = 200
    static var stubError: Error? = nil
    static var capturedRequests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        StubURLProtocol.capturedRequests.append(request)
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
        StubURLProtocol.capturedRequests = []
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

    // Test 10: getIntegrationConnectURL parses auth_url field
    func testGetIntegrationConnectURLParsesAuthUrl() async throws {
        try keychain.save(key: "access_token", value: "at-test")
        let body = #"{"auth_url":"https://accounts.google.com/o/oauth2/auth?x=1"}"#.data(using: .utf8)!
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = body

        let url = try await auth.getIntegrationConnectURL(provider: "google")
        XCTAssertEqual(url.absoluteString, "https://accounts.google.com/o/oauth2/auth?x=1")
    }

    // Test 11: getIntegrationConnectURL sends Bearer Authorization header
    func testGetIntegrationConnectURLSendsBearerHeader() async throws {
        try keychain.save(key: "access_token", value: "at-test-bearer")
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = #"{"auth_url":"https://x"}"#.data(using: .utf8)!

        _ = try? await auth.getIntegrationConnectURL(provider: "google")

        let req = try XCTUnwrap(StubURLProtocol.capturedRequests.first)
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer at-test-bearer")
        XCTAssertTrue(req.url?.path.hasSuffix("/integrations/google/connect") == true)
        XCTAssertEqual(req.httpMethod, "GET")
    }

    // Test 12: getIntegrationConnectURL on 401 throws AuthError.unauthorized
    func testGetIntegrationConnectURLUnauthorized() async throws {
        try keychain.save(key: "access_token", value: "at-test")
        StubURLProtocol.stubStatusCode = 401
        StubURLProtocol.stubResponseData = Data()

        do {
            _ = try await auth.getIntegrationConnectURL(provider: "google")
            XCTFail("Expected AuthError.unauthorized")
        } catch AuthError.unauthorized {
            // expected
        }
    }

    // Test 13: getIntegrationConnectURL on malformed JSON throws AuthError.decoding
    func testGetIntegrationConnectURLDecodingError() async throws {
        try keychain.save(key: "access_token", value: "at-test")
        StubURLProtocol.stubStatusCode = 200
        StubURLProtocol.stubResponseData = #"{"wrong_field":"x"}"#.data(using: .utf8)!

        do {
            _ = try await auth.getIntegrationConnectURL(provider: "google")
            XCTFail("Expected AuthError.decoding")
        } catch AuthError.decoding {
            // expected
        }
    }

    // Test 14: savePreferences sends PUT to /users/me/preferences with Bearer + Content-Type headers on 204
    func testSavePreferencesSucceedsOn204() async throws {
        try keychain.save(key: "access_token", value: "at-test")
        StubURLProtocol.stubStatusCode = 204
        StubURLProtocol.stubResponseData = Data()

        try await auth.savePreferences(briefingTime: "07:00", timezone: "Australia/Brisbane")

        let req = try XCTUnwrap(StubURLProtocol.capturedRequests.first)
        XCTAssertEqual(req.httpMethod, "PUT")
        XCTAssertTrue(req.url?.path.hasSuffix("/users/me/preferences") == true)
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer at-test")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Content-Type"), "application/json")
    }

    // Test 15: savePreferences sends briefing_time and timezone in body
    func testSavePreferencesSendsBodyFields() async throws {
        try keychain.save(key: "access_token", value: "at-test")
        StubURLProtocol.stubStatusCode = 204
        StubURLProtocol.stubResponseData = Data()

        try await auth.savePreferences(briefingTime: "07:30", timezone: "America/Los_Angeles")

        let req = try XCTUnwrap(StubURLProtocol.capturedRequests.first)
        let bodyData: Data
        if let direct = req.httpBody {
            bodyData = direct
        } else if let stream = req.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buf = Data()
            let bufSize = 1024
            var bytes = [UInt8](repeating: 0, count: bufSize)
            while stream.hasBytesAvailable {
                let read = stream.read(&bytes, maxLength: bufSize)
                if read <= 0 { break }
                buf.append(bytes, count: read)
            }
            bodyData = buf
        } else {
            bodyData = Data()
        }
        let json = try JSONSerialization.jsonObject(with: bodyData) as? [String: String]
        XCTAssertEqual(json?["briefing_time"], "07:30")
        XCTAssertEqual(json?["timezone"], "America/Los_Angeles")
    }
}
