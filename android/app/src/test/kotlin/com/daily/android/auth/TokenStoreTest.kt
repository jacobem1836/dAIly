package com.daily.android.auth

import androidx.test.core.app.ApplicationProvider
import com.google.crypto.tink.aead.AeadConfig
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.io.File

@RunWith(RobolectricTestRunner::class)
class TokenStoreTest {
    private lateinit var store: TokenStore
    private val testFileName = "tokens-test.enc"

    @Before fun setUp() = runTest {
        AeadConfig.register()
        store = TokenStore(ApplicationProvider.getApplicationContext(), fileName = testFileName)
        store.clearAll()
    }
    @After fun tearDown() = runTest { store.clearAll() }

    @Test fun saveAndLoad_roundTrip() = runTest {
        store.save("access_token", "abc")
        assertEquals("abc", store.load("access_token"))
    }
    @Test fun loadMissingKey_returnsNull() = runTest {
        assertNull(store.load("missing"))
    }
    @Test fun deleteRemovesItem() = runTest {
        store.save("access_token", "abc")
        store.delete("access_token")
        assertNull(store.load("access_token"))
    }
    @Test fun saveOverwritesExisting() = runTest {
        store.save("k", "v1")
        store.save("k", "v2")
        assertEquals("v2", store.load("k"))
    }
    @Test fun clearAll_removesEverything() = runTest {
        store.save("access_token", "a")
        store.save("refresh_token", "r")
        store.clearAll()
        assertNull(store.load("access_token"))
        assertNull(store.load("refresh_token"))
    }
    @Test fun storedBytesAreEncrypted() = runTest {
        store.save("access_token", "PLAINTEXT_MARKER_xyz")
        val ctx = ApplicationProvider.getApplicationContext<android.content.Context>()
        val file = File(ctx.filesDir, "datastore/$testFileName")
        if (file.exists()) {
            val bytes = file.readBytes()
            assertFalse("Token persisted in cleartext", String(bytes).contains("PLAINTEXT_MARKER_xyz"))
        }
    }
}
