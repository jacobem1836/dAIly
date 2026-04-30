package com.daily.android.auth

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.core.DataStoreFactory
import androidx.datastore.core.Serializer
import androidx.datastore.dataStoreFile
import com.google.crypto.tink.Aead
import com.google.crypto.tink.KeyTemplates
import com.google.crypto.tink.aead.AeadConfig
import com.google.crypto.tink.integration.android.AndroidKeysetManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.InputStream
import java.io.OutputStream

/**
 * Secure token storage backed by DataStore + Google Tink AES-256-GCM.
 *
 * Master key is stored in the Android Keystore (hardware-backed where available).
 * Tokens are never written to disk in plaintext — every byte on disk is Tink-encrypted.
 *
 * Supported keys (mirror iOS KeychainStore):
 *   - "access_token"
 *   - "refresh_token"
 *   - "access_token_expires_at"
 *
 * Security notes:
 *   - Deprecated SharedPreferences encryption APIs are NOT used (deprecated since API 33).
 *   - All methods are suspend-only; no blocking calls in this class (T-20-09).
 *   - Test isolation: pass a custom fileName so tests never touch the production file.
 */
class TokenStore(context: Context, fileName: String = "tokens.enc") {

    private val aead: Aead by lazy {
        AeadConfig.register()
        AndroidKeysetManager.Builder()
            .withSharedPref(context, "tokenstore_keyset", "tokenstore_master_key")
            .withKeyTemplate(KeyTemplates.get("AES256_GCM"))
            .withMasterKeyUri("android-keystore://tokenstore_master_key")
            .build()
            .keysetHandle
            .getPrimitive(Aead::class.java)
    }

    private val serializer = object : Serializer<Map<String, String>> {
        override val defaultValue: Map<String, String> = emptyMap()

        override suspend fun readFrom(input: InputStream): Map<String, String> {
            val ciphertext = input.readBytes()
            if (ciphertext.isEmpty()) return emptyMap()
            return try {
                val plaintext = aead.decrypt(ciphertext, null)
                parseFlatMap(plaintext)
            } catch (_: Exception) {
                emptyMap()
            }
        }

        override suspend fun writeTo(t: Map<String, String>, output: OutputStream) {
            val plaintext = serializeFlatMap(t)
            val ciphertext = aead.encrypt(plaintext, null)
            output.write(ciphertext)
        }
    }

    private val store: DataStore<Map<String, String>> = DataStoreFactory.create(
        serializer = serializer,
        scope = CoroutineScope(Dispatchers.IO + SupervisorJob()),
        produceFile = { context.dataStoreFile(fileName) }
    )

    /**
     * Persist [value] under [key], overwriting any existing entry.
     */
    suspend fun save(key: String, value: String) {
        store.updateData { it + (key to value) }
    }

    /**
     * Return the stored value for [key], or null if absent.
     */
    suspend fun load(key: String): String? = store.data.first()[key]

    /**
     * Remove the entry for [key]. No-op if absent.
     */
    suspend fun delete(key: String) {
        store.updateData { it - key }
    }

    /**
     * Wipe all stored tokens. Called on first launch (T-20-06 / mirror of iOS T-19-15 clearAll).
     */
    suspend fun clearAll() {
        store.updateData { emptyMap() }
    }

    // ── Serialisation helpers ──────────────────────────────────────────────────

    /**
     * Length-prefixed flat-map encoding: [keyLen:Int][key bytes][valLen:Int][val bytes]…
     * The byte order is big-endian (Java DataOutputStream default).
     */
    private fun serializeFlatMap(map: Map<String, String>): ByteArray {
        val baos = ByteArrayOutputStream()
        val dos = DataOutputStream(baos)
        for ((k, v) in map) {
            val kb = k.toByteArray(Charsets.UTF_8)
            val vb = v.toByteArray(Charsets.UTF_8)
            dos.writeInt(kb.size)
            dos.write(kb)
            dos.writeInt(vb.size)
            dos.write(vb)
        }
        return baos.toByteArray()
    }

    private fun parseFlatMap(bytes: ByteArray): Map<String, String> {
        val dis = DataInputStream(ByteArrayInputStream(bytes))
        val out = mutableMapOf<String, String>()
        while (dis.available() > 0) {
            val kLen = dis.readInt()
            val kb = ByteArray(kLen)
            dis.readFully(kb)
            val vLen = dis.readInt()
            val vb = ByteArray(vLen)
            dis.readFully(vb)
            out[String(kb, Charsets.UTF_8)] = String(vb, Charsets.UTF_8)
        }
        return out
    }
}
