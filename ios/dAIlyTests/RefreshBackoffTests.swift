import XCTest
@testable import dAIly

// MARK: - RefreshBackoffTests
//
// Tests for the backoff constants and state-machine behaviour introduced in
// ios/dAIly/auth/TokenRefresher.swift as part of plan 21.45-04.
//
// These tests do NOT exercise real timing (would be slow/flaky) — they verify:
//   - Constants have the documented values
//   - maxAttempts equals retryDelaysNs.count + 1
//   - Hard 401 escalates immediately without burning through all attempts
//   - Transient failure retries maxAttempts times then throws last error

final class RefreshBackoffTests: XCTestCase {

    // MARK: Constant tests (documented schedule: 0.5 s / 1.0 s)

    // Test 1: retryDelaysNs[0] == 500_000_000 (0.5 s)
    func testFirstRetryDelayIs500ms() {
        XCTAssertEqual(RefreshBackoff.retryDelaysNs[0], 500_000_000,
                       "First retry delay must be 500 ms (0.5 s)")
    }

    // Test 2: retryDelaysNs[1] == 1_000_000_000 (1.0 s)
    func testSecondRetryDelayIs1000ms() {
        XCTAssertEqual(RefreshBackoff.retryDelaysNs[1], 1_000_000_000,
                       "Second retry delay must be 1000 ms (1.0 s)")
    }

    // Test 3: maxAttempts == retryDelaysNs.count + 1 (3 total)
    func testMaxAttemptsIsThree() {
        XCTAssertEqual(RefreshBackoff.maxAttempts, 3,
                       "maxAttempts must be 3 (1 immediate + 2 retries)")
        XCTAssertEqual(RefreshBackoff.maxAttempts,
                       RefreshBackoff.retryDelaysNs.count + 1,
                       "maxAttempts must equal retryDelaysNs.count + 1")
    }

    // MARK: Behaviour tests (stubbed AuthService)

    // Test 4: refreshWithBackoff succeeds on first attempt — no retries needed
    func testSucceedsOnFirstAttempt() async throws {
        var callCount = 0
        let auth = await makeStubAuth { _ in
            callCount += 1
            // first call succeeds
        }
        try await RefreshBackoff.refreshWithBackoff(auth)
        XCTAssertEqual(callCount, 1, "Should succeed after exactly 1 attempt")
    }

    // Test 5: hard 401 escapes immediately — only 1 attempt made
    func testHard401EscapesImmediately() async {
        var callCount = 0
        let auth = await makeStubAuth { _ in
            callCount += 1
            throw AuthError.unauthorized
        }
        do {
            try await RefreshBackoff.refreshWithBackoff(auth)
            XCTFail("Expected AuthError.unauthorized to be thrown")
        } catch AuthError.unauthorized {
            // expected
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
        XCTAssertEqual(callCount, 1,
                       "Hard 401 must escalate after exactly 1 attempt, not retry")
    }

    // Test 6: transient failure retries maxAttempts times then throws
    func testTransientFailureRetriesMaxAttemptsTimes() async {
        var callCount = 0
        let auth = await makeStubAuth { _ in
            callCount += 1
            throw AuthError.network("transient_error_\(callCount)")
        }
        do {
            try await RefreshBackoff.refreshWithBackoff(auth)
            XCTFail("Expected error to be thrown after exhausting retries")
        } catch AuthError.unauthorized {
            XCTFail("Should not throw .unauthorized for transient network errors")
        } catch {
            // expected — last transient error rethrown
        }
        XCTAssertEqual(callCount, RefreshBackoff.maxAttempts,
                       "Must attempt exactly maxAttempts (\(RefreshBackoff.maxAttempts)) times before giving up")
    }

    // Test 7: succeeds on third (last) attempt after two transient failures
    func testSucceedsOnLastAttempt() async throws {
        var callCount = 0
        let auth = await makeStubAuth { _ in
            callCount += 1
            if callCount < RefreshBackoff.maxAttempts {
                throw AuthError.network("transient")
            }
            // last attempt succeeds
        }
        try await RefreshBackoff.refreshWithBackoff(auth)
        XCTAssertEqual(callCount, RefreshBackoff.maxAttempts,
                       "Should succeed on the last attempt")
    }
}

// MARK: - Helpers

/// Creates a minimal AuthService whose `refresh()` call executes `handler`.
/// Uses a stub URLProtocol so no real network traffic occurs.
/// The handler receives the attempt index (1-based) via a shared counter in the closure.
@MainActor
private func makeStubAuth(handler: @escaping (URLRequest) throws -> Void) -> AuthService {
    // We stub the URLSession used by AuthService.
    // The handler fires when the stub URLProtocol executes — but because RefreshBackoff
    // calls auth.refresh() which calls postJSON → sendAndDecode → URLSession.data(for:),
    // we can intercept at the URLProtocol level.
    //
    // However, to keep tests simple and not depend on URL path matching, we use a thin
    // subclass that ignores the real network and delegates to our closure.
    let cfg = URLSessionConfiguration.ephemeral
    cfg.protocolClasses = [BackoffStubProtocol.self]
    let session = URLSession(configuration: cfg)
    BackoffStubProtocol.handler = { req in
        do {
            try handler(req)
            // Successful refresh: return a valid token response
            let json = #"{"access_token":"new_tok","expires_in":3600}"#
            return (200, Data(json.utf8))
        } catch AuthError.unauthorized {
            return (401, Data())
        } catch {
            return (503, Data())
        }
    }
    let keychain = KeychainStore(service: "test.backoff.\(UUID().uuidString)")
    try? keychain.save(key: "refresh_token", value: "rt")
    return AuthService(baseURL: URL(string: "https://test.example.com")!,
                       session: session,
                       keychain: keychain)
}

private final class BackoffStubProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = BackoffStubProtocol.handler else {
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
