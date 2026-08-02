"""OpenAI Speech-to-Text provider (Whisper / gpt-4o-transcribe).

API: POST {OPENAI_API_URL}/audio/transcriptions
  - Multipart form: file + model
  - Auth: Bearer {OPENAI_API_KEY}
  - Modelos: ``gpt-4o-mini-transcribe`` (default tras Wave E),
    ``gpt-4o-transcribe``, ``whisper-1`` (legacy).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.core.config import settings
from app.services.stt.base import STTError, STTProvider, STTResult


class OpenAISTTProvider(STTProvider):
    name = "openai"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, db=None, org_id=None) -> None:
        ui_model = None
        ui_key = None
        if db is not None:
            try:
                from app.services.settings_service import get_runtime_str
                from app.services.integration_credentials_service import get_credential
                ui_model = get_runtime_str(db, "OPENAI_STT_MODEL", org_id)
                ui_key   = get_credential(db, "ai_providers", "openai_api_key", org_id=org_id)
            except Exception:  # noqa: S110
                pass
        self._model = (
            model
            or ui_model
            or os.environ.get("OPENAI_STT_MODEL")
            or getattr(settings, "OPENAI_STT_MODEL", None)
            or "gpt-4o-mini-transcribe"
        )
        self._api_key = api_key or ui_key or settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = settings.OPENAI_API_URL or "https://api.openai.com/v1"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def transcribe(self, audio_bytes, filename, content_type, language=None):
        if not self.is_available():
            raise STTError(self.name, "OPENAI_API_KEY not configured")

        data = {"model": self._model}
        if language:
            data["language"] = language

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (filename, audio_bytes, content_type or "audio/wav")},
                    data=data,
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

        text = (resp.json().get("text") or "").strip()
        if not text:
            raise STTError(self.name, "Resultado vacío (audio sin habla detectable)", status_code=422)

        return STTResult(text=text, provider=self.name, model=self._model, language=language)
