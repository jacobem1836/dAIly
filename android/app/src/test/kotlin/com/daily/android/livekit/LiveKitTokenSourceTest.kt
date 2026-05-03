package com.daily.android.livekit

import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class LiveKitTokenSourceTest {

    private lateinit var server: MockWebServer
    private lateinit var tokenSource: LiveKitTokenSource

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        tokenSource = LiveKitTokenSource(
            baseUrl = server.url("").toString().trimEnd('/'),
            client = OkHttpClient(),
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    /** Test 1: POST /livekit/token is issued with correct Authorization Bearer header. */
    @Test fun `POST to livekit token with Bearer JWT header`() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"token":"T","room":"R","livekit_url":"wss://lk"}""")
        )

        tokenSource.fetchToken("JWT123")

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/livekit/token", recorded.path)
        assertEquals("Bearer JWT123", recorded.getHeader("Authorization"))
    }

    /** Test 2: 200 response with correct JSON parses to LiveKitToken. */
    @Test fun `200 response parses to LiveKitToken correctly`() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"token":"T","room":"R","livekit_url":"wss://lk"}""")
        )

        val result = tokenSource.fetchToken("jwt")

        assertEquals(LiveKitToken(token = "T", room = "R", url = "wss://lk"), result)
    }

    /** Test 3: 401 response throws LiveKitTokenError.Unauthorized. */
    @Test fun `401 response throws Unauthorized`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401))

        var threw: LiveKitTokenError? = null
        try {
            tokenSource.fetchToken("jwt")
        } catch (e: LiveKitTokenError.Unauthorized) {
            threw = e
        }

        assertTrue("Expected Unauthorized to be thrown", threw is LiveKitTokenError.Unauthorized)
    }

    /** Test 4: Malformed JSON body throws LiveKitTokenError.Decoding. */
    @Test fun `malformed JSON throws Decoding`() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"foo":"bar"}""")
        )

        var threw: LiveKitTokenError? = null
        try {
            tokenSource.fetchToken("jwt")
        } catch (e: LiveKitTokenError.Decoding) {
            threw = e
        }

        assertTrue("Expected Decoding to be thrown", threw is LiveKitTokenError.Decoding)
    }
}
