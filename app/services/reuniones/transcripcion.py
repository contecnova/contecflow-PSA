"""Voz a texto con los proveedores que la empresa permite, y texto a segmentos.

- STT: la factoría de siempre (`app.services.stt`), pero solo con los
  proveedores permitidos: whisper local siempre; los externos (OpenAI, Azure,
  Google) solo con `transcription.allow_external_stt` y su contrato.
- VTT (Teams, Zoom): `<v Nombre>texto</v>` o `Nombre: texto` en cada cue.
- Texto pegado: `[mm:ss] Nombre: texto`, `Nombre: texto` o párrafos sueltos.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo

logger = logging.getLogger(__name__)


def proveedores_configurados(db: Session, org: Optional[str]) -> list[str]:
    """Los STT de la empresa en su orden (primario + respaldos), estén o no permitidos."""
    from app.services.stt import _PROVIDER_REGISTRY, _setting
    primero = _setting("STT_PROVIDER", "openai", db=db, org_id=org).strip().lower()
    resto = [p.strip().lower() for p in _setting("STT_FALLBACK_PROVIDERS", "", db=db, org_id=org).split(",")]
    salida: list[str] = []
    for p in [primero, *resto]:
        if p and p in _PROVIDER_REGISTRY and p not in salida:
            salida.append(p)
    return salida


def _externo_permitido(db: Session, org: Optional[str]) -> bool:
    from app.services.reuniones.config import leer
    tr = leer(db, org)["transcription"]
    return bool(tr.get("allow_external_stt") and (tr.get("external_stt_contract") or "").strip())


def proveedores_permitidos(db: Session, org: Optional[str]) -> list[str]:
    from app.services.reuniones.config import STT_LOCALES
    externos = _externo_permitido(db, org)
    candidatos = proveedores_configurados(db, org)
    for local in STT_LOCALES:
        if local not in candidatos:
            candidatos.append(local)
    return [p for p in candidatos if p in STT_LOCALES or externos]


def transcribir(db: Session, org: Optional[str], datos: bytes, nombre: str, mime: str,
                idioma: Optional[str] = None):
    """`STTResult` del primer proveedor permitido y disponible que lo consiga."""
    from app.services.stt import STTError, get_stt_provider
    if org:
        from app.services.ai_provider_service import _exigir_presupuesto
        _exigir_presupuesto(db, org)
    ultimo: Optional[Exception] = None
    probados = 0
    for nombre_p in proveedores_permitidos(db, org):
        try:
            proveedor = get_stt_provider(nombre_p, db=db, org_id=org)
        except Exception as exc:  # noqa: BLE001 - un proveedor mal configurado no tumba los demás
            logger.warning("reuniones: STT %s no instanciable: %s", nombre_p, exc)
            continue
        if not proveedor.is_available():
            continue
        probados += 1
        try:
            return proveedor.transcribe(datos, nombre, mime or "audio/webm", language=idioma)
        except STTError as exc:
            logger.warning("reuniones: STT %s falló: %s", nombre_p, exc)
            ultimo = exc
    if not probados:
        raise ErrorConCodigo("reuniones_sin_stt_permitido")
    raise ultimo or ErrorConCodigo("reuniones_sin_stt_permitido")


# ── Texto a segmentos ─────────────────────────────────────────────────────────

_TIEMPO = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")
_CUE = re.compile(r"^\s*([\d:.,]+)\s*-->\s*([\d:.,]+)")
_VOZ = re.compile(r"<v(?:\.[^ >]*)?\s+([^>]+)>(.*?)(?:</v>|$)", re.S)
_HABLANTE = re.compile(r"^\s*(?:\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?([^:\[\]]{1,60}?):\s+(.+)$")


def ms(texto: str) -> Optional[int]:
    m = _TIEMPO.search(texto or "")
    if not m:
        return None
    h, mi, s, frac = m.groups()
    total = (int(h or 0) * 3600 + int(mi) * 60 + int(s)) * 1000
    if frac:
        total += int(frac.ljust(3, "0")[:3])
    return total


def de_vtt(texto: str) -> list[dict]:
    """Cues de WebVTT a segmentos `{speaker, start_ms, end_ms, text}`."""
    salida: list[dict] = []
    bloques = re.split(r"\r?\n\r?\n", (texto or "").replace("﻿", ""))
    for bloque in bloques:
        lineas = [x for x in bloque.splitlines() if x.strip()]
        idx = next((i for i, x in enumerate(lineas) if _CUE.match(x)), None)
        if idx is None:
            continue
        cue = _CUE.match(lineas[idx])
        cuerpo = "\n".join(lineas[idx + 1:]).strip()
        if not cuerpo:
            continue
        hablante = None
        voz = _VOZ.search(cuerpo)
        if voz:
            hablante, cuerpo = voz.group(1).strip(), voz.group(2).strip()
        else:
            h = _HABLANTE.match(cuerpo)
            if h:
                hablante, cuerpo = h.group(2).strip(), h.group(3).strip()
        cuerpo = re.sub(r"<[^>]+>", "", cuerpo).strip()
        if not cuerpo:
            continue
        previo = salida[-1] if salida else None
        if previo and previo["speaker"] == hablante and previo["end_ms"] == ms(cue.group(1)):
            previo["text"] += " " + cuerpo
            previo["end_ms"] = ms(cue.group(2))
            continue
        salida.append({"speaker": hablante, "start_ms": ms(cue.group(1)), "end_ms": ms(cue.group(2)),
                       "text": cuerpo})
    return salida


def de_texto(texto: str) -> list[dict]:
    """Texto pegado a segmentos. Sin «Nombre:», un segmento por párrafo y sin hablante."""
    salida: list[dict] = []
    if (texto or "").lstrip().upper().startswith("WEBVTT") or "-->" in (texto or "")[:500]:
        return de_vtt(texto)
    for linea in (texto or "").splitlines():
        if not linea.strip():
            continue
        m = _HABLANTE.match(linea)
        if m:
            salida.append({"speaker": m.group(2).strip(), "start_ms": ms(m.group(1)) if m.group(1) else None,
                           "end_ms": None, "text": m.group(3).strip()})
        elif salida:
            salida[-1]["text"] += " " + linea.strip()
        else:
            salida.append({"speaker": None, "start_ms": None, "end_ms": None, "text": linea.strip()})
    return salida


def marca(ms_: Optional[int]) -> str:
    if ms_ is None:
        return ""
    s = ms_ // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def a_texto(segmentos) -> str:
    """`[mm:ss] Hablante: texto` por línea (para el análisis y la descarga .txt)."""
    lineas = []
    for s in segmentos:
        inicio = getattr(s, "start_ms", None) if not isinstance(s, dict) else s.get("start_ms")
        quien = (getattr(s, "speaker", None) if not isinstance(s, dict) else s.get("speaker")) or ""
        texto = getattr(s, "text", None) if not isinstance(s, dict) else s.get("text")
        pre = f"[{marca(inicio)}] " if inicio is not None else ""
        lineas.append(f"{pre}{quien + ': ' if quien else ''}{texto}")
    return "\n".join(lineas)


def a_vtt(segmentos) -> str:
    def _t(v):
        v = v or 0
        return f"{v // 3600000:02d}:{v % 3600000 // 60000:02d}:{v % 60000 // 1000:02d}.{v % 1000:03d}"
    partes = ["WEBVTT", ""]
    for s in segmentos:
        inicio = s.start_ms or 0
        fin = s.end_ms if s.end_ms is not None else inicio + 5000
        voz = f"<v {s.speaker}>" if s.speaker else ""
        partes += [f"{_t(inicio)} --> {_t(fin)}", f"{voz}{s.text}", ""]
    return "\n".join(partes)
