package com.daily.android.livekit

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.daily.android.auth.AuthService
import com.daily.android.auth.TokenStore
import io.livekit.android.LiveKit
import io.livekit.android.events.RoomEvent
import io.livekit.android.events.collect
import io.livekit.android.room.Room
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Six-state voice session state machine, mirroring iOS VoiceSessionState.
 */
sealed class VoiceState {
    object Idle : VoiceState()
    object Connecting : VoiceState()
    object Listening : VoiceState()
    object Speaking : VoiceState()
    object Reconnecting : VoiceState()
    data class Error(val message: String) : VoiceState()
}

/**
 * AndroidViewModel wrapping the LiveKit Room lifecycle.
 *
 * Key design notes:
 * - viewModelScope is Dispatchers.Main-bound; no explicit @MainActor needed.
 * - Room events collected via room.events Flow (RESEARCH §Pattern 2; Kotlin Flows replace iOS RoomDelegate).
 * - IMPORTANT: No custom audio options passed to LiveKit.create —
 *   default WebRTC AEC preserved (RESEARCH §Pitfall 2 / T-20-22).
 * - Single-retry on 401 mirrors iOS T-19-21 (T-20-19).
 * - 8s unreachable timeout mirrors iOS T-19-22 (T-20-20).
 * - 30s reconnect timeout mirrors iOS T-19-28 (T-20-21).
 */
class VoiceSession(
    application: Application,
    private val tokenSource: LiveKitTokenSource,
    private val auth: AuthService,
    private val tokenStore: TokenStore,
) : AndroidViewModel(application) {

    private val _state = MutableStateFlow<VoiceState>(VoiceState.Idle)
    val state: StateFlow<VoiceState> = _state.asStateFlow()

    private var room: Room? = null
    private var unreachableTimeoutJob: Job? = null
    private var reconnectTimeoutJob: Job? = null
    private var eventsJob: Job? = null

    fun connect() {
        viewModelScope.launch {
            _state.value = VoiceState.Connecting
            var jwt = tokenStore.load("access_token") ?: run {
                _state.value = VoiceState.Error("not_authenticated"); return@launch
            }

            // Single-retry on 401 (T-20-19 — mirror of iOS T-19-21)
            val lkToken: LiveKitToken = try {
                tokenSource.fetchToken(jwt)
            } catch (e: LiveKitTokenError.Unauthorized) {
                try { auth.refresh() } catch (_: Exception) {
                    _state.value = VoiceState.Error("auth_refresh_failed"); return@launch
                }
                jwt = tokenStore.load("access_token") ?: run {
                    _state.value = VoiceState.Error("auth_refresh_failed"); return@launch
                }
                try { tokenSource.fetchToken(jwt) } catch (_: Exception) {
                    _state.value = VoiceState.Error("token_unauthorized"); return@launch
                }
            } catch (e: Exception) {
                _state.value = VoiceState.Error("token_fetch_failed"); return@launch
            }

            // IMPORTANT: do NOT pass custom audio options to LiveKit.create.
            // SDK default activates WebRTC AEC (RESEARCH §Pitfall 2 — T-20-22).
            val r = LiveKit.create(getApplication())
            room = r

            try {
                r.connect(url = lkToken.url, token = lkToken.token)
                r.localParticipant.setMicrophoneEnabled(true)
            } catch (e: Exception) {
                _state.value = VoiceState.Error("connect_failed: ${e.message?.take(60)}")
                return@launch
            }

            // 8s unreachable timeout (T-20-20 — mirror of iOS T-19-22)
            unreachableTimeoutJob?.cancel()
            unreachableTimeoutJob = viewModelScope.launch {
                delay(8_000)
                if (_state.value is VoiceState.Connecting) {
                    _state.value = VoiceState.Error("agent_unreachable")
                }
            }

            // Collect Room events as Flow (RESEARCH §Pattern 2)
            eventsJob?.cancel()
            eventsJob = viewModelScope.launch {
                r.events.collect { event ->
                    when (event) {
                        is RoomEvent.Connected -> {
                            unreachableTimeoutJob?.cancel()
                            reconnectTimeoutJob?.cancel()
                            _state.value = VoiceState.Listening
                        }
                        is RoomEvent.Reconnecting -> {
                            _state.value = VoiceState.Reconnecting
                            // 30s reconnect timeout (T-20-21 — mirror of iOS T-19-28)
                            reconnectTimeoutJob?.cancel()
                            reconnectTimeoutJob = viewModelScope.launch {
                                delay(30_000)
                                if (_state.value is VoiceState.Reconnecting) {
                                    _state.value = VoiceState.Error("reconnect_timeout")
                                }
                            }
                        }
                        is RoomEvent.Reconnected -> {
                            reconnectTimeoutJob?.cancel()
                            _state.value = VoiceState.Listening
                        }
                        is RoomEvent.Disconnected -> {
                            reconnectTimeoutJob?.cancel()
                            unreachableTimeoutJob?.cancel()
                            val err = event.error
                            if (err != null) {
                                _state.value = VoiceState.Error("disconnected: ${err.message?.take(60)}")
                            } else if (_state.value !is VoiceState.Error) {
                                _state.value = VoiceState.Idle
                            }
                        }
                        is RoomEvent.ParticipantSpeakingChanged -> {
                            // Identity-filter: only count remote (agent) speakers
                            if (event.participant.identity != r.localParticipant.identity) {
                                handleAgentSpeaking(event.participant.isSpeaking)
                            }
                        }
                        else -> Unit
                    }
                }
            }
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            unreachableTimeoutJob?.cancel(); unreachableTimeoutJob = null
            reconnectTimeoutJob?.cancel(); reconnectTimeoutJob = null
            eventsJob?.cancel(); eventsJob = null
            room?.disconnect()
            room = null
            _state.value = VoiceState.Idle
        }
    }

    /**
     * Mute or unmute the microphone.
     * Active only when [DebugFlags.pttEnabled] in DEBUG builds (D-07 mirror — T-20-23).
     */
    fun setMicrophone(enabled: Boolean) {
        if (!DebugFlags.pttEnabled) return
        viewModelScope.launch {
            room?.localParticipant?.setMicrophoneEnabled(enabled)
        }
    }

    private fun handleAgentSpeaking(speaking: Boolean) {
        if (speaking) _state.value = VoiceState.Speaking
        else if (_state.value is VoiceState.Speaking) _state.value = VoiceState.Listening
    }

    // ── DEBUG-only test hooks (mirror of iOS _test* prefixed functions) ──────────

    internal fun _testForceState(s: VoiceState) { _state.value = s }
    internal fun _testHandleAgentSpeaking(speaking: Boolean) = handleAgentSpeaking(speaking)
    internal fun _testForceReconnecting() { _state.value = VoiceState.Reconnecting }
}
