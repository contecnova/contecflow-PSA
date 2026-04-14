"""Utilities to encrypt/decrypt sensitive values in integration config dictionaries."""
from __future__ import annotations

from app.core.encryption import encrypt_value, decrypt_value

SENSITIVE_KEY_HINTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "webhook",
    "client_secret",
)


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(h in k for h in SENSITIVE_KEY_HINTS)


def encrypt_config_secrets(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(v, str) and v and _is_sensitive_key(k):
                out[k] = encrypt_value(v)
            else:
                out[k] = encrypt_config_secrets(v)
        return out
    if isinstance(value, list):
        return [encrypt_config_secrets(v) for v in value]
    return value


def decrypt_config_secrets(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(v, str) and _is_sensitive_key(k):
                dec = decrypt_value(v)
                out[k] = dec if dec is not None else v
            else:
                out[k] = decrypt_config_secrets(v)
        return out
    if isinstance(value, list):
        return [decrypt_config_secrets(v) for v in value]
    return value
