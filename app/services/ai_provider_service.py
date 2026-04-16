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
from typing import Optional

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import encrypt_value, decrypt_value

_logger = logging.getLogger("ai_provider_service")

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


def _call_ollama(base_url, model, messages, system, max_tokens) -> dict:
    url = base_url.rstrip("/") + "/api/chat"
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": model, "messages": all_messages, "stream": False,
            "options": {"num_predict": max_tokens}}
    resp = httpx.post(url, json=body, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"Ollama {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    text = data.get("message", {}).get("content", "")
    return {"text": text, "model": model, "tokens_in": 0, "tokens_out": 0}


def call_provider(provider, messages: list, system: str = None,
                  model: str = None, max_tokens: int = None, temperature: float = None) -> dict:
    """Unified dispatcher for all AI providers."""
    model       = model or provider.default_model or "default"
    _validate_model(provider.provider, model)
    max_tokens  = max_tokens or provider.max_tokens or 2000
    temperature = temperature if temperature is not None else (provider.temperature or 0.7)
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
        return _call_ollama(base_url or settings.OLLAMA_BASE_URL, model, messages, system, max_tokens)
    else:
        raise ValueError(f"Proveedor no soportado: {provider.provider}")


# ── CRUD service functions ────────────────────────────────────────────────────

def list_providers(db: Session, *, is_superadmin: bool, organization_id) -> list:
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.order_by(AIProvider.is_default.desc(), AIProvider.name).all()


def _clear_default(db: Session, *, is_superadmin: bool, organization_id) -> None:
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    q.update({"is_default": False})


def create_provider(db: Session, *, organization_id, created_by, data: dict,
                    is_superadmin: bool) -> object:
    from app.models.ai_providers import AIProvider
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
    from app.models.ai_providers import AIProvider
    q = db.query(AIProvider).filter(AIProvider.id == pid)
    if not is_superadmin and organization_id:
        q = q.filter(AIProvider.organization_id == organization_id)
    return q.first()


def update_provider(db: Session, provider, data: dict, *,
                    is_superadmin: bool, organization_id) -> object:
    if data.get("is_default"):
        _clear_default(db, is_superadmin=is_superadmin, organization_id=organization_id)
    for k, v in data.items():
        if k == "available_models" and isinstance(v, list):
            v = ",".join(v)
        if k == "api_key":
            if not v:
                continue
            v = encrypt_value(v)
        if hasattr(provider, k):
            setattr(provider, k, v)
    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, provider) -> None:
    db.delete(provider)
    db.commit()


def set_default_provider(db: Session, pid: str, *, is_superadmin: bool,
                         organization_id) -> object | None:
    from app.models.ai_providers import AIProvider
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
    from app.models.ai_providers import AIProvider, AIUsageLog
    from app.models.user import User
    from sqlalchemy import func as sqlfunc
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


def get_default_provider(db: Session):
    """Return the default (or first active) provider."""
    from app.models.ai_providers import AIProvider
    p = db.query(AIProvider).filter(
        AIProvider.is_default == True, AIProvider.status != "error"
    ).first()
    if not p:
        p = db.query(AIProvider).filter(AIProvider.status != "error").first()
    return p


def call_ai(
    db: Session,
    messages: list,
    system: str = None,
    module: str = "general",
    user_id: str = None,
    model: str = None,
    max_tokens: int = None,
    provider_id: str = None,
) -> str:
    """
    Main AI dispatch function.
    Selects configured provider (or default), makes the call, logs usage.
    Returns the response text.
    """
    from app.models.ai_providers import AIProvider, AIUsageLog

    if provider_id:
        p = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    else:
        p = get_default_provider(db)

    t0        = time.time()
    error_msg = None
    result    = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "fallback"}

    if p:
        try:
            result = call_provider(p, messages, system=system,
                                   model=model or p.default_model,
                                   max_tokens=max_tokens)
            p.total_requests   += 1
            p.total_tokens_in  += result["tokens_in"]
            p.total_tokens_out += result["tokens_out"]
            p.last_used_at      = datetime.now(timezone.utc)
            cat_models = PROVIDER_CATALOG.get(p.provider, {}).get("models", [])
            m_info = next((m for m in cat_models if m["id"] == (model or p.default_model)), None)
            if m_info:
                cost = (result["tokens_in"]  / 1_000_000 * m_info["cost_in"] +
                        result["tokens_out"] / 1_000_000 * m_info["cost_out"])
                p.total_cost_usd    += cost
                result["cost_usd"]   = cost
            db.commit()
        except Exception as e:
            error_msg     = str(e)
            p.last_error  = error_msg[:500]
            p.last_error_at = datetime.now(timezone.utc)
            p.status      = "error"
            db.commit()
            api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
            if api_key and p.provider != "anthropic":
                try:
                    result    = _call_anthropic(api_key, settings.NEXUS_AI_MODEL,
                                                messages, system, max_tokens or 1500, 0.7)
                    error_msg = None
                except Exception:
                    pass
    else:
        api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if api_key:
            try:
                result = _call_anthropic(api_key, settings.NEXUS_AI_MODEL,
                                         messages, system, max_tokens or 1500, 0.7)
            except Exception as e:
                error_msg = str(e)
        else:
            result["text"] = (
                "⚠️ No hay ningún proveedor de IA configurado. "
                "Ve a Inteligencia IA → IA & Conectores para añadir uno."
            )

    latency = int((time.time() - t0) * 1000)
    log = AIUsageLog(
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
    )
    db.add(log)
    try:
        db.commit()
    except Exception:
        db.rollback()

    if error_msg is None and result.get("cost_usd", 0) > 0:
        try:
            threshold   = settings.AI_COST_ALERT_USD_PER_DAY
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_cost  = db.query(func.sum(AIUsageLog.cost_usd)).filter(
                AIUsageLog.created_at >= today_start,
                AIUsageLog.success == True,
            ).scalar() or 0
            if today_cost > threshold:
                _logger.warning(
                    "AI_COST_ALERT: coste diario acumulado $%.4f supera el umbral $%.2f.",
                    today_cost, threshold,
                )
        except Exception as alert_exc:
            _logger.debug("Cost alert check failed (non-critical): %s", alert_exc)

    return result["text"]
