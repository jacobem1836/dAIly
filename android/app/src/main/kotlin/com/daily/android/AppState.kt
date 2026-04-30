package com.daily.android

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class AppState {
    private val _hasAccessToken = MutableStateFlow(false)
    val hasAccessToken: StateFlow<Boolean> = _hasAccessToken.asStateFlow()
    fun setAuthenticated(value: Boolean) { _hasAccessToken.value = value }
}
