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

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AI CALL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def api_key() -> Optional[str]:
    return settings.ANTHROPIC_API_KEY or None


def call_ai_unified(db, messages, system=None, module="v16", user_id=None, max_tokens=1000):
    """Wrapper that uses the configured provider or falls back to direct Claude."""
    try:
        return call_ai(db, messages, system=system, module=module,
                       user_id=user_id, max_tokens=max_tokens)
    except Exception:
        resp = call_claude(messages, system=system, max_tokens=max_tokens)
        return extract_text(resp)


def call_claude(messages, system=None, model=None, tools=None, max_tokens=1000):
    import urllib.request
    import json as _json
    body = {"model": model or settings.NEXUS_AI_MODEL, "max_tokens": max_tokens, "messages": messages}
    if system: body["system"] = system
    if tools:  body["tools"] = tools
    data = _json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key(),
        "anthropic-version": "2023-06-01",
    }
    req = urllib.request.Request(settings.ANTHROPIC_API_URL, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read())


def extract_text(response) -> str:
    return "\n".join(b["text"] for b in response.get("content", []) if b.get("type") == "text")


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
        pass


def log_action(db, user_id, module, action_type, input_s=None, output_s=None,
               entities=None, tokens=0, latency=0, status="success"):
    from app.models.ai_chat import AIActionLog
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

def run_oracle_analysis(db: Session, current_user) -> dict:
    """
    Runs all rule-based risk analyses and stores results as AIPrediction records.
    Returns { ok, methodology, alerts_generated, alerts, run_at }.
    """
    from app.models.project import Project
    from app.models.task import Task
    from app.models.imputation import Imputation
    from app.models.service_desk import Ticket
    from app.models.user import User
    from app.models.ai_chat import AIPrediction

    now       = datetime.now(timezone.utc)
    generated = []

    # ── 1. Project delay prediction ──────────────────────────────────────────
    projects = db.query(Project).filter(Project.status.in_(["active", "planning"])).all()
    for p in projects:
        tasks = db.query(Task).filter(Task.project_id == p.id).all()
        if not tasks:
            continue
        done    = sum(1 for t in tasks if t.status == "done")
        overdue = sum(1 for t in tasks if t.status != "done" and t.due_date and t.due_date < now.date())
        pct_done = done / len(tasks)

        hours_total = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        budget = p.budget_amount or 1
        budget_consumed_pct = (hours_total * (getattr(p, "billing_rate", 100) or 100)) / max(budget, 1)

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

        severity = "critical" if probability > 0.75 else "high" if probability > 0.5 else "medium"
        title = f"Riesgo de retraso — {p.name}"
        explanation = (
            f"El proyecto tiene {overdue} tareas vencidas de {len(tasks)} totales "
            f"({round(pct_done*100)}% completado). "
            f"Consumo de presupuesto estimado: {round(budget_consumed_pct*100)}%."
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
                }),
            )
            db.add(pred)
            generated.append({"type": "project_delay", "entity": p.name, "probability": probability})

    # ── 2. SLA breach prediction ──────────────────────────────────────────────
    open_tickets = db.query(Ticket).filter(Ticket.status.in_(["open", "in_progress"])).all()
    for t in open_tickets:
        if not t.created_at:
            continue
        created_aware = t.created_at.replace(tzinfo=timezone.utc) if t.created_at.tzinfo is None else t.created_at
        age_hours = (now - created_aware).total_seconds() / 3600
        sla_limit = {"critical": 4, "high": 8, "medium": 24, "low": 72}.get(t.priority or "medium", 24)
        if age_hours < sla_limit * 0.7:
            continue

        remaining  = sla_limit - age_hours
        probability = min(round(age_hours / sla_limit, 2), 0.99)
        severity   = "critical" if remaining < 1 else "high" if remaining < 4 else "medium"
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

    # ── 3. Burnout detection ─────────────────────────────────────────────────
    active_users = db.query(User).filter(User.is_active == True).all()
    week_starts  = [(now - timedelta(weeks=i)).date() for i in range(4)]
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
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == u.id,
            AIPrediction.prediction_type == "burnout",
            AIPrediction.is_acknowledged == False,
        ).first()
        if existing:
            existing.probability = probability
            existing.severity    = "critical" if probability > 0.75 else "high" if probability > 0.5 else "medium"
        else:
            db.add(AIPrediction(
                prediction_type="burnout", entity_type="user", entity_id=u.id,
                probability=probability,
                severity="critical" if probability > 0.75 else "high" if probability > 0.5 else "medium",
                title=f"Riesgo de burnout — {u.full_name}",
                explanation=(
                    f"Media ponderada (semanas recientes 2×): {round(avg,1)}h/sem. "
                    f"Pico: {round(max_w,1)}h.{trend_txt} "
                    f"Semanas con >42h: {sum(1 for h in weekly if h > 42)}."
                ),
                recommended_action="Revisar asignaciones. Redistribuir carga de trabajo.",
            ))
            generated.append({"type": "burnout", "entity": u.full_name, "probability": probability})

    # ── 4. Budget overrun anomaly detection ──────────────────────────────────
    for p in projects:
        if not p.budget_amount:
            continue
        hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        rate  = getattr(p, "billing_rate", 85) or 85
        spent = hours * rate
        ratio = spent / p.budget_amount
        if ratio < 0.85:
            continue
        existing = db.query(AIPrediction).filter(
            AIPrediction.entity_id == p.id,
            AIPrediction.prediction_type == "budget_overrun",
            AIPrediction.is_acknowledged == False,
        ).first()
        if not existing:
            db.add(AIPrediction(
                prediction_type="budget_overrun", entity_type="project", entity_id=p.id,
                probability=min(ratio - 0.5, 0.99),
                severity="critical" if ratio > 1 else "high",
                title=f"Desviación presupuestaria — {p.name}",
                explanation=f"Consumo estimado: {round(ratio*100)}% del presupuesto ({round(spent/1000,1)}k€ de {round(p.budget_amount/1000,1)}k€).",
                recommended_action="Revisar alcance con el cliente. Preparar change order si hay trabajo extra.",
            ))
            generated.append({"type": "budget_overrun", "entity": p.name, "probability": round(ratio - 0.5, 2)})

    log_action(db, current_user.id, "nexusoracle", "run",
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
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:limit]]
    except Exception:
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
        return None


def process_voice_core(transcript: str, db, current_user) -> dict:
    """Shared voice command processing logic."""
    from app.models.project import Project
    from app.models.task import Task
    from app.models.service_desk import Ticket
    from app.models.imputation import Imputation
    from app.models.ai_chat import AIVoiceCommand
    import re as _re

    t0 = time.time()
    intent = "unknown"
    entities: dict = {}
    action_taken = ""
    status = "done"

    try:
        prompt = f"""Analiza este comando de voz de un usuario de Clarive y extrae:
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
            except json.JSONDecodeError:
                pass
    except Exception as e:
        _log.warning(f"Voice command parsing failed: {e}")
        intent = "unknown"
        action_taken = "Error en IA, modo fallback activado"

    result: dict = {"intent": intent, "entities": entities, "action": action_taken}

    if intent == "log_hours" and entities.get("hours") and entities.get("project_name"):
        project = db.query(Project).filter(
            Project.name.ilike(f"%{entities['project_name']}%")
        ).first()
        if project:
            imp = Imputation(
                user_id=current_user.id, project_id=project.id,
                hours=float(entities["hours"]),
                date=date.today(),
                description=f"Imputado por voz: {transcript[:100]}",
                is_billable=True,
            )
            db.add(imp)
            result["action"] = f"✓ Registradas {entities['hours']}h en {project.name}"

    elif intent == "create_ticket" and entities.get("ticket_title"):
        ticket = Ticket(
            title=entities["ticket_title"],
            priority=entities.get("priority", "medium"),
            status="open",
            requester_user_id=current_user.id,
        )
        db.add(ticket); db.flush()
        result["action"] = f"✓ Ticket creado: {ticket.title}"

    elif intent == "query_hours":
        week_start = (date.today() - timedelta(days=date.today().weekday()))
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == current_user.id,
            Imputation.date >= week_start,
        ).scalar() or 0
        result["action"] = f"Esta semana llevas {round(hours, 1)} horas imputadas."

    elif intent == "create_task" and entities.get("task_name"):
        project = None
        if entities.get("project_name"):
            project = db.query(Project).filter(
                Project.name.ilike(f"%{entities['project_name']}%")
            ).first()
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

    elif intent == "get_summary" and entities.get("project_name"):
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

    elif intent == "other" and len(transcript.strip()) > 20:
        from app.models.ai_chat import AIAgentExecution as _Exec
        from app.worker import run_agent_task
        exec_record = _Exec(
            user_id=current_user.id,
            instruction=transcript,
            status="queued",
        )
        db.add(exec_record); db.flush()
        run_agent_task.delay(str(exec_record.id), transcript, str(current_user.id))
        result["action"] = (
            f"Comando enviado al agente (ID: {str(exec_record.id)[:8]}). "
            "Revisa el historial de NexusAgent para el resultado."
        )
        result["execution_id"] = str(exec_record.id)

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
    """Get sanitized project data for client portal."""
    from app.models.project import Project
    from app.models.task import Task

    projects = db.query(Project).filter(
        Project.client_name.ilike(f"%{getattr(client_user, 'company', '')}%")
    ).limit(5).all()

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
    projects = project_data.get("projects", [])
    if projects:
        p = projects[0]
        return (f"Su proyecto **{p['name']}** tiene un progreso del {p['progress_pct']}% "
                f"con {p['open_tasks']} tareas pendientes. "
                f"Para análisis detallado, configure ANTHROPIC_API_KEY.")
    return "Hola, soy el asistente del portal. Configure ANTHROPIC_API_KEY para respuestas completas."


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
