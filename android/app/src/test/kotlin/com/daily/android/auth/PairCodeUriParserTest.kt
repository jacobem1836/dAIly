package com.daily.android.auth

import android.net.Uri
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class PairCodeUriParserTest {

    @Test fun `extractCode returns code from valid pair uri`() {
        val uri = Uri.parse("https://app.example.com/pair?code=123456")
        assertEquals("123456", PairCodeUriParser.extractCode(uri))
    }

    @Test fun `extractCode returns null for uppercase PAIR path`() {
        val uri = Uri.parse("https://app.example.com/PAIR?code=123456")
        assertNull(PairCodeUriParser.extractCode(uri))
    }

    @Test fun `extractCode returns null for wrong path`() {
        val uri = Uri.parse("https://app.example.com/other?code=123456")
        assertNull(PairCodeUriParser.extractCode(uri))
    }

    @Test fun `extractCode returns null when code param missing`() {
        val uri = Uri.parse("https://app.example.com/pair")
        assertNull(PairCodeUriParser.extractCode(uri))
    }
}
