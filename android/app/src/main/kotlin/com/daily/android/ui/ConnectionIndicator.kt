package com.daily.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.daily.android.livekit.VoiceState

/**
 * State indicator circle + label. Maps each VoiceState to a semantic colour and label.
 *
 * Idle        → grey      "Tap to start"
 * Connecting  → amber     "Connecting..."
 * Listening   → green     "Listening"
 * Speaking    → blue      "Speaking"
 * Reconnecting→ amber     "Reconnecting..."
 * Error       → red       error.message (truncated to 60 chars)
 */
@Composable
fun ConnectionIndicator(state: VoiceState) {
    val (color, label) = when (state) {
        VoiceState.Idle -> Color.Gray to "Tap to start"
        VoiceState.Connecting -> Color(0xFFFFC107) to "Connecting..."
        VoiceState.Listening -> Color(0xFF4CAF50) to "Listening"
        VoiceState.Speaking -> Color(0xFF2196F3) to "Speaking"
        VoiceState.Reconnecting -> Color(0xFFFFC107) to "Reconnecting..."
        is VoiceState.Error -> Color(0xFFF44336) to state.message.take(60)
    }
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
                .background(color)
        )
        Spacer(Modifier.height(12.dp))
        Text(label, style = MaterialTheme.typography.bodyLarge)
    }
}
