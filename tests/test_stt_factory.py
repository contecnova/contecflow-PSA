"""Tests for the STT (Speech-to-Text) multi-provider factory (Item #51)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.stt import (
    STTError,
    STTProvider,
    STTResult,
    get_stt_provider,
    list_known_providers,
    transcribe_audio,
)
from app.services.stt.azure_stt import AzureSTTProvider
from app.services.stt.google_stt import GoogleSTTProvider, _encoding_for
from app.services.stt.openai_stt import OpenAISTTProvider
from app.services.stt.whisper_local_stt import WhisperLocalSTTProvider


def test_known_providers_list():
    names = set(list_known_providers())
    assert names == {"openai", "azure", "google", "whisper_local"}


def test_get_stt_provider_unknown_raises_value_error():
    with pytest.raises(ValueError, match="STT provider desconocido"):
        get_stt_provider("quantum-stt")


def test_get_stt_provider_returns_correct_type():
    assert isinstance(get_stt_provider("openai"), OpenAISTTProvider)
    assert isinstance(get_stt_provider("azure"), AzureSTTProvider)
    assert isinstance(get_stt_provider("google"), GoogleSTTProvider)
    assert isinstance(get_stt_provider("whisper_local"), WhisperLocalSTTProvider)


def test_openai_provider_unavailable_when_no_key():
    p = OpenAISTTProvider(api_key="")
    assert p.is_available() is False
    with pytest.raises(STTError, match="OPENAI_API_KEY not configured"):
        p.transcribe(b"x", "a.wav", "audio/wav")


def test_azure_provider_unavailable_when_no_key():
    p = AzureSTTProvider(api_key="", region="")
    assert p.is_available() is False
    with pytest.raises(STTError, match="AZURE_SPEECH_KEY"):
        p.transcribe(b"x", "a.wav", "audio/wav")


def test_google_provider_unavailable_when_no_key():
    p = GoogleSTTProvider(api_key="")
    assert p.is_available() is False
    with pytest.raises(STTError, match="GOOGLE_STT_API_KEY"):
        p.transcribe(b"x", "a.wav", "audio/wav")


def test_google_encoding_mapping():
    assert _encoding_for("audio/wav") == "LINEAR16"
    assert _encoding_for("audio/ogg") == "OGG_OPUS"
    assert _encoding_for("audio/webm") == "WEBM_OPUS"
    assert _encoding_for("audio/flac") == "FLAC"
    assert _encoding_for("audio/unknown") == "ENCODING_UNSPECIFIED"


def test_whisper_local_unavailable_when_no_binary():
    # PATH no debería tener un binario llamado "definitely-not-on-path-xyz".
    p = WhisperLocalSTTProvider(binary="definitely-not-on-path-xyz")
    assert p.is_available() is False
    with pytest.raises(STTError, match="no encontrado"):
        p.transcribe(b"x", "a.wav", "audio/wav")


def test_transcribe_audio_raises_when_no_providers_configured(monkeypatch):
    # Sin credenciales para ningún provider, el factory debe lanzar STTError
    # con un mensaje claro al usuario.
    monkeypatch.setenv("STT_PROVIDER", "openai")
    monkeypatch.setenv("STT_FALLBACK_PROVIDERS", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_STT_API_KEY", raising=False)

    # También vaciar el settings cache para que el factory respete env
    with patch("app.services.stt.settings") as mock_settings:
        mock_settings.STT_PROVIDER = "openai"
        mock_settings.STT_FALLBACK_PROVIDERS = ""
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.AZURE_SPEECH_KEY = ""
        mock_settings.AZURE_SPEECH_REGION = ""
        mock_settings.GOOGLE_STT_API_KEY = ""
        with patch("app.services.stt.openai_stt.settings", mock_settings):
            with patch("app.services.stt.azure_stt.settings", mock_settings):
                with patch("app.services.stt.google_stt.settings", mock_settings):
                    with pytest.raises(STTError, match="Ningún STT provider está disponible"):
                        transcribe_audio(b"dummy", "audio.wav", "audio/wav")


def test_transcribe_audio_falls_back_when_primary_fails(monkeypatch):
    """Cuando el primario tira STTError, debe intentar el siguiente fallback
    y devolver el resultado del que funcione."""
    monkeypatch.setenv("STT_PROVIDER", "azure")
    monkeypatch.setenv("STT_FALLBACK_PROVIDERS", "openai")

    class _MockBroken(STTProvider):
        name = "azure"
        def is_available(self): return True
        def transcribe(self, *a, **kw):
            raise STTError("azure", "boom", status_code=502)

    class _MockOk(STTProvider):
        name = "openai"
        def is_available(self): return True
        def transcribe(self, *a, **kw):
            return STTResult(text="ok-text", provider="openai")

    with patch("app.services.stt._PROVIDER_REGISTRY", {
        "azure": _MockBroken,
        "openai": _MockOk,
    }):
        with patch("app.services.stt.settings") as mock_settings:
            mock_settings.STT_PROVIDER = "azure"
            mock_settings.STT_FALLBACK_PROVIDERS = "openai"
            result = transcribe_audio(b"x", "a.wav", "audio/wav")
            assert result.text == "ok-text"
            assert result.provider == "openai"


def test_transcribe_audio_raises_last_error_when_all_fail(monkeypatch):
    class _MockBrokenA(STTProvider):
        name = "azure"
        def is_available(self): return True
        def transcribe(self, *a, **kw):
            raise STTError("azure", "azure-failed", status_code=502)

    class _MockBrokenB(STTProvider):
        name = "openai"
        def is_available(self): return True
        def transcribe(self, *a, **kw):
            raise STTError("openai", "openai-failed", status_code=500)

    with patch("app.services.stt._PROVIDER_REGISTRY", {
        "azure": _MockBrokenA,
        "openai": _MockBrokenB,
    }):
        with patch("app.services.stt.settings") as mock_settings:
            mock_settings.STT_PROVIDER = "azure"
            mock_settings.STT_FALLBACK_PROVIDERS = "openai"
            with pytest.raises(STTError, match="openai-failed"):
                transcribe_audio(b"x", "a.wav", "audio/wav")


def test_fallback_skips_providers_without_credentials():
    """Provider configurado como fallback pero sin credenciales debe ser
    skipped (no contar como intento)."""
    class _NotAvailable(STTProvider):
        name = "azure"
        def is_available(self): return False
        def transcribe(self, *a, **kw):
            raise AssertionError("Should never be called")

    class _OkSecondary(STTProvider):
        name = "openai"
        def is_available(self): return True
        def transcribe(self, *a, **kw):
            return STTResult(text="secondary-ok", provider="openai")

    with patch("app.services.stt._PROVIDER_REGISTRY", {
        "azure": _NotAvailable,
        "openai": _OkSecondary,
    }):
        with patch("app.services.stt.settings") as mock_settings:
            mock_settings.STT_PROVIDER = "azure"
            mock_settings.STT_FALLBACK_PROVIDERS = "openai"
            result = transcribe_audio(b"x", "a.wav", "audio/wav")
            assert result.text == "secondary-ok"
