package com.daily.android.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.daily.android.auth.AuthService
import kotlinx.coroutines.launch

private enum class PairingPhase { IDLE, SENT }

/**
 * Two-state pairing screen mirroring iOS PairingView.
 *
 * IDLE  — email text field + "Send magic link" button
 * SENT  — confirmation message + "Use a different email" option
 *
 * Deep-link completion is handled in MainActivity.onNewIntent / handleDeepLink,
 * not in this composable.
 */
@Composable
fun PairingScreen(auth: AuthService) {
    var email by remember { mutableStateOf("") }
    var phase by remember { mutableStateOf(PairingPhase.IDLE) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when (phase) {
            PairingPhase.IDLE -> {
                Text("Sign in to dAIly", style = MaterialTheme.typography.headlineSmall)
                Spacer(Modifier.height(24.dp))
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                )
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = {
                        scope.launch {
                            error = null
                            try {
                                auth.sendLink(email)
                                phase = PairingPhase.SENT
                            } catch (e: Exception) {
                                error = e.message ?: "send failed"
                            }
                        }
                    },
                    enabled = email.contains("@"),
                ) {
                    Text("Send magic link")
                }
                error?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
            PairingPhase.SENT -> {
                Text("Check your email", style = MaterialTheme.typography.headlineSmall)
                Spacer(Modifier.height(8.dp))
                Text("Tap the magic link to finish signing in.")
                Spacer(Modifier.height(24.dp))
                TextButton(onClick = { phase = PairingPhase.IDLE; error = null }) {
                    Text("Use a different email")
                }
            }
        }
    }
}
