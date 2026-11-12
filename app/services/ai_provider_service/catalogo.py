"""Catalogo de proveedores y modelos (de `app/core/ai_models.json`), modelos retirados y normalizacion de URLs base.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import os
import json

from app.core.config import settings

def _normalize_openai_base(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base[: -len("/chat/completions")]
    return base


def _normalize_ollama_base(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/api/chat"):
        return base[: -len("/api/chat")]
    return base

# ── Catálogo de modelos por proveedor ─────────────────────────────────────────
# Auditoria 2026-11: los modelos y sus precios ($/M tokens, usados para el coste
# de cada llamada) estaban escritos aqui; cambian cada pocos meses y obligaban a
# tocar codigo. Ahora salen de `app/core/ai_models.json`, y una instalacion puede
# usar el suyo con `AI_MODELS_CATALOG_PATH` sin desplegar codigo.
_MODELOS_POR_DEFECTO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "core", "ai_models.json")


def _cargar_modelos() -> dict:
    ruta = os.getenv("AI_MODELS_CATALOG_PATH") or _MODELOS_POR_DEFECTO
    with open(ruta, encoding="utf-8") as fichero:
        return json.load(fichero)


_MODELOS = _cargar_modelos()


def _modelos(proveedor: str) -> list:
    return _MODELOS.get(proveedor, [])


PROVIDER_CATALOG = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "icon": "🟠",
        "models": _modelos("anthropic"),
        "base_url": settings.ANTHROPIC_API_URL,
        "key_hint": "sk-ant-...",
        "docs_url": settings.ANTHROPIC_DOCS_URL,
    },
    "openai": {
        "name": "OpenAI",
        "icon": "🟢",
        "models": _modelos("openai"),
        "base_url": settings.OPENAI_API_URL,
        "key_hint": "sk-...",
        "docs_url": settings.OPENAI_DOCS_URL,
    },
    "gemini": {
        "name": "Google (Gemini)",
        "icon": "🔵",
        "models": _modelos("gemini"),
        "base_url": settings.GEMINI_API_URL,
        "key_hint": "AIza...",
        "docs_url": settings.GEMINI_DOCS_URL,
    },
    "deepseek": {
        "name": "DeepSeek",
        "icon": "🐋",
        "models": _modelos("deepseek"),
        "base_url": settings.DEEPSEEK_API_URL,
        "key_hint": "sk-...",
        "docs_url": settings.DEEPSEEK_DOCS_URL,
    },
    "groq": {
        "name": "Groq (ultra rápido)",
        "icon": "⚡",
        "models": _modelos("groq"),
        "base_url": settings.GROQ_API_URL,
        "key_hint": "gsk_...",
        "docs_url": settings.GROQ_DOCS_URL,
    },
    "mistral": {
        "name": "Mistral AI",
        "icon": "🌪",
        "models": _modelos("mistral"),
        "base_url": settings.MISTRAL_API_URL,
        "key_hint": "...",
        "docs_url": settings.MISTRAL_DOCS_URL,
    },
    "ollama": {
        "name": "Ollama (local)",
        "icon": "🦙",
        "models": _modelos("ollama"),
        "base_url": settings.OLLAMA_BASE_URL + "/api/chat",
        "key_hint": "(no requiere clave)",
        "docs_url": settings.OLLAMA_DOCS_URL,
    },
    "azure": {
        "name": "Azure OpenAI",
        "icon": "☁️",
        "models": _modelos("azure"),
        "base_url": settings.AZURE_OPENAI_API_URL,
        "key_hint": "(Azure API key)",
        "docs_url": settings.AZURE_OPENAI_DOCS_URL,
    },
}

# ── Modelos retirados por proveedor ───────────────────────────────────────────
_DEPRECATED_MODELS: dict = {
    "anthropic": set(),
    "openai":    set(),
    "gemini":    {"gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"},
    "groq":      {"mixtral-8x7b-32768"},
    "mistral":   set(),
    "deepseek":  set(),
    "ollama":    set(),
    "azure":     set(),
}


def _validate_model(provider: str, model: str) -> None:
    deprecated = _DEPRECATED_MODELS.get(provider, set())
    if model in deprecated:
        raise Exception(
            f"El modelo '{model}' ha sido retirado por el proveedor '{provider}' y ya no está disponible. "
            "Por favor, actualiza la configuración del proveedor IA con un modelo vigente."
        )
