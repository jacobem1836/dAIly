package com.daily.android.auth

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.time.Instant
import java.time.format.DateTimeFormatter

/**
 * Sealed hierarchy mirroring iOS AuthError enum.
 *
 * T-20-14: Error messages never include token values or response bodies.
 */
sealed class AuthError(message: String) : Exception(message) {
    object Unauthorized : AuthError("unauthorized")
    data class Server(val code: Int) : AuthError("server $code")
    object Decoding : AuthError("decoding")
    data class Network(val detail: String) : AuthError("network: $detail")
}

/**
 * Mirror of iOS PairingResult — exact field names preserved for cross-platform contract.
 */
data class PairingResult(
    val accessToken: String,
    val refreshToken: String,
    val expiresAt: Instant,
)

/**
 * OkHttp + coroutines auth service mirroring ios/dAIly/auth/AuthService.swift.
 *
 * Endpoints:
 *   POST /auth/pair/send-link  — body {"email": "..."}
 *   POST /auth/pair/complete   — body {"code": "..."}
 *   POST /auth/token/refresh   — body {"refresh_token": "..."}
 *
 * All network I/O dispatched on Dispatchers.IO.
 * Tokens persisted to TokenStore immediately after successful response (T-20-14: never logged).
 */
class AuthService(
    private val baseUrl: String,
    private val tokenStore: TokenStore,
    private val client: OkHttpClient = OkHttpClient(),
) {
    private val json = "application/json".toMediaType()

    suspend fun sendLink(email: String): Unit = withContext(Dispatchers.IO) {
        val body = JSONObject(mapOf("email" to email)).toString().toRequestBody(json)
        val req = Request.Builder().url("$baseUrl/auth/pair/send-link").post(body).build()
        try {
            client.newCall(req).execute().use { resp ->
                if (resp.code == 401) throw AuthError.Unauthorized
                if (resp.code !in 200..299) throw AuthError.Server(resp.code)
            }
        } catch (e: AuthError) {
            throw e
        } catch (e: Exception) {
            throw AuthError.Network(e.javaClass.simpleName)
        }
    }

    suspend fun completePairing(code: String): PairingResult = withContext(Dispatchers.IO) {
        val body = JSONObject(mapOf("code" to code)).toString().toRequestBody(json)
        val req = Request.Builder().url("$baseUrl/auth/pair/complete").post(body).build()
        val text = try {
            client.newCall(req).execute().use { resp ->
                if (resp.code == 401) throw AuthError.Unauthorized
                if (resp.code !in 200..299) throw AuthError.Server(resp.code)
                resp.body?.string() ?: throw AuthError.Decoding
            }
        } catch (e: AuthError) {
            throw e
        } catch (e: Exception) {
            throw AuthError.Network(e.javaClass.simpleName)
        }

        val parsed = try { JSONObject(text) } catch (_: Exception) { throw AuthError.Decoding }
        val at = parsed.optString("access_token", "")
        val rt = parsed.optString("refresh_token", "")
        val exp = parsed.optInt("expires_in", -1)
        if (at.isEmpty() || rt.isEmpty() || exp < 0) throw AuthError.Decoding

        val expiresAt = Instant.now().plusSeconds(exp.toLong())
        tokenStore.save("access_token", at)
        tokenStore.save("refresh_token", rt)
        tokenStore.save("access_token_expires_at", DateTimeFormatter.ISO_INSTANT.format(expiresAt))
        PairingResult(at, rt, expiresAt)
    }

    suspend fun refresh(): Unit = withContext(Dispatchers.IO) {
        val rt = tokenStore.load("refresh_token") ?: throw AuthError.Unauthorized
        val body = JSONObject(mapOf("refresh_token" to rt)).toString().toRequestBody(json)
        val req = Request.Builder().url("$baseUrl/auth/token/refresh").post(body).build()
        val text = try {
            client.newCall(req).execute().use { resp ->
                if (resp.code == 401) throw AuthError.Unauthorized
                if (resp.code !in 200..299) throw AuthError.Server(resp.code)
                resp.body?.string() ?: throw AuthError.Decoding
            }
        } catch (e: AuthError) {
            throw e
        } catch (e: Exception) {
            throw AuthError.Network(e.javaClass.simpleName)
        }

        val parsed = try { JSONObject(text) } catch (_: Exception) { throw AuthError.Decoding }
        val at = parsed.optString("access_token", "")
        val exp = parsed.optInt("expires_in", -1)
        if (at.isEmpty() || exp < 0) throw AuthError.Decoding

        val expiresAt = Instant.now().plusSeconds(exp.toLong())
        tokenStore.save("access_token", at)
        tokenStore.save("access_token_expires_at", DateTimeFormatter.ISO_INSTANT.format(expiresAt))
    }
}
