"""Ajustes por empresa del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

Grupo de ajustes en caliente `portal_chat` (Configuración › Portal › Chat del
portal, `org.administrar`; cada cambio queda auditado por `set_runtime_value`).
Se leen por empresa con respaldo global y de entorno (`app/core/config.py`).

- Llamadas y vídeo: si están apagados, iniciar devuelve 403 con código.
- Adjuntos: apagados → 403; extensiones permitidas por empresa que SOLO acotan
  el catálogo aprobado de `app/core/uploads.py` (una empresa no puede abrir lo
  que la plataforma bloquea: SVG, comprimidos, ejecutables); tamaño máximo que
  nunca pasa del global `MAX_FILE_SIZE_MB`.
- Grabación (24-11-2026, migración 214): apagada por defecto; con ella, el
  operador puede proponer grabar y solo se graba con el consentimiento del
  cliente (`grabacion.py`). Transcripción, días de retención y texto del aviso.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings

#: El catálogo de la plataforma para el chat del portal: el de adjuntos SIN SVG
#: (puede llevar script y se pintaría como vista previa).
_EXTENSIONES_VETADAS = {".svg"}


@dataclass(frozen=True)
class AjustesDelChat:
    llamadas: bool
    video: bool
    adjuntos: bool
    extensiones: tuple[str, ...]
    max_mb: int
    minutos_de_edicion: int
    segundos_de_tono: int
    # 24-11-2026 (migración 214): grabación con aviso y consentimiento del cliente.
    grabacion: bool = False
    transcripcion: bool = False
    dias_grabaciones: int = 90
    dias_transcripciones: int = 365
    aviso_de_grabacion: str = ""

    def salida(self) -> dict:
        d = asdict(self)
        return {
            "recording_enabled": d["llamadas"] and d["grabacion"],
            "transcription_enabled": d["llamadas"] and d["grabacion"] and d["transcripcion"],
            "recording_notice": d["aviso_de_grabacion"],
            "calls_enabled": d["llamadas"],
            "video_enabled": d["llamadas"] and d["video"],
            "attachments_enabled": d["adjuntos"],
            "allowed_extensions": list(d["extensiones"]),
            "max_file_mb": d["max_mb"],
            "edit_window_minutes": d["minutos_de_edicion"],
            "call_ring_seconds": d["segundos_de_tono"],
        }


def catalogo_de_extensiones() -> set[str]:
    from app.core.uploads import ALLOWED_EXTENSIONS
    return set(ALLOWED_EXTENSIONS) - _EXTENSIONES_VETADAS


def _extensiones(texto: Optional[str]) -> tuple[str, ...]:
    catalogo = catalogo_de_extensiones()
    pedidas = []
    for trozo in (texto or "").split(","):
        ext = trozo.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext in catalogo and ext not in pedidas:
            pedidas.append(ext)
    return tuple(pedidas)


def leer(db: Session, organization_id: Optional[str]) -> AjustesDelChat:
    from app.services.settings_service import get_runtime_bool, get_runtime_int, get_runtime_str

    def _b(clave: str) -> bool:
        v = get_runtime_bool(db, clave, organization_id)
        return bool(getattr(settings, clave) if v is None else v)

    def _i(clave: str) -> int:
        v = get_runtime_int(db, clave, organization_id)
        return int(getattr(settings, clave) if v is None else v)

    tope_global = int(getattr(settings, "MAX_FILE_SIZE_MB", 100) or 100)
    max_mb = max(1, min(_i("PORTAL_CHAT_MAX_FILE_MB"), tope_global))
    return AjustesDelChat(
        llamadas=_b("PORTAL_CHAT_CALLS_ENABLED"),
        video=_b("PORTAL_CHAT_VIDEO_ENABLED"),
        adjuntos=_b("PORTAL_CHAT_ATTACHMENTS_ENABLED"),
        extensiones=_extensiones(get_runtime_str(db, "PORTAL_CHAT_ALLOWED_EXTENSIONS", organization_id)),
        max_mb=max_mb,
        minutos_de_edicion=max(0, _i("PORTAL_CHAT_EDIT_WINDOW_MINUTES")),
        segundos_de_tono=max(10, _i("PORTAL_CHAT_CALL_RING_SECONDS")),
        grabacion=_b("PORTAL_CHAT_RECORDING_ENABLED"),
        transcripcion=_b("PORTAL_CHAT_TRANSCRIPTION_ENABLED"),
        dias_grabaciones=max(1, _i("PORTAL_CHAT_RECORDING_RETENTION_DAYS")),
        dias_transcripciones=max(1, _i("PORTAL_CHAT_TRANSCRIPT_RETENTION_DAYS")),
        aviso_de_grabacion=(get_runtime_str(db, "PORTAL_CHAT_RECORDING_NOTICE", organization_id)
                            or getattr(settings, "PORTAL_CHAT_RECORDING_NOTICE", "") or "").strip()[:2000],
    )
