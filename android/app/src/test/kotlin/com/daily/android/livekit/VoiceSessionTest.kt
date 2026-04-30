package com.daily.android.livekit

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import com.daily.android.auth.AuthService
import com.daily.android.auth.AuthError
import com.daily.android.auth.TokenStore
import io.mockk.coEvery
import io.mockk.coJustRun
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class VoiceSessionTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var application: Application
    private lateinit var tokenStore: TokenStore
    private lateinit var tokenSource: LiveKitTokenSource
    private lateinit var auth: AuthService

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        application = ApplicationProvider.getApplicationContext()
        // Use a unique filename per test run to avoid DataStore conflicts
        tokenStore = TokenStore(application, "voice_test_${System.nanoTime()}.enc")
        tokenSource = mockk()
        auth = mockk()
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun makeSession(): VoiceSession =
        VoiceSession(application, tokenSource, auth, tokenStore)

    /** Test 1: Initial state is Idle. */
    @Test fun `initial state is Idle`() {
        val session = makeSession()
        assertEquals(VoiceState.Idle, session.state.value)
    }

    /** Test 2: connect() with no access_token → Error("not_authenticated"). */
    @Test fun `connect with no access token transitions to Error not_authenticated`() = runTest {
        val session = makeSession()
        // TokenStore empty — no access_token

        session.connect()
        advanceUntilIdle()

        assertTrue(
            "Expected Error(not_authenticated) but got ${session.state.value}",
            session.state.value == VoiceState.Error("not_authenticated")
        )
    }

    /** Test 3: 401 once then refresh + second fetch succeeds → VoiceState is not Error("token_unauthorized"). */
    @Test fun `single 401 then refresh and second fetch does not reach token_unauthorized`() = runTest {
        val session = makeSession()
        // Seed a token so connect() gets past the null check
        tokenStore.save("access_token", "old_jwt")

        var callCount = 0
        coEvery { tokenSource.fetchToken(any()) } answers {
            callCount++
            if (callCount == 1) throw LiveKitTokenError.Unauthorized
            else throw LiveKitTokenError.Network("test_abort") // abort before Room.connect
        }
        coJustRun { auth.refresh() }
        // After refresh, TokenStore still has old_jwt — session re-reads it

        session.connect()
        advanceUntilIdle()

        // Should not be token_unauthorized — the single retry was attempted
        assertTrue(
            "Should not be token_unauthorized after single retry",
            session.state.value != VoiceState.Error("token_unauthorized")
        )
    }

    /** Test 4: 401 twice → Error("token_unauthorized"). */
    @Test fun `double 401 transitions to Error token_unauthorized`() = runTest {
        val session = makeSession()
        tokenStore.save("access_token", "jwt")

        coEvery { tokenSource.fetchToken(any()) } throws LiveKitTokenError.Unauthorized
        coJustRun { auth.refresh() }

        session.connect()
        advanceUntilIdle()

        assertEquals(VoiceState.Error("token_unauthorized"), session.state.value)
    }

    /** Test 5: _testForceState(Listening) then _testHandleAgentSpeaking(true) → Speaking. */
    @Test fun `force Listening then agent speaking true transitions to Speaking`() {
        val session = makeSession()

        session._testForceState(VoiceState.Listening)
        session._testHandleAgentSpeaking(true)

        assertEquals(VoiceState.Speaking, session.state.value)
    }

    /** Test 6: From Speaking, _testHandleAgentSpeaking(false) → Listening. */
    @Test fun `from Speaking agent speaking false transitions to Listening`() {
        val session = makeSession()

        session._testForceState(VoiceState.Speaking)
        session._testHandleAgentSpeaking(false)

        assertEquals(VoiceState.Listening, session.state.value)
    }

    /** Test 7: _testForceReconnecting() transitions state to Reconnecting. */
    @Test fun `testForceReconnecting sets state to Reconnecting`() {
        val session = makeSession()

        session._testForceReconnecting()

        assertEquals(VoiceState.Reconnecting, session.state.value)
    }
}
