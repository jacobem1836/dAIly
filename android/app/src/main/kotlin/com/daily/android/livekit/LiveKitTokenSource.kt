package com.daily.android.livekit

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

data class LiveKitToken(val token: String, val room: String, val url: String)

/**
 * Sealed error hierarchy mirroring iOS LiveKitTokenError enum.
 *
 * T-20-17: The token value is never included in error messages.
 */
sealed class LiveKitTokenError(message: String) : Exception(message) {
    object Unauthorized : LiveKitTokenError("unauthorized")
    data class Server(val code: Int) : LiveKitTokenError("server $code")
    object Decoding : LiveKitTokenError("decoding")
    data class Network(val detail: String) : LiveKitTokenError("network: $detail")
}

/**
 * Fetches a short-lived LiveKit room token from the backend.
 *
 * POST /livekit/token
 *   Authorization: Bearer <accessJWT>
 *   → 200: {"token":"...", "room":"...", "livekit_url":"wss://..."}
 *
 * T-20-18: Token sourced exclusively from authenticated endpoint; WSS URL from server only.
 */
class LiveKitTokenSource(
    private val baseUrl: String,
    private val client: OkHttpClient = OkHttpClient(),
) {
    suspend fun fetchToken(accessJWT: String): LiveKitToken = withContext(Dispatchers.IO) {
        val body = "{}".toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url("$baseUrl/livekit/token")
            .addHeader("Authorization", "Bearer $accessJWT")
            .post(body)
            .build()

        val text = try {
            client.newCall(req).execute().use { resp ->
                if (resp.code == 401) throw LiveKitTokenError.Unauthorized
                if (resp.code !in 200..299) throw LiveKitTokenError.Server(resp.code)
                resp.body?.string() ?: throw LiveKitTokenError.Decoding
            }
        } catch (e: LiveKitTokenError) {
            throw e
        } catch (e: Exception) {
            throw LiveKitTokenError.Network(e.javaClass.simpleName)
        }

        val json = try {
            JSONObject(text)
        } catch (_: Exception) {
            throw LiveKitTokenError.Decoding
        }

        val tk = json.optString("token", "")
        val rm = json.optString("room", "")
        val url = json.optString("livekit_url", "")
        if (tk.isEmpty() || rm.isEmpty() || url.isEmpty()) throw LiveKitTokenError.Decoding
        LiveKitToken(tk, rm, url)
    }
}
