package com.daily.android.auth

import android.net.Uri

object PairCodeUriParser {
    /**
     * Extract the pairing code from an App Links deep-link URI.
     *
     * Requirements (T-20-11):
     *  - Path must be exactly "/pair" — case-sensitive, no trailing slash
     *  - "code" query parameter must be present and non-blank
     *
     * Returns null for any URI that does not satisfy both conditions.
     */
    fun extractCode(uri: Uri): String? {
        if (uri.path != "/pair") return null
        val code = uri.getQueryParameter("code") ?: return null
        if (code.isBlank()) return null
        return code
    }
}
