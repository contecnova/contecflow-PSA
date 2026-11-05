"""Transcripción audio→texto para subtítulos en tiempo real y resúmenes.

Backends:
  - OPENAI_API_KEY  → usa Whisper API
  - WHISPER_LOCAL=1 → usa whisper.cpp si está instalado
  - sin nada       → devuelve "" (los subtítulos se quedan vacíos)
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


def transcribe_audio_chunk(data: bytes, filename: str = "chunk.webm", db=None, org_id=None) -> str:
    """Devuelve el texto transcrito o "".

    Item #51: ahora delegamos primero al factory STT (que respeta
    ``STT_PROVIDER`` + fallbacks). Si el factory no tiene providers
    disponibles, mantenemos el comportamiento legacy de este módulo
    (OpenAI directo / whisper local) como red de seguridad para chunks
    pequeños del módulo de colaboración.
    """
    try:
        from app.services.stt import transcribe_audio as _factory_transcribe, STTError as _STTError
        # Revisión 2026-11: con la empresa, usa SU configuración de STT y su tope.
        result = _factory_transcribe(data, filename, "audio/webm", language="es", db=db, org_id=org_id)
        return (result.text or "").strip()
    except _STTError as exc:
        logger.warning("Factory STT failed for chunk: %s", exc)
    except Exception as exc:
        logger.warning("Factory STT crash for chunk: %s", exc)

    # Fallback legacy — solo si el factory completo no pudo.
    # env-driven feature toggle: legacy fallback path bypasses the STT factory and
    # is intentionally controlled via raw env to keep the failsafe independent of Settings.
    if os.environ.get("OPENAI_API_KEY"):
        return _via_openai(data, filename) or ""
    if os.environ.get("WHISPER_LOCAL") == "1":
        return _via_whisper_local(data, filename) or ""
    return ""


def _via_openai(data: bytes, filename: str) -> Optional[str]:
    try:
        import httpx
        files = {"file": (filename, data, "audio/webm")}
        r = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            data={
                "model": os.environ.get("OPENAI_STT_MODEL") or "gpt-4o-mini-transcribe",
                "language": "es",
            },
            files=files,
            timeout=30,
        )
        if r.status_code >= 400:
            return None
        return (r.json().get("text") or "").strip()
    except Exception as exc:
        logger.warning("openai transcribe failed: %s", exc)
        return None


def _via_whisper_local(data: bytes, filename: str) -> Optional[str]:
    binary = os.environ.get("WHISPER_BIN", "whisper")
    model = os.environ.get("WHISPER_MODEL", "base")
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, filename)
        with open(in_path, "wb") as f:
            f.write(data)
        try:
            subprocess.run(
                [binary, in_path, "--model", model, "--language", "es", "--output_format", "txt", "--output_dir", td],
                check=True, capture_output=True, timeout=120,
            )
            txt_path = in_path.rsplit(".", 1)[0] + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path) as f:
                    return f.read().strip()
        except Exception as exc:
            logger.warning("whisper local failed: %s", exc)
    return None


# ── Resumen post-llamada (mejor IA si hay) ──────────────────────────────────
def summarize_text(text: str, db=None, organization_id=None) -> tuple[str, list[dict]]:
    """Devuelve (summary, action_items).

    Revisión 2026-11: el resumen llamaba a OpenAI directamente con la clave del
    `.env` (sin el proveedor de la empresa, sin tope, sin registro de uso ni
    guardarraíles). Ahora va por `call_ai` con la empresa de la llamada; sin IA,
    el resumen heurístico de siempre.
    """
    if not text:
        return "", []
    if db is not None and organization_id:
        result = _summarize_con_call_ai(text, db, organization_id)
        if result:
            return result
    # Fallback heurístico
    import re
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 20]
    summary = "• " + "\n• ".join(sentences[:5]) if sentences else text[:280]
    actions = []
    for s in sentences:
        low = s.lower()
        if any(kw in low for kw in ("acción", "tarea", "todo", "asignar", "antes del", "deadline")):
            actions.append({"text": s[:200]})
    return summary, actions


def _summarize_con_call_ai(text: str, db, organization_id) -> Optional[tuple[str, list[dict]]]:
    import json
    from app.services.ai_provider_service import PresupuestoDeIAAgotado, call_ai, es_aviso_de_ia
    try:
        crudo = call_ai(db, [{"role": "user", "content": f"Resume esta reunión y extrae las acciones:\n\n{text[:8000]}"}],
                        system=("Resumes reuniones en español. Responde SOLO JSON con las claves 'summary' (texto) y "
                                "'actions' (lista de {text, owner})."),
                        module="meeting_assistant", organization_id=organization_id, is_superadmin=False,
                        max_tokens=800)
    except PresupuestoDeIAAgotado:
        logger.info("resumen de reunión: tope diario de IA alcanzado; resumen heurístico")
        return None
    if not crudo or es_aviso_de_ia(crudo) or crudo.startswith("["):
        return None
    try:
        datos = json.loads(crudo.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        return str(datos.get("summary", "")), list(datos.get("actions", []))
    except (ValueError, AttributeError):
        return crudo.strip(), []

