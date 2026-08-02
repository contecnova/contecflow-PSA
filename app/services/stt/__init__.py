"""STT (Speech-to-Text) factory.

Uso típico:
    from app.services.stt import transcribe_audio
    result = transcribe_audio(audio_bytes, filename, content_type, language="es")
    print(result.text, result.provider)

Settings relevantes (todos optional; los defaults asumen OpenAI):
  - ``STT_PROVIDER``           — openai | azure | google | whisper_local
  - ``STT_FALLBACK_PROVIDERS`` — lista CSV: "azure,whisper_local"
  - Credenciales según provider (ver clases en este package).

Item #51: antes el sistema estaba force-hardcoded a OpenAI. Esta capa permite
intercambiar providers sin tocar endpoints y configurar fallbacks ordenados.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, List, Optional

from app.core.config import settings
from app.services.stt.azure_stt import AzureSTTProvider
from app.services.stt.base import STTError, STTProvider, STTResult
from app.services.stt.google_stt import GoogleSTTProvider
from app.services.stt.openai_stt import OpenAISTTProvider
from app.services.stt.whisper_local_stt import WhisperLocalSTTProvider

logger = logging.getLogger(__name__)


_PROVIDER_REGISTRY = {
    "openai":        OpenAISTTProvider,
    "azure":         AzureSTTProvider,
    "google":        GoogleSTTProvider,
    "whisper_local": WhisperLocalSTTProvider,
}


def _setting(name: str, default: str = "", db=None, org_id=None) -> str:
    """Resolve a setting with org → global runtime → env precedence.

    Used by the STT factory so admins can switch provider / fallbacks via
    Settings → Sistema → Config. dinámica → IA without redeploy.
    """
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_str
            v = get_runtime_str(db, name, org_id)
            if v:
                return v
        except Exception:  # noqa: S110
            pass
    return getattr(settings, name, None) or os.environ.get(name, default) or default


def list_known_providers() -> List[str]:
    return list(_PROVIDER_REGISTRY.keys())


def get_stt_provider(name: Optional[str] = None, db=None, org_id=None) -> STTProvider:
    """Devuelve la instancia del provider solicitado. Sin argumento → usa
    ``STT_PROVIDER`` (runtime → env, default ``openai``).
    """
    chosen = (name or _setting("STT_PROVIDER", "openai", db=db, org_id=org_id)).strip().lower()
    cls = _PROVIDER_REGISTRY.get(chosen)
    if cls is None:
        raise ValueError(
            f"STT provider desconocido: '{chosen}'. "
            f"Opciones: {', '.join(_PROVIDER_REGISTRY.keys())}"
        )
    return cls(db=db, org_id=org_id) if _accepts_db(cls) else cls()


def _accepts_db(cls) -> bool:
    """True if the provider __init__ accepts a ``db`` kwarg (post-migration)."""
    import inspect
    try:
        return "db" in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return False


def _ordered_providers(db=None, org_id=None) -> Iterable[STTProvider]:
    """Genera providers en orden: primario + fallbacks configurados.

    ``STT_PROVIDER`` + ``STT_FALLBACK_PROVIDERS`` resuelven primero via
    Settings → Config. dinámica → IA y luego al env.
    """
    seen = set()
    primary = _setting("STT_PROVIDER", "openai", db=db, org_id=org_id).strip().lower()
    candidates = [primary]
    fallback_csv = _setting("STT_FALLBACK_PROVIDERS", "", db=db, org_id=org_id)
    if fallback_csv:
        candidates.extend(p.strip().lower() for p in fallback_csv.split(",") if p.strip())

    for name in candidates:
        if name in seen or name not in _PROVIDER_REGISTRY:
            continue
        seen.add(name)
        try:
            cls = _PROVIDER_REGISTRY[name]
            provider = cls(db=db, org_id=org_id) if _accepts_db(cls) else cls()
        except Exception as exc:
            logger.warning("STT provider '%s' falló al instanciar: %s", name, exc)
            continue
        if provider.is_available():
            yield provider
        else:
            logger.info("STT provider '%s' configurado pero sin credenciales — skip", name)


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: Optional[str] = None,
    db=None,
    org_id=None,
) -> STTResult:
    """Transcribe usando el provider primario; si falla, recorre los fallbacks.

    Cuando se llama con ``db`` (recomendado desde endpoints), el factory
    resuelve provider/fallbacks/credenciales contra la BD; si no, usa env.
    """
    last_error: STTError | None = None
    attempted = 0
    for provider in _ordered_providers(db=db, org_id=org_id):
        attempted += 1
        try:
            return provider.transcribe(audio_bytes, filename, content_type, language=language)
        except STTError as exc:
            logger.warning("STT provider '%s' falló: %s", provider.name, exc)
            last_error = exc
            continue

    if attempted == 0:
        raise STTError(
            "factory",
            "Ningún STT provider está disponible. Configura credenciales para "
            f"al menos uno de: {', '.join(_PROVIDER_REGISTRY.keys())}",
        )
    assert last_error is not None  # defensive  # noqa: S101
    raise last_error


__all__ = [
    "STTError",
    "STTProvider",
    "STTResult",
    "get_stt_provider",
    "list_known_providers",
    "transcribe_audio",
]
