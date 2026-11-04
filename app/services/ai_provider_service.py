"""
ai_provider_service.py — Motor unificado de llamadas IA y gestión de proveedores.

Funciones exportadas (públicas):
  PROVIDER_CATALOG          — dict con todos los proveedores y modelos
  get_default_provider(db)  — obtener el proveedor por defecto
  call_ai(db, messages, ...) -> str  — despacho principal
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import encrypt_value, decrypt_value
from app.models.ai_providers import AIProvider
from app.models.ai_providers import AIUsageLog
from app.models.user import User
from sqlalchemy import func as sqlfunc

_logger = logging.getLogger("ai_provider_service")


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
PROVIDER_CATALOG = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "icon": "🟠",
        "models": [
            {"id": "claude-opus-4-5",               "name": "Claude Opus 4.5",             "context": 200000, "cost_in": 15.0,  "cost_out": 75.0},
            {"id": "claude-sonnet-4-5",              "name": "Claude Sonnet 4.5",           "context": 200000, "cost_in": 3.0,   "cost_out": 15.0},
            {"id": "claude-haiku-4-5",               "name": "Claude Haiku 4.5",            "context": 200000, "cost_in": 0.80,  "cost_out": 4.0},
            {"id": "claude-3-7-sonnet-20250219",     "name": "Claude 3.7 Sonnet",           "context": 200000, "cost_in": 3.0,   "cost_out": 15.0},
            {"id": "claude-3-5-sonnet-20241022",     "name": "Claude 3.5 Sonnet",           "context": 200000, "cost_in": 3.0,   "cost_out": 15.0},
            {"id": "claude-3-5-haiku-20241022",      "name": "Claude 3.5 Haiku",            "context": 200000, "cost_in": 0.80,  "cost_out": 4.0},
        ],
        "base_url": settings.ANTHROPIC_API_URL,
        "key_hint": "sk-ant-...",
        "docs_url": settings.ANTHROPIC_DOCS_URL,
    },
    "openai": {
        "name": "OpenAI",
        "icon": "🟢",
        "models": [
            {"id": "gpt-4o",      "name": "GPT-4o",       "context": 128000, "cost_in": 2.50, "cost_out": 10.0},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini",  "context": 128000, "cost_in": 0.15, "cost_out": 0.60},
            {"id": "o3",          "name": "o3 (razonamiento)", "context": 200000, "cost_in": 10.0, "cost_out": 40.0},
            {"id": "o3-mini",     "name": "o3-mini",      "context": 200000, "cost_in": 1.10, "cost_out": 4.40},
            {"id": "o4-mini",     "name": "o4-mini",      "context": 200000, "cost_in": 1.10, "cost_out": 4.40},
            {"id": "o1",          "name": "o1",           "context": 200000, "cost_in": 15.0, "cost_out": 60.0},
            {"id": "o1-mini",     "name": "o1-mini",      "context": 128000, "cost_in": 3.0,  "cost_out": 12.0},
        ],
        "base_url": settings.OPENAI_API_URL,
        "key_hint": "sk-...",
        "docs_url": settings.OPENAI_DOCS_URL,
    },
    "gemini": {
        "name": "Google (Gemini)",
        "icon": "🔵",
        "models": [
            {"id": "gemini-2.5-pro",        "name": "Gemini 2.5 Pro",        "context": 1000000, "cost_in": 1.25,  "cost_out": 10.0},
            {"id": "gemini-2.5-flash",      "name": "Gemini 2.5 Flash",      "context": 1000000, "cost_in": 0.15,  "cost_out": 0.60},
            {"id": "gemini-2.0-flash",      "name": "Gemini 2.0 Flash",      "context": 1000000, "cost_in": 0.10,  "cost_out": 0.40},
            {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite", "context": 1000000, "cost_in": 0.075, "cost_out": 0.30},
        ],
        "base_url": settings.GEMINI_API_URL,
        "key_hint": "AIza...",
        "docs_url": settings.GEMINI_DOCS_URL,
    },
    "deepseek": {
        "name": "DeepSeek",
        "icon": "🐋",
        "models": [
            {"id": "deepseek-chat",     "name": "DeepSeek-V3", "context": 64000, "cost_in": 0.27, "cost_out": 1.10},
            {"id": "deepseek-reasoner", "name": "DeepSeek-R1", "context": 64000, "cost_in": 0.55, "cost_out": 2.19},
        ],
        "base_url": settings.DEEPSEEK_API_URL,
        "key_hint": "sk-...",
        "docs_url": settings.DEEPSEEK_DOCS_URL,
    },
    "groq": {
        "name": "Groq (ultra rápido)",
        "icon": "⚡",
        "models": [
            {"id": "meta-llama/llama-4-maverick-17b-128e-instruct", "name": "Llama 4 Maverick 17B", "context": 131072, "cost_in": 0.20, "cost_out": 0.60},
            {"id": "meta-llama/llama-4-scout-17b-16e-instruct",     "name": "Llama 4 Scout 17B",    "context": 131072, "cost_in": 0.11, "cost_out": 0.34},
            {"id": "llama-3.3-70b-versatile",  "name": "Llama 3.3 70B",         "context": 128000, "cost_in": 0.59, "cost_out": 0.79},
            {"id": "llama-3.1-8b-instant",     "name": "Llama 3.1 8B",          "context": 128000, "cost_in": 0.05, "cost_out": 0.08},
            {"id": "qwen-qwq-32b",             "name": "QwQ 32B (razonamiento)", "context": 131072, "cost_in": 0.29, "cost_out": 0.39},
            {"id": "gemma2-9b-it",             "name": "Gemma 2 9B",             "context": 8192,   "cost_in": 0.20, "cost_out": 0.20},
        ],
        "base_url": settings.GROQ_API_URL,
        "key_hint": "gsk_...",
        "docs_url": settings.GROQ_DOCS_URL,
    },
    "mistral": {
        "name": "Mistral AI",
        "icon": "🌪",
        "models": [
            {"id": "mistral-large-latest", "name": "Mistral Large",   "context": 131000, "cost_in": 2.0,  "cost_out": 6.0},
            {"id": "mistral-small-latest", "name": "Mistral Small 3", "context": 32000,  "cost_in": 0.10, "cost_out": 0.30},
            {"id": "codestral-latest",     "name": "Codestral",       "context": 256000, "cost_in": 0.30, "cost_out": 0.90},
            {"id": "ministral-8b-latest",  "name": "Ministral 8B",    "context": 131000, "cost_in": 0.10, "cost_out": 0.10},
            {"id": "mistral-saba-latest",  "name": "Mistral Saba",    "context": 32000,  "cost_in": 0.20, "cost_out": 0.60},
            {"id": "open-mistral-nemo",    "name": "Mistral Nemo 12B","context": 128000, "cost_in": 0.15, "cost_out": 0.15},
        ],
        "base_url": settings.MISTRAL_API_URL,
        "key_hint": "...",
        "docs_url": settings.MISTRAL_DOCS_URL,
    },
    "ollama": {
        "name": "Ollama (local)",
        "icon": "🦙",
        "models": [
            {"id": "llama3.3",       "name": "Llama 3.3 70B",      "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "llama3.2",       "name": "Llama 3.2 3B",       "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "llama3.1:70b",   "name": "Llama 3.1 70B",      "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "gemma3",         "name": "Gemma 3 4B",         "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "gemma3:27b",     "name": "Gemma 3 27B",        "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "phi4",           "name": "Phi-4 14B",          "context": 16000,  "cost_in": 0, "cost_out": 0},
            {"id": "qwen2.5",        "name": "Qwen 2.5 7B",        "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "qwen2.5-coder",  "name": "Qwen 2.5 Coder 7B",  "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "deepseek-r1",    "name": "DeepSeek-R1 8B",     "context": 64000,  "cost_in": 0, "cost_out": 0},
            {"id": "mistral",        "name": "Mistral 7B",         "context": 32000,  "cost_in": 0, "cost_out": 0},
            {"id": "mistral-nemo",   "name": "Mistral Nemo 12B",   "context": 128000, "cost_in": 0, "cost_out": 0},
            {"id": "codellama",      "name": "CodeLlama",          "context": 16000,  "cost_in": 0, "cost_out": 0},
        ],
        "base_url": settings.OLLAMA_BASE_URL + "/api/chat",
        "key_hint": "(no requiere clave)",
        "docs_url": settings.OLLAMA_DOCS_URL,
    },
    "azure": {
        "name": "Azure OpenAI",
        "icon": "☁️",
        "models": [
            {"id": "gpt-4o",      "name": "GPT-4o",      "context": 128000, "cost_in": 2.50, "cost_out": 10.0},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": 128000, "cost_in": 0.15, "cost_out": 0.60},
            {"id": "o3-mini",     "name": "o3-mini",     "context": 200000, "cost_in": 1.10, "cost_out": 4.40},
            {"id": "o4-mini",     "name": "o4-mini",     "context": 200000, "cost_in": 1.10, "cost_out": 4.40},
        ],
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


def _call_anthropic(api_key, model, messages, system, max_tokens, temperature) -> dict:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
    if system:
        body["system"] = system
    resp = httpx.post(f"{settings.ANTHROPIC_API_URL.rstrip('/')}/messages",
                      json=body, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"Anthropic {resp.status_code}: {resp.text[:200]}")
    data  = resp.json()
    text  = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage", {})
    return {"text": text, "model": model,
            "tokens_in": usage.get("input_tokens", 0),
            "tokens_out": usage.get("output_tokens", 0)}


def _call_openai_compat(base_url, api_key, model, messages, system, max_tokens, temperature) -> dict:
    """Handles OpenAI, Groq, Mistral, DeepSeek, Azure (same chat/completions format)."""
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": model, "messages": all_messages, "max_tokens": max_tokens, "temperature": temperature}
    resp = httpx.post(endpoint, json=body, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"API {resp.status_code}: {resp.text[:200]}")
    data  = resp.json()
    text  = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {"text": text, "model": model,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0)}


def _call_gemini(api_key, model, messages, system, max_tokens, temperature) -> dict:
    url = f"{settings.GEMINI_API_URL}/models/{model}:generateContent?key={api_key}"
    contents = []
    if system:
        contents.append({"role": "user",  "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "Entendido."}]})
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    body = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    resp = httpx.post(url, json=body, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"Gemini {resp.status_code}: {resp.text[:200]}")
    data  = resp.json()
    text  = data["candidates"][0]["content"]["parts"][0]["text"]
    usage = data.get("usageMetadata", {})
    return {"text": text, "model": model,
            "tokens_in": usage.get("promptTokenCount", 0),
            "tokens_out": usage.get("candidatesTokenCount", 0)}


def _call_ollama(base_url, model, messages, system, max_tokens, temperature) -> dict:
    url = _normalize_ollama_base(base_url).rstrip("/") + "/api/chat"
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": model, "messages": all_messages, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature}}
    resp = httpx.post(url, json=body, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"Ollama {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    text = data.get("message", {}).get("content", "")
    return {"text": text, "model": model,
            "tokens_in": data.get("prompt_eval_count", 0) or 0,
            "tokens_out": data.get("eval_count", 0) or 0}


def _list_openai_compatible_models(base_url: str, api_key: str) -> list[str]:
    base = _normalize_openai_base(base_url)
    if not base:
        raise ValueError("Base URL vacía para proveedor compatible OpenAI")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = httpx.get(f"{base}/models", headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"List Models {resp.status_code}: {resp.text[:250]}")
    data = resp.json()
    raw = data.get("data", []) if isinstance(data, dict) else []
    models = sorted({str(m.get("id", "")).strip() for m in raw if isinstance(m, dict) and m.get("id")})
    return [m for m in models if m]


def _list_anthropic_models(api_key: str) -> list[str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = httpx.get(f"{settings.ANTHROPIC_API_URL.rstrip('/')}/models", headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Anthropic list models {resp.status_code}: {resp.text[:250]}")
    data = resp.json()
    raw = data.get("data", []) if isinstance(data, dict) else []
    models = sorted({str(m.get("id", "")).strip() for m in raw if isinstance(m, dict) and m.get("id")})
    return [m for m in models if m]


def _list_gemini_models(api_key: str) -> list[str]:
    base = settings.GEMINI_API_URL.rstrip("/")
    url = f"{base}/models?key={api_key}"
    models: set[str] = set()
    for _ in range(3):
        resp = httpx.get(url, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"Gemini list models {resp.status_code}: {resp.text[:250]}")
        data = resp.json() if resp.content else {}
        for m in data.get("models", []) if isinstance(data, dict) else []:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name", "")).strip()  # e.g. models/gemini-2.5-flash
            if not name:
                continue
            clean = name.split("models/", 1)[-1]
            # Keep Gemini family models only to avoid unrelated endpoints
            if clean.startswith("gemini"):
                models.add(clean)
        next_token = data.get("nextPageToken") if isinstance(data, dict) else None
        if not next_token:
            break
        sep = "&" if "?" in url else "?"
        url = f"{base}/models?key={api_key}{sep}pageToken={next_token}"
    return sorted(models)


def _list_ollama_models(base_url: str) -> list[str]:
    base = _normalize_ollama_base(base_url)
    if not base:
        raise ValueError("Base URL vacía para Ollama")
    resp = httpx.get(f"{base}/api/tags", timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Ollama list models {resp.status_code}: {resp.text[:250]}")
    data = resp.json() if resp.content else {}
    raw = data.get("models", []) if isinstance(data, dict) else []
    names = sorted({str(m.get("name", "")).strip() for m in raw if isinstance(m, dict) and m.get("name")})
    return [m for m in names if m]


def _list_azure_models(base_url: str, api_key: str) -> list[str]:
    base = _normalize_openai_base(base_url)
    if not base:
        raise ValueError("Base URL vacía para Azure OpenAI")
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    # Data-plane model listing in Azure OpenAI
    resp = httpx.get(f"{base}/models?api-version=2024-10-21", headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Azure list models {resp.status_code}: {resp.text[:250]}")
    data = resp.json() if resp.content else {}
    raw = data.get("data", []) if isinstance(data, dict) else []
    models = sorted({str(m.get("id", "")).strip() for m in raw if isinstance(m, dict) and m.get("id")})
    return [m for m in models if m]


def list_models_for_provider(provider) -> list[str]:
    provider_type = provider.provider.value if hasattr(provider.provider, "value") else str(provider.provider)
    api_key = decrypt_value(provider.api_key) if provider.api_key else ""
    base_url = (provider.api_base_url or PROVIDER_CATALOG.get(provider_type, {}).get("base_url") or "").strip()

    if provider_type == "ollama":
        return _list_ollama_models(base_url or settings.OLLAMA_BASE_URL)

    if provider_type == "anthropic":
        if not api_key:
            raise ValueError("Falta API key para listar modelos de Anthropic")
        return _list_anthropic_models(api_key)

    if provider_type == "gemini":
        if not api_key:
            raise ValueError("Falta API key para listar modelos de Gemini")
        return _list_gemini_models(api_key)

    if provider_type in ("openai", "groq", "mistral", "deepseek"):
        if not api_key:
            raise ValueError(f"Falta API key para listar modelos de {provider_type}")
        return _list_openai_compatible_models(base_url, api_key)

    if provider_type == "azure":
        if not api_key:
            raise ValueError("Falta API key para listar modelos de Azure")
        return _list_azure_models(base_url, api_key)

    raise ValueError(f"Proveedor no soportado para list models: {provider_type}")


def sync_provider_models(db: Session, provider) -> list[str]:
    discovered = list_models_for_provider(provider)
    if not discovered:
        raise Exception("El proveedor no devolvió modelos disponibles")

    # Remove known deprecated IDs from discovered list.
    provider_type = provider.provider.value if hasattr(provider.provider, "value") else str(provider.provider)
    filtered = [m for m in discovered if m not in _DEPRECATED_MODELS.get(provider_type, set())]
    if not filtered:
        raise Exception("Tras filtrar modelos retirados no quedan modelos disponibles")

    provider.available_models = ",".join(filtered)
    if provider.default_model not in filtered:
        provider.default_model = filtered[0]
    provider.last_error = None
    provider.status = "active"
    db.commit()
    db.refresh(provider)
    return filtered


def call_provider(provider, messages: list, system: str = None,
                  model: str = None, max_tokens: int = None, temperature: float = None) -> dict:
    """Unified dispatcher for all AI providers."""
    model       = model or provider.default_model or "default"
    _validate_model(provider.provider, model)
    max_tokens  = max_tokens or provider.max_tokens or 2000
    # `or` convertia una temperatura 0.0 guardada en 0.7.
    if temperature is None:
        temperature = provider.temperature if provider.temperature is not None else 0.7
    raw_key     = provider.api_key or ""
    api_key     = decrypt_value(raw_key) if raw_key else ""
    base_url    = provider.api_base_url or ""

    if provider.provider == "anthropic":
        return _call_anthropic(api_key, model, messages, system, max_tokens, temperature)
    elif provider.provider in ("openai", "groq", "mistral", "azure", "deepseek"):
        return _call_openai_compat(
            base_url or PROVIDER_CATALOG.get(provider.provider, {}).get("base_url", ""),
            api_key, model, messages, system, max_tokens, temperature,
        )
    elif provider.provider == "gemini":
        return _call_gemini(api_key, model, messages, system, max_tokens, temperature)
    elif provider.provider == "ollama":
        return _call_ollama(base_url or settings.OLLAMA_BASE_URL, model, messages, system, max_tokens, temperature)
    else:
        raise ValueError(f"Proveedor no soportado: {provider.provider}")


# ── CRUD service functions ────────────────────────────────────────────────────

def list_providers(db: Session, *, is_superadmin: bool, organization_id) -> list:
    q = db.query(AIProvider).filter(AIProvider.is_active == True)  # audit #36 soft-delete
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.order_by(AIProvider.is_default.desc(), AIProvider.name).all()


def _clear_default(db: Session, *, is_superadmin: bool, organization_id) -> None:
    q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    q.update({"is_default": False})


def create_provider(db: Session, *, organization_id, created_by, data: dict,
                    is_superadmin: bool) -> object:
    count_q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        count_q = count_q.filter(AIProvider.organization_id == organization_id)
    count = count_q.count()
    raw_key = data.get("api_key") or None
    p = AIProvider(
        organization_id=organization_id,
        name=data.get("name", ""),
        provider=data.get("provider", "anthropic"),
        api_key=encrypt_value(raw_key) if raw_key else None,
        api_base_url=data.get("api_base_url") or None,
        default_model=data.get("default_model"),
        available_models=",".join(data.get("available_models", [])) if data.get("available_models") else None,
        is_default=data.get("is_default", count == 0),
        max_tokens=data.get("max_tokens", 2000),
        temperature=data.get("temperature", 0.7),
        created_by=created_by,
    )
    if p.is_default:
        _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def get_provider(db: Session, pid: str, *, is_superadmin: bool, organization_id) -> object | None:
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.first()


def update_provider(db: Session, provider, data: dict, *,
                    is_superadmin: bool, organization_id) -> object:
    if data.get("is_default"):
        _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)

    changed_runtime_fields = False
    for k, v in data.items():
        if k == "available_models" and isinstance(v, list):
            v = ",".join(v)
        if k == "api_key":
            if not v:
                continue
            v = encrypt_value(v)
        if k in {"api_key", "api_base_url", "default_model", "provider", "available_models"}:
            changed_runtime_fields = True
        if hasattr(provider, k):
            setattr(provider, k, v)

    if changed_runtime_fields:
        provider.status = "active"
        provider.last_error = None

    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, provider) -> None:
    # audit #36 soft-delete — preserva trazabilidad de uso (AIUsageLog).
    provider.is_active = False
    db.commit()


def set_default_provider(db: Session, pid: str, *, is_superadmin: bool,
                         organization_id) -> object | None:
    _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    p = q.first()
    if p:
        p.is_default = True
        db.commit()
    return p


def update_provider_test_result(db: Session, provider, *, success: bool,
                                error: str | None = None) -> None:
    if success:
        provider.status = "active"
        provider.last_error = None
    else:
        provider.status = "error"
        provider.last_error = (error or "")[:500]
        provider.last_error_at = datetime.now(timezone.utc)
    db.commit()


def get_stats(db: Session, *, is_superadmin: bool, organization_id) -> dict:
    p_q = db.query(AIProvider)
    l_q = db.query(
        AIUsageLog.module,
        sqlfunc.count(AIUsageLog.id).label("calls"),
        sqlfunc.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out).label("tokens"),
        sqlfunc.sum(AIUsageLog.cost_usd).label("cost"),
    )
    if not is_superadmin and organization_id:
        p_q = p_q.filter(AIProvider.organization_id == organization_id)
        org_user_ids = db.query(User.id).filter(
            User.organization_id == organization_id
        ).scalar_subquery()
        l_q = l_q.filter(AIUsageLog.user_id.in_(org_user_ids))
    providers = p_q.all()
    logs = l_q.group_by(AIUsageLog.module).all()
    return {
        "providers": providers,
        "logs": logs,
        "total_cost": round(sum(p.total_cost_usd for p in providers), 4),
        "total_requests": sum(p.total_requests for p in providers),
    }


class ProveedorDeEntorno:
    """El proveedor que describe el `.env`, sin pasar por la base de datos.

    Es el último escalón de la resolución y existe para que un despliegue de un
    solo cliente se configure entero por fichero, sin abrir la aplicación.

    No hereda de `AIProvider` a propósito: no es una fila, no se persiste y no
    debe poder acabar en la sesión por accidente. Lleva los mismos atributos que
    `call_provider` y el registro de uso necesitan —`id` a `None`, que
    `_registrar_uso` ya contempla— y los contadores en cero, que se mueven en
    memoria y se descartan al acabar la petición.
    """

    __slots__ = ("id", "name", "provider", "status", "api_key", "api_base_url",
                 "default_model", "max_tokens", "temperature", "total_requests",
                 "total_tokens_in", "total_tokens_out", "total_cost_usd",
                 "last_used_at", "last_error", "last_error_at", "organization_id",
                 "is_default", "is_active")

    def __init__(self, *, proveedor: str, api_key: str, modelo: str, base_url: str):
        self.id = None
        self.name = f"{proveedor} (.env)"
        self.provider = proveedor
        self.status = "active"
        # Cifrada, porque `call_provider` descifra siempre. Así el camino de
        # llamada es EL MISMO que el de un proveedor de base de datos: un solo
        # sitio que descifra, y no dos ramas que puedan divergir.
        self.api_key = encrypt_value(api_key) if api_key else None
        self.api_base_url = base_url or None
        self.default_model = modelo or None
        self.max_tokens = 2000
        self.temperature = 0.7
        self.total_requests = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost_usd = 0.0
        self.last_used_at = None
        self.last_error = None
        self.last_error_at = None
        self.organization_id = None
        self.is_default = True
        self.is_active = True


#: Proveedores que no necesitan clave porque corren en la propia máquina.
_SIN_CLAVE = {"ollama"}


def proveedor_desde_entorno():
    """El proveedor descrito por `.env`, o `None` si no hay ninguno.

    `AI_PROVIDER` + `AI_API_KEY` es la forma agnóstica. `ANTHROPIC_API_KEY` se
    sigue aceptando como alias heredado —era la única que existía— para que
    ningún `.env` deje de funcionar por este cambio.
    """
    proveedor = (settings.AI_PROVIDER or "").strip().lower()
    api_key = (settings.AI_API_KEY or "").strip()

    if not proveedor and (settings.ANTHROPIC_API_KEY or "").strip():
        proveedor, api_key = "anthropic", settings.ANTHROPIC_API_KEY.strip()

    if not proveedor:
        return None
    if proveedor not in PROVIDER_CATALOG:
        _logger.warning(
            "AI_PROVIDER='%s' no es un proveedor conocido. Opciones: %s",
            proveedor, ", ".join(sorted(PROVIDER_CATALOG)))
        return None
    if not api_key and proveedor not in _SIN_CLAVE:
        _logger.warning("AI_PROVIDER='%s' sin AI_API_KEY: no se usa.", proveedor)
        return None

    return ProveedorDeEntorno(
        proveedor=proveedor,
        api_key=api_key,
        modelo=(settings.AI_MODEL or "").strip(),
        base_url=(settings.AI_BASE_URL or "").strip(),
    )


def get_default_provider(
    db: Session,
    *,
    is_superadmin: bool = True,
    organization_id=None,
):
    """Return default (or first active) provider with tenant-aware fallback.

    Resolution order for non-superadmin users:
    1) Org-specific provider
    2) Global shared provider (organization_id is NULL)
    3) El proveedor del `.env` (ver `proveedor_desde_entorno`)

    El tercer escalón es el mismo patrón que ya usaba el motor de voz en
    `app/services/stt/__init__.py`: organización → global → entorno. La base de
    datos no sobra —un despliegue multi-empresa necesita un proveedor por
    organización, y eso un fichero de entorno no lo puede expresar—, pero uno de
    un solo cliente tiene que poder configurarse sin abrir la aplicación.
    """
    base_q = db.query(AIProvider).filter(
        AIProvider.status != "error",
        AIProvider.is_active == True,  # audit #36 soft-delete
    )

    def _pick(q):
        # Determinism: si hay default explícito, gana. Si no, orden estable por
        # (status='active' primero, created_at asc, id asc) para evitar que dos
        # providers idénticos elijan uno u otro arbitrariamente entre requests.
        p = q.filter(AIProvider.is_default == True).order_by(
            AIProvider.created_at.asc(), AIProvider.id.asc()
        ).first()
        if not p:
            # active > otros estados; luego más antiguo primero, id como tie-breaker
            from sqlalchemy import case as sql_case
            order_status = sql_case((AIProvider.status == "active", 0), else_=1)
            p = q.order_by(order_status, AIProvider.created_at.asc(), AIProvider.id.asc()).first()
        return p

    if is_superadmin:
        return _pick(base_q) or proveedor_desde_entorno()

    if organization_id:
        org_q = base_q.filter(AIProvider.organization_id == organization_id)
        p = _pick(org_q)
        if p:
            return p

    shared_q = base_q.filter(AIProvider.organization_id.is_(None))
    return _pick(shared_q) or proveedor_desde_entorno()


def _try_fallback_providers(
    db: Session,
    messages: list,
    system: str,
    max_tokens: int,
    is_superadmin: bool,
    organization_id,
) -> "tuple[AIProvider | None, dict | None]":
    """
    Try any available provider as fallback (provider-agnostic).

    Devuelve `(proveedor, resultado)` del primero que responda, o
    `(None, None)` si fallan todos.

    Antes devolvia solo el resultado, y `call_ai` no podia saber quien habia
    atendido la llamada: la registraba con `provider_id = None`. El proveedor si
    actualizaba sus propios contadores aqui dentro, asi que los agregados por
    proveedor y `AIUsageLog` discrepaban justo para el trafico de respaldo — el
    coste contado en el proveedor y las filas del log sin poder agruparse por el.
    """
    # Get all available active providers
    query = db.query(AIProvider).filter(
        AIProvider.status != "error",
        AIProvider.is_active == True,  # audit #36 soft-delete
    )

    if not is_superadmin and organization_id:
        # Try org-specific first, then shared
        org_providers = query.filter(AIProvider.organization_id == organization_id).all()
        shared_providers = query.filter(AIProvider.organization_id.is_(None)).all()
        all_providers = org_providers + shared_providers
    else:
        all_providers = query.all()

    # Try each provider in order
    for provider in all_providers:
        try:
            result = call_provider(
                provider,
                messages,
                system=system,
                model=None,  # Use provider's default model
                max_tokens=max_tokens,
            )

            # Update provider stats
            provider.total_requests   += 1
            provider.total_tokens_in  += result.get("tokens_in", 0)
            provider.total_tokens_out += result.get("tokens_out", 0)
            provider.last_used_at      = datetime.now(timezone.utc)

            # Calculate cost if model info available
            cat_models = PROVIDER_CATALOG.get(provider.provider, {}).get("models", [])
            m_info = next(
                (m for m in cat_models if m["id"] == (result.get("model"))),
                None
            )
            if m_info:
                cost = (
                    result.get("tokens_in", 0) / 1_000_000 * m_info["cost_in"] +
                    result.get("tokens_out", 0) / 1_000_000 * m_info["cost_out"]
                )
                provider.total_cost_usd += cost
                result["cost_usd"] = cost

            # La llamada YA se ha atendido y el proveedor YA la ha facturado,
            # asi que la contabilidad va en su propio `try`: si el `commit()` de
            # estadisticas falla, se deshace y la respuesta se devuelve IGUAL.
            #
            # Antes ese `commit()` estaba dentro del `try` de la llamada, de modo
            # que un fallo de NUESTRA base caia en el `except ... continue` de
            # abajo: se descartaba una respuesta ya pagada y, peor, la sesion
            # quedaba envenenada, asi que todos los proveedores siguientes del
            # bucle fallaban tambien y la funcion acababa devolviendo «todos los
            # proveedores han fallado» — el diagnostico contrario al real.
            # Auditoria 2026-08, hallazgo 22.
            try:
                db.commit()
            except Exception:
                db.rollback()
                _logger.warning(
                    "no se pudieron guardar las estadisticas del proveedor %s; "
                    "la respuesta se devuelve igual", provider.name,
                    exc_info=True,
                )
            _logger.info(
                "Fallback AI provider succeeded: %s (%s)",
                provider.name, provider.provider
            )
            return provider, result

        except Exception as exc:
            # Solo el fallo de la LLAMADA justifica probar el siguiente
            # proveedor. El de la contabilidad no llega aqui: lo atrapa el `try`
            # interior de arriba.
            _logger.debug(
                "Fallback provider %s failed: %s",
                provider.name, str(exc)
            )
            continue

    # All providers failed
    _logger.warning("All AI providers failed as fallback")
    return None, None



# ── Despacho de una llamada a un modelo ──────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 + hueco de observabilidad encontrado de paso).
# `call_ai` era complejidad 24 en siete fases mezcladas: gobernanza de entrada,
# eleccion de proveedor, llamada con respaldo, registro de uso, aviso de coste y
# gobernanza de salida. Ahora cada fase tiene nombre.
#
# ── El hueco ──────────────────────────────────────────────────────────────────
#
# `_try_fallback_providers` devolvia solo el resultado, no el proveedor que lo
# habia servido, y `call_ai` ponia `p = None` antes de llamarlo. Consecuencia:
# una llamada atendida por el respaldo se registraba en `AIUsageLog` con
# `provider_id = None`.
#
# El proveedor SI actualizaba sus propios contadores dentro del respaldo, asi que
# los agregados por proveedor y el registro de uso DISCREPABAN justo para ese
# trafico: el coste estaba contado en el proveedor pero las filas del log no se
# podian agrupar por el. Con un primario caido —que es cuando el respaldo
# actua— eso puede ser una parte grande del gasto sin atribuir.
#
# Arreglo: `_try_fallback_providers` devuelve `(proveedor, resultado)` y el
# registro apunta al proveedor que de verdad respondio. Es una funcion privada
# llamada solo desde aqui, asi que el cambio de contrato esta contenido.


def _resolver_usuario_de_gobernanza(db: Session, user_id, skip_guardrails: bool):
    """El usuario contra el que se evaluan las politicas, resuelto una sola vez.

    Se reutiliza para la entrada y para la salida: dos consultas para el mismo
    dato en la misma llamada no aportan nada.

    Devuelve None ante cualquier problema, y eso desactiva los guardrails de esa
    llamada. Es el comportamiento del original; queda anotado porque no es
    obvio: sin usuario no hay politicas que aplicar, asi que un fallo al
    cargarlo abre el paso en vez de cerrarlo.
    """
    if skip_guardrails or not user_id:
        return None
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        _logger.warning(
            "Failed to load governance_user for user_id=%s", user_id, exc_info=True
        )
        return None


def _aplicar_guardrail_de_entrada(db: Session, messages: list, governance_user,
                                  module: str, skip_guardrails: bool):
    """Evalua las politicas sobre el ultimo mensaje del usuario.

    Devuelve un texto de bloqueo si hay que cortar, o None para seguir. Cuando
    la politica redacta, ESCRIBE el texto redactado en `messages` — a proposito:
    lo que se manda al modelo tiene que ser el texto ya redactado, no el
    original.
    """
    if skip_guardrails or not governance_user or not messages:
        return None

    last_user_msg = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    if not last_user_msg or not isinstance(last_user_msg.get("content"), str):
        return None

    try:
        from app.services.ai_governance import check_prompt as _gr_check_prompt
        gr = _gr_check_prompt(last_user_msg["content"], governance_user, module, db)
    except Exception as gr_exc:
        # Se sigue a proposito: un fallo del motor de politicas no puede dejar
        # la aplicacion sin IA. Queda en el log.
        _logger.warning("Guardrail prompt check failed (continuing): %s", gr_exc)
        return None

    if not gr.allowed:
        return (
            "[Mensaje bloqueado por política de gobernanza: "
            f"{gr.blocked_by or 'policy'}]"
        )
    if gr.redacted_text:
        last_user_msg["content"] = gr.redacted_text
    return None


def _seleccionar_proveedor(db: Session, provider_id, is_superadmin: bool, organization_id):
    """El proveedor primario: el pedido explicitamente, o el de la organizacion.

    El filtro por `organization_id` cuando no es superadmin es lo que impide que
    un identificador adivinado sirva para usar el proveedor —y la clave— de otro
    cliente.
    """
    if not provider_id:
        return get_default_provider(
            db, is_superadmin=is_superadmin, organization_id=organization_id
        )
    q = db.query(AIProvider).filter(AIProvider.id == provider_id)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.first()


def _apuntar_uso_en_el_proveedor(p, result: dict, model) -> None:
    """Suma peticiones, tokens y coste al proveedor que ha respondido."""
    p.total_requests += 1
    p.total_tokens_in += result["tokens_in"]
    p.total_tokens_out += result["tokens_out"]
    p.last_used_at = datetime.now(timezone.utc)

    cat_models = PROVIDER_CATALOG.get(p.provider, {}).get("models", [])
    m_info = next((m for m in cat_models if m["id"] == (model or p.default_model)), None)
    if m_info:
        cost = (result["tokens_in"] / 1_000_000 * m_info["cost_in"] +
                result["tokens_out"] / 1_000_000 * m_info["cost_out"])
        p.total_cost_usd += cost
        result["cost_usd"] = cost


def _marcar_proveedor_en_error(p, error_msg: str) -> None:
    p.last_error = error_msg[:500]
    p.last_error_at = datetime.now(timezone.utc)
    p.status = "error"


SIN_PROVEEDOR = "no_ai_provider_configured"
AVISO_SIN_PROVEEDOR = (
    "⚠️ No hay ningún proveedor de IA configurado. "
    "Ve a Inteligencia IA → IA & Conectores para añadir uno."
)


def es_aviso_de_ia(texto) -> bool:
    """True si `call_ai` devolvio un aviso (sin proveedor o error) y no una respuesta."""
    return isinstance(texto, str) and texto.lstrip().startswith("⚠️")


def _llamar_con_respaldo(db: Session, p, messages: list, system, model, max_tokens,
                         is_superadmin: bool, organization_id):
    """Llama al primario y, si falla, a cualquier otro disponible.

    Devuelve `(proveedor_que_respondio, resultado, error)`. El proveedor
    devuelto es el que DE VERDAD atendio la llamada, que es lo que hace que el
    registro de uso quede atribuido — ver la nota de cabecera.
    """
    vacio = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "unknown"}

    if p:
        # El `try` cubre SOLO la llamada. Antes cubria tambien el `commit()` de
        # estadisticas, y eso hacia que un fallo de nuestra base marcase
        # `status = "error"` en un proveedor que HABIA FUNCIONADO —el valor que
        # lo excluye de futuras selecciones— y volviese a hacer `commit()` sobre
        # la sesion ya abortada. Auditoria 2026-08, hallazgo 22.
        try:
            result = call_provider(p, messages, system=system,
                                   model=model or p.default_model,
                                   max_tokens=max_tokens)
        except Exception as e:
            error_msg = str(e)
            _marcar_proveedor_en_error(p, error_msg)
            try:
                db.commit()
            except Exception:
                # Que no se pueda anotar el error del proveedor no debe tapar el
                # error del proveedor: se deshace y se sigue al respaldo.
                db.rollback()
                _logger.warning("no se pudo marcar el proveedor %s en error",
                                p.name, exc_info=True)
            respaldo, result = _try_fallback_providers(
                db, messages, system, max_tokens, is_superadmin, organization_id
            )
            if result:
                return respaldo, result, None
            # Se conserva el error del primario: es el informativo.
            return None, vacio, error_msg

        # La llamada ya se ha atendido y facturado: la contabilidad no puede
        # tirar la respuesta.
        try:
            _apuntar_uso_en_el_proveedor(p, result, model)
            db.commit()
        except Exception:
            db.rollback()
            _logger.warning(
                "no se pudieron guardar las estadisticas del proveedor %s; la "
                "respuesta se devuelve igual", p.name, exc_info=True,
            )
        return p, result, None

    respaldo, result = _try_fallback_providers(
        db, messages, system, max_tokens, is_superadmin, organization_id
    )
    if result:
        return respaldo, result, None

    vacio["text"] = AVISO_SIN_PROVEEDOR
    # Auditoria 2026-11: antes error=None, asi que el uso se registraba como
    # exito con 0 tokens y las funciones daban la llamada por buena.
    return None, vacio, SIN_PROVEEDOR


def _registrar_uso(db: Session, p, result: dict, *, user_id, module,
                   latency: int, error_msg) -> None:
    """Escribe la fila de `AIUsageLog`. Un fallo al registrar no rompe la llamada.

    El `rollback` del `except` no es opcional: sin el, una sesion en transaccion
    abortada haria fallar todo lo que viene despues, incluido el aviso de coste.
    """
    db.add(AIUsageLog(
        provider_id=p.id if p else None,
        user_id=user_id,
        module=module,
        model=result.get("model"),
        tokens_in=result.get("tokens_in", 0),
        tokens_out=result.get("tokens_out", 0),
        cost_usd=result.get("cost_usd", 0),
        latency_ms=latency,
        success=error_msg is None,
        error_msg=error_msg,
    ))
    try:
        db.commit()
    except Exception:
        _logger.warning("Failed to persist AIUsageLog entry; rolling back", exc_info=True)
        db.rollback()


def _avisar_si_el_coste_diario_se_pasa(db: Session, result: dict) -> None:
    """Avisa en el log si el gasto acumulado del dia supera el umbral.

    Es un aviso y no un corte: cortar la IA a media jornada por un umbral de
    coste dejaria la aplicacion a medias sin que nadie lo hubiera decidido.
    """
    if result.get("cost_usd", 0) <= 0:
        return
    try:
        from app.services.settings_service import get_runtime_float
        threshold = (get_runtime_float(db, "AI_COST_ALERT_USD_PER_DAY")
                     or settings.AI_COST_ALERT_USD_PER_DAY)
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_cost = db.query(func.sum(AIUsageLog.cost_usd)).filter(
            AIUsageLog.created_at >= today_start,
            AIUsageLog.success == True,   # noqa: E712 — comparación SQL, no Python
        ).scalar() or 0
        if today_cost > threshold:
            _logger.warning(
                "AI_COST_ALERT: coste diario acumulado $%.4f supera el umbral $%.2f.",
                today_cost, threshold,
            )
    except Exception as alert_exc:
        _logger.debug("Cost alert check failed (non-critical): %s", alert_exc)


def _aplicar_guardrail_de_salida(db: Session, texto: str, governance_user,
                                 module: str, skip_guardrails: bool, error_msg) -> str:
    """Evalua las politicas sobre la respuesta del modelo.

    No se evalua cuando la llamada fallo: no hay respuesta que revisar y el
    texto que se devuelve es el mensaje de error del proveedor.
    """
    if skip_guardrails or not governance_user or not texto or error_msg is not None:
        return texto
    try:
        from app.services.ai_governance import check_output as _gr_check_output
        gr_out = _gr_check_output(texto, governance_user, module, db)
    except Exception as gr_exc:
        _logger.warning("Guardrail output check failed (continuing): %s", gr_exc)
        return texto

    if not gr_out.allowed:
        return "[Respuesta bloqueada por política de gobernanza]"
    if gr_out.redacted_text:
        return gr_out.redacted_text
    return texto


def call_ai(
    db: Session,
    messages: list,
    system: str = None,
    module: str = "general",
    user_id: str = None,
    model: str = None,
    max_tokens: int = None,
    provider_id: str = None,
    is_superadmin: bool = True,
    organization_id=None,
    skip_guardrails: bool = False,
) -> str:
    """
    Main AI dispatch function (provider-agnostic).

    Resolution order:
    1. Explicit provider_id (if provided)
    2. Default provider for organization
    3. Any available provider as fallback
    4. No provider available → error message

    Multi-tenant aware: filtra providers por ``organization_id`` cuando no es
    superadmin. Cost tracking real desde PROVIDER_CATALOG. Fallback automático
    si el primary provider falla.

    Governance: aplica ``check_prompt`` sobre el último mensaje de usuario
    antes de llamar al LLM y ``check_output`` sobre la respuesta. Pasa
    ``skip_guardrails=True`` SOLO para llamadas internas que no son
    user-facing (p. ej. construcción de embeddings, sondas de salud).
    Antes los guardrails sólo se aplicaban en ``ai_chat.py`` → 54% del
    tráfico IA bypasaba policies.
    """
    governance_user = _resolver_usuario_de_gobernanza(db, user_id, skip_guardrails)

    bloqueo = _aplicar_guardrail_de_entrada(
        db, messages, governance_user, module, skip_guardrails
    )
    if bloqueo:
        return bloqueo

    p = _seleccionar_proveedor(db, provider_id, is_superadmin, organization_id)

    t0 = time.time()
    p, result, error_msg = _llamar_con_respaldo(
        db, p, messages, system, model, max_tokens, is_superadmin, organization_id
    )
    latency = int((time.time() - t0) * 1000)

    _registrar_uso(db, p, result, user_id=user_id, module=module,
                   latency=latency, error_msg=error_msg)
    if error_msg is None:
        _avisar_si_el_coste_diario_se_pasa(db, result)

    final_text = _aplicar_guardrail_de_salida(
        db, result.get("text", "") or "", governance_user, module,
        skip_guardrails, error_msg,
    )

    # Si falló el provider, devolvemos un texto explícito de error que el
    # caller puede distinguir (#43): prefijo "⚠️". `es_aviso_de_ia()` lo detecta.
    if error_msg == SIN_PROVEEDOR:
        return AVISO_SIN_PROVEEDOR
    if error_msg is not None:
        return f"⚠️ AI provider error: {error_msg[:200]}"

    return final_text


# ── Diagnóstico por proveedor ─────────────────────────────────────────────────

def diagnose_provider(provider) -> dict:
    """
    Comprueba conectividad y validez de configuración de un proveedor IA.

    Retorna un dict con:
      id, name, provider_type, status ("ok"|"warning"|"error"),
      latency_ms, model, models_found, error
    """
    provider_type = provider.provider.value if hasattr(provider.provider, "value") else str(provider.provider)
    api_key = decrypt_value(provider.api_key) if provider.api_key else ""

    result: dict = {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider_type,
        "status": "error",
        "latency_ms": None,
        "model": provider.default_model,
        "models_found": 0,
        "error": None,
    }

    # --- Step 1: check api_key present (not needed for Ollama) ---
    if provider_type != "ollama" and not api_key:
        result["error"] = "API key ausente o no se pudo desencriptar"
        result["status"] = "error"
        return result

    # --- Step 2: try to list models (connectivity + auth check) ---
    t0 = time.time()
    try:
        models = list_models_for_provider(provider)
        latency_ms = round((time.time() - t0) * 1000)
        result["latency_ms"] = latency_ms
        result["models_found"] = len(models)

        # --- Step 3: check default_model is in the discovered list ---
        if provider.default_model and models and provider.default_model not in models:
            result["status"] = "warning"
            result["error"] = (
                f"Modelo por defecto '{provider.default_model}' no está en la lista "
                f"descubierta ({len(models)} modelos). Sincroniza los modelos."
            )
        else:
            result["status"] = "ok"
            result["error"] = None

    except Exception as exc:
        _logger.warning("Provider diagnostic failed for id=%s name=%s: %s", provider.id, provider.name, exc, exc_info=True)
        latency_ms = round((time.time() - t0) * 1000)
        result["latency_ms"] = latency_ms
        result["error"] = str(exc)
        result["status"] = "error"

    return result
