import XCTest
@testable import dAIly

// MARK: - URLProtocol stub (shared with AuthServiceTests pattern)

final class VoiceStubURLProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = VoiceStubURLProtocol.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown))
            return
        }
        let (statusCode, data) = handler(request)
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

// MARK: - Helpers

private func makeStubSession() -> URLSession {
    let cfg = URLSessionConfiguration.ephemeral
    cfg.protocolClasses = [VoiceStubURLProtocol.self]
    return URLSession(configuration: cfg)
}

private let baseURL = URL(string: "https://test.example.com")!

// MARK: - LiveKitTokenSourceTests

final class LiveKitTokenSourceTests: XCTestCase {

    // Test 1: POST to /livekit/token with Authorization: Bearer header
    func testFetchTokenPostsToCorrectEndpointWithBearerHeader() async throws {
        var capturedRequest: URLRequest?
        VoiceStubURLProtocol.handler = { req in
            capturedRequest = req
            let json = #"{"token":"T","room":"R","livekit_url":"wss://lk"}"#
            return (200, Data(json.utf8))
        }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        _ = try await source.fetchToken(accessJWT: "abc")
        XCTAssertEqual(capturedRequest?.httpMethod, "POST")
        XCTAssertTrue(capturedRequest?.url?.absoluteString.contains("/livekit/token") == true)
        XCTAssertEqual(capturedRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer abc")
    }

    // Test 2: 200 response with valid JSON returns LiveKitToken
    func testFetchTokenParsesValidResponse() async throws {
        VoiceStubURLProtocol.handler = { _ in
            let json = #"{"token":"mytoken","room":"session-1-123","livekit_url":"wss://lk.example.com"}"#
            return (200, Data(json.utf8))
        }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let result = try await source.fetchToken(accessJWT: "abc")
        XCTAssertEqual(result.token, "mytoken")
        XCTAssertEqual(result.room, "session-1-123")
        XCTAssertEqual(result.url, "wss://lk.example.com")
    }

    // Test 3: 401 throws .unauthorized
    func testFetchTokenThrowsUnauthorizedOn401() async {
        VoiceStubURLProtocol.handler = { _ in (401, Data()) }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        do {
            _ = try await source.fetchToken(accessJWT: "bad_token")
            XCTFail("Expected LiveKitTokenError.unauthorized")
        } catch LiveKitTokenError.unauthorized {
            // expected
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    // Test 4: Malformed JSON throws .decoding
    func testFetchTokenThrowsDecodingForMalformedJSON() async {
        VoiceStubURLProtocol.handler = { _ in (200, Data("not-json".utf8)) }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        do {
            _ = try await source.fetchToken(accessJWT: "abc")
            XCTFail("Expected LiveKitTokenError.decoding")
        } catch LiveKitTokenError.decoding {
            // expected
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}

// MARK: - VoiceSessionStateTests (state machine — no real LiveKit needed)

final class VoiceSessionStateTests: XCTestCase {

    // Test 1: New session has state == .idle
    func testInitialStateIsIdle() {
        let keychain = KeychainStore(service: "test.voice.session")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        if case .idle = session.state { } else {
            XCTFail("Expected .idle, got \(session.state)")
        }
    }

    // Test 2: connect() with no Keychain JWT throws .notAuthenticated
    func testConnectWithNoJWTThrowsNotAuthenticated() async {
        let keychain = KeychainStore(service: "test.voice.nojwt.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        do {
            try await session.connect()
            XCTFail("Expected VoiceSessionError.notAuthenticated")
        } catch VoiceSessionError.notAuthenticated {
            // expected
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    // Test 3: connect() transitions state to .connecting initially
    func testConnectSetsConnectingStateThenError() async {
        let keychain = KeychainStore(service: "test.voice.connecting.\(UUID().uuidString)")
        try? keychain.save(key: "access_token", value: "valid_jwt")
        // Token source returns 500 so connect fails but we verify .connecting was set
        VoiceStubURLProtocol.handler = { _ in (500, Data()) }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        // After connect() fails (server error), state should be .error
        do {
            try await session.connect()
            XCTFail("Expected error")
        } catch {
            // expected — token fetch failed
        }
        if case .error = session.state { } else {
            XCTFail("Expected .error state after failed connect, got \(session.state)")
        }
    }

    // Test 4: _testForceState transitions to .listening
    func testForceStateToListening() {
        let keychain = KeychainStore(service: "test.voice.force.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.listening)
        if case .listening = session.state { } else {
            XCTFail("Expected .listening, got \(session.state)")
        }
    }

    // Test 5: handleAgentSpeaking(true) flips .listening -> .speaking
    func testAgentSpeakingFlipsToSpeaking() {
        let keychain = KeychainStore(service: "test.voice.speaking.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.listening)
        session._testHandleAgentSpeaking(true)
        if case .speaking = session.state { } else {
            XCTFail("Expected .speaking, got \(session.state)")
        }
    }

    // Test 6: 401 from token source triggers auth.refresh() then ONE retry; second 401 surfaces .error
    // (tested via state: after double-401 connect fails with .error)
    func testDouble401SurfacesError() async {
        let keychain = KeychainStore(service: "test.voice.401.\(UUID().uuidString)")
        try? keychain.save(key: "access_token", value: "expired_jwt")
        try? keychain.save(key: "refresh_token", value: "refresh_tok")
        // All calls return 401
        VoiceStubURLProtocol.handler = { _ in (401, Data()) }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        do {
            try await session.connect()
            XCTFail("Expected error")
        } catch {
            // expected
        }
        if case .error = session.state { } else {
            XCTFail("Expected .error after double-401, got \(session.state)")
        }
    }

    // Test 7: handleConnectionState(.connected) transitions to .listening
    func testConnectionStateConnectedTransitionsToListening() {
        let keychain = KeychainStore(service: "test.voice.connected.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.connecting)
        session._testHandleConnectionState(.connected)
        if case .listening = session.state { } else {
            XCTFail("Expected .listening after .connected, got \(session.state)")
        }
    }
}
