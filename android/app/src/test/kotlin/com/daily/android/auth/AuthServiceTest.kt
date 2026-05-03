package com.daily.android.auth

import androidx.test.core.app.ApplicationProvider
import com.google.crypto.tink.aead.AeadConfig
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.time.Instant

@RunWith(RobolectricTestRunner::class)
class AuthServiceTest {
    private lateinit var server: MockWebServer
    private lateinit var store: TokenStore
    private lateinit var auth: AuthService

    @Before fun setUp() = runTest {
        AeadConfig.register()
        server = MockWebServer().apply { start() }
        store = TokenStore(ApplicationProvider.getApplicationContext(), fileName = "auth-test.enc")
        store.clearAll()
        auth = AuthService(server.url("/").toString().trimEnd('/'), store)
    }

    @After fun tearDown() = runTest {
        server.shutdown()
        store.clearAll()
    }

    @Test fun `sendLink posts email json and succeeds on 204`() = runTest {
        server.enqueue(MockResponse().setResponseCode(204))
        auth.sendLink("a@b.com")
        val rec = server.takeRequest()
        assertEquals("POST", rec.method)
        assertEquals("/auth/pair/send-link", rec.path)
        assertTrue(rec.body.readUtf8().contains("\"email\":\"a@b.com\""))
    }

    @Test fun `sendLink throws AuthError Server on 500`() = runTest {
        server.enqueue(MockResponse().setResponseCode(500))
        try {
            auth.sendLink("a@b.com")
            fail("Expected AuthError.Server")
        } catch (e: AuthError.Server) {
            assertEquals(500, e.code)
        }
    }

    @Test fun `completePairing returns PairingResult and persists tokens`() = runTest {
        server.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody("""{"access_token":"AT","refresh_token":"RT","expires_in":900}""")
            .addHeader("Content-Type", "application/json"))
        val result = auth.completePairing("123456")
        val rec = server.takeRequest()
        assertEquals("POST", rec.method)
        assertEquals("/auth/pair/complete", rec.path)
        assertTrue(rec.body.readUtf8().contains("\"code\":\"123456\""))
        assertEquals("AT", result.accessToken)
        assertEquals("RT", result.refreshToken)
        assertEquals("AT", store.load("access_token"))
        assertEquals("RT", store.load("refresh_token"))
        val expiresAtStr = store.load("access_token_expires_at")
        assertNotNull(expiresAtStr)
        // Must be parseable as ISO-8601 instant
        val parsed = Instant.parse(expiresAtStr)
        assertTrue(parsed.isAfter(Instant.now()))
    }

    @Test fun `completePairing throws AuthError Unauthorized on 401`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401))
        try {
            auth.completePairing("bad-code")
            fail("Expected AuthError.Unauthorized")
        } catch (e: AuthError.Unauthorized) {
            // expected
        }
    }

    @Test fun `refresh reads refresh token and updates access token`() = runTest {
        store.save("refresh_token", "RT_existing")
        server.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody("""{"access_token":"AT2","expires_in":900}""")
            .addHeader("Content-Type", "application/json"))
        auth.refresh()
        val rec = server.takeRequest()
        assertEquals("POST", rec.method)
        assertEquals("/auth/token/refresh", rec.path)
        assertTrue(rec.body.readUtf8().contains("\"refresh_token\":\"RT_existing\""))
        assertEquals("AT2", store.load("access_token"))
        val expiresAtStr = store.load("access_token_expires_at")
        assertNotNull(expiresAtStr)
        Instant.parse(expiresAtStr) // must not throw
    }
}
