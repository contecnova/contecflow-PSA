"""Google Cloud Speech-to-Text provider.

API: POST https://speech.googleapis.com/v1/speech:recognize?key={API_KEY}
Body JSON: ``{"config": {...}, "audio": {"content": "<base64>"}}``

Auth: API key (más simple) o service account OAuth2 (requeriría google-auth,
no instalado). Usamos API key vía query param para mantener cero dependencias
nuevas.

Limitación: el endpoint síncrono acepta audios <= 60s. Para más largo se
necesitaría ``longrunningrecognize`` (otro endpoint + polling). Documentado.

Encoding inferido del content-type:
  - audio/wav, audio/x-wav        → LINEAR16
  - audio/ogg, audio/ogg;codecs=… → OGG_OPUS
  - audio/webm                    → WEBM_OPUS
  - audio/flac                    → FLAC
  - audio/mp3, audio/mpeg         → MP3
"""
from __future__ import annotations

import base64
import os
from typing import Optional

import httpx

from app.core.config import settings
from app.services.stt.base import STTError, STTProvider, STTResult
import logging

logger = logging.getLogger(__name__)


def _google_setting(name: str, default: str = "") -> str:
    return getattr(settings, name, None) or os.environ.get(name, default) or default


_ENCODING_MAP = {
    "audio/wav": "LINEAR16",
    "audio/x-wav": "LINEAR16",
    "audio/wave": "LINEAR16",
    "audio/ogg": "OGG_OPUS",
    "audio/ogg;codecs=opus": "OGG_OPUS",
    "audio/webm": "WEBM_OPUS",
    "audio/webm;codecs=opus": "WEBM_OPUS",
    "audio/flac": "FLAC",
    "audio/mp3": "MP3",
    "audio/mpeg": "MP3",
}


def _encoding_for(content_type: str) -> str:
    return _ENCODING_MAP.get((content_type or "").lower(), "ENCODING_UNSPECIFIED")


class GoogleSTTProvider(STTProvider):
    name = "google"

    def __init__(self, api_key: Optional[str] = None, language: Optional[str] = None, db=None, org_id=None) -> None:
        ui_key = ui_lang = None
        if db is not None:
            try:
                from app.services.settings_service import get_runtime_str
                from app.services.integration_credentials_service import get_credential
                ui_key  = get_credential(db, "ai_providers", "google_stt_api_key", org_id=org_id)
                ui_lang = get_runtime_str(db, "GOOGLE_STT_LANGUAGE", org_id)
            except Exception:  # noqa: S110
                pass
        self._api_key = api_key or ui_key or _google_setting("GOOGLE_STT_API_KEY")
        self._default_language = language or ui_lang or _google_setting("GOOGLE_STT_LANGUAGE", "es-ES")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def transcribe(self, audio_bytes, filename, content_type, language=None):
        if not self.is_available():
            raise STTError(self.name, "GOOGLE_STT_API_KEY no configurado")

        body = {
            "config": {
                "encoding": _encoding_for(content_type or ""),
                "languageCode": language or self._default_language,
                "enableAutomaticPunctuation": True,
            },
            "audio": {
                "content": base64.b64encode(audio_bytes).decode("ascii"),
            },
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://speech.googleapis.com/v1/speech:recognize",
                    params={"key": self._api_key},
                    json=body,
                )
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
        results = data.get("results") or []
        chunks = []
        for r in results:
            alt = (r.get("alternatives") or [{}])[0]
            t = alt.get("transcript")
            if t:
                chunks.append(t.strip())
        text = " ".join(chunks).strip()
        if not text:
            raise STTError(self.name, "Resultado vacío", status_code=422)

        return STTResult(
            text=text,
            provider=self.name,
            model="google-stt-v1",
            language=language or self._default_language,
        )
