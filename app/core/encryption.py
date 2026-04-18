"""
Field-level encryption helpers for sensitive model data.

Usage:
    from app.core.encryption import encrypt_value, decrypt_value

    # Store encrypted:
    user.hourly_rate_enc = encrypt_value(str(hourly_rate))
    # Read decrypted:
    rate = decrypt_value(user.hourly_rate_enc)

The encryption key is derived from `settings.SECRET_KEY` using PBKDF2 (v1 legacy)
or HKDF with a per-record random salt (v2, current default).

v2 format: "v2:<base64-salt>.<fernet-token>"
v1 format: raw Fernet token (no prefix)  — still decryptable for backward compat.
"""
import base64
import logging
import os
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("clarive.encryption")


def _kms_enabled() -> bool:
    return settings.KMS_PROVIDER.lower() == "aws" and bool(settings.AWS_KMS_KEY_ID)


def _kms_client():
    import boto3

    kwargs = {}
    if settings.AWS_KMS_REGION:
        kwargs["region_name"] = settings.AWS_KMS_REGION
    return boto3.client("kms", **kwargs)

# ── v1 legacy: deterministic global key ───────────────────────────────────────

def _derive_key() -> bytes:
    """Derive a 32-byte Fernet key from SECRET_KEY via PBKDF2 (v1 legacy)."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"clarive_field_enc_v1",
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))


_KEY: Optional[bytes] = None


def _get_key() -> bytes:
    global _KEY
    if _KEY is None:
        _KEY = _derive_key()
    return _KEY


# ── v2 current: per-record HKDF key ───────────────────────────────────────────

def _derive_record_key(salt: bytes) -> bytes:
    """Derive a per-record 32-byte Fernet key from SECRET_KEY + random salt via HKDF."""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"clarive_field_enc_v2",
    )
    return base64.urlsafe_b64encode(hkdf.derive(settings.SECRET_KEY.encode()))


def encrypt_value(plaintext: str) -> str:
    """Encrypt `plaintext` → v2 ciphertext with per-record salt.

    Format: ``v2:<base64url(16-byte-salt)>.<fernet-token>``
    """
    try:
        if _kms_enabled():
            client = _kms_client()
            enc = client.encrypt(KeyId=settings.AWS_KMS_KEY_ID, Plaintext=plaintext.encode())
            blob = base64.urlsafe_b64encode(enc["CiphertextBlob"]).decode()
            return f"kmsv1:{blob}"

        from cryptography.fernet import Fernet
        salt = os.urandom(16)
        key = _derive_record_key(salt)
        token = Fernet(key).encrypt(plaintext.encode()).decode()
        salt_b64 = base64.urlsafe_b64encode(salt).decode()
        return f"v2:{salt_b64}.{token}"
    except Exception as exc:
        logger.error(f"Encryption failed: {exc}")
        raise


def decrypt_value(ciphertext: str) -> Optional[str]:
    """Decrypt v2 (per-record salt) or v1 (global key) ciphertext.

    Returns None on failure.
    """
    if not ciphertext:
        return None
    try:
        if ciphertext.startswith("kmsv1:"):
            blob_b64 = ciphertext[6:]
            blob = base64.urlsafe_b64decode(blob_b64.encode())
            client = _kms_client()
            dec = client.decrypt(CiphertextBlob=blob)
            return dec["Plaintext"].decode()

        from cryptography.fernet import Fernet
        if ciphertext.startswith("v2:"):
            # Current format: per-record HKDF salt
            rest = ciphertext[3:]
            salt_b64, token = rest.split(".", 1)
            salt = base64.urlsafe_b64decode(salt_b64 + "==")  # pad for urlsafe_b64decode
            key = _derive_record_key(salt)
            return Fernet(key).decrypt(token.encode()).decode()
        else:
            raise ValueError("Legacy v1 format is no longer supported.")
    except Exception as exc:
        logger.warning(f"Decryption failed (value may be unencrypted plaintext): {exc}")
        return None


def encrypt_float(value: Optional[float]) -> Optional[str]:
    """Encrypt a float value; returns None if value is None."""
    if value is None:
        return None
    return encrypt_value(str(value))


def decrypt_float(ciphertext: Optional[str]) -> Optional[float]:
    """Decrypt a float that was encrypted with encrypt_float."""
    if not ciphertext:
        return None
    raw = decrypt_value(ciphertext)
    if raw is None:
        # Fallback: try to parse as plaintext float (for migration)
        try:
            return float(ciphertext)
        except (ValueError, TypeError):
            return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None
