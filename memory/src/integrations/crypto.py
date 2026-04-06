"""
Crypto utilities for encrypting/decrypting API keys and connection strings.

Uses AES-256-GCM for authenticated encryption.
Compatible with the legacy TypeScript crypto.ts format — same
{iv, encryptedData, authTag} shape is used for secure storage.

Usage:
    from src.integrations.crypto import encrypt, decrypt, mask_key

    encrypted = encrypt("sk-my-secret-api-key")
    # → {"iv": "hex...", "encryptedData": "hex...", "authTag": "hex..."}

    plaintext = decrypt(encrypted)
    # → "sk-my-secret-api-key"

    masked = mask_key("sk-my-secret-api-key")
    # → "sk-m••••••••••••-key"
"""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import TypedDict

# ── Constants ─────────────────────────────────────────

ALGORITHM = "aes-256-gcm"
IV_LENGTH = 16  # 128-bit IV
TAG_LENGTH = 16  # 128-bit GCM auth tag

# Encryption key: 32 bytes from env var or derived from a default passphrase.
# In production, set ENCRYPTION_KEY in .env (64 hex chars = 32 bytes).
_RAW_KEY = os.getenv("ENCRYPTION_KEY", "")


def _get_key() -> bytes:
    """
    Resolve the 32-byte AES key.

    Priority:
      1. ENCRYPTION_KEY env var as raw hex (64 chars)
      2. ENCRYPTION_KEY env var as passphrase → SHA-256 digest
      3. Deterministic fallback (dev only — same as legacy TS default)
    """
    if _RAW_KEY:
        # If it looks like hex (64 chars, all hex digits), decode directly
        if len(_RAW_KEY) == 64:
            try:
                return bytes.fromhex(_RAW_KEY)
            except ValueError:
                pass
        # Otherwise hash it (matches legacy TS: crypto.createHash('sha256').update(passphrase).digest())
        return hashlib.sha256(_RAW_KEY.encode("utf-8")).digest()

    # Default fallback — DO NOT use in production; set ENCRYPTION_KEY env var
    return hashlib.sha256(b"clingysocks-default-key-change-in-production").digest()


# ── Types ─────────────────────────────────────────────

class EncryptedData(TypedDict):
    iv: str           # hex-encoded 16-byte IV
    encryptedData: str  # hex-encoded ciphertext
    authTag: str      # hex-encoded 16-byte GCM auth tag


# ── Encrypt / Decrypt ─────────────────────────────────

def encrypt(plaintext: str) -> EncryptedData:
    """
    Encrypt a plaintext string with AES-256-GCM.

    Returns a dict with hex-encoded iv, encryptedData, authTag.
    Compatible with the legacy storage format.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key()
    iv = secrets.token_bytes(IV_LENGTH)
    aesgcm = AESGCM(key)

    # AESGCM.encrypt returns ciphertext + tag concatenated
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

    # Split: last TAG_LENGTH bytes are the auth tag
    ciphertext = ct_with_tag[:-TAG_LENGTH]
    auth_tag = ct_with_tag[-TAG_LENGTH:]

    return EncryptedData(
        iv=iv.hex(),
        encryptedData=ciphertext.hex(),
        authTag=auth_tag.hex(),
    )


def decrypt(encrypted: dict) -> str:
    """
    Decrypt an EncryptedData dict back to plaintext.

    Accepts the same {iv, encryptedData, authTag} format as the legacy storage,
    whether from Python encrypt() or legacy TypeScript encrypt().
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key()
    iv = bytes.fromhex(encrypted["iv"])
    ciphertext = bytes.fromhex(encrypted["encryptedData"])
    auth_tag = bytes.fromhex(encrypted["authTag"])

    aesgcm = AESGCM(key)

    # AESGCM.decrypt expects ciphertext + tag concatenated
    ct_with_tag = ciphertext + auth_tag
    plaintext = aesgcm.decrypt(iv, ct_with_tag, None)

    return plaintext.decode("utf-8")


# ── Helpers ───────────────────────────────────────────

def mask_key(key: str) -> str:
    """
    Mask an API key for display.  Shows first 4 and last 4 characters.

    Examples:
        "sk-proj-very-long-key-here" → "sk-p••••••••••••here"
        "short"                      → "••••••••"
    """
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}{'•' * min(20, len(key) - 8)}{key[-4:]}"
