import Testing
import Foundation
@testable import dAIly

// MARK: - VoiceSessionErrorMappingTests
//
// Tests for VoiceSession.humanizeConnectError(_:) — D-01.
// Verifies that known NSURLError codes and LiveKit error patterns map to
// user-facing strings instead of raw NSError descriptions.

@Suite
struct VoiceSessionErrorMappingTests {

    // Test 1: NSURLErrorCannotConnectToHost (-1004) returns a "couldn't reach" message
    @Test("NSURLErrorCannotConnectToHost maps to reachability message")
    func cannotConnectToHostReturnsReachabilityMessage() {
        let error = NSError(
            domain: NSURLErrorDomain,
            code: NSURLErrorCannotConnectToHost,
            userInfo: [NSLocalizedDescriptionKey: "Could not connect to the server."]
        )
        let result = VoiceSession.humanizeConnectError(error)
        #expect(result.lowercased().contains("reach") || result.lowercased().contains("internet"))
    }

    // Test 2: NSURLErrorTimedOut (-1001) returns a timeout/backend-down message
    @Test("NSURLErrorTimedOut maps to timeout message")
    func timedOutReturnsTimeoutMessage() {
        let error = NSError(
            domain: NSURLErrorDomain,
            code: NSURLErrorTimedOut,
            userInfo: [NSLocalizedDescriptionKey: "The request timed out."]
        )
        let result = VoiceSession.humanizeConnectError(error)
        #expect(result.lowercased().contains("respond") || result.lowercased().contains("down"))
    }

    // Test 3: Error with "websocket" in its description returns a worker-may-not-be-running message
    @Test("Error with websocket in description maps to worker message")
    func websocketErrorReturnsWorkerMessage() {
        let error = NSError(
            domain: "io.livekit.swift-sdk",
            code: -1,
            userInfo: [NSLocalizedDescriptionKey: "WebSocket handshake failed."]
        )
        let result = VoiceSession.humanizeConnectError(error)
        #expect(result.lowercased().contains("worker"))
    }

    // Test 4: Unknown error returns the generic fallback message
    @Test("Unknown error returns generic fallback message")
    func unknownErrorReturnsGenericFallback() {
        let error = NSError(
            domain: "com.example.unknown",
            code: 9999,
            userInfo: [NSLocalizedDescriptionKey: "Something went wrong."]
        )
        let result = VoiceSession.humanizeConnectError(error)
        #expect(result.lowercased().contains("couldn't connect") || result.lowercased().contains("try again"))
    }
}
