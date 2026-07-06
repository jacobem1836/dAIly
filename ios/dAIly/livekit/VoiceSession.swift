import Foundation
import LiveKit
import Combine

// MARK: - Public Types

public enum VoiceSessionState: Equatable {
    case idle
    case connecting
    case listening
    case speaking
    case reconnecting
    /// Transient failure — user can tap Retry to re-run connect().
    /// Distinct from `.error` which is a terminal state routing to onboarding.
    case retryable(String)
    case error(String)
}

public enum VoiceSessionError: Error, Equatable {
    case notAuthenticated
    case tokenFetchFailed
    case connectFailed(String)
}

// MARK: - VoiceSession

/// Owns the LiveKit Room lifecycle and drives a published state machine.
///
/// Connection flow:
///   1. Loads access JWT from Keychain
///   2. Fetches a LiveKit room token from POST /livekit/token via LiveKitTokenSource
///   3. On 401: calls RefreshBackoff.refreshWithBackoff() (3 attempts: 0→0.5s→1s)
///      - Transient exhaustion → .retryable state + user-facing Retry affordance
///      - Hard 401 (invalid refresh token) → .error("re_pair_required") — VoiceView
///        observes this specific value and calls AppState.signOut() so the app root
///        routes back to pairing instead of leaving the user stuck on a broken voice
///        screen with a Retry that can never succeed (T-22-xx re-pair dead end fix).
///   4. Connects to LiveKit room with mic enabled (ConnectOptions.enableMicrophone: true)
///   5. An 8-second timeout fires if the room never reaches .listening state (T-19-22)
///   6. A 30-second timeout fires if reconnecting does not recover (T-19-28)
///   7. roomDidDisconnect with non-nil error surfaces .error("disconnected: …") (T-19-29)
///   8. scenePhase transitions: handleBackground() pauses; handleForeground() reconnects if live
///
/// IMPORTANT: Do NOT disable AudioManager's automatic audio session configuration.
/// The LiveKit SDK auto-configures AVAudioSession to .playAndRecord + .voiceChat, activating
/// iOS hardware AEC automatically (T-19-24, MOB-01). Overriding this disables hardware AEC.
@MainActor
public final class VoiceSession: ObservableObject {
    @Published public private(set) var state: VoiceSessionState = .idle

    private let tokenSource: LiveKitTokenSource
    private let auth: AuthService
    private let keychain: KeychainStore
    private var room: Room?
    private var roomDelegate: SessionRoomDelegate?
    private var listeningTimeoutTask: Task<Void, Never>?
    private var agentJoinTimeoutTask: Task<Void, Never>?
    private var reconnectTimeoutTask: Task<Void, Never>?

    /// Tracks whether a live session was interrupted by backgrounding.
    /// Set by handleBackground() when the app leaves foreground with an active session.
    /// Cleared by handleForeground() after a reconnect attempt or when already idle.
    private var shouldResume: Bool = false

    /// How long to wait, after the room connects, for the agent to join and
    /// start speaking before surfacing an actionable error (T-22-01).
    private static let agentJoinTimeout: Duration = .seconds(20)

    public init(tokenSource: LiveKitTokenSource,
                auth: AuthService,
                keychain: KeychainStore = .shared) {
        self.tokenSource = tokenSource
        self.auth = auth
        self.keychain = keychain
    }

    // MARK: - Public API

    public func connect() async throws {
        state = .connecting
        guard var jwt = keychain.load(key: "access_token") else {
            state = .error("not_authenticated")
            throw VoiceSessionError.notAuthenticated
        }

        var lkToken: LiveKitToken
        do {
            lkToken = try await tokenSource.fetchToken(accessJWT: jwt)
        } catch LiveKitTokenError.unauthorized {
            // Refresh with exponential backoff: 3 attempts (0 → 0.5 s → 1 s).
            // See RefreshBackoff for constants. Hard 401 throws AuthError.unauthorized
            // immediately; transient exhaustion throws the last network error.
            do {
                try await RefreshBackoff.refreshWithBackoff(auth)
            } catch AuthError.unauthorized {
                // Invalid refresh token — terminal failure, user must re-pair.
                // Route via the dedicated sentinel so the UI can sign the user
                // out instead of offering a Retry that will fail forever.
                state = .error("re_pair_required")
                throw VoiceSessionError.notAuthenticated
            } catch {
                // Transient network failure after all backoff attempts exhausted.
                // Surface a retryable state so the UI can offer a Retry button.
                state = .retryable("auth_refresh_failed")
                throw VoiceSessionError.notAuthenticated
            }
            guard let newJwt = keychain.load(key: "access_token") else {
                state = .retryable("auth_refresh_failed")
                throw VoiceSessionError.notAuthenticated
            }
            jwt = newJwt
            do {
                lkToken = try await tokenSource.fetchToken(accessJWT: jwt)
            } catch {
                state = .retryable("token_fetch_after_refresh_failed")
                throw VoiceSessionError.tokenFetchFailed
            }
        } catch {
            state = .error("token_fetch_failed")
            throw VoiceSessionError.tokenFetchFailed
        }

        let newRoom = Room()
        let delegate = SessionRoomDelegate(owner: self)
        newRoom.add(delegate: delegate)
        self.room = newRoom
        self.roomDelegate = delegate

        do {
            try await newRoom.connect(
                url: lkToken.url,
                token: lkToken.token,
                connectOptions: ConnectOptions(enableMicrophone: true)
            )
        } catch {
            state = .error(Self.humanizeConnectError(error))
            throw VoiceSessionError.connectFailed(String(describing: error))
        }

        // 8-second timeout: if the room is connected but agent hasn't produced a listening state,
        // surface an error so the UI doesn't hang indefinitely (T-19-22)
        listeningTimeoutTask?.cancel()
        listeningTimeoutTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            await MainActor.run { [weak self] in
                guard let self else { return }
                if case .connecting = self.state {
                    self.state = .error("agent_unreachable")
                }
            }
        }
    }

    public func disconnect() async {
        shouldResume = false
        listeningTimeoutTask?.cancel()
        listeningTimeoutTask = nil
        agentJoinTimeoutTask?.cancel()
        agentJoinTimeoutTask = nil
        reconnectTimeoutTask?.cancel()
        reconnectTimeoutTask = nil
        await room?.disconnect()
        room = nil
        roomDelegate = nil
        state = .idle
    }

    /// Retry a failed connection after a `.retryable` state.
    /// No-ops if the session is not in a retryable state.
    public func retry() async {
        guard case .retryable = state else { return }
        try? await connect()
    }

    // MARK: - scenePhase lifecycle handling

    /// Called when the app transitions to the background.
    /// Tears down the LiveKit room gracefully and records that a session was live
    /// so `handleForeground()` can reconnect when the app returns.
    /// Cancels all in-flight timers to prevent spurious timeout errors while suspended.
    public func handleBackground() async {
        let wasActive: Bool
        switch state {
        case .listening, .speaking, .connecting, .reconnecting:
            wasActive = true
        default:
            wasActive = false
        }
        // Cancel timers before disconnect so they do not fire during suspension
        listeningTimeoutTask?.cancel()
        listeningTimeoutTask = nil
        agentJoinTimeoutTask?.cancel()
        agentJoinTimeoutTask = nil
        reconnectTimeoutTask?.cancel()
        reconnectTimeoutTask = nil
        if wasActive {
            // Gracefully close room without clearing shouldResume
            await room?.disconnect()
            room = nil
            roomDelegate = nil
            state = .idle
            shouldResume = true
        }
    }

    /// Called when the app returns to the foreground.
    /// If a session was live before backgrounding, attempts to reconnect using
    /// the existing connect() path (which includes backoff token refresh).
    public func handleForeground() async {
        guard shouldResume else { return }
        shouldResume = false
        try? await connect()
    }

    // MARK: - Debug PTT (D-07) — never surfaced in production UI

    /// Mute/unmute the local mic. Only active when `DebugFlags.pttEnabled` is true in DEBUG builds.
    public func setMicrophone(enabled: Bool) async {
        #if DEBUG
        guard DebugFlags.pttEnabled, let room = room else { return }
        _ = try? await room.localParticipant.setMicrophone(enabled: enabled)
        #endif
    }

    // MARK: - Delegate forwarding (fileprivate — called from SessionRoomDelegate)

    fileprivate func handleConnectionState(_ newState: ConnectionState) {
        switch newState {
        case .connected:
            reconnectTimeoutTask?.cancel()
            reconnectTimeoutTask = nil
            state = .listening
            // Agent-join timeout: if no agent participant speaks within
            // Self.agentJoinTimeout of the room connecting, surface an actionable
            // error. This guards against the worker not running or pointing at a
            // different LiveKit server — without this the UI stays in .listening
            // forever (T-22-01).
            agentJoinTimeoutTask?.cancel()
            agentJoinTimeoutTask = Task { [weak self] in
                try? await Task.sleep(for: Self.agentJoinTimeout)
                await MainActor.run { [weak self] in
                    guard let self else { return }
                    if case .listening = self.state {
                        self.state = .error("Voice agent didn't join — the worker may not be running, or LIVEKIT_URL is misconfigured. Check the runbook.")
                    }
                }
            }
        case .reconnecting:
            state = .reconnecting
            // 30-second reconnect timeout — if state hasn't recovered, surface error (T-19-28)
            reconnectTimeoutTask?.cancel()
            reconnectTimeoutTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                await MainActor.run { [weak self] in
                    guard let self else { return }
                    if case .reconnecting = self.state {
                        self.state = .error("reconnect_timeout")
                    }
                }
            }
        case .disconnected:
            reconnectTimeoutTask?.cancel()
            reconnectTimeoutTask = nil
            // Only reset to idle on clean disconnect; error disconnects are handled by handleDisconnect
            if case .reconnecting = state {
                // Reconnect gave up — keep existing error or set disconnected error
                state = .error("disconnected")
            } else if case .error = state {
                // Already in error state — leave it
                break
            } else {
                state = .idle
            }
        case .connecting:
            state = .connecting
        case .disconnecting:
            break
        @unknown default:
            break
        }
    }

    fileprivate func handleAgentSpeaking(_ speaking: Bool) {
        if speaking {
            // Agent has joined and is speaking — permanently cancel the join timeout.
            // Once the agent proves it joined by speaking, we never re-arm this timer.
            // Bug fix: previously agentJoinTimeoutTask remained running after speaking=true
            // fired and was cancelled, meaning it could fire spuriously during post-briefing
            // silence if total elapsed time exceeded 60s (T-22-01 regression).
            agentJoinTimeoutTask?.cancel()
            agentJoinTimeoutTask = nil
            state = .speaking
        } else if case .speaking = state {
            // Agent stopped speaking — return to listening.
            // agentJoinTimeoutTask is already nil here (cancelled above), so no
            // spurious "agent didn't join" error can fire during silence.
            state = .listening
        }
    }

    /// Called when the room disconnects with a non-nil error (unexpected disconnect).
    /// Clean user-initiated disconnects go through disconnect() which sets .idle directly.
    fileprivate func handleDisconnect(error: Error?) {
        reconnectTimeoutTask?.cancel()
        reconnectTimeoutTask = nil
        listeningTimeoutTask?.cancel()
        listeningTimeoutTask = nil
        agentJoinTimeoutTask?.cancel()
        agentJoinTimeoutTask = nil
        if let error = error {
            state = .error(Self.humanizeConnectError(error))
        }
        // No else: clean disconnects arrive via didUpdateConnectionState(.disconnected)
        // which already transitions to .idle via handleConnectionState
    }

    // MARK: - Error mapping (D-01)

    /// Maps LiveKit / NSURLError values to user-facing strings.
    /// Internal so unit tests can call it; not part of the public API.
    nonisolated internal static func humanizeConnectError(_ error: Error) -> String {
        let ns = error as NSError
        // NSURLError codes (transport-level — pre-WebSocket)
        if ns.domain == NSURLErrorDomain {
            switch ns.code {
            case NSURLErrorNotConnectedToInternet:
                return "You appear to be offline. Check your internet connection and try again."
            case NSURLErrorTimedOut:
                return "Voice server didn't respond. The backend may be down."
            case NSURLErrorCannotConnectToHost, NSURLErrorCannotFindHost:
                return "Couldn't reach the voice server. Check your internet connection."
            default:
                break
            }
        }
        // Anything LiveKit raises post-DNS/TCP — usually means the URL is wrong
        // or the LiveKit server / agent worker isn't reachable from this host.
        let desc = ns.localizedDescription.lowercased()
        if desc.contains("websocket") || desc.contains("handshake") {
            return "Couldn't open a voice session — the worker may not be running."
        }
        if ns.domain.contains("livekit") {
            return "Voice server rejected the connection. The worker may be offline or misconfigured."
        }
        return "Couldn't connect to voice. Try again — if this keeps happening, check the worker is running."
    }

    // MARK: - Test hooks (DEBUG only)

    #if DEBUG
    /// Force-set state directly — for unit tests only.
    public func _testForceState(_ s: VoiceSessionState) { state = s }

    /// Trigger handleConnectionState — for unit tests only.
    public func _testHandleConnectionState(_ s: ConnectionState) { handleConnectionState(s) }

    /// Trigger handleAgentSpeaking — for unit tests only.
    public func _testHandleAgentSpeaking(_ speaking: Bool) { handleAgentSpeaking(speaking) }

    /// Trigger handleDisconnect with an error — for unit tests only.
    public func _testHandleDisconnect(error: Error?) { handleDisconnect(error: error) }

    /// Read shouldResume flag — for unit tests only.
    public var _testShouldResume: Bool { shouldResume }
    #endif
}

// MARK: - SessionRoomDelegate

/// Bridges LiveKit RoomDelegate callbacks into VoiceSession state transitions.
/// Isolated to @MainActor via Task dispatch — safe for Swift 6 strict concurrency.
@MainActor
private final class SessionRoomDelegate: NSObject, RoomDelegate {
    weak var owner: VoiceSession?

    init(owner: VoiceSession) {
        self.owner = owner
    }

    nonisolated func room(
        _ room: Room,
        didUpdateConnectionState newState: ConnectionState,
        from oldState: ConnectionState
    ) {
        Task { @MainActor [weak self] in
            self?.owner?.handleConnectionState(newState)
        }
    }

    // Agent audio activity detection: observe the speaking participants list.
    // RoomDelegate.room(_:didUpdateSpeakingParticipants:) is fired whenever the
    // set of actively-speaking participants changes. Any remote participant in the
    // list is considered "speaking" — any absence means they stopped.
    //
    // Note: room(_:participant:didUpdateIsSpeaking:) does NOT exist in the LiveKit
    // Swift SDK 2.x RoomDelegate protocol — using that name silently produces a
    // dead method that never fires. The correct API is didUpdateSpeakingParticipants.
    nonisolated func room(_ room: Room, didUpdateSpeakingParticipants participants: [Participant]) {
        let agentSpeaking = participants.contains { $0 is RemoteParticipant }
        Task { @MainActor [weak self] in
            self?.owner?.handleAgentSpeaking(agentSpeaking)
        }
    }

    /// Called when the room disconnects unexpectedly (error != nil) or cleanly (error == nil).
    /// The clean path is already handled by didUpdateConnectionState(.disconnected).
    /// Here we forward only unexpected disconnects (non-nil error) to surface user-visible feedback.
    nonisolated func room(_ room: Room, didDisconnectWithError error: LiveKitError?) {
        guard let error = error else { return }
        Task { @MainActor [weak self] in
            self?.owner?.handleDisconnect(error: error)
        }
    }
}
