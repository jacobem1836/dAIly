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
///   3. On 401: calls auth.refresh() once and retries; second 401 surfaces .error
///   4. Connects to LiveKit room with mic enabled (ConnectOptions.enableMicrophone: true)
///   5. An 8-second timeout fires if the room never reaches .listening state (T-19-22)
///   6. A 30-second timeout fires if reconnecting does not recover (T-19-28)
///   7. roomDidDisconnect with non-nil error surfaces .error("disconnected: …") (T-19-29)
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
    private var reconnectTimeoutTask: Task<Void, Never>?

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
            // Attempt exactly one auth refresh before giving up (T-19-21)
            do {
                try await auth.refresh()
            } catch {
                state = .error("auth_refresh_failed")
                throw VoiceSessionError.notAuthenticated
            }
            guard let newJwt = keychain.load(key: "access_token") else {
                state = .error("auth_refresh_failed")
                throw VoiceSessionError.notAuthenticated
            }
            jwt = newJwt
            do {
                lkToken = try await tokenSource.fetchToken(accessJWT: jwt)
            } catch {
                state = .error("token_unauthorized")
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
            state = .error("connect_failed:\(error)")
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
        listeningTimeoutTask?.cancel()
        listeningTimeoutTask = nil
        reconnectTimeoutTask?.cancel()
        reconnectTimeoutTask = nil
        await room?.disconnect()
        room = nil
        roomDelegate = nil
        state = .idle
    }

    // MARK: - Debug PTT (D-07) — never surfaced in production UI

    /// Mute/unmute the local mic. Only active when `DebugFlags.pttEnabled` is true in DEBUG builds.
    public func setMicrophone(enabled: Bool) async {
        #if DEBUG
        guard DebugFlags.pttEnabled, let room = room else { return }
        try? await room.localParticipant.setMicrophone(enabled: enabled)
        #endif
    }

    // MARK: - Delegate forwarding (fileprivate — called from SessionRoomDelegate)

    fileprivate func handleConnectionState(_ newState: ConnectionState) {
        switch newState {
        case .connected:
            reconnectTimeoutTask?.cancel()
            reconnectTimeoutTask = nil
            state = .listening
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
        @unknown default:
            break
        }
    }

    fileprivate func handleAgentSpeaking(_ speaking: Bool) {
        if speaking {
            state = .speaking
        } else if case .speaking = state {
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
        if let error = error {
            let msg = String(error.localizedDescription.prefix(60))
            state = .error("disconnected: \(msg)")
        }
        // No else: clean disconnects arrive via didUpdateConnectionState(.disconnected)
        // which already transitions to .idle via handleConnectionState
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

    // Agent audio activity detection: observe isSpeaking on remote participants.
    // RoomDelegate.room(_:participant:didUpdateIsSpeaking:) is the idiomatic callback.
    // Falls back to polling audioLevel at 10Hz if isSpeaking is unavailable.
    nonisolated func room(_ room: Room, participant: RemoteParticipant, didUpdateIsSpeaking speaking: Bool) {
        Task { @MainActor [weak self] in
            self?.owner?.handleAgentSpeaking(speaking)
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
