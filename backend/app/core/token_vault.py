"""
OAuth Token Vault
AES-256-GCM encryption for storing platform credentials securely.
All connector OAuth tokens are encrypted before being saved to the database.
"""
import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _get_key() -> bytes:
    """Derive a 32-byte AES key from the app SECRET_KEY."""
    key_bytes = settings.SECRET_KEY.encode("utf-8")
    # Pad or truncate to exactly 32 bytes
    return key_bytes[:32].ljust(32, b"0")


def encrypt(data: dict[str, Any]) -> str:
    """
    Encrypt a dictionary of credentials using AES-256-GCM.
    Returns a base64-encoded string safe for storage in JSONB.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    plaintext = json.dumps(data).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    # Combine nonce + ciphertext and encode as base64
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("utf-8")


def decrypt(encrypted: str) -> dict[str, Any]:
    """
    Decrypt an AES-256-GCM encrypted credential string.
    Returns the original dictionary.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    combined = base64.b64decode(encrypted.encode("utf-8"))
    nonce = combined[:12]
    ciphertext = combined[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


def encrypt_token(token_data: dict[str, Any]) -> dict[str, str]:
    """
    Wrap token data into an encrypted vault entry.
    Stored as {"vault": "<encrypted_base64>"} in the DB.
    """
    return {"vault": encrypt(token_data)}


def decrypt_token(vault_entry: dict[str, str]) -> dict[str, Any]:
    """
    Decrypt a vault entry back to the original token data.
    """
    if "vault" not in vault_entry:
        raise ValueError("Invalid vault entry — missing 'vault' key")
    return decrypt(vault_entry["vault"])


# ─── Convenience helpers for common OAuth token structures ────────────────────

def store_oauth_tokens(
    access_token: str,
    refresh_token: str | None = None,
    expires_at: int | None = None,
    scope: str | None = None,
    extra: dict | None = None,
) -> dict[str, str]:
    """
    Build and encrypt a standard OAuth token payload.
    Returns encrypted vault entry ready for DB storage.
    """
    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope,
        **(extra or {}),
    }
    return encrypt_token(token_data)


def retrieve_oauth_tokens(vault_entry: dict[str, str]) -> dict[str, Any]:
    """Decrypt and return OAuth tokens from vault entry."""
    return decrypt_token(vault_entry)
