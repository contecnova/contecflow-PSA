"""STT (Speech-to-Text) provider abstraction.

Item #51: Antes el sistema solo soportaba OpenAI/Whisper hardcoded. Esta capa
extrae la interfaz para que distintas implementaciones (OpenAI, Azure Speech,
Google Speech-to-Text, whisper.cpp local) puedan ser intercambiadas vía
``settings.STT_PROVIDER`` sin tocar los endpoints que las consumen.

Modelo simple — sin async, sin streaming, una llamada blocking que recibe
``audio_bytes`` y devuelve texto. Los streaming/realtime se manejarían en
otra capa si se necesitaran (no es el caso hoy).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


class STTError(Exception):
    """Error genérico de transcripción. Mantiene el provider y el status code
    HTTP devuelto por la API remota (cuando aplica) para que el caller pueda
    decidir si reintentar con otro provider o devolver el error al user."""

    def __init__(self, provider: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status_code = status_code


@dataclass
class STTResult:
    text: str
    provider: str
    model: str | None = None
    duration_ms: int | None = None
    language: str | None = None


class STTProvider(abc.ABC):
    """Interface mínima que toda implementación STT debe satisfacer."""

    name: str = "abstract"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Devuelve True si las credenciales/binarios necesarios están
        configurados. Permite al factory descartar providers no listos sin
        intentar la llamada y fallar."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
    ) -> STTResult:
        """Transcribe el audio recibido. Lanza ``STTError`` en fallo."""
