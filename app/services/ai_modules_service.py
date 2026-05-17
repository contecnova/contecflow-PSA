"""
ai_modules_service.py — Business logic extracted from ai_modules.py router.
"""
from __future__ import annotations
import json
import time
import logging
from datetime import datetime, timedelta, date, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.services.ai_dispatch import call_ai
from app.core.security import verify_client_token
from app.models.ai_chat import (
    AIActionLog, AIPrediction, AIVoiceCommand,
    AIMeeting, AIMeetingAction, AIContract, AIContractClause,
    AIKBArticle, AIClientChatSession, AIClientChatMessage,
    AIAgentExecution as _ExecRecord,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.worker import run_agent_task
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AI CALL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def api_key(db=None, org_id: Optional[str] = None) -> Optional[str]:
    if db is not None:
        try:
            from app.services.integration_credentials_service import get_credential
            ui_key = get_credential(db, "ai_providers", "anthropic_api_key", org_id=org_id)
            if ui_key:
                return ui_key
        except Exception:
            pass
    return settings.ANTHROPIC_API_KEY or None


def _default_model(db=None, org_id: Optional[str] = None) -> str:
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_str
            ui_val = get_runtime_str(db, "CONTECFLOW_AI_MODEL", org_id)
            if ui_val:
                return ui_val
        except Exception:
            pass
    return settings.CONTECFLOW_AI_MODEL


def call_ai_unified(db, messages, system=None, module="v16", user_id=None, max_tokens=1000):
    """Wrapper that uses the configured provider or falls back to direct Claude."""
    try:
        return call_ai(db, messages, system=system, module=module,
                       user_id=user_id, max_tokens=max_tokens)
    except Exception:
        _log.warning("Unified AI call failed for module=%s user=%s; falling back to direct Claude", module, user_id, exc_info=True)
        resp = call_claude(messages, system=system, max_tokens=max_tokens, db=db)
        return extract_text(resp)


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


# ═══════════════════════════════════════════════════════════════════════════════
# BURNOUT MULTI-FACTOR SCORER
# ═══════════════════════════════════════════════════════════════════════════════

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
    wavg    = sum(h * w for h, w in zip(weekly_hours, weights)) / sum(weights)
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


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNKING HELPERS FOR LONG DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# NEXUSORACLE — run_oracle business logic
# ═══════════════════════════════════════════════════════════════════════════════

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
        return q.filter(getattr(model, "organization_id") == user_org)
    return q


def _severity_from_probability(probability: float) -> str:
    """Map probability to severity bucket: critical (>0.75), high (>0.5), else medium."""
    if probability > 0.75:
        return "critical"
    if probability > 0.5:
        return "high"
    return "medium"


def _oracle_project_delay(db: Session, projects: list, now: datetime) -> list:
    """Sección 1 de Oracle: detección de riesgo de retraso por proyecto.

    Devuelve la lista de alertas generadas (dicts) y muta la DB añadiendo /
    actualizando ``AIPrediction(prediction_type='project_delay')``. No commit.
    """
    from app.core.config import settings as _s  # noqa: PLC0415
    _rate_fb = float(getattr(_s, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)

    generated: list = []
    for p in projects:
        tasks = db.query(Task).filter(Task.project_id == p.id).all()
        if not tasks:
            continue
        done    = sum(1 for t in tasks if t.status == "done")
        overdue = sum(1 for t in tasks if t.status != "done" and t.due_date and t.due_date < now.date())
        pct_done = done / len(tasks)

        hours_total = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        budget = p.budget_amount or 1
        # Tarifa: si el proyecto define billing_rate, ese gana. Si no, usar el
        # fallback global configurable (antes 100 aquí y 85 en run_oracle_health
        # → inconsistente). Centralizamos en AI_REVENUE_HOURLY_RATE_FALLBACK.
        revenue_consumed_pct = (hours_total * (getattr(p, "billing_rate", _rate_fb) or _rate_fb)) / max(budget, 1)
        # Item #83: añadimos coste interno como segunda métrica. El riesgo se
        # dispara con el PEOR de los dos — un proyecto que quema horas más
        # rápido de lo que factura debe surgir aunque parezca OK por revenue.
        cost_info_d = _project_internal_cost(db, p.id)
        cost_consumed_pct = (float(cost_info_d["cost_eur"]) / max(budget, 1)) if budget else 0.0
        budget_consumed_pct = max(revenue_consumed_pct, cost_consumed_pct)

        risk_score = 0
        if overdue > 0:
            risk_score += min(overdue / max(len(tasks), 1) * 50, 40)
        if pct_done < 0.3 and p.end_date_planned and p.end_date_planned < (now + timedelta(days=14)).date():
            risk_score += 35
        if budget_consumed_pct > 0.9:
            risk_score += 25

        probability = min(round(risk_score / 100, 2), 0.99)
        if probability < 0.25:
            continue

        severity = _severity_from_probability(probability)
        title = f"Riesgo de retraso — {p.name}"
        explanation = (
            f"El proyecto tiene {overdue} tareas vencidas de {len(tasks)} totales "
            f"({round(pct_done*100)}% completado). "
            f"Consumo facturable: {round(revenue_consumed_pct*100)}%, "
            f"coste interno: {round(cost_consumed_pct*100)}% "
            f"(método={cost_info_d['method']}, cobertura={cost_info_d['coverage_pct']}%)."
        )
        action = "Revisar tareas bloqueadas con el PM. Considerar reasignación de recursos."

        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == p.id,
            AIPrediction.prediction_type == "project_delay",
            AIPrediction.is_acknowledged == False,
        ).first()
        if existing:
            existing.probability = probability
            existing.severity = severity
            existing.explanation = explanation
            existing.recommended_action = action
        else:
            pred = AIPrediction(
                prediction_type="project_delay", entity_type="project", entity_id=p.id,
                probability=probability, severity=severity,
                title=title, explanation=explanation, recommended_action=action,
                features_used=json.dumps({
                    "overdue_ratio": round(overdue / max(len(tasks), 1), 2),
                    "pct_done": round(pct_done, 2),
                    "budget_consumed": round(budget_consumed_pct, 2),
                    # Item #83: ambas vistas explícitas para auditoría
                    "revenue_consumed_pct": round(revenue_consumed_pct, 2),
                    "cost_consumed_pct": round(cost_consumed_pct, 2),
                    "cost_method": cost_info_d["method"],
                    "cost_coverage_pct": cost_info_d["coverage_pct"],
                }),
            )
            db.add(pred)
            generated.append({"type": "project_delay", "entity": p.name, "probability": probability})
    return generated


def _oracle_sla_breach(db: Session, open_tickets: list, now: datetime) -> list:
    """Sección 2 de Oracle: detección de riesgo de incumplimiento SLA por ticket."""
    from app.core.config import settings as _env  # noqa: PLC0415
    from app.services.settings_service import get_runtime_namespace
    _s = get_runtime_namespace(db, {
        "SLA_PREDICTION_HOURS_CRITICAL": "int",
        "SLA_PREDICTION_HOURS_HIGH": "int",
        "SLA_PREDICTION_HOURS_MEDIUM": "int",
        "SLA_PREDICTION_HOURS_LOW": "int",
        "SLA_PREDICTION_WARNING_PCT": "float",
        "SLA_PREDICTION_SEVERITY_CRITICAL_H": "float",
        "SLA_PREDICTION_SEVERITY_HIGH_H": "float",
    })
    _sla_hours = {
        "critical": _s.SLA_PREDICTION_HOURS_CRITICAL or _env.SLA_PREDICTION_HOURS_CRITICAL,
        "high":     _s.SLA_PREDICTION_HOURS_HIGH or _env.SLA_PREDICTION_HOURS_HIGH,
        "medium":   _s.SLA_PREDICTION_HOURS_MEDIUM or _env.SLA_PREDICTION_HOURS_MEDIUM,
        "low":      _s.SLA_PREDICTION_HOURS_LOW or _env.SLA_PREDICTION_HOURS_LOW,
    }

    generated: list = []
    for t in open_tickets:
        if not t.created_at:
            continue
        created_aware = t.created_at.replace(tzinfo=timezone.utc) if t.created_at.tzinfo is None else t.created_at
        age_hours = (now - created_aware).total_seconds() / 3600
        sla_limit = _sla_hours.get(t.priority or "medium", _sla_hours["medium"])
        warn_pct = _s.SLA_PREDICTION_WARNING_PCT or _env.SLA_PREDICTION_WARNING_PCT
        if age_hours < sla_limit * warn_pct:
            continue

        remaining   = sla_limit - age_hours
        probability = min(round(age_hours / sla_limit, 2), 0.99)
        crit_h      = _s.SLA_PREDICTION_SEVERITY_CRITICAL_H or _env.SLA_PREDICTION_SEVERITY_CRITICAL_H
        high_h      = _s.SLA_PREDICTION_SEVERITY_HIGH_H or _env.SLA_PREDICTION_SEVERITY_HIGH_H
        severity    = ("critical" if remaining < crit_h
                       else "high" if remaining < high_h
                       else "medium")
        existing   = db.query(AIPrediction).filter(
            AIPrediction.entity_id == t.id,
            AIPrediction.prediction_type == "sla_breach",
            AIPrediction.is_acknowledged == False,
        ).first()
        if not existing:
            db.add(AIPrediction(
                prediction_type="sla_breach", entity_type="ticket", entity_id=t.id,
                probability=probability, severity=severity,
                title=f"Riesgo de incumplimiento SLA — Ticket {t.number}",
                explanation=f"Llevas {round(age_hours,1)}h abierto. Límite SLA para prioridad '{t.priority}': {sla_limit}h. Quedan {round(remaining,1)}h.",
                recommended_action="Asignar o escalar el ticket inmediatamente.",
            ))
            generated.append({"type": "sla_breach", "entity": t.number, "probability": probability})
    return generated


def _oracle_burnout(db: Session, active_users: list, now: datetime) -> list:
    """Sección 3 de Oracle: detección de burnout por usuario activo."""
    week_starts = [(now - timedelta(weeks=i)).date() for i in range(4)]

    generated: list = []
    for u in active_users:
        weekly = []
        for ws in week_starts:
            we = ws + timedelta(days=6)
            h  = db.query(func.sum(Imputation.hours)).filter(
                Imputation.user_id == u.id,
                Imputation.date >= ws, Imputation.date <= we,
            ).scalar() or 0
            weekly.append(h)
        probability = burnout_score(weekly)
        if probability < 0.25:
            continue
        avg   = sum(weekly) / max(len(weekly), 1)
        max_w = max(weekly)
        trend = weekly[0] - weekly[-1] if len(weekly) > 1 else 0
        trend_txt = f" Tendencia: {'↑ creciente' if trend > 3 else '→ estable'}." if len(weekly) > 1 else ""
        severity = _severity_from_probability(probability)
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == u.id,
            AIPrediction.prediction_type == "burnout",
            AIPrediction.is_acknowledged == False,
        ).first()
        if existing:
            existing.probability = probability
            existing.severity    = severity
        else:
            db.add(AIPrediction(
                prediction_type="burnout", entity_type="user", entity_id=u.id,
                probability=probability,
                severity=severity,
                title=f"Riesgo de burnout — {u.full_name}",
                explanation=(
                    f"Media ponderada (semanas recientes 2×): {round(avg,1)}h/sem. "
                    f"Pico: {round(max_w,1)}h.{trend_txt} "
                    f"Semanas con >42h: {sum(1 for h in weekly if h > 42)}."
                ),
                recommended_action="Revisar asignaciones. Redistribuir carga de trabajo.",
            ))
            generated.append({"type": "burnout", "entity": u.full_name, "probability": probability})
    return generated


def _oracle_budget_overrun(db: Session, projects: list) -> list:
    """Sección 4 de Oracle: detección de desviación presupuestaria.

    Item #83: dos métricas:
      - revenue_ratio = hours × billing_rate / budget (lo facturable al cliente)
      - cost_ratio    = internal_cost / budget       (lo que NOS cuesta, vía UserCostProfile)
    Alerta dispara cuando CUALQUIERA supera 85%. Severidad usa el peor ratio.
    Si cost_ratio > revenue_ratio + 0.10, marcamos margen erosionado.
    """
    from app.core.config import settings as _s_oracle  # noqa: PLC0415
    _rate_fb_oracle = float(getattr(_s_oracle, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)

    generated: list = []
    for p in projects:
        if not p.budget_amount:
            continue
        hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        # Revenue (lo que facturas)
        rate  = getattr(p, "billing_rate", _rate_fb_oracle) or _rate_fb_oracle
        revenue_spent = hours * rate
        revenue_ratio = revenue_spent / p.budget_amount
        # Internal cost (lo que gastas)
        cost_info = _project_internal_cost(db, p.id)
        cost_spent = float(cost_info["cost_eur"] or 0.0)
        cost_ratio = cost_spent / p.budget_amount if p.budget_amount else 0.0
        # Decisión: la peor de las dos manda
        worst_ratio = max(revenue_ratio, cost_ratio)
        if worst_ratio < 0.85:
            continue
        margin_eroded = cost_ratio > revenue_ratio + 0.10  # >10pp de gap = mal margen
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == p.id,
            AIPrediction.prediction_type == "budget_overrun",
            AIPrediction.is_acknowledged == False,
        ).first()
        if not existing:
            margin_note = ""
            if margin_eroded:
                margin_note = (
                    f" ⚠ Margen erosionado: coste interno {round(cost_ratio*100)}% > "
                    f"facturación {round(revenue_ratio*100)}% → posibles pérdidas reales."
                )
            db.add(AIPrediction(
                prediction_type="budget_overrun", entity_type="project", entity_id=p.id,
                probability=min(worst_ratio - 0.5, 0.99),
                severity="critical" if worst_ratio > 1 else "high",
                title=f"Desviación presupuestaria — {p.name}",
                explanation=(
                    f"Consumo facturable: {round(revenue_ratio*100)}% "
                    f"({round(revenue_spent/1000,1)}k€ de {round(p.budget_amount/1000,1)}k€). "
                    f"Coste interno: {round(cost_ratio*100)}% "
                    f"({round(cost_spent/1000,1)}k€, método={cost_info['method']}, "
                    f"cobertura datos reales={cost_info['coverage_pct']}%)."
                    f"{margin_note}"
                ),
                recommended_action=(
                    "Revisar alcance con el cliente. Preparar change order si hay trabajo extra."
                    + (" Auditar costes internos y replantear pricing del proyecto." if margin_eroded else "")
                ),
                features_used=json.dumps({
                    "revenue_ratio": round(revenue_ratio, 3),
                    "cost_ratio": round(cost_ratio, 3),
                    "hours_total": round(hours, 1),
                    "budget_eur": round(p.budget_amount, 2),
                    "revenue_eur": round(revenue_spent, 2),
                    "cost_eur": round(cost_spent, 2),
                    "cost_method": cost_info["method"],
                    "cost_coverage_pct": cost_info["coverage_pct"],
                    "margin_eroded": margin_eroded,
                }),
            ))
            generated.append({
                "type": "budget_overrun", "entity": p.name,
                "probability": round(worst_ratio - 0.5, 2),
                "revenue_ratio": round(revenue_ratio, 2),
                "cost_ratio": round(cost_ratio, 2),
                "margin_eroded": margin_eroded,
            })
    return generated


def run_oracle_analysis(db: Session, current_user) -> dict:
    """
    Runs all rule-based risk analyses and stores results as AIPrediction records.
    Returns { ok, methodology, alerts_generated, alerts, run_at }.

    Multi-tenant: cuando ``current_user.is_superadmin`` es False, todas las
    queries se filtran por ``current_user.organization_id``. Antes este job
    iteraba proyectos / tickets / users globalmente.

    Refactor #25: delega cada sección a un helper privado
    (``_oracle_project_delay``, ``_oracle_sla_breach``, ``_oracle_burnout``,
    ``_oracle_budget_overrun``) para reducir complejidad ciclomática.
    """
    now      = datetime.now(timezone.utc)
    is_super = bool(getattr(current_user, "is_superadmin", False))
    user_org = None if is_super else getattr(current_user, "organization_id", None)

    projects = _scope_query_by_org(
        db.query(Project).filter(Project.status.in_(["active", "planning"])),
        Project, user_org,
    ).all()
    open_tickets = _scope_query_by_org(
        db.query(Ticket).filter(Ticket.status.in_(["open", "in_progress"])),
        Ticket, user_org,
    ).all()
    active_users = _scope_query_by_org(
        db.query(User).filter(User.is_active == True),
        User, user_org,
    ).all()

    generated: list = []
    generated.extend(_oracle_project_delay(db, projects, now))
    generated.extend(_oracle_sla_breach(db, open_tickets, now))
    generated.extend(_oracle_burnout(db, active_users, now))
    generated.extend(_oracle_budget_overrun(db, projects))

    log_action(db, current_user.id, "contecfloworacle", "run",
               "oracle_full_analysis", f"Generated {len(generated)} predictions")
    db.commit()

    return {
        "ok": True,
        "methodology": "rules_based",
        "alerts_generated": len(generated),
        "alerts": generated,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

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


def _voice_parse_intent(db, transcript: str, current_user) -> tuple:
    """Llama al LLM con el transcript y extrae (intent, entities, action_description).

    Devuelve siempre una tupla 3 — fallback a ("unknown", {}, "...") si el LLM
    falla o el JSON no parsea.
    """
    import re as _re
    intent = "unknown"
    entities: dict = {}
    action_taken = ""
    try:
        prompt = f"""Analiza este comando de voz de un usuario de Contecflow y extrae:
- intent: log_hours | create_ticket | query_hours | create_task | get_summary | other
- entities: objetos relevantes (project_name, hours, task_name, date, ticket_title, priority, etc.)

Comando: "{transcript}"
Usuario: {current_user.full_name}
Hoy: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

Responde SOLO con JSON: {{"intent": "...", "entities": {{...}}, "action_description": "..."}}"""
        text = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="voice", user_id=current_user.id, max_tokens=300
        )
        match = _re.search(r'\{.*\}', text, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                intent = data.get("intent", "unknown")
                entities = data.get("entities", {})
                action_taken = data.get("action_description", "")
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except json.JSONDecodeError:
                pass
    except Exception as e:
        _log.warning(f"Voice command parsing failed: {e}")
        intent = "unknown"
        action_taken = "Error en IA, modo fallback activado"
    return intent, entities, action_taken


def _voice_find_project_scoped(db, name_pattern: str, cu_org, is_super_cu: bool):
    """Busca un Project por ``name ilike %pattern%`` filtrado por organization."""
    q = db.query(Project).filter(Project.name.ilike(f"%{name_pattern}%"))
    if cu_org and not is_super_cu:
        q = q.filter(Project.organization_id == cu_org)
    return q.first()


def _voice_handle_log_hours(db, current_user, transcript: str, entities: dict,
                            project, confirm: bool, result: dict) -> None:
    """Handler para intent ``log_hours``. Muta ``result`` in place."""
    if not project:
        result["action"] = f"No encontré el proyecto '{entities['project_name']}'."
        return
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: registrar {entities['hours']}h en {project.name}. "
            f"Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "log_hours",
            "project_id": project.id,
            "project_name": project.name,
            "hours": float(entities["hours"]),
        }
        return
    imp = Imputation(
        user_id=current_user.id, project_id=project.id,
        hours=float(entities["hours"]),
        date=date.today(),
        description=f"Imputado por voz: {transcript[:100]}",
        is_billable=True,
    )
    db.add(imp)
    result["action"] = f"✓ Registradas {entities['hours']}h en {project.name}"


def _voice_handle_create_ticket(db, current_user, entities: dict,
                                confirm: bool, result: dict) -> None:
    """Handler para intent ``create_ticket``. Muta ``result`` in place."""
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: crear ticket '{entities['ticket_title']}'. Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "create_ticket",
            "title": entities["ticket_title"],
            "priority": entities.get("priority", "medium"),
        }
        return
    ticket = Ticket(
        title=entities["ticket_title"],
        priority=entities.get("priority", "medium"),
        status="open",
        requester_user_id=current_user.id,
    )
    db.add(ticket); db.flush()
    result["action"] = f"✓ Ticket creado: {ticket.title}"


def _voice_handle_query_hours(db, current_user, result: dict) -> None:
    """Handler para intent ``query_hours`` (sólo lectura, no requiere confirm)."""
    week_start = (date.today() - timedelta(days=date.today().weekday()))
    hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == current_user.id,
        Imputation.date >= week_start,
    ).scalar() or 0
    result["action"] = f"Esta semana llevas {round(hours, 1)} horas imputadas."


def _voice_handle_create_task(db, current_user, entities: dict, project,
                              confirm: bool, result: dict) -> None:
    """Handler para intent ``create_task``. Muta ``result`` in place."""
    if not confirm:
        result["action"] = (
            f"⏳ Propuesta: crear tarea '{entities['task_name']}'"
            + (f" en {project.name}" if project else "")
            + ". Confirma para ejecutar."
        )
        result["pending_action"] = {
            "type": "create_task",
            "title": entities["task_name"][:255],
            "project_id": project.id if project else None,
            "project_name": project.name if project else None,
            "priority": entities.get("priority", "medium"),
        }
        return
    task = Task(
        title=entities["task_name"][:255],
        project_id=project.id if project else None,
        status="todo",
        priority=entities.get("priority", "medium"),
        created_by=current_user.id,
    )
    db.add(task); db.flush()
    result["action"] = f"✓ Tarea creada: {task.title}"
    if project:
        result["action"] += f" en {project.name}"


def _voice_handle_get_summary(db, entities: dict, result: dict) -> None:
    """Handler para intent ``get_summary`` (sólo lectura)."""
    project = db.query(Project).filter(
        Project.name.ilike(f"%{entities['project_name']}%")
    ).first()
    if project:
        tasks = db.query(Task).filter(Task.project_id == project.id).all()
        done = sum(1 for t in tasks if t.status == "done")
        open_tasks = sum(1 for t in tasks if t.status != "done")
        result["action"] = (
            f"Proyecto '{project.name}': {round(done / max(len(tasks), 1) * 100)}% completado, "
            f"{open_tasks} tareas pendientes, estado: {project.status}."
        )
    else:
        result["action"] = f"No encontré el proyecto '{entities['project_name']}'."


def _voice_handle_other(db, current_user, transcript: str, result: dict) -> None:
    """Handler para intent ``other`` (>20 chars): dispara agente async."""
    exec_record = _ExecRecord(
        user_id=current_user.id,
        instruction=transcript,
        status="queued",
    )
    db.add(exec_record); db.flush()
    run_agent_task.delay(str(exec_record.id), transcript, str(current_user.id))
    result["action"] = (
        f"Comando enviado al agente (ID: {str(exec_record.id)[:8]}). "
        "Revisa el historial de ContecflowAgent para el resultado."
    )
    result["execution_id"] = str(exec_record.id)


def process_voice_core(transcript: str, db, current_user,
                       *, confirm: bool = False) -> dict:
    """Shared voice command processing logic.

    Modo "dry-run" (``confirm=False``, default): el LLM extrae intent +
    entities, busca el target (project/task), pero NO ejecuta la acción.
    Devuelve un resumen para que el cliente muestre confirmación humana.

    Modo "confirm" (``confirm=True``): ejecuta la acción sugerida.

    Antes este servicio ejecutaba directamente — un Whisper que
    transcribiera mal "3h" → "30h" registraba 30h sin confirmación.

    Refactor #25: extracción a helpers ``_voice_*`` por intent para reducir
    complejidad ciclomática (de >15 a ~6).
    """
    t0 = time.time()
    status = "done"

    intent, entities, action_taken = _voice_parse_intent(db, transcript, current_user)

    result: dict = {
        "intent": intent, "entities": entities, "action": action_taken,
        "confirmed": confirm,
    }

    # Multi-tenant: limitar matching de proyectos a la org del current_user
    cu_org = getattr(current_user, "organization_id", None)
    is_super_cu = bool(getattr(current_user, "is_superadmin", False))

    if intent == "log_hours" and entities.get("hours") and entities.get("project_name"):
        project = _voice_find_project_scoped(db, entities['project_name'], cu_org, is_super_cu)
        _voice_handle_log_hours(db, current_user, transcript, entities, project, confirm, result)
    elif intent == "create_ticket" and entities.get("ticket_title"):
        _voice_handle_create_ticket(db, current_user, entities, confirm, result)
    elif intent == "query_hours":
        _voice_handle_query_hours(db, current_user, result)
    elif intent == "create_task" and entities.get("task_name"):
        project = None
        if entities.get("project_name"):
            project = _voice_find_project_scoped(db, entities['project_name'], cu_org, is_super_cu)
        _voice_handle_create_task(db, current_user, entities, project, confirm, result)
    elif intent == "get_summary" and entities.get("project_name"):
        _voice_handle_get_summary(db, entities, result)
    elif intent == "other" and len(transcript.strip()) > 20:
        _voice_handle_other(db, current_user, transcript, result)

    latency = int((time.time() - t0) * 1000)
    vc = AIVoiceCommand(
        user_id=current_user.id,
        transcript=transcript,
        intent=intent,
        entities=json.dumps(entities),
        action_taken=result.get("action", ""),
        status=status,
    )
    db.add(vc)
    log_action(db, current_user.id, "voice", "command", transcript[:200],
               result.get("action", ""), latency=latency)
    db.commit()

    return {
        "transcript": transcript,
        "intent": intent,
        "entities": entities,
        "action": result.get("action", action_taken),
        "status": status,
        "latency_ms": latency,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT PORTAL AI
# ═══════════════════════════════════════════════════════════════════════════════

def get_client_project_data(client_user, db: Session) -> dict:
    """Get sanitized project data for client portal.

    Multi-tenant fix: filtra por la organización del cliente cuando existe,
    además del fuzzy ``ilike`` por ``client_name``. Antes el fuzzy podía
    matchear proyectos de otra organización con cliente de nombre parecido.
    """
    company = getattr(client_user, "company", "") or ""
    org_id  = getattr(client_user, "organization_id", None)

    q = db.query(Project).filter(Project.client_name.ilike(f"%{company}%"))
    if org_id:
        q = q.filter(Project.organization_id == org_id)
    projects = q.limit(5).all()

    result = []
    for p in projects:
        tasks = db.query(Task).filter(Task.project_id == p.id).all()
        done  = sum(1 for t in tasks if t.status == "done")
        result.append({
            "name": p.name, "status": p.status,
            "progress_pct": round(done / max(len(tasks), 1) * 100),
            "start_date": str(p.start_date) if p.start_date else None,
            "end_date": str(p.end_date_planned) if p.end_date_planned else None,
            "open_tasks": sum(1 for t in tasks if t.status != "done"),
        })
    return {"projects": result}


def client_demo_response(message: str, project_data: dict) -> str:
    # Items #72/#73: mensajes agnósticos al proveedor. Antes hardcoded a
    # ANTHROPIC_API_KEY — engañoso si la empresa usa Gemini/OpenAI/Mistral.
    projects = project_data.get("projects", [])
    if projects:
        p = projects[0]
        return (f"Su proyecto **{p['name']}** tiene un progreso del {p['progress_pct']}% "
                f"con {p['open_tasks']} tareas pendientes. "
                "Para análisis detallado, configura un proveedor IA en *IA & Conectores*.")
    return ("Hola, soy el asistente del portal. Configura un proveedor IA en "
            "*IA & Conectores* para respuestas completas.")


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRUN PREDICTION
# ═══════════════════════════════════════════════════════════════════════════════

def predict_overrun_ml(
    cpi: float, spi: float,
    budget_used_pct: float, elapsed_pct: float,
    task_completion_pct: float,
    overdue_task_ratio: float,
    team_load_pct: float,
) -> dict:
    """
    Heuristic ensemble model for overrun prediction.
    Returns probabilities, magnitudes, confidence, signals, and recommendation.
    """
    signals = []
    cost_score = 0.0
    sched_score = 0.0

    if cpi < 0.7:
        cost_score += 0.45
        signals.append({"signal": "CPI crítico", "value": round(cpi, 2), "weight": 0.45, "type": "cost"})
    elif cpi < 0.85:
        cost_score += 0.25
        signals.append({"signal": "CPI bajo", "value": round(cpi, 2), "weight": 0.25, "type": "cost"})
    elif cpi < 1.0:
        cost_score += 0.10
        signals.append({"signal": "CPI ligeramente bajo", "value": round(cpi, 2), "weight": 0.10, "type": "cost"})

    if spi < 0.65:
        sched_score += 0.5
        signals.append({"signal": "SPI crítico (muy retrasado)", "value": round(spi, 2), "weight": 0.5, "type": "schedule"})
    elif spi < 0.8:
        sched_score += 0.3
        signals.append({"signal": "SPI bajo", "value": round(spi, 2), "weight": 0.3, "type": "schedule"})
    elif spi < 0.95:
        sched_score += 0.15
        signals.append({"signal": "SPI moderadamente bajo", "value": round(spi, 2), "weight": 0.15, "type": "schedule"})

    burn_delta = budget_used_pct - elapsed_pct
    if burn_delta > 20:
        cost_score += 0.3
        signals.append({"signal": "Quema de presupuesto avanzada vs tiempo", "value": round(burn_delta, 1), "weight": 0.3, "type": "cost"})
    elif burn_delta > 10:
        cost_score += 0.15
        signals.append({"signal": "Quema de presupuesto algo elevada", "value": round(burn_delta, 1), "weight": 0.15, "type": "cost"})

    completion_gap = elapsed_pct - task_completion_pct
    if completion_gap > 25:
        sched_score += 0.35
        signals.append({"signal": "Tareas retrasadas respecto al avance temporal", "value": round(completion_gap, 1), "weight": 0.35, "type": "schedule"})
    elif completion_gap > 10:
        sched_score += 0.15
        signals.append({"signal": "Leve retraso en finalización de tareas", "value": round(completion_gap, 1), "weight": 0.15, "type": "schedule"})

    if overdue_task_ratio > 0.4:
        sched_score += 0.25
        cost_score  += 0.1
        signals.append({"signal": "Alto porcentaje de tareas vencidas", "value": f"{overdue_task_ratio*100:.0f}%", "weight": 0.25, "type": "both"})
    elif overdue_task_ratio > 0.2:
        sched_score += 0.1
        signals.append({"signal": "Tareas vencidas moderadas", "value": f"{overdue_task_ratio*100:.0f}%", "weight": 0.1, "type": "schedule"})

    if team_load_pct > 110:
        cost_score  += 0.15
        sched_score += 0.2
        signals.append({"signal": "Equipo sobrecargado (burnout risk)", "value": f"{team_load_pct:.0f}%", "weight": 0.15, "type": "both"})

    cost_prob  = min(round(cost_score,  2), 0.97)
    sched_prob = min(round(sched_score, 2), 0.97)

    cost_overrun_pct = 0.0
    if cpi > 0 and cpi < 1:
        cost_overrun_pct = round((1 / cpi - 1) * 100 * budget_used_pct / 100, 1)

    sched_overrun_days = 0
    if spi > 0 and spi < 1:
        sched_overrun_days = max(0, int((1 / spi - 1) * 30))

    n_signals = len(signals)
    confidence = "high" if n_signals >= 4 else ("medium" if n_signals >= 2 else "low")

    if cost_prob > 0.6 and sched_prob > 0.6:
        rec = "Revisión ejecutiva urgente: alto riesgo de sobrecosto y retraso. Considera replanning o recorte de alcance."
    elif cost_prob > 0.5:
        rec = "Revisar coste: CPI bajo indica gasto mayor que lo planificado. Optimiza asignaciones."
    elif sched_prob > 0.5:
        rec = "Revisar cronograma: SPI bajo y tareas vencidas. Considera aumentar capacidad o reducir alcance."
    elif cost_prob + sched_prob < 0.3:
        rec = "Proyecto dentro de parámetros normales. Mantén el seguimiento semanal."
    else:
        rec = "Señales de alerta moderadas. Monitorea KPIs semana a semana."

    return {
        "cost_overrun_prob":     cost_prob,
        "schedule_overrun_prob": sched_prob,
        "cost_overrun_pct":      cost_overrun_pct,
        "schedule_overrun_days": sched_overrun_days,
        "confidence":            confidence,
        "signals":               signals,
        "recommendation":        rec,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def list_predictions(db: Session, severity=None, prediction_type=None, only_unacked: bool = True):
    q = db.query(AIPrediction)
    if severity:        q = q.filter(AIPrediction.severity == severity)
    if prediction_type: q = q.filter(AIPrediction.prediction_type == prediction_type)
    if only_unacked:    q = q.filter(AIPrediction.is_acknowledged == False)
    preds = q.order_by(AIPrediction.created_at.desc()).limit(50).all()
    return [{
        "id": p.id, "type": p.prediction_type, "severity": p.severity,
        "title": p.title, "explanation": p.explanation,
        "recommended_action": p.recommended_action,
        "probability": p.probability, "entity_type": p.entity_type,
        "entity_id": p.entity_id, "created_at": str(p.created_at)[:16],
        "methodology": "rules_based",
    } for p in preds]


def acknowledge_prediction(db: Session, pred_id: str, user_id: str) -> dict:
    pred = db.query(AIPrediction).filter(AIPrediction.id == pred_id).first()
    if not pred:
        raise ValueError("not_found")
    pred.is_acknowledged = True
    pred.acknowledged_by = user_id
    pred.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# MEETINGS
# ═══════════════════════════════════════════════════════════════════════════════

def list_meetings(db: Session, project_id=None):
    q = db.query(AIMeeting).options(joinedload(AIMeeting.actions))
    if project_id: q = q.filter(AIMeeting.project_id == project_id)
    meetings = q.order_by(AIMeeting.created_at.desc()).limit(50).all()
    return [{
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "status": m.status,
        "actions_count": len(m.actions),
        "created_actions": sum(1 for a in m.actions if a.is_created),
        "meeting_date": str(m.meeting_date)[:16] if m.meeting_date else None,
        "created_at": str(m.created_at)[:16],
    } for m in meetings]


def process_meeting(db: Session, payload, current_user) -> dict:
    import re

    t0 = time.time()
    # Item #68: registramos el tamaño original para trazabilidad de citas.
    # El campo ``transcript`` truncamos a 50K para no inflar la DB, pero el
    # análisis LLM (map-reduce) puede usar más; guardamos ``original_length``
    # y un flag ``truncated`` para que ``original_text`` en respuestas LLM se
    # pueda re-referenciar al transcript completo si el caller lo necesita.
    _full_transcript = payload.transcript or ""
    _was_truncated = len(_full_transcript) > 50000
    meeting = AIMeeting(
        project_id=payload.project_id,
        title=payload.title or "Reunión procesada por IA",
        platform=payload.platform,
        duration_min=payload.duration_min,
        participants=json.dumps(payload.participants or []),
        transcript=_full_transcript[:50000],
        status="processing",
        created_by=current_user.id,
    )
    # Anotamos en summary la truncación si aplica (se sobreescribe luego con el
    # resumen del LLM, pero queda en el log/audit que hubo truncación).
    if _was_truncated:
        meeting.summary = (
            f"[TRUNCADO: transcripción original {len(_full_transcript)} chars, "
            f"guardados primeros 50000. Para audit completo consulta el original.]"
        )
    if payload.meeting_date:
        try:
            meeting.meeting_date = datetime.fromisoformat(payload.meeting_date)
        except ValueError:
            raise ValueError("invalid_meeting_date")
    db.add(meeting); db.commit(); db.refresh(meeting)

    try:
        MAP_SYSTEM = (
            "Eres un asistente experto en análisis de reuniones de trabajo. "
            "Analiza el texto dado y extrae puntos clave: decisiones, acciones, riesgos."
        )
        REDUCE_SYSTEM = MAP_SYSTEM
        MAP_PREFIX = "Analiza este fragmento de transcripción de reunión:"
        REDUCE_SUFFIX = """Basándote en el análisis anterior, genera el informe final completo.

Responde SOLO con JSON:
{
  "title": "...",
  "summary": "...",
  "decisions": ["...", "..."],
  "actions": [{"description": "...", "assignee_name": "...", "due_date_text": "..."}],
  "risks": ["...", "..."]
}"""
        text = map_reduce_analysis(
            payload.transcript,
            map_system=MAP_SYSTEM, map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM, reduce_user_suffix=REDUCE_SUFFIX,
            db=db, module="meeting_assistant", user_id=current_user.id,
            map_tokens=1500, reduce_tokens=2000,
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            # Hardening: el LLM puede devolver JSON casi-bien (trailing comma,
            # comilla simple, texto adicional). Antes una sola coma arrastrada
            # rompía toda la persistencia del meeting → caía al except y se
            # guardaba "Error procesando con IA".
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())  # trailing commas
                data = json.loads(_cleaned)
            meeting.title   = data.get("title", meeting.title)
            meeting.summary = data.get("summary")
            meeting.decisions = json.dumps(data.get("decisions", []))
            meeting.risks_mentioned = json.dumps(data.get("risks", []))
            for action_data in data.get("actions", []):
                action = AIMeetingAction(
                    meeting_id=meeting.id,
                    description=action_data.get("description", ""),
                    assignee_name=action_data.get("assignee_name"),
                    due_date_text=action_data.get("due_date_text"),
                )
                if action_data.get("assignee_name"):
                    # Multi-tenant fix: limitar matching a usuarios de la
                    # organización del current_user. Sin este filtro un
                    # "Juan" en el transcript podía resolverse a Juan
                    # cualquiera de cualquier organización.
                    user_q = db.query(User).filter(
                        User.full_name.ilike(f"%{action_data['assignee_name']}%")
                    )
                    cu_org = getattr(current_user, "organization_id", None)
                    if cu_org and not bool(getattr(current_user, "is_superadmin", False)):
                        user_q = user_q.filter(User.organization_id == cu_org)
                    user = user_q.first()
                    if user: action.assignee_id = user.id
                db.add(action)
        meeting.status = "done"
    except Exception as e:
        _log.exception("Meeting assistant processing failed for meeting=%s", getattr(meeting, "id", None))
        meeting.summary = f"Error procesando con IA: {str(e)[:100]}"
        meeting.status = "failed"

    latency = int((time.time() - t0) * 1000)
    log_action(db, current_user.id, "meeting_assistant", "process",
               f"transcript_len={len(payload.transcript)}", meeting.summary, latency=latency)
    db.commit(); db.refresh(meeting)

    return {
        "meeting_id": meeting.id, "title": meeting.title, "summary": meeting.summary,
        "decisions": json.loads(meeting.decisions or "[]"),
        "risks": json.loads(meeting.risks_mentioned or "[]"),
        "actions": [{"id": a.id, "description": a.description,
                     "assignee_name": a.assignee_name,
                     "due_date_text": a.due_date_text} for a in meeting.actions],
        "status": meeting.status, "latency_ms": latency,
    }


def create_tasks_from_meeting(db: Session, meeting_id: str, payload: dict, current_user) -> dict:

    meeting = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not meeting:
        raise ValueError("not_found")
    project_id = payload.get("project_id") or meeting.project_id
    if not project_id:
        raise ValueError("project_id_required")
    action_ids = payload.get("action_ids", [a.id for a in meeting.actions])
    created = []
    for action in meeting.actions:
        if action.id not in action_ids or action.is_created: continue
        task = Task(
            project_id=project_id, title=action.description[:255],
            status="todo", priority="medium",
            assignee_id=action.assignee_id, created_by=current_user.id,
        )
        db.add(task); db.flush()
        action.task_id = task.id
        action.is_created = True
        created.append({"action_id": action.id, "task_id": task.id, "title": task.title})
    db.commit()
    return {"ok": True, "tasks_created": len(created), "tasks": created}


def get_meeting(db: Session, meeting_id: str) -> dict:

    m = db.query(AIMeeting).options(joinedload(AIMeeting.actions)).filter(
        AIMeeting.id == meeting_id
    ).first()
    if not m:
        raise ValueError("not_found")
    return {
        "id": m.id, "title": m.title, "project_id": m.project_id,
        "platform": m.platform, "duration_min": m.duration_min,
        "summary": m.summary,
        "decisions": json.loads(m.decisions or "[]"),
        "risks": json.loads(m.risks_mentioned or "[]"),
        "participants": json.loads(m.participants or "[]"),
        "status": m.status,
        "actions": [{
            "id": a.id, "description": a.description,
            "assignee_name": a.assignee_name, "assignee_id": a.assignee_id,
            "due_date_text": a.due_date_text, "is_created": a.is_created,
            "task_id": a.task_id,
        } for a in m.actions],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AI CONTRACT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

def list_ai_contracts(db: Session, project_id=None, current_user=None):
    # H22: filtro multi-tenant — los AIContract sin project_id (textos pegados
    # ad-hoc) se filtran por created_by; los enlazados a project se filtran
    # vía Project.organization_id. Superadmin sin filtro.
    q = db.query(AIContract).options(joinedload(AIContract.clauses))
    if project_id:
        q = q.filter(AIContract.project_id == project_id)
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_org = getattr(current_user, "organization_id", None)
        cu_id  = getattr(current_user, "id", None)
        if cu_org:
            # AIContract ligado a project: filtrar por org del proyecto
            q_proj = q.join(Project, AIContract.project_id == Project.id).filter(
                Project.organization_id == cu_org
            )
            # AIContract ad-hoc (sin project) creado por el caller
            q_adhoc = q.filter(AIContract.project_id.is_(None), AIContract.created_by == cu_id)
            contracts = (q_proj.all() + q_adhoc.all())
            # Dedupe + sort
            seen = set()
            uniq = []
            for c in sorted(contracts, key=lambda c: c.created_at or datetime.min, reverse=True):
                if c.id in seen:
                    continue
                seen.add(c.id)
                uniq.append(c)
            contracts = uniq[:50]
        else:
            contracts = q.filter(AIContract.created_by == cu_id).order_by(
                AIContract.created_at.desc()
            ).limit(50).all()
    else:
        contracts = q.order_by(AIContract.created_at.desc()).limit(50).all()
    return [{
        "id": c.id, "client_name": c.client_name, "project_id": c.project_id,
        "filename": c.filename, "status": c.status,
        "total_value": c.total_value, "risk_level": c.risk_level,
        "scope_creep_alerts": c.scope_creep_alerts,
        "clauses_count": len(c.clauses),
        "at_risk_clauses": sum(1 for cl in c.clauses if cl.is_at_risk),
        "created_at": str(c.created_at)[:16],
    } for c in contracts]


def get_ai_contract(db: Session, contract_id: str, current_user=None) -> dict:
    """Detalle de un AIContract con todas sus cláusulas. Respeta multi-tenant."""
    contract = db.query(AIContract).options(joinedload(AIContract.clauses)).filter(
        AIContract.id == contract_id
    ).first()
    if not contract:
        return None
    # Visibility check: o eres superadmin, o lo creaste, o el project pertenece
    # a tu org.
    if current_user is not None and not bool(getattr(current_user, "is_superadmin", False)):
        cu_id  = getattr(current_user, "id", None)
        cu_org = getattr(current_user, "organization_id", None)
        allowed = False
        if contract.created_by and contract.created_by == cu_id:
            allowed = True
        elif contract.project_id and cu_org:
            proj = db.query(Project).filter(Project.id == contract.project_id).first()
            if proj and getattr(proj, "organization_id", None) == cu_org:
                allowed = True
        if not allowed:
            return None
    return {
        "id": contract.id,
        "client_name": contract.client_name,
        "project_id": contract.project_id,
        "filename": contract.filename,
        "status": contract.status,
        "total_value": contract.total_value,
        "scope_summary": contract.scope_summary,
        "risk_level": contract.risk_level,
        "scope_creep_alerts": contract.scope_creep_alerts,
        "created_at": str(contract.created_at)[:16],
        "clauses": [{
            "id": cl.id,
            "clause_type": cl.clause_type,
            "title": cl.title,
            "description": cl.description,
            "original_text": cl.original_text,
            "impact_amount": cl.impact_amount,
            "due_date": str(cl.due_date)[:10] if cl.due_date else None,
            "is_at_risk": cl.is_at_risk,
            "risk_reason": cl.risk_reason,
        } for cl in contract.clauses],
    }


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extrae texto plano de un PDF (pypdf). Devuelve "" si falla."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415
        from io import BytesIO  # noqa: PLC0415
        reader = PdfReader(BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                _log.debug("PDF page extract_text failed, skipping page", exc_info=True)
                continue
        return "\n\n".join(chunks).strip()
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("PDF extraction failed: %s", exc)
        return ""


def analyze_contract(db: Session, payload, current_user) -> dict:
    import re

    t0 = time.time()
    # Item #69: registramos truncación. El LLM analiza ``contract_text``
    # completo vía map-reduce; en DB solo guardamos los primeros 20K para no
    # inflar la tabla. Si el contrato es más largo, anotamos el tamaño
    # original en ``scope_summary`` (queda registrado aunque el LLM falle).
    _full_contract = payload.contract_text or ""
    _was_truncated = len(_full_contract) > 20000
    contract = AIContract(
        project_id=payload.project_id,
        client_name=payload.client_name,
        filename=payload.filename,
        file_content=_full_contract[:20000],
        status="analyzing",
        created_by=current_user.id,
    )
    if _was_truncated:
        contract.scope_summary = (
            f"[TRUNCADO: contrato original {len(_full_contract)} chars; "
            f"guardados primeros 20000. Citas LLM pueden referirse a partes no persistidas.]"
        )
    db.add(contract); db.commit(); db.refresh(contract)

    try:
        MAP_SYSTEM = (
            "Eres un experto en análisis de contratos de servicios profesionales. "
            "Analiza el fragmento dado y extrae cláusulas relevantes, penalizaciones, "
            "entregables, hitos de pago, SLAs, terminación y riesgos."
        )
        REDUCE_SYSTEM = MAP_SYSTEM
        MAP_PREFIX = "Analiza este fragmento del contrato:"
        REDUCE_SUFFIX = """Basándote en el análisis anterior del contrato completo, genera el informe consolidado.

Responde SOLO con JSON:
{
  "total_value": 0.0,
  "scope_summary": "...",
  "risk_level": "medium",
  "clauses": [
    {"type": "deliverable|penalty|milestone|sla|termination|payment|scope",
     "title": "...", "description": "...", "original_text": "...",
     "impact_amount": null, "due_date": null, "is_at_risk": false, "risk_reason": null}
  ]
}"""
        text = map_reduce_analysis(
            payload.contract_text,
            map_system=MAP_SYSTEM, map_user_prefix=MAP_PREFIX,
            reduce_system=REDUCE_SYSTEM, reduce_user_suffix=REDUCE_SUFFIX,
            db=db, module="contract_intelligence", user_id=current_user.id,
            map_tokens=1500, reduce_tokens=3000,
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())
                data = json.loads(_cleaned)
            contract.total_value   = data.get("total_value")
            contract.scope_summary = data.get("scope_summary")
            contract.risk_level    = data.get("risk_level", "medium")
            at_risk = 0
            for cl_data in data.get("clauses", []):
                cl = AIContractClause(
                    contract_id=contract.id,
                    clause_type=cl_data.get("type", "scope"),
                    title=cl_data.get("title", "")[:255],
                    description=cl_data.get("description"),
                    original_text=cl_data.get("original_text"),
                    impact_amount=cl_data.get("impact_amount"),
                    is_at_risk=cl_data.get("is_at_risk", False),
                    risk_reason=cl_data.get("risk_reason"),
                )
                if cl_data.get("due_date"):
                    try:
                        cl.due_date = datetime.fromisoformat(cl_data["due_date"])
                    except ValueError:
                        _log.warning(f"Invalid due_date in contract clause: {cl_data.get('due_date')}")
                db.add(cl)
                if cl.is_at_risk: at_risk += 1
            contract.scope_creep_alerts = at_risk
        contract.status = "done"
    except Exception as e:
        _log.exception("Contract intelligence analysis failed for contract=%s", getattr(contract, "id", None))
        contract.scope_summary = f"Error: {str(e)[:100]}"
        contract.status = "failed"

    latency = int((time.time() - t0) * 1000)
    log_action(db, current_user.id, "contract_intelligence", "analyze",
               f"contract_len={len(payload.contract_text)}", f"risk={contract.risk_level}",
               latency=latency)
    db.commit(); db.refresh(contract)

    return {
        "contract_id": contract.id, "status": contract.status,
        "risk_level": contract.risk_level, "scope_summary": contract.scope_summary,
        "total_value": contract.total_value,
        "clauses_count": len(contract.clauses),
        "at_risk_clauses": contract.scope_creep_alerts, "latency_ms": latency,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def list_kb(db: Session, published_only: bool = False, category=None):
    q = db.query(AIKBArticle)
    if published_only: q = q.filter(AIKBArticle.is_published == True)
    if category:       q = q.filter(AIKBArticle.category == category)
    articles = q.order_by(AIKBArticle.created_at.desc()).limit(100).all()
    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "tags": json.loads(a.tags or "[]"),
        "view_count": a.view_count, "helpful_votes": a.helpful_votes,
        "is_published": a.is_published, "is_ai_generated": a.is_ai_generated,
        "source_ticket_id": a.source_ticket_id,
        "created_at": str(a.created_at)[:10],
    } for a in articles]


def generate_kb_from_ticket(db: Session, ticket_id: str, current_user) -> dict:
    import re

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ValueError("not_found")

    title   = f"Cómo resolver: {ticket.title}"
    content = ""
    tags    = []

    try:
        prompt = f"""Crea un artículo de base de conocimiento profesional basado en este ticket de soporte resuelto.

Título del ticket: {ticket.title}
Descripción: {ticket.description or 'Sin descripción'}
Categoría: {ticket.ticket_type or 'General'}
Prioridad: {ticket.priority or 'medium'}

Responde SOLO con JSON:
{{
  "title": "Cómo [resolver/configurar/solucionar] ...",
  "content": "## Síntoma\\n...\\n## Causa\\n...\\n## Solución\\n...\\n## Pasos\\n1. ...\\n## Verificación\\n...",
  "tags": ["tag1", "tag2"],
  "category": "..."
}}"""
        text = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="knowledge_base", user_id=current_user.id, max_tokens=1500
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())
                data = json.loads(_cleaned)
            title   = data.get("title", title)
            content = data.get("content", "")
            tags    = data.get("tags", [])
    except Exception as e:
        _log.exception("KB article generation failed for title=%s", title)
        content = f"Error generando artículo: {str(e)[:100]}"

    article = AIKBArticle(
        source_ticket_id=ticket_id, title=title, content=content,
        tags=json.dumps(tags), category=ticket.ticket_type or "General",
        is_ai_generated=True, is_published=False,
    )
    db.add(article)
    log_action(db, current_user.id, "knowledge_base", "generate_from_ticket",
               f"ticket={ticket_id}", f"title={title}")
    db.commit(); db.refresh(article)
    compute_kb_embedding(db, article.id, title + " " + (content or ""))
    return {"article_id": article.id, "title": article.title, "is_published": article.is_published}


def search_kb(db: Session, query: str) -> list:

    articles = kb_vector_search(db, query, limit=10)
    if not articles:
        articles = db.query(AIKBArticle).filter(
            AIKBArticle.is_published == True,
            or_(
                AIKBArticle.title.ilike(f"%{query}%"),
                AIKBArticle.content.ilike(f"%{query}%"),
            )
        ).limit(10).all()

    for a in articles:
        a.view_count = (a.view_count or 0) + 1
    db.commit()

    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "content_preview": a.content[:300] if a.content else "",
        "tags": json.loads(a.tags or "[]"),
    } for a in articles]


def rebuild_kb_embeddings(db: Session) -> dict:
    articles = db.query(AIKBArticle).all()
    count = 0
    for a in articles:
        compute_kb_embedding(db, a.id, (a.title or "") + " " + (a.content or ""))
        count += 1
    return {"rebuilt": count}


def update_kb(db: Session, article_id: str, payload: dict, current_user) -> dict:
    article = db.query(AIKBArticle).filter(AIKBArticle.id == article_id).first()
    if not article:
        raise ValueError("not_found")
    for field in ["title", "content", "category", "is_published"]:
        if field in payload: setattr(article, field, payload[field])
    if "tags" in payload: article.tags = json.dumps(payload["tags"])
    if payload.get("is_published"): article.reviewed_by = current_user.id
    db.commit()
    if "title" in payload or "content" in payload:
        compute_kb_embedding(db, article.id, article.title + " " + (article.content or ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT PORTAL CHAT
# ═══════════════════════════════════════════════════════════════════════════════

_CLIENT_AI_SYSTEM = """Eres el asistente de IA del portal de cliente de Contecflow.
Ayudas a los clientes a entender el estado de sus proyectos de forma clara y profesional.
IMPORTANTE: Solo tienes acceso a los datos del proyecto del cliente. Nunca reveles información de otros clientes,
datos financieros internos (márgenes, costes internos) ni información confidencial del equipo.
Responde siempre en el idioma del cliente. Sé transparente y profesional.
Datos disponibles del proyecto:
{project_data}"""


def client_portal_chat(db: Session, payload: dict) -> dict:

    client_token = payload.get("client_token")
    message      = payload.get("message", "")
    session_id   = payload.get("session_id")

    if not client_token or not message:
        raise ValueError("missing_fields")

    try:
        client_user = verify_client_token(client_token, db)
    except Exception:
        _log.warning("Client portal chat: invalid client token presented", exc_info=True)
        raise ValueError("invalid_token")

    if not client_user:
        raise ValueError("invalid_token")

    return _client_portal_chat_for_user(db, client_user, message, session_id)


def client_portal_chat_authenticated(db: Session, client_user, message: str, session_id: str | None = None) -> dict:
    """Variante del chat del portal que recibe el ``client_user`` ya autenticado
    (vía cookie portal en el endpoint). Reusa toda la lógica de sesión, history
    y guardrails. Se añadió para I26 — el widget flotante en el portal usa
    autenticación por cookie httponly, que no es legible desde JS, así que no
    podemos pasar el JWT como ``client_token`` en el body.
    """
    if not message:
        raise ValueError("missing_fields")
    if not client_user:
        raise ValueError("invalid_token")
    return _client_portal_chat_for_user(db, client_user, message, session_id)


def _client_portal_chat_for_user(db: Session, client_user, message: str, session_id: str | None) -> dict:
    session = None
    if session_id:
        session = db.query(AIClientChatSession).filter(
            AIClientChatSession.id == session_id,
            AIClientChatSession.client_user_id == client_user.id,
        ).first()
    if not session:
        session = AIClientChatSession(client_user_id=client_user.id)
        db.add(session); db.flush()

    project_data = get_client_project_data(client_user, db)

    db.add(AIClientChatMessage(session_id=session.id, role="user", content=message))

    history = db.query(AIClientChatMessage).filter(
        AIClientChatMessage.session_id == session.id
    ).order_by(AIClientChatMessage.created_at.desc()).limit(8).all()
    history.reverse()

    messages = [{"role": m.role, "content": m.content} for m in history[:-1]]
    messages.append({"role": "user", "content": message})

    system = _CLIENT_AI_SYSTEM.format(project_data=json.dumps(project_data, ensure_ascii=False))

    try:
        response_text = call_ai_unified(
            db, messages, system=system,
            module="client_portal", max_tokens=800
        )
    except Exception as e:
        _log.exception("Client portal chat AI call failed for session=%s", getattr(session, "id", None))
        response_text = f"Error del asistente: {str(e)[:80]}"

    db.add(AIClientChatMessage(session_id=session.id, role="assistant", content=response_text))
    db.commit()

    return {"session_id": session.id, "response": response_text}


def list_client_chat_messages(db: Session, client_user, session_id: str, limit: int = 50) -> list:
    """Lee historial de mensajes de una sesión, verificando ownership. Útil
    para que el widget muestre la conversación al reabrirlo."""
    session = db.query(AIClientChatSession).filter(
        AIClientChatSession.id == session_id,
        AIClientChatSession.client_user_id == client_user.id,
    ).first()
    if not session:
        return []
    msgs = db.query(AIClientChatMessage).filter(
        AIClientChatMessage.session_id == session.id
    ).order_by(AIClientChatMessage.created_at.asc()).limit(limit).all()
    return [{
        "role": m.role,
        "content": m.content,
        "created_at": str(m.created_at)[:16],
    } for m in msgs]


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE FORECAST
# ═══════════════════════════════════════════════════════════════════════════════

def revenue_forecast(db: Session, months_ahead: int = 3) -> dict:
    """Revenue forecast con regresión lineal OLS sobre facturas históricas.

    Bug histórico corregido:
      - El import era ``app.models.invoicing.Invoice`` (módulo inexistente)
        → siempre caía al except y usaba ``hours × 85€`` hardcoded como
        proxy. Ahora importa desde ``app.models.billing_reports``.
      - ``func.date_trunc('month', ...)`` solo funciona en Postgres. En
        SQLite el query rompía. Sustituido por extracción YYYY-MM en
        Python para compatibilidad dialect-agnóstica.
    """
    from app.models.billing_reports import Invoice  # noqa: PLC0415

    now   = datetime.utcnow()
    start = (now.replace(day=1) - timedelta(days=365)).replace(day=1)
    history: list[dict] = []

    try:
        invoices = (
            db.query(Invoice.issue_date, Invoice.total)
            .filter(Invoice.issue_date >= start.date(),
                    Invoice.status != "cancelled")
            .all()
        )
        # Agrupar por YYYY-MM en Python (dialect-agnóstico)
        agg: dict[str, float] = {}
        for issue_date, total in invoices:
            if not issue_date:
                continue
            key = issue_date.strftime("%Y-%m") if hasattr(issue_date, "strftime") else str(issue_date)[:7]
            agg[key] = agg.get(key, 0.0) + float(total or 0)
        history = [{"month": k, "amount": v} for k, v in sorted(agg.items())]
    except Exception as exc:
        _log.warning("Invoice-based revenue forecast unavailable (%s); using hours fallback", exc)
        # Fallback: usa imputaciones × tarifa horaria como proxy. NOTA: la
        # tarifa 85 €/h es una estimación grosera. Si tu empresa tiene
        # tarifa distinta, configurar AI_REVENUE_HOURLY_RATE_FALLBACK.
        imp_rows = (
            db.query(Imputation.date, Imputation.hours)
            .filter(Imputation.date >= start.date())
            .all()
        )
        rate = float(getattr(settings, "AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0) or 85.0)
        agg = {}
        for imp_date, hours in imp_rows:
            if not imp_date:
                continue
            key = imp_date.strftime("%Y-%m") if hasattr(imp_date, "strftime") else str(imp_date)[:7]
            agg[key] = agg.get(key, 0.0) + float(hours or 0) * rate
        history = [{"month": k, "amount": v} for k, v in sorted(agg.items())]

    if len(history) < 3:
        return {"error": "Insufficient data", "message": "Need at least 3 months of data", "history": history}

    n   = len(history)
    xs  = list(range(n))
    ys  = [h["amount"] for h in history]
    sx  = sum(xs);      sy  = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return {"error": "Degenerate data", "history": history}
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n

    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0

    forecast = []
    last_month_str = history[-1]["month"]
    lm_year, lm_mon = int(last_month_str[:4]), int(last_month_str[5:7])
    for i in range(1, months_ahead + 1):
        xi    = n - 1 + i
        pred  = max(0.0, a + b * xi)
        fm    = lm_mon + i
        fy    = lm_year + (fm - 1) // 12
        fm    = (fm - 1) % 12 + 1
        label = f"{fy}-{fm:02d}"
        res_std = (ss_res / max(n - 2, 1)) ** 0.5
        ci    = 1.28 * res_std
        forecast.append({"month": label, "amount": round(pred, 2),
                          "ci_low": round(max(0, pred - ci), 2),
                          "ci_high": round(pred + ci, 2)})

    return {
        "history": history, "forecast": forecast, "r2": round(r2, 4),
        "trend_monthly": round(b, 2),
        "model": "OLS linear regression (pure Python)",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SMART SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════════

def smart_schedule(db: Session, payload, current_user) -> dict:
    import re as _re
    import json as _json

    is_super = bool(getattr(current_user, "is_superadmin", False))
    user_org = None if is_super else getattr(current_user, "organization_id", None)

    # Multi-tenant: filtrar tasks por org del current_user a través de Project,
    # excepto si es superadmin. Antes leía tasks globalmente.
    q = db.query(Task).filter(Task.start_date == None, Task.due_date == None)
    if payload.project_id:
        q = q.filter(Task.project_id == payload.project_id)
    elif user_org:
        # Filtrar via join con Project.organization_id
        q = q.join(Project, Task.project_id == Project.id).filter(
            Project.organization_id == user_org
        )
    unscheduled = q.filter(Task.status.notin_(["done", "cancelled", "closed"])).limit(payload.max_tasks).all()

    if not unscheduled:
        return {"scheduled": [], "message": "No unscheduled tasks found"}

    now   = datetime.utcnow()
    w4ago = (now - timedelta(weeks=4)).date()
    capacity = []
    users_q = db.query(User).filter(User.is_active == True)
    if user_org:
        users_q = users_q.filter(User.organization_id == user_org)
    users = users_q.all()
    for u in users:
        hrs = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == u.id, Imputation.date >= w4ago
        ).scalar() or 0
        available = max(0, 40 - round(hrs / 4, 1))
        capacity.append({"name": u.full_name, "available_hours_per_week": available})

    task_list = "\n".join(
        f"- [{t.id}] {t.title} (priority={t.priority or 'medium'}, points={t.story_points or '?'})"
        for t in unscheduled
    )
    capacity_str = "\n".join(f"  {c['name']}: ~{c['available_hours_per_week']}h/week free" for c in capacity[:10])
    today_str = now.strftime("%Y-%m-%d")

    # Item #70: prompts en español (alineado con el resto del sistema).
    from app.core.config import settings as _s_for_cap  # noqa: PLC0415
    _weekly_cap = float(getattr(_s_for_cap, "DEFAULT_WEEKLY_CAPACITY_HOURS", 40.0) or 40.0)
    system = (
        "Eres una IA experta en planificación de proyectos. Recibes una lista "
        "de tareas sin fechas y la capacidad disponible del equipo. Genera un "
        "plan realista empezando hoy. "
        "Responde SOLO con un array JSON, sin texto adicional:\n"
        '[{"task_id": <int>, "suggested_start": "YYYY-MM-DD", '
        '"suggested_due": "YYYY-MM-DD", "rationale": "..."}]'
    )
    user_msg = (
        f"Hoy: {today_str}\n\n"
        f"Tareas pendientes de planificar:\n{task_list}\n\n"
        f"Capacidad del equipo (horas disponibles/semana):\n{capacity_str}\n\n"
        "Planifica las tareas teniendo en cuenta prioridad y capacidad. "
        f"Asume 1 story point ≈ 8 horas. Capacidad base {_weekly_cap:.0f}h/semana por persona."
    )

    try:
        response = call_ai_unified(db, [{"role": "user", "content": user_msg}], system=system,
                                   module="smart_schedule", user_id=current_user.id, max_tokens=2000)
        # call_ai_unified ya devuelve texto plano (call_ai dispatcher → str;
        # fallback claude → extract_text aplicado dentro). Aplicar extract_text
        # a un string vuelve a `.get(...)` y lanza AttributeError → la respuesta
        # IA se perdía silenciosamente.
        text = response if isinstance(response, str) else extract_text(response)
        match = _re.search(r'\[.*\]', text, _re.DOTALL)
        if match:
            try:
                scheduled = _json.loads(match.group(0))
            except _json.JSONDecodeError:
                _cleaned = _re.sub(r",\s*([}\]])", r"\1", match.group(0))
                scheduled = _json.loads(_cleaned)
        else:
            scheduled = []
    except Exception as exc:
        _log.exception("Smart schedule AI call failed for user=%s project=%s", current_user.id, payload.project_id)
        return {"scheduled": [], "error": str(exc),
                "message": "AI scheduling falló — configura un proveedor IA en IA & Conectores"}

    # Item #71: persistir traza de la sugerencia. Antes el LLM proponía y la
    # UI tenía que aplicar manualmente sin que quedara registro de qué
    # sugerencia se mostró. log_action deja entrada en AIActionLog (tabla
    # existente, indexada por user/module/created_at).
    try:
        log_action(
            db, current_user.id, "smart_schedule", "suggest",
            input_s=f"tasks={len(unscheduled)} project={payload.project_id or '-'}",
            output_s=json.dumps(scheduled)[:2000],
            status="success",
        )
    except Exception:
        _log.debug("Best-effort audit log_action failed for smart_schedule", exc_info=True)

    return {"scheduled": scheduled, "unscheduled_count": len(unscheduled), "capacity_summary": capacity[:10]}


# ═══════════════════════════════════════════════════════════════════════════════
# OVERRUN PREDICTION (data gathering)
# ═══════════════════════════════════════════════════════════════════════════════

def get_overrun_prediction_data(db: Session, project_id: str) -> dict:
    """Build overrun-prediction payload reutilizando ``extract_project_features``.

    Item #56: antes este código duplicaba el cálculo CPI/SPI con otras
    constantes (no usaba ``AI_REVENUE_HOURLY_RATE_FALLBACK``, no respetaba
    ``cost_amount`` correctamente). Ahora delegamos en la fuente canónica
    de features ML y solo añadimos ``project`` ORM object como conveniencia.
    """
    from app.services.ml_features import extract_project_features  # noqa: PLC0415

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("not_found")

    feats = extract_project_features(db, project_id)
    if feats is None:
        raise ValueError("no_tasks")

    return {
        "project": project,
        "cpi": feats["cpi"],
        "spi": feats["spi"],
        "budget_used_pct": feats["budget_used_pct"],
        "elapsed_pct": feats["elapsed_pct"],
        "task_completion_pct": feats["task_completion_pct"],
        "overdue_ratio": feats["overdue_ratio"],
    }
