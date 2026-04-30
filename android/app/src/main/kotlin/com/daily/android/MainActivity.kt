package com.daily.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Surface
import androidx.compose.material3.Text

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            Surface { Text("dAIly — voice screen wired in Plan 20-04") }
        }
    }
    // onNewIntent + deep-link wiring added in Plan 20-03
}
