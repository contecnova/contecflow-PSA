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


def transcribe_audio_chunk(data: bytes, filename: str = "chunk.webm") -> str:
    """Devuelve el texto transcrito o "".

    Item #51: ahora delegamos primero al factory STT (que respeta
    ``STT_PROVIDER`` + fallbacks). Si el factory no tiene providers
    disponibles, mantenemos el comportamiento legacy de este módulo
    (OpenAI directo / whisper local) como red de seguridad para chunks
    pequeños del módulo de colaboración.
    """
    try:
        from app.services.stt import transcribe_audio as _factory_transcribe, STTError as _STTError  # noqa: PLC0415
        result = _factory_transcribe(data, filename, "audio/webm", language="es")
        return (result.text or "").strip()
    except _STTError as exc:
        logger.warning("Factory STT failed for chunk: %s", exc)
    except Exception as exc:
        logger.warning("Factory STT crash for chunk: %s", exc)

    # Fallback legacy — solo si el factory completo no pudo.
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
            proc = subprocess.run(
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
def summarize_text(text: str) -> tuple[str, list[dict]]:
    """Devuelve (summary, action_items)."""
    if not text:
        return "", []
    if os.environ.get("OPENAI_API_KEY"):
        result = _summarize_openai(text)
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


def _summarize_openai(text: str) -> Optional[tuple[str, list[dict]]]:
    try:
        import httpx, json
        body = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": "Eres un asistente que resume reuniones en español. Responde JSON con keys 'summary' (texto) y 'actions' (lista de {text, owner})."},
                {"role": "user", "content": f"Resume esta reunión y extrae las acciones:\n\n{text[:8000]}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        if r.status_code >= 400:
            return None
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return data.get("summary", ""), data.get("actions", [])
    except Exception as exc:
        logger.warning("openai summarize failed: %s", exc)
        return None
