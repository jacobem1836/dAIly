package com.daily.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.lifecycleScope
import com.daily.android.auth.AuthService
import com.daily.android.auth.FirstLaunchCleanup
import com.daily.android.auth.PairCodeUriParser
import com.daily.android.auth.TokenStore
import com.daily.android.ui.PairingScreen
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var tokenStore: TokenStore
    private lateinit var auth: AuthService
    private val appState = AppState()

    // BASE_URL replaced by Config.kt in Plan 20-05
    private val backendBaseURL: String = "https://app.example.com"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        tokenStore = TokenStore(applicationContext)
        auth = AuthService(backendBaseURL, tokenStore)

        lifecycleScope.launch {
            FirstLaunchCleanup.runIfNeeded(applicationContext, tokenStore)
            appState.setAuthenticated(tokenStore.load("access_token") != null)
        }

        setContent {
            MaterialTheme {
                Surface {
                    val authed by appState.hasAccessToken.collectAsState()
                    if (authed) {
                        Text("Voice screen — Plan 20-04")
                    } else {
                        PairingScreen(auth = auth)
                    }
                }
            }
        }

        // Handle cold-launch deep link (App Links arriving in onCreate)
        handleDeepLink(intent)
    }

    /**
     * Called when the app is already running (singleTop) and a new deep link arrives.
     * T-20-15: Both cold-launch (onCreate) and warm-launch (onNewIntent) paths handled.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDeepLink(intent)
    }

    private fun handleDeepLink(intent: Intent?) {
        val uri = intent?.data ?: return
        val code = PairCodeUriParser.extractCode(uri) ?: return
        lifecycleScope.launch {
            try {
                auth.completePairing(code)
                appState.setAuthenticated(true)
            } catch (_: Exception) {
                // Surfaced in PairingScreen error state in Plan 20-05 polish
            }
        }
    }
}
