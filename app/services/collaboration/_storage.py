"""
File storage abstraction.

Local: writes under uploads/collaboration/{org}/{conversation}/{key}
S3/MinIO: future plug-in.

All callers use:
  storage.save(...)            -> StoredFile
  storage.read(...)            -> bytes
  storage.signed_url(...)      -> str (URL valid for X seconds)
  storage.delete(...)
  storage.compute_sha256(...)  -> hex
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

logger = logging.getLogger(__name__)

UPLOADS_ROOT = Path(os.environ.get("UPLOADS_DIR", "uploads"))
COLLAB_ROOT = UPLOADS_ROOT / "collaboration"
COLLAB_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class StoredFile:
    storage_provider: str
    storage_key: str
    size_bytes: int
    sha256: Optional[str] = None


# In-memory signed URL token store (TTL based). For prod with multiple workers
# replace with Redis / KMS. The token itself is the storage opaque key.
_SIGNED: dict[str, dict] = {}


class FileStorage:
    """Local file storage. Subclass / swap to plug S3/MinIO."""

    provider: str = "local"

    def _abs(self, key: str) -> Path:
        base = COLLAB_ROOT.resolve()
        target = (base / key).resolve()
        if not str(target).startswith(str(base) + os.sep):
            raise PermissionError("Access denied: path outside collaboration upload root")
        return target

    def save(self, key: str, fp: BinaryIO) -> StoredFile:
        target = self._abs(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        size = 0
        with target.open("wb") as out:
            while True:
                chunk = fp.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                h.update(chunk)
                out.write(chunk)
        return StoredFile(
            storage_provider=self.provider,
            storage_key=key,
            size_bytes=size,
            sha256=h.hexdigest(),
        )

    def save_bytes(self, key: str, data: bytes) -> StoredFile:
        target = self._abs(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StoredFile(
            storage_provider=self.provider,
            storage_key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def read(self, key: str) -> bytes:
        return self._abs(key).read_bytes()

    def open(self, key: str) -> BinaryIO:
        return self._abs(key).open("rb")

    def exists(self, key: str) -> bool:
        return self._abs(key).exists()

    def delete(self, key: str) -> None:
        try:
            self._abs(key).unlink()
        except FileNotFoundError:
            pass

    def size(self, key: str) -> int:
        try:
            return self._abs(key).stat().st_size
        except FileNotFoundError:
            return 0

    # ── Signed URLs ──────────────────────────────────────────────────────────
    def signed_url(self, key: str, *, ttl_seconds: int = 3600, mode: str = "download") -> str:
        token = secrets.token_urlsafe(24)
        _SIGNED[token] = {
            "key": key,
            "mode": mode,
            "expires_at": time.time() + ttl_seconds,
        }
        return f"/api/v1/collaboration/files/by-token/{token}"

    @staticmethod
    def resolve_token(token: str) -> Optional[dict]:
        rec = _SIGNED.get(token)
        if not rec:
            return None
        if rec["expires_at"] < time.time():
            _SIGNED.pop(token, None)
            return None
        return rec


def _build_storage() -> FileStorage:
    backend = os.environ.get("COLLAB_STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return FileStorage()
    if backend in {"s3", "minio"}:
        try:
            from app.services.collaboration._storage_s3 import S3FileStorage
            return S3FileStorage()
        except Exception as exc:
            logger.warning("S3 backend unavailable, fallback local: %s", exc)
            return FileStorage()
    return FileStorage()


storage: FileStorage = _build_storage()


# ── AV / DLP hooks ───────────────────────────────────────────────────────────
_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _scan_with_clamd(data: bytes) -> tuple[str, dict] | None:
    """Conecta a clamd via TCP o socket UNIX. Devuelve None si no disponible."""
    host = os.environ.get("CLAMAV_HOST", "localhost")
    port = int(os.environ.get("CLAMAV_PORT", "3310"))
    socket_path = os.environ.get("CLAMAV_SOCKET")  # /var/run/clamav/clamd.sock
    timeout = float(os.environ.get("CLAMAV_TIMEOUT", "30"))
    try:
        import socket
        if socket_path:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(socket_path)
        else:
            sock = socket.create_connection((host, port), timeout=timeout)
        try:
            # INSTREAM protocol: zINSTREAM\\0 + (size u32 BE + chunk)+ + size 0
            sock.sendall(b"zINSTREAM\0")
            chunk = data
            sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
            sock.sendall((0).to_bytes(4, "big"))
            buf = b""
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                buf += part
            response = buf.decode(errors="replace").strip("\0\r\n ")
        finally:
            try: sock.close()
            except Exception: pass
        if response.endswith("OK"):
            return "clean", {"clamd_response": response}
        if "FOUND" in response:
            sig = response.split(":", 1)[-1].rsplit(" ", 1)[0].strip()
            return "infected", {"clamd_response": response, "signature": sig}
        return "skipped", {"clamd_response": response, "reason": "unexpected response"}
    except Exception as exc:
        logger.warning("clamd unreachable: %s", exc)
        return None


def scan_with_av(data: bytes) -> tuple[str, dict]:
    """Devuelve (status, details). status: clean|infected|skipped.

    Si CLAMAV_ENABLED=1 intenta conectar a clamd (TCP o socket UNIX). Si la
    conexión falla cae al chequeo dev (firma EICAR explícita). Si está
    deshabilitado, marca como 'skipped' con reason."""
    if os.environ.get("CLAMAV_ENABLED", "0") == "1":
        result = _scan_with_clamd(data)
        if result is not None:
            return result
        # clamd unreachable — degrade to dev scan but flag the reason
        if _EICAR in data:
            return "infected", {"signature": "EICAR-Test-File", "note": "fallback scan"}
        return "skipped", {"reason": "clamd unreachable; fallback scan passed"}
    # AV disabled — quick local-dev scan against EICAR signature
    if _EICAR in data:
        return "infected", {"signature": "EICAR-Test-File"}
    return "skipped", {"reason": "AV disabled (dev)"}


_DLP_PATTERNS = [
    ("credit_card", r"\b(?:\d[ -]*?){13,16}\b"),
    ("iban", r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    ("dni_es", r"\b\d{8}[A-Za-z]\b"),
    ("api_token", r"(?i)(?:secret|api[_-]?key|token)[\"'=:\s]+[A-Za-z0-9_\-]{16,}"),
    ("password", r"(?i)password[\"'=:\s]+\S{6,}"),
]


def scan_dlp(text: str) -> tuple[str, list[dict]]:
    """Returns (status, findings). status: allowed|flagged|blocked."""
    import re

    findings = []
    for name, pat in _DLP_PATTERNS:
        for m in re.finditer(pat, text or ""):
            findings.append({"rule": name, "match_excerpt": m.group(0)[:32] + "..."})
    if not findings:
        return "allowed", []
    if any(f["rule"] in {"credit_card", "iban"} for f in findings):
        return "blocked", findings
    return "flagged", findings
