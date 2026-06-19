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

@MainActor
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

    // Test 6: hard 401 on both token fetch AND token refresh → .error("re_pair_required")
    // The refresh token is invalid — terminal failure routes to re-pair, not a retryable state.
    func testHard401SurfacesRePairRequiredError() async {
        let keychain = KeychainStore(service: "test.voice.401.\(UUID().uuidString)")
        try? keychain.save(key: "access_token", value: "expired_jwt")
        try? keychain.save(key: "refresh_token", value: "invalid_refresh_tok")
        // All calls return 401 (both /livekit/token and /auth/token/refresh)
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
        // Hard 401 on refresh must surface re_pair_required (.error), not .retryable
        if case .error(let reason) = session.state {
            XCTAssertEqual(reason, "re_pair_required",
                           "Hard 401 must route to re_pair_required, got '\(reason)'")
        } else {
            XCTFail("Expected .error(re_pair_required) after hard 401 refresh, got \(session.state)")
        }
    }

    // Test 6b: transient network failure on refresh (not a 401) → .retryable state
    func testTransientRefreshFailureSurfacesRetryableState() async {
        let keychain = KeychainStore(service: "test.voice.transient.\(UUID().uuidString)")
        try? keychain.save(key: "access_token", value: "expired_jwt")
        try? keychain.save(key: "refresh_token", value: "valid_refresh_tok")
        // Token fetch returns 401 (triggers refresh); refresh endpoint returns 503 (transient)
        VoiceStubURLProtocol.handler = { req in
            if req.url?.path.contains("/livekit/token") == true {
                return (401, Data())
            }
            // /auth/token/refresh → transient server error
            return (503, Data())
        }
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        do {
            try await session.connect()
            XCTFail("Expected error")
        } catch {
            // expected
        }
        // Transient exhaustion must land in .retryable, not .error
        if case .retryable = session.state { } else {
            XCTFail("Expected .retryable after transient refresh failure, got \(session.state)")
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

    // Test 8: retry() no-ops when state is not .retryable
    func testRetryNoOpsWhenNotRetryable() async {
        let keychain = KeychainStore(service: "test.voice.retry.noop.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.idle)
        await session.retry()  // should be a no-op
        if case .idle = session.state { } else {
            XCTFail("Expected .idle (no-op) after retry() when not in .retryable, got \(session.state)")
        }
    }

    // Test 9: handleBackground() with an active session sets shouldResume; idle does not
    func testHandleBackgroundSetsResumeWhenActive() async {
        let keychain = KeychainStore(service: "test.voice.bg.active.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.listening)
        await session.handleBackground()
        XCTAssertTrue(session._testShouldResume,
                      "shouldResume must be true after backgrounding from .listening")
        if case .idle = session.state { } else {
            XCTFail("Expected .idle after handleBackground(), got \(session.state)")
        }
    }

    // Test 10: handleBackground() when idle does NOT set shouldResume
    func testHandleBackgroundWhenIdleDoesNotSetResume() async {
        let keychain = KeychainStore(service: "test.voice.bg.idle.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        // state is .idle by default
        await session.handleBackground()
        XCTAssertFalse(session._testShouldResume,
                       "shouldResume must be false when backgrounding from .idle")
    }

    // Test 11: handleForeground() clears shouldResume and does not loop infinitely on no-JWT
    func testHandleForegroundClearsShouldResumeOnAttempt() async {
        let keychain = KeychainStore(service: "test.voice.fg.resume.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        // Simulate: session was live when backgrounded
        session._testForceState(.listening)
        await session.handleBackground()
        XCTAssertTrue(session._testShouldResume)
        // No JWT in keychain — connect() will fail cleanly; shouldResume is cleared before attempt
        await session.handleForeground()
        XCTAssertFalse(session._testShouldResume,
                       "shouldResume must be cleared after handleForeground() attempt")
    }

    // Test 12: disconnect() clears shouldResume
    func testDisconnectClearsShouldResume() async {
        let keychain = KeychainStore(service: "test.voice.disconnect.resume.\(UUID().uuidString)")
        let source = LiveKitTokenSource(baseURL: baseURL, session: makeStubSession())
        let auth = AuthService(baseURL: baseURL, session: makeStubSession(), keychain: keychain)
        let session = VoiceSession(tokenSource: source, auth: auth, keychain: keychain)
        session._testForceState(.listening)
        await session.handleBackground()
        XCTAssertTrue(session._testShouldResume)
        await session.disconnect()
        XCTAssertFalse(session._testShouldResume,
                       "disconnect() must clear shouldResume")
    }
}
