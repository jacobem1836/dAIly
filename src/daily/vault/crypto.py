"""AES-256-GCM token encryption/decryption vault.

All OAuth tokens pass through this module before being written to the database.
Tokens are never logged, never passed to the LLM, and never stored in plaintext.
"""
import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def load_vault_key(vault_key: str | bytes) -> bytes:
    """Decode ``Settings.vault_key`` into the raw 32-byte AES-256 key.

    This is the SOLE decoder for the vault key in the codebase (audit finding
    H-4 / CRIT-02). Previously nodes.py, auth/router.py, and integrations/
    router.py each decoded the same base64 string differently: standard
    b64decode, urlsafe_b64decode, and a try/except-with-raw-bytes-fallback
    respectively. For a well-formed VAULT_KEY the first two happen to agree,
    but integrations/router.py's fallback meant that any malformed or
    unexpected-length VAULT_KEY value was silently accepted there as a
    *different* key (the literal ASCII bytes of the string) instead of
    failing the way the other two call sites would — a silent, undiagnosable
    divergence in exactly the path (action execution) where a wrong key
    causes every real send to fail. Every caller must go through this
    function so the same VAULT_KEY value always yields identical bytes, or
    every call site fails identically instead of one silently disagreeing.

    Canonical form: standard base64 (base64.b64decode), matching the
    generator documented in .env.example
    (``base64.b64encode(os.urandom(32))``). Also tolerant of the urlsafe
    alphabet — '-'/'_' are normalized to '+'/'/' before decoding — so a key
    that happens to have been produced with urlsafe_b64encode still decodes
    correctly instead of silently corrupting (plain, non-strict b64decode
    discards unrecognized characters rather than raising).

    Args:
        vault_key: The raw VAULT_KEY value from Settings (a base64-encoded
            string), or already-decoded bytes.

    Returns:
        Exactly 32 bytes suitable for AES-256-GCM.

    Raises:
        ValueError: If vault_key is empty, is not valid base64, or does not
            decode to exactly 32 bytes.
    """
    if isinstance(vault_key, bytes):
        decoded = vault_key
    else:
        if not vault_key:
            raise ValueError("VAULT_KEY is not set")
        normalized = vault_key.replace("-", "+").replace("_", "/")
        try:
            decoded = base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                "VAULT_KEY must be valid base64-encoded data"
            ) from exc

    if len(decoded) != 32:
        raise ValueError(
            f"VAULT_KEY must decode to exactly 32 bytes for AES-256 "
            f"(got {len(decoded)})"
        )
    return decoded


def encrypt_token(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt a token string.

    Args:
        plaintext: The token string to encrypt.
        key: 32-byte encryption key (AES-256 requires exactly 32 bytes).

    Returns:
        Base64-encoded string containing nonce + ciphertext + GCM auth tag.

    Raises:
        ValueError: If key is not exactly 32 bytes.
    """
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for AES-256")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce, fresh every call — prevents nonce reuse
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_token(encrypted: str, key: bytes) -> str:
    """AES-256-GCM decrypt a vault-stored token.

    Args:
        encrypted: Base64-encoded string from encrypt_token.
        key: 32-byte decryption key (must match the encryption key).

    Returns:
        Decrypted plaintext token string.

    Raises:
        ValueError: If key is not exactly 32 bytes.
        cryptography.exceptions.InvalidTag: If key is wrong or ciphertext tampered.
    """
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for AES-256")
    data = base64.b64decode(encrypted.encode())
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
