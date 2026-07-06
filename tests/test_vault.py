"""Vault encryption unit tests — AES-256-GCM correctness and security properties."""
import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from daily.vault.crypto import decrypt_token, encrypt_token, load_vault_key


def test_encrypt_returns_base64_string(vault_key):
    result = encrypt_token("my_secret_token", vault_key)
    assert isinstance(result, str)


def test_encrypt_does_not_contain_plaintext(vault_key):
    result = encrypt_token("my_secret_token", vault_key)
    assert "my_secret_token" not in result


def test_round_trip(vault_key):
    plaintext = "my_secret_token"
    encrypted = encrypt_token(plaintext, vault_key)
    decrypted = decrypt_token(encrypted, vault_key)
    assert decrypted == plaintext


def test_nonce_uniqueness(vault_key):
    """Two encryptions of the same plaintext must produce different ciphertexts."""
    c1 = encrypt_token("same_token", vault_key)
    c2 = encrypt_token("same_token", vault_key)
    assert c1 != c2


def test_wrong_key_raises(vault_key):
    encrypted = encrypt_token("secret", vault_key)
    wrong_key = os.urandom(32)
    with pytest.raises(InvalidTag):
        decrypt_token(encrypted, wrong_key)


def test_invalid_key_length_encrypt():
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_token("secret", b"tooshort")


def test_invalid_key_length_decrypt():
    with pytest.raises(ValueError, match="32 bytes"):
        decrypt_token("somebase64data", b"tooshort")


def test_empty_plaintext_round_trip(vault_key):
    """Edge case: empty string must round-trip correctly."""
    encrypted = encrypt_token("", vault_key)
    assert decrypt_token(encrypted, vault_key) == ""


# ---------------------------------------------------------------------------
# CRIT-02 / H-4 regression: canonical VAULT_KEY decoding
#
# Before this fix, three call sites decoded settings.vault_key differently:
#   - orchestrator/nodes.py used base64.urlsafe_b64decode
#   - auth/router.py used base64.b64decode
#   - integrations/router.py's _vault_key() tried base64.b64decode, and if
#     the result wasn't exactly 32 bytes, silently fell back to the raw
#     UTF-8 bytes of the VAULT_KEY string itself
#
# For a properly generated VAULT_KEY (base64.b64encode(os.urandom(32)) per
# .env.example), Python's urlsafe_b64decode and b64decode happen to agree —
# urlsafe_b64decode only translates '-'/'_' to '+'/'/' before delegating to
# the standard decoder, which is a no-op on a standard-alphabet string. The
# real, verified divergence is the raw-bytes FALLBACK: for any malformed or
# unexpected-length VAULT_KEY value, integrations/router.py would silently
# accept and use a completely different key (the literal ASCII bytes of the
# string) than what nodes.py/auth/router.py would derive (which fail loudly
# instead). That inconsistency — one code path silently "succeeding" with
# different key bytes than the others reject — is exactly the class of bug
# that made action-execution failures undiagnosable. load_vault_key() is now
# the sole decoder everywhere: for any given VAULT_KEY value, every call
# site now either agrees on the same bytes, or raises the same ValueError.
# ---------------------------------------------------------------------------


def _old_vault_key_fallback(raw: str) -> bytes:
    """Reproduces integrations/router.py's PRE-FIX `_vault_key()` logic, to
    prove what it used to do differently from the strict decoders.
    """
    try:
        decoded = base64.b64decode(raw)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return raw.encode()


def test_old_raw_bytes_fallback_diverged_from_strict_decoding():
    """The actual CRIT-02 divergence: a malformed VAULT_KEY value ("y" * 32,
    32 ASCII chars — not valid base64 for 32 bytes, it decodes to 24 bytes)
    was silently accepted by integrations/router.py's old fallback as a
    *different* 32-byte key, while a strict decoder rejects it outright.
    Same env var, two code paths, two different outcomes — one silent.
    """
    malformed = "y" * 32

    # Strict standard decode: succeeds but yields the WRONG length (24, not 32).
    strict_decoded = base64.b64decode(malformed)
    assert len(strict_decoded) != 32

    # Old integrations/router.py behaviour: silently falls back to raw ASCII
    # bytes of the string — a key nodes.py/auth/router.py never derived.
    old_fallback_key = _old_vault_key_fallback(malformed)
    assert len(old_fallback_key) == 32
    assert old_fallback_key != strict_decoded
    assert old_fallback_key == malformed.encode()


def test_load_vault_key_rejects_the_old_silent_fallback_case():
    """The fix: load_vault_key has no raw-bytes fallback. The same malformed
    value that integrations/router.py used to silently accept now raises,
    the same way nodes.py/auth/router.py's strict decoders always would.
    """
    with pytest.raises(ValueError, match="32 bytes"):
        load_vault_key("y" * 32)


def test_load_vault_key_consistent_across_repeated_calls():
    """Every call site now goes through the same function, so the same
    VAULT_KEY value always yields identical bytes regardless of how many
    "call sites" (simulated here as repeated calls) decode it.
    """
    raw_key = os.urandom(32)
    env_value = base64.b64encode(raw_key).decode()

    key_from_call_site_a = load_vault_key(env_value)
    key_from_call_site_b = load_vault_key(env_value)

    assert key_from_call_site_a == key_from_call_site_b == raw_key
    assert len(key_from_call_site_a) == 32


def test_load_vault_key_round_trip_through_encrypt_decrypt():
    """Full regression guard: a token encrypted using the key derived at one
    call site must decrypt correctly using the key independently re-derived
    at another — the exact action-executor path (nodes.py encrypts/decrypts
    via the same VAULT_KEY env value other modules also decode).
    """
    raw_key = os.urandom(32)
    env_value = base64.b64encode(raw_key).decode()

    key_at_encrypt_site = load_vault_key(env_value)
    plaintext = "ya29.fake-oauth-access-token"
    encrypted = encrypt_token(plaintext, key_at_encrypt_site)

    key_at_decrypt_site = load_vault_key(env_value)
    decrypted = decrypt_token(encrypted, key_at_decrypt_site)

    assert decrypted == plaintext


def test_load_vault_key_rejects_wrong_length():
    with pytest.raises(ValueError, match="32 bytes"):
        load_vault_key(base64.b64encode(b"tooshort").decode())


def test_load_vault_key_rejects_empty():
    with pytest.raises(ValueError):
        load_vault_key("")


def test_load_vault_key_accepts_raw_bytes_passthrough():
    """Already-decoded 32-byte keys (e.g. test fixtures) pass through unchanged."""
    raw = os.urandom(32)
    assert load_vault_key(raw) == raw


def test_load_vault_key_normalizes_urlsafe_alphabet():
    """A VAULT_KEY that happens to have been base64-encoded with the urlsafe
    alphabet (containing '-'/'_') decodes to the same bytes as the standard
    encoding of the same underlying 32 bytes. This matters because plain
    base64.b64decode (non-strict) silently discards '-'/'_' as invalid
    characters rather than raising, which can yield a *different*, wrong-but
    -still-32-byte key with no visible error — load_vault_key's alphabet
    normalization closes that gap too.
    """
    raw_key = os.urandom(32)
    standard_encoded = base64.b64encode(raw_key).decode()
    urlsafe_encoded = base64.urlsafe_b64encode(raw_key).decode()

    assert load_vault_key(standard_encoded) == raw_key
    assert load_vault_key(urlsafe_encoded) == raw_key
