package com.daily.android

import android.app.Application
import com.google.crypto.tink.aead.AeadConfig

class DailyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AeadConfig.register()  // Tink one-time init for AES-256-GCM
    }
}
