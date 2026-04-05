"""Vault encryption unit tests — AES-256-GCM correctness and security properties."""
import os

import pytest
from cryptography.exceptions import InvalidTag

from daily.vault.crypto import decrypt_token, encrypt_token


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
