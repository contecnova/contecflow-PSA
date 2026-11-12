"""Azure Speech-to-Text provider.

API: POST https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1
Headers:
  - ``Ocp-Apim-Subscription-Key``: subscription key
  - ``Content-Type``: audio mime (audio/wav, audio/ogg;codecs=opus, ...)
Query:
  - language=es-ES (BCP-47, default ``settings.AZURE_STT_LANGUAGE``)
  - format=detailed

Respuesta short JSON: ``{"RecognitionStatus": "Success", "DisplayText": "..."}``.

Limitación: el endpoint short-recognize de Azure solo acepta audios <= 60s y sin
chunks. Para audios largos se necesitaría batch transcription (otra API).
Documentado: si esto resulta limitante, migrar a la API de batch.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.core.config import settings
from app.services.stt.base import STTError, STTProvider, STTResult
import logging

logger = logging.getLogger(__name__)


def _azure_setting(name: str, default: str = "") -> str:
    return getattr(settings, name, None) or os.environ.get(name, default) or default


class AzureSTTProvider(STTProvider):
    name = "azure"

    def __init__(
        self,
        api_key: Optional[str] = None,
        region: Optional[str] = None,
        language: Optional[str] = None,
        db=None,
        org_id=None,
    ) -> None:
        ui_key = ui_region = ui_lang = None
        if db is not None:
            try:
                from app.services.settings_service import get_runtime_str
                from app.services.integration_credentials_service import get_credential
                ui_key    = get_credential(db, "ai_providers", "azure_speech_key", org_id=org_id)
                ui_region = get_runtime_str(db, "AZURE_SPEECH_REGION", org_id)
                ui_lang   = get_runtime_str(db, "AZURE_STT_LANGUAGE", org_id)
            except Exception:
                logger.debug("__init__: fallo best-effort ignorado", exc_info=True)
        self._api_key = api_key or ui_key or _azure_setting("AZURE_SPEECH_KEY")
        self._region = region or ui_region or _azure_setting("AZURE_SPEECH_REGION", "westeurope")
        self._default_language = language or ui_lang or _azure_setting("AZURE_STT_LANGUAGE", "es-ES")

    def is_available(self) -> bool:
        return bool(self._api_key and self._region)

    def transcribe(self, audio_bytes, filename, content_type, language=None):
        if not self.is_available():
            raise STTError(self.name, "AZURE_SPEECH_KEY/REGION no configurados")

        url = (
            f"https://{self._region}.stt.speech.microsoft.com"
            "/speech/recognition/conversation/cognitiveservices/v1"
        )
        # El llamador pasa el idioma del usuario en ISO 639-1 ("es"); Azure
        # quiere BCP-47 y, si es el mismo idioma, se respeta la variante
        # configurada (AZURE_STT_LANGUAGE).
        from app.services.formato_regional import a_bcp47
        language = a_bcp47(language, self._default_language)
        params = {
            "language": language,
            "format": "detailed",
        }
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": content_type or "audio/wav",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, params=params, headers=headers, content=audio_bytes)
        except httpx.TimeoutException as exc:
            raise STTError(self.name, "Timeout esperando respuesta", status_code=504) from exc
        except Exception as exc:
            raise STTError(self.name, f"Error de red: {exc}") from exc

        if resp.status_code != 200:
            raise STTError(
                self.name,
                f"API devolvió {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )

        data = resp.json() or {}
        status = data.get("RecognitionStatus")
        if status != "Success":
            raise STTError(self.name, f"RecognitionStatus={status}", status_code=422)

        text = (data.get("DisplayText") or "").strip()
        if not text:
            # Cuando hay alternativas detalladas, intentar la mejor de ``NBest``.
            nbest = data.get("NBest") or []
            if nbest:
                text = (nbest[0].get("Display") or nbest[0].get("Lexical") or "").strip()
        if not text:
            raise STTError(self.name, "Resultado vacío", status_code=422)

        return STTResult(
            text=text, provider=self.name, model="azure-stt-short",
            language=language or self._default_language,
        )
