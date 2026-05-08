"""LiveKit token signing — autohosteado.

Si LIVEKIT_API_KEY/SECRET están en env, firma JWTs con HS256 según el esquema
oficial de LiveKit (`exp`, `iss`=apiKey, `nbf`, `sub`=identity, `name`, `video.room`,
`video.roomJoin`=true, etc).

En dev sin secret: produce un token "dev:" no válido para LiveKit pero útil
para ejecutar el flujo end-to-end del front + persistir la sala.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class LiveKitConfig:
    url: str = os.environ.get("LIVEKIT_URL", "wss://livekit.local")
    api_key: Optional[str] = os.environ.get("LIVEKIT_API_KEY")
    api_secret: Optional[str] = os.environ.get("LIVEKIT_API_SECRET")


CONFIG = LiveKitConfig()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def issue_access_token(
    *,
    room: str,
    identity: str,
    name: Optional[str] = None,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
    is_recorder: bool = False,
    ttl_seconds: int = 3600,
) -> str:
    """Build a LiveKit JWT (HS256) — same structure as livekit-server-sdk."""
    if not CONFIG.api_key or not CONFIG.api_secret:
        # dev fallback
        return f"dev:{room}:{identity}:{int(time.time()) + ttl_seconds}"
    now = int(time.time())
    grants = {
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": can_publish_data,
            "recorder": is_recorder,
        }
    }
    payload = {
        "iss": CONFIG.api_key,
        "sub": identity,
        "name": name or identity,
        "nbf": now,
        "exp": now + ttl_seconds,
        **grants,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        CONFIG.api_secret.encode(),
        f"{h}.{p}".encode(),
        hashlib.sha256,
    ).digest()
    s = _b64url(sig)
    return f"{h}.{p}.{s}"


def url() -> str:
    return CONFIG.url
