"""Audio de las reuniones en disco local (`uploads/reuniones/<empresa>/<reunión>/`).

Aparte del almacén de documentos a propósito: el audio vive poco (retención
corta, `retention.audio_days`), no tiene versiones y no debe salir a S3 de
documentos con otra retención. La clave es relativa y se valida contra la
raíz (sin `..`), igual que `LocalFileStorage.get_file_bytes`.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3] / "uploads" / "reuniones"

_EXTENSIONES = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
                "audio/wav": "wav", "audio/x-wav": "wav", "video/webm": "webm"}


def _ruta(clave: str) -> Path:
    raiz = RAIZ.resolve()
    ruta = (raiz / clave).resolve()
    if not ruta.is_relative_to(raiz):
        raise PermissionError("clave fuera del almacén de reuniones")
    return ruta


def guardar(org: str, reunion_id: str, seq: int, datos: bytes, mime: str) -> str:
    ext = _EXTENSIONES.get((mime or "").split(";")[0].strip().lower(), "bin")
    clave = f"{org or 'sin-empresa'}/{reunion_id}/{seq:05d}-{uuid.uuid4().hex[:8]}.{ext}"
    ruta = _ruta(clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return clave


def leer(clave: str) -> bytes:
    return _ruta(clave).read_bytes()


def borrar(clave: str) -> bool:
    ruta = _ruta(clave)
    if ruta.exists():
        ruta.unlink()
        return True
    return False


def borrar_reunion(org: str, reunion_id: str) -> None:
    carpeta = _ruta(f"{org or 'sin-empresa'}/{reunion_id}")
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)
