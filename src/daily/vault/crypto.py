"""AES-256-GCM token encryption/decryption vault.

All OAuth tokens pass through this module before being written to the database.
Tokens are never logged, never passed to the LLM, and never stored in plaintext.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


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
