package com.daily.android.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.daily.android.livekit.VoiceSession
import com.daily.android.livekit.VoiceState

/**
 * Full-screen voice interaction UI. Renders [ConnectionIndicator] + action button driven by
 * [VoiceSession.state].
 *
 * Button behaviour:
 *   Idle   → "Start"  → session.connect()
 *   Active (Connecting/Listening/Speaking/Reconnecting) → "End" (OutlinedButton) → session.disconnect()
 *   Error  → "Retry"  → session.connect()
 *
 * D-06: Auto VAD only — no push-to-talk button in production UI. Debug mute lives in VoiceSession.setMicrophone.
 */
@Composable
fun VoiceScreen(session: VoiceSession) {
    val state by session.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Spacer(Modifier.weight(1f))

        ConnectionIndicator(state = state)

        if (state is VoiceState.Error) {
            Spacer(Modifier.height(16.dp))
            Text(
                text = (state as VoiceState.Error).message.take(60),
                color = MaterialTheme.colorScheme.error,
                textAlign = TextAlign.Center,
                modifier = Modifier.widthIn(max = 280.dp),
            )
        }

        Spacer(Modifier.height(32.dp))

        when (state) {
            VoiceState.Idle ->
                Button(onClick = { session.connect() }) { Text("Start") }

            is VoiceState.Error ->
                Button(onClick = { session.connect() }) { Text("Retry") }

            VoiceState.Connecting,
            VoiceState.Listening,
            VoiceState.Speaking,
            VoiceState.Reconnecting ->
                OutlinedButton(onClick = { session.disconnect() }) { Text("End") }
        }

        // Auto VAD only — no manual mute button in production UI (D-06 / D-07).
        // Debug mute toggle lives in VoiceSession.setMicrophone (gated by DebugFlags in DebugFlags.kt).

        Spacer(Modifier.weight(1f))
    }
}
