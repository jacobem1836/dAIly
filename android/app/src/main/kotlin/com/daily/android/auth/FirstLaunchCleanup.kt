package com.daily.android.auth

import android.content.Context

/**
 * Clears stale TokenStore entries on first launch after a fresh install.
 *
 * SharedPreferences flag is cleared when app data is wiped (uninstall + reinstall),
 * which is exactly when stale tokens would be present. This mirrors iOS T-19-15
 * (UserDefaults flag pattern).
 *
 * Threat: T-20-13 — prevents stale tokens from a previous install being reused.
 */
object FirstLaunchCleanup {
    private const val PREFS = "com.daily.android.flags"
    private const val KEY = "hasLaunchedBefore"

    suspend fun runIfNeeded(context: Context, tokenStore: TokenStore) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getBoolean(KEY, false)) return
        tokenStore.clearAll()
        prefs.edit().putBoolean(KEY, true).apply()
    }
}
