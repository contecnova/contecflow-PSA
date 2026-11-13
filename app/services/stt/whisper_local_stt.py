"""Whisper local (whisper.cpp) STT provider.

Útil para despliegues on-prem / compliance que no admiten enviar audio a la
nube. Requiere el binario ``whisper`` (o ``whisper-cli`` de whisper.cpp) en el
PATH y un fichero de modelo. Lento sin GPU pero gratis y sin red.

Configuración:
  - ``WHISPER_LOCAL_BIN`` (si no, ``WHISPER_BIN``; default: ``whisper``)
  - ``WHISPER_LOCAL_MODEL`` (si no, ``WHISPER_MODEL``; default: ``base``)
  - ``WHISPER_LOCAL_LANGUAGE`` (default: ``es``); todos en `Settings`
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from app.core.config import settings
from app.services.stt.base import STTError, STTProvider, STTResult

logger = logging.getLogger(__name__)


class WhisperLocalSTTProvider(STTProvider):
    name = "whisper_local"

    def __init__(
        self,
        binary: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        self._binary = binary or settings.WHISPER_LOCAL_BIN or settings.WHISPER_BIN or "whisper"
        self._model = model or settings.WHISPER_LOCAL_MODEL or settings.WHISPER_MODEL or "base"
        self._language = language or settings.WHISPER_LOCAL_LANGUAGE or settings.DEFAULT_LANGUAGE

    def is_available(self) -> bool:
        return shutil.which(self._binary) is not None

    def transcribe(self, audio_bytes, filename, content_type, language=None):
        if not self.is_available():
            raise STTError(self.name, f"Binario '{self._binary}' no encontrado en PATH")

        # whisper.cpp acepta wav/mp3/m4a/flac; usamos la extensión del filename si
        # parece razonable, si no .wav como fallback.
        ext = (filename.rsplit(".", 1)[-1] if "." in filename else "wav").lower()[:5]
        with tempfile.TemporaryDirectory() as td:
            in_path = os.path.join(td, f"input.{ext}")
            with open(in_path, "wb") as f:
                f.write(audio_bytes)
            cmd = [
                self._binary,
                in_path,
                "--model", self._model,
                "--language", language or self._language,
                "--output_format", "txt",
                "--output_dir", td,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            except subprocess.TimeoutExpired as exc:
                raise STTError(self.name, "Timeout (>5 min) ejecutando whisper local") from exc
            except subprocess.CalledProcessError as exc:
                msg = (exc.stderr or b"").decode("utf-8", errors="ignore")[:200]
                raise STTError(self.name, f"whisper local falló: {msg}") from exc
            except FileNotFoundError as exc:
                raise STTError(self.name, f"Binario '{self._binary}' no encontrado") from exc

            txt_path = in_path.rsplit(".", 1)[0] + ".txt"
            if not os.path.exists(txt_path):
                raise STTError(self.name, "Whisper local no produjo .txt de salida")
            with open(txt_path) as f:
                text = f.read().strip()
            if not text:
                raise STTError(self.name, "Resultado vacío")

            return STTResult(
                text=text, provider=self.name, model=self._model,
                language=language or self._language,
            )
