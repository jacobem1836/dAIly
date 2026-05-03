package com.daily.android.livekit

import com.daily.android.BuildConfig

/**
 * Debug feature flags.
 *
 * All flags short-circuit to false in Release builds (T-20-23).
 * D-07 mirror: PTT (push-to-talk) is never surfaced in production UI.
 */
object DebugFlags {
    /// Push-to-talk: surfaced only in DEBUG builds (D-07 mirror — never in production UI).
    val pttEnabled: Boolean = BuildConfig.DEBUG && false  // flip to true locally to enable
}
