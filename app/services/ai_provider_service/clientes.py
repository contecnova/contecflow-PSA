"""Clientes HTTP de cada proveedor: llamada, adjuntos, listado y sincronizacion de modelos, despacho `call_provider` y diagnostico.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_value
from app.services.ai_provider_service.catalogo import (
    PROVIDER_CATALOG,
    _DEPRECATED_MODELS,
    _normalize_ollama_base,
    _normalize_openai_base,
    _validate_model,
)
from app.core.codigos_de_error import ErrorConCodigo

_logger = logging.getLogger("ai_provider_service")


# ── Salida a la red (auditoría 22-11-2026, 02 C4) ─────────────────────────────
#
# `api_base_url` lo edita el admin de empresa: sin guardia, la API key viajaba a
# cualquier host y `169.254.169.254` o la intranet quedaban a un «probar» de
# distancia. Todas las llamadas pasan por `_http`: si el destino es el de la
# configuración de PLATAFORMA (`settings.*_API_URL`, `OLLAMA_BASE_URL`, mismo
# esquema+host+puerto) se confía en él (Ollama local en localhost es legítimo);
# cualquier otro pasa por el guardia SSRF central con comprobación de la IP
# conectada. El cuerpo de la respuesta remota solo se devuelve en el error si
# el destino es de plataforma (si no, sería un oráculo para sondear la red).

def _origenes_de_plataforma() -> set[tuple]:
    from urllib.parse import urlparse

    origenes = set()
    for clave in ("ANTHROPIC_API_URL", "OPENAI_API_URL", "GEMINI_API_URL", "DEEPSEEK_API_URL",
                  "GROQ_API_URL", "MISTRAL_API_URL", "OLLAMA_BASE_URL", "AZURE_OPENAI_API_URL"):
        u = urlparse(str(getattr(settings, clave, "") or ""))
        if u.hostname:
            origenes.add((u.scheme.lower(), u.hostname.lower(), u.port))
    return origenes


def _es_de_plataforma(url: str) -> bool:
    from urllib.parse import urlparse

    u = urlparse(str(url))
    return (u.scheme.lower(), (u.hostname or "").lower(), u.port) in _origenes_de_plataforma()


def _http(metodo: str, url: str, **kwargs) -> httpx.Response:
    """Petición a un proveedor de IA: destino de plataforma o guardia SSRF."""
    if _es_de_plataforma(url):
        return getattr(httpx, metodo.lower())(url, **kwargs)
    from app.core.outbound_url import cliente_httpx, validar_url_o_valueerror

    validar_url_o_valueerror(url, field="api_base_url")
    timeout = kwargs.pop("timeout", 30.0)
    with cliente_httpx(timeout=timeout) as c:
        return c.request(metodo, url, **kwargs)


def _cuerpo(resp: httpx.Response, n: int = 200) -> str:
    """El cuerpo remoto para el mensaje de error, solo si el destino es de plataforma."""
    try:
        if _es_de_plataforma(str(resp.request.url)):
            return resp.text[:n]
    except Exception:  # noqa: BLE001 — sin petición asociada (tests)
        _logger.debug("_cuerpo: excepcion ignorada", exc_info=True)
        return resp.text[:n]
    return "(respuesta omitida: destino configurado por la empresa)"


# ── Adjuntos (imágenes y PDF) ────────────────────────────────────────────────
#
# Revisión 2026-11. Un mensaje puede llevar `adjuntos=[{"media": "image/png",
# "datos": "<base64>"}]` y cada familia lo traduce a su formato. Antes la única
# llamada con imagen (el OCR de recibos) iba directa a Anthropic y con otro
# proveedor no había OCR.

def _con_adjuntos(messages: list, familia: str) -> list:
    salida = []
    for m in messages:
        adjuntos = m.get("adjuntos") or []
        if not adjuntos:
            salida.append({k: v for k, v in m.items() if k != "adjuntos"})
            continue
        texto = m.get("content") or ""
        if familia == "anthropic":
            bloques = [{"type": "document" if a["media"] == "application/pdf" else "image",
                        "source": {"type": "base64", "media_type": a["media"], "data": a["datos"]}} for a in adjuntos]
            salida.append({"role": m["role"], "content": bloques + [{"type": "text", "text": texto}]})
        elif familia == "openai":
            bloques = [{"type": "file", "file": {"filename": "documento.pdf", "file_data": f"data:application/pdf;base64,{a['datos']}"}}
                       if a["media"] == "application/pdf" else
                       {"type": "image_url", "image_url": {"url": f"data:{a['media']};base64,{a['datos']}"}} for a in adjuntos]
            salida.append({"role": m["role"], "content": [{"type": "text", "text": texto}] + bloques})
        elif familia == "gemini":
            salida.append({"role": m["role"], "content": texto,
                           "_partes": [{"inline_data": {"mime_type": a["media"], "data": a["datos"]}} for a in adjuntos]})
        elif familia == "ollama":
            if any(a["media"] == "application/pdf" for a in adjuntos):
                raise ErrorConCodigo("ia_ollama_sin_pdf")
            salida.append({"role": m["role"], "content": texto, "images": [a["datos"] for a in adjuntos]})
        else:
            raise ErrorConCodigo("ia_proveedor_sin_adjuntos", proveedor=familia)
    return salida


def _call_anthropic(api_key, model, messages, system, max_tokens, temperature) -> dict:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": _con_adjuntos(messages, "anthropic")}
    if system:
        body["system"] = system
    resp = _http("POST", f"{settings.ANTHROPIC_API_URL.rstrip('/')}/messages",
                      json=body, headers=headers, timeout=espera_de_ia("OUTBOUND_AI_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"Anthropic {resp.status_code}: {_cuerpo(resp, 200)}")
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
    all_messages.extend(_con_adjuntos(messages, "openai"))
    body = {"model": model, "messages": all_messages, "max_tokens": max_tokens, "temperature": temperature}
    resp = _http("POST", endpoint, json=body, headers=headers, timeout=espera_de_ia("OUTBOUND_AI_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"API {resp.status_code}: {_cuerpo(resp, 200)}")
    data  = resp.json()
    text  = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {"text": text, "model": model,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0)}


def _call_gemini(api_key, model, messages, system, max_tokens, temperature) -> dict:
    # M43 (auditoría 22-11-2026): la clave va en la cabecera `x-goog-api-key`
    # (documentada por la API de Gemini), no en la URL que registran httpx y los proxies.
    url = f"{settings.GEMINI_API_URL}/models/{model}:generateContent"
    cabeceras = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    contents = []
    if system:
        contents.append({"role": "user",  "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "Entendido."}]})
    for m in _con_adjuntos(messages, "gemini"):
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": (m.get("_partes") or []) + [{"text": m["content"]}]})
    # Revisión 2026-11, medido con la API real: los modelos 2.5 «piensan» y el
    # razonamiento cuenta dentro de `maxOutputTokens`. Con el tope justo la
    # respuesta llegaba cortada a media frase (`finishReason: MAX_TOKENS`) y se
    # devolvía tal cual: el resumen ejecutivo acababa en «una falta crítica de».
    # Si se corta por el tope y hubo razonamiento, se repite una vez dando a la
    # respuesta su presupuesto entero además de lo que gastó en pensar.
    tope = max_tokens
    gastado_antes = 0
    for intento in range(2):
        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": tope, "temperature": temperature},
        }
        resp = _http("POST", url, json=body, headers=cabeceras, timeout=espera_de_ia("OUTBOUND_AI_TIMEOUT_SECONDS"))
        if resp.status_code != 200:
            raise Exception(f"Gemini {resp.status_code}: {_cuerpo(resp, 200)}")
        data  = resp.json()
        candidato = (data.get("candidates") or [{}])[0]
        partes = (candidato.get("content") or {}).get("parts") or []
        text  = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        usage = data.get("usageMetadata", {})
        pensado = usage.get("thoughtsTokenCount", 0)
        cortado = candidato.get("finishReason") == "MAX_TOKENS"
        if intento == 0 and cortado and pensado:
            gastado_antes = usage.get("candidatesTokenCount", 0) + pensado
            tope = max_tokens + pensado
            continue
        break
    if not text:
        motivo = candidato.get("finishReason") or "sin texto"
        raise ErrorConCodigo("ia_sin_texto_tokens", detail=f"Gemini no devolvió texto ({motivo}; {pensado} tokens "
                         f"de razonamiento de {tope}): sube el máximo de tokens del proveedor")
    if cortado:
        _logger.warning("Gemini cortó la respuesta en el tope (%s tokens, %s de razonamiento)", tope, pensado)
    return {"text": text, "model": model, "truncado": cortado,
            "tokens_in": usage.get("promptTokenCount", 0),
            # El razonamiento se factura como salida, también el del primer intento.
            "tokens_out": usage.get("candidatesTokenCount", 0) + pensado + gastado_antes}


def espera_de_ia(clave: str) -> float:
    """Tiempo de espera (s) de una llamada a un proveedor: ajuste de Admin, si no `.env`.

    La lectura va a la cache de `settings_service`; la llamada al modelo tarda
    segundos, una consulta mas no se nota.

    Baja (auditoría 22-11-2026): el valor se guarda 60 s por clave; antes cada
    llamada HTTP a un proveedor abría una sesión de base de datos nueva.
    """
    import time as _time
    guardado = _ESPERAS.get(clave)
    if guardado and _time.monotonic() - guardado[1] < 60:
        return guardado[0]
    valor = _espera_de_ia_sin_cache(clave)
    _ESPERAS[clave] = (valor, _time.monotonic())
    return valor


_ESPERAS: dict = {}


def _espera_de_ia_sin_cache(clave: str) -> float:
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import get_runtime_float
        with SessionLocal() as _db:
            from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
            _declarar_sistema(_db, "ajustes globales de IA")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
            v = get_runtime_float(_db, clave)
        if v:
            return float(v)
    except Exception:
        _logger.debug("Ajuste %s no disponible; uso .env", clave, exc_info=True)
    return float(getattr(settings, clave))


def _call_ollama(base_url, model, messages, system, max_tokens, temperature) -> dict:
    url = _normalize_ollama_base(base_url).rstrip("/") + "/api/chat"
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(_con_adjuntos(messages, "ollama"))
    body = {"model": model, "messages": all_messages, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature}}
    resp = _http("POST", url, json=body, timeout=espera_de_ia("AI_LOCAL_HTTP_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"Ollama {resp.status_code}: {_cuerpo(resp, 200)}")
    data = resp.json()
    text = data.get("message", {}).get("content", "")
    return {"text": text, "model": model,
            "tokens_in": data.get("prompt_eval_count", 0) or 0,
            "tokens_out": data.get("eval_count", 0) or 0}


def _list_openai_compatible_models(base_url: str, api_key: str) -> list[str]:
    base = _normalize_openai_base(base_url)
    if not base:
        raise ErrorConCodigo("integracion_no_configurada", detail="Base URL vacía para proveedor compatible OpenAI", nombre="OpenAI")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = _http("GET", f"{base}/models", headers=headers, timeout=espera_de_ia("AI_MODELS_LIST_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"List Models {resp.status_code}: {_cuerpo(resp, 250)}")
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
    resp = _http("GET", f"{settings.ANTHROPIC_API_URL.rstrip('/')}/models", headers=headers, timeout=espera_de_ia("AI_MODELS_LIST_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"Anthropic list models {resp.status_code}: {_cuerpo(resp, 250)}")
    data = resp.json()
    raw = data.get("data", []) if isinstance(data, dict) else []
    models = sorted({str(m.get("id", "")).strip() for m in raw if isinstance(m, dict) and m.get("id")})
    return [m for m in models if m]


def _list_gemini_models(api_key: str) -> list[str]:
    base = settings.GEMINI_API_URL.rstrip("/")
    url = f"{base}/models"   # M43: clave en cabecera
    models: set[str] = set()
    for _ in range(3):
        resp = _http("GET", url, headers={"x-goog-api-key": api_key},
                     timeout=espera_de_ia("AI_MODELS_LIST_TIMEOUT_SECONDS"))
        if resp.status_code != 200:
            raise Exception(f"Gemini list models {resp.status_code}: {_cuerpo(resp, 250)}")
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
        url = f"{base}/models?pageToken={next_token}"
    return sorted(models)


def _list_ollama_models(base_url: str) -> list[str]:
    base = _normalize_ollama_base(base_url)
    if not base:
        raise ErrorConCodigo("integracion_no_configurada", detail="Base URL vacía para Ollama", nombre="Ollama")
    resp = _http("GET", f"{base}/api/tags", timeout=espera_de_ia("AI_MODELS_LIST_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"Ollama list models {resp.status_code}: {_cuerpo(resp, 250)}")
    data = resp.json() if resp.content else {}
    raw = data.get("models", []) if isinstance(data, dict) else []
    names = sorted({str(m.get("name", "")).strip() for m in raw if isinstance(m, dict) and m.get("name")})
    return [m for m in names if m]


def _list_azure_models(base_url: str, api_key: str) -> list[str]:
    base = _normalize_openai_base(base_url)
    if not base:
        raise ErrorConCodigo("integracion_no_configurada", detail="Base URL vacía para Azure OpenAI", nombre="Azure OpenAI")
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    # Data-plane model listing in Azure OpenAI
    resp = _http("GET", f"{base}/models?api-version=2024-10-21", headers=headers, timeout=espera_de_ia("AI_MODELS_LIST_TIMEOUT_SECONDS"))
    if resp.status_code != 200:
        raise Exception(f"Azure list models {resp.status_code}: {_cuerpo(resp, 250)}")
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
            raise ErrorConCodigo("ia_falta_api_key", detail="Falta API key para listar modelos de Anthropic", proveedor="Anthropic")
        return _list_anthropic_models(api_key)

    if provider_type == "gemini":
        if not api_key:
            raise ErrorConCodigo("ia_falta_api_key", detail="Falta API key para listar modelos de Gemini", proveedor="Gemini")
        return _list_gemini_models(api_key)

    if provider_type in ("openai", "groq", "mistral", "deepseek"):
        if not api_key:
            raise ErrorConCodigo("ia_falta_api_key", detail=f"Falta API key para listar modelos de {provider_type}", proveedor=provider_type)
        return _list_openai_compatible_models(base_url, api_key)

    if provider_type == "azure":
        if not api_key:
            raise ErrorConCodigo("ia_falta_api_key", detail="Falta API key para listar modelos de Azure", proveedor="Azure")
        return _list_azure_models(base_url, api_key)

    raise ErrorConCodigo("proveedor_no_soportado", detail=f"Proveedor no soportado para list models: {provider_type}", proveedor=provider_type)


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
        raise ErrorConCodigo("proveedor_no_soportado", proveedor=provider.provider)


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
