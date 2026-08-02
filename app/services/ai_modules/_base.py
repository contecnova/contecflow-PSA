"""Shared AI primitives and helpers for the ai_modules service package."""
from __future__ import annotations
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.ai_dispatch import call_ai
from app.models.ai_chat import (
    AIActionLog,
)
from app.models.imputation import Imputation

_log = logging.getLogger(__name__)


def api_key(db=None, org_id: Optional[str] = None) -> Optional[str]:
    if db is not None:
        try:
            from app.services.integration_credentials_service import get_credential
            ui_key = get_credential(db, "ai_providers", "anthropic_api_key", org_id=org_id)
            if ui_key:
                return ui_key
        except Exception:
            _log.debug("api_key: fallo best-effort ignorado", exc_info=True)
    return settings.ANTHROPIC_API_KEY or None


def _default_model(db=None, org_id: Optional[str] = None) -> str:
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_str
            ui_val = get_runtime_str(db, "CONTECFLOW_AI_MODEL", org_id)
            if ui_val:
                return ui_val
        except Exception:
            _log.debug("_default_model: fallo best-effort ignorado", exc_info=True)
    return settings.CONTECFLOW_AI_MODEL


def call_claude(messages, system=None, model=None, tools=None, max_tokens=1000, db=None, org_id: Optional[str] = None):
    """Llamada síncrona a Anthropic API usando httpx.

    Migrado de urllib.request → httpx (#66): httpx aporta retries
    configurables, timeouts más granulares (connect/read/write/pool),
    soporte nativo HTTP/2 y mejor manejo de errores.
    """
    import httpx
    body = {"model": model or _default_model(db=db, org_id=org_id), "max_tokens": max_tokens, "messages": messages}
    if system: body["system"] = system
    if tools:  body["tools"] = tools
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key(db=db, org_id=org_id),
        "anthropic-version": "2023-06-01",
    }
    from app.services.settings_service import outbound_ai_timeout
    timeout = outbound_ai_timeout(db)
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        response = client.post(settings.ANTHROPIC_API_URL, json=body, headers=headers)
        response.raise_for_status()
        return response.json()


def call_ai_unified(db, messages, system=None, module="v16", user_id=None, max_tokens=1000):
    """Wrapper that uses the configured provider or falls back to direct Claude."""
    try:
        return call_ai(db, messages, system=system, module=module,
                       user_id=user_id, max_tokens=max_tokens)
    except Exception:
        _log.warning("Unified AI call failed for module=%s user=%s; falling back to direct Claude", module, user_id, exc_info=True)
        resp = call_claude(messages, system=system, max_tokens=max_tokens, db=db)
        return extract_text(resp)


def extract_text(response) -> str:
    return "\n".join(b["text"] for b in response.get("content", []) if b.get("type") == "text")


def _parse_llm_json(raw: str, pattern: str = r"\{.*\}"):
    """Extrae y parsea el primer bloque JSON de la respuesta LLM.

    LLMs devuelven JSON imperfecto a menudo: markdown fences, trailing commas,
    prefijos de explicación. Este helper:
      1. Quita fences ``` ```json ``` ``` o ``` ``` ``` (item #74).
      2. Busca con la regex (default ``{...}``; usar ``[.*]`` para arrays).
      3. Intenta ``json.loads`` directo.
      4. Si falla, sanea trailing commas y reintenta.

    Devuelve ``None`` si no encuentra match. Lanza ``json.JSONDecodeError``
    solo si el saneado también falla → el caller puede capturarlo.
    """
    import json as __json
    import re as __re
    if not raw:
        return None
    # Item #74: strip markdown fences. El LLM a veces envuelve el JSON en
    # ```json … ``` o ``` … ```; el regex `\{.*\}` lo cazaba bien porque las
    # llaves siguen presentes, pero los fence delimiters dejan caracteres
    # extra (espacios, "json") al inicio del primer match que rompe parses.
    cleaned_raw = __re.sub(r"```(?:json)?\s*", "", raw, flags=__re.IGNORECASE)
    cleaned_raw = cleaned_raw.replace("```", "")
    m = __re.search(pattern, cleaned_raw, __re.DOTALL)
    if not m:
        return None
    try:
        return __json.loads(m.group(0))
    except __json.JSONDecodeError:
        cleaned = __re.sub(r",\s*([}\]])", r"\1", m.group(0))
        return __json.loads(cleaned)


def compute_kb_embedding(db, article_id: str, text: str):
    """Compute and persist the vector embedding for a KB article (best-effort)."""
    try:
        from app.services.semantic_classifier import _get_model
        model, _ = _get_model()
        if hasattr(model, "encode"):
            emb = model.encode([text], show_progress_bar=False)[0].tolist()
        else:
            emb = model.encode([text])[0]
        from app.models.ai_chat import AIKBArticle as _Art
        art = db.query(_Art).filter(_Art.id == article_id).first()
        if art:
            art.embedding = json.dumps(emb)
            db.commit()
    except Exception:
        _log.warning("Failed to compute KB embedding for article=%s", article_id, exc_info=True)


def log_action(db, user_id, module, action_type, input_s=None, output_s=None,
               entities=None, tokens=0, latency=0, status="success"):
    db.add(AIActionLog(
        user_id=user_id, module=module, action_type=action_type,
        input_summary=(input_s or "")[:300], output_summary=(output_s or "")[:300],
        entities_affected=json.dumps(entities or []),
        tokens_used=tokens, latency_ms=latency, status=status,
    ))


def burnout_score(weekly_hours: list) -> float:
    """
    Multi-factor burnout probability (0–0.99):
      - Weighted average (most recent 2 weeks weighted 2×)
      - Trend factor (increasing load adds up to +0.15)
      - Coefficient of Variation (high variance = additional stress)
      - Consecutive overloaded weeks (>42h each adds +0.08)
    """
    n = len(weekly_hours)
    if n == 0:
        return 0.0
    weights = ([2, 2] + [1] * max(n - 2, 0))[:n]
    wavg    = sum(h * w for h, w in zip(weekly_hours, weights)) / sum(weights)  # noqa: B905
    if wavg < 30:
        return 0.0

    base = max(0.0, (wavg - 35) / 25)

    if n > 1:
        trend = (weekly_hours[0] - weekly_hours[-1]) / max(weekly_hours[-1], 1)
        trend_factor = max(0.0, min(trend * 0.15, 0.15))
    else:
        trend_factor = 0.0

    mean = sum(weekly_hours) / n
    variance = sum((h - mean) ** 2 for h in weekly_hours) / n
    std = variance ** 0.5
    cv  = std / max(mean, 1)
    cv_factor = min(cv * 0.05, 0.08)

    consecutive = sum(1 for h in weekly_hours if h > 42)
    consec_factor = consecutive * 0.08

    return min(base + trend_factor + cv_factor + consec_factor, 0.99)


def chunk_text(text: str, chunk_size: int = 6000, overlap: int = 500) -> list:
    """Split text into overlapping chunks so no content is lost."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def map_reduce_analysis(
    text: str,
    map_system: str,
    map_user_prefix: str,
    reduce_system: str,
    reduce_user_suffix: str,
    db,
    module: str,
    user_id: str,
    map_tokens: int = 1500,
    reduce_tokens: int = 3000,
) -> str:
    chunks = chunk_text(text)

    if len(chunks) == 1:
        prompt = f"{map_user_prefix}\n\n{text}\n\n{reduce_user_suffix}"
        return call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            system=reduce_system, module=module, user_id=user_id, max_tokens=reduce_tokens,
        )

    partials = []
    for i, chunk in enumerate(chunks):
        prompt = (
            f"{map_user_prefix}\n\n"
            f"[Fragmento {i + 1} de {len(chunks)}]:\n{chunk}\n\n"
            "Extrae los puntos más importantes de este fragmento en texto libre. Sé conciso."
        )
        partial = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            system=map_system, module=module, user_id=user_id, max_tokens=map_tokens,
        )
        partials.append(f"--- Fragmento {i + 1} ---\n{partial}")

    combined = "\n\n".join(partials)
    reduce_prompt = (
        f"Los siguientes son los análisis parciales de cada fragmento del documento completo:\n\n"
        f"{combined}\n\n"
        f"{reduce_user_suffix}"
    )
    return call_ai_unified(
        db, [{"role": "user", "content": reduce_prompt}],
        system=reduce_system, module=module, user_id=user_id, max_tokens=reduce_tokens,
    )


def _project_internal_cost(db: Session, project_id: str) -> dict:
    """Calcula el coste INTERNO de un proyecto (lo que gastamos en sueldos +
    overhead), no lo que facturamos al cliente.

    Item #83: antes Oracle solo conocía ``hours × billing_rate`` (revenue).
    Para detectar pérdidas reales necesitamos comparar el presupuesto contra
    el coste real, que viene de ``UserCostProfile.cost_per_hour`` (salario +
    impuestos + overhead) por user, válido en la fecha de cada imputación.

    Cascada de fuentes (en orden de preferencia):
      1. ``Imputation.cost_amount`` si está populado → usarlo directamente.
      2. ``hours × UserCostProfile.cost_per_hour`` válido para esa fecha.
      3. ``hours × AI_REVENUE_HOURLY_RATE_FALLBACK`` (último recurso).

    Devuelve ``{"cost_eur": float, "method": str, "coverage_pct": float}``
    donde ``coverage_pct`` indica qué porcentaje de las horas se calculó con
    datos reales (cost_amount o cost_profile) vs fallback global.
    """
    from app.models.user_cost import UserCostProfile  # noqa: PLC0415
    from app.core.config import settings as _s  # noqa: PLC0415

    fallback_rate = float(getattr(_s, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)
    imps = db.query(Imputation).filter(Imputation.project_id == project_id).all()
    if not imps:
        return {"cost_eur": 0.0, "method": "no_data", "coverage_pct": 0.0}

    # Cargamos todos los cost profiles de los users involucrados de una sola vez
    # (evita N queries por user).
    user_ids = {i.user_id for i in imps if i.user_id}
    profiles_by_user: dict = {}
    if user_ids:
        rows = db.query(UserCostProfile).filter(
            UserCostProfile.user_id.in_(list(user_ids))
        ).all()
        for r in rows:
            profiles_by_user.setdefault(r.user_id, []).append(r)

    def _rate_for(user_id, imp_date):
        profiles = profiles_by_user.get(user_id, [])
        if not profiles:
            return None
        # Buscar el profile cuya vigencia [valid_from, valid_to|None] contenga imp_date
        for prof in profiles:
            vf = prof.valid_from
            vt = prof.valid_to
            if vf and imp_date < vf:
                continue
            if vt is not None and imp_date > vt:
                continue
            return float(prof.cost_per_hour or 0)
        # Si ninguno aplica, tomar el más reciente con vt=None (current)
        current_open = [p for p in profiles if p.valid_to is None]
        if current_open:
            current_open.sort(key=lambda p: p.valid_from or 0, reverse=True)
            return float(current_open[0].cost_per_hour or 0)
        return None

    total_cost = 0.0
    real_hours = 0.0
    fallback_hours = 0.0

    for imp in imps:
        hours = float(imp.hours or 0)
        if hours <= 0:
            continue
        if imp.cost_amount is not None and imp.cost_amount > 0:
            total_cost += float(imp.cost_amount)
            real_hours += hours
            continue
        rate = _rate_for(imp.user_id, imp.date) if imp.user_id else None
        if rate is not None and rate > 0:
            total_cost += hours * rate
            real_hours += hours
        else:
            total_cost += hours * fallback_rate
            fallback_hours += hours

    total_hours = real_hours + fallback_hours
    coverage = (real_hours / total_hours * 100) if total_hours > 0 else 0.0

    if fallback_hours == 0 and real_hours > 0:
        method = "cost_profile"
    elif real_hours == 0:
        method = "fallback_only"
    else:
        method = "mixed"

    return {"cost_eur": round(total_cost, 2), "method": method, "coverage_pct": round(coverage, 1)}


def _scope_query_by_org(q, model, user_org):
    """Apply organization_id filter to a query if user is not superadmin.

    Centraliza el patrón ``if user_org and hasattr(model, ...): q.filter(...)``
    para reusarlo en helpers Oracle. Devuelve la query (mutable) ya filtrada.
    """
    if user_org and hasattr(model, "organization_id"):
        return q.filter(getattr(model, "organization_id") == user_org)  # noqa: B009
    return q


def _severity_from_probability(probability: float) -> str:
    """Map probability to severity bucket: critical (>0.75), high (>0.5), else medium."""
    if probability > 0.75:
        return "critical"
    if probability > 0.5:
        return "high"
    return "medium"


def kb_vector_search(db, query_text: str, limit: int = 5, only_published: bool = True) -> list:
    """
    Vector similarity search over KB articles.
    Falls back to empty list if no embeddings exist.
    """
    try:
        from app.services.semantic_classifier import _get_model, _cosine
        from app.models.ai_chat import AIKBArticle
        model, _ = _get_model()
        if hasattr(model, "encode"):
            q_emb = model.encode([query_text], show_progress_bar=False)[0].tolist()
        else:
            q_emb = model.encode([query_text])[0]

        q = db.query(AIKBArticle).filter(AIKBArticle.embedding.isnot(None))
        if only_published:
            q = q.filter(AIKBArticle.is_published == True)
        articles = q.all()
        if not articles:
            return []

        scored = []
        for a in articles:
            try:
                a_emb = json.loads(a.embedding)
                sim = _cosine(q_emb, a_emb)
                scored.append((sim, a))
            except Exception:
                _log.debug("Skipping KB article %s due to embedding decode failure", getattr(a, "id", None), exc_info=True)
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:limit]]
    except Exception:
        _log.warning("KB semantic search failed", exc_info=True)
        return []


def openai_key_from_db(db) -> Optional[str]:
    """Return the API key of the first active OpenAI provider, or None."""
    try:
        from app.models.ai_providers import AIProvider
        p = db.query(AIProvider).filter(
            AIProvider.provider == "openai",
            AIProvider.status != "error",
        ).first()
        return p.api_key if p and p.api_key else None
    except Exception:
        _log.warning("Failed to load OpenAI provider key from DB", exc_info=True)
        return None
