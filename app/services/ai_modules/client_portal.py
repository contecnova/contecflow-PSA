"""ai_modules.client_portal — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import logging
from datetime import timedelta
from app.core.timeutil import utcnow

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.security import verify_client_token
from app.models.ai_chat import (
    AIClientChatSession, AIClientChatMessage,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

_log = logging.getLogger(__name__)


from app.services.ai_modules._base import (
    call_ai_unified, extract_text, log_action,
)

_CLIENT_AI_SYSTEM = """Eres el asistente de IA del portal de cliente de Contecflow.
Ayudas a los clientes a entender el estado de sus proyectos de forma clara y profesional.
IMPORTANTE: Solo tienes acceso a los datos del proyecto del cliente. Nunca reveles información de otros clientes,
datos financieros internos (márgenes, costes internos) ni información confidencial del equipo.
Responde siempre en el idioma del cliente. Sé transparente y profesional.
Datos disponibles del proyecto:
{project_data}"""

def get_client_project_data(client_user, db: Session) -> dict:
    """Datos de SUS proyectos para el prompt del chat del portal.

    Revision 2026-11: antes se buscaban por `client_name ILIKE '%<empresa>%'`.
    Con la empresa vacia (el campo es opcional) casaba con todos los proyectos
    de la organizacion y el modelo recibia los de otros clientes. Ahora son los
    proyectos asignados al usuario del portal, como en el resto del portal.
    """
    ids = client_user.get_project_ids() if hasattr(client_user, "get_project_ids") else []
    projects = db.query(Project).filter(Project.id.in_(ids)).limit(5).all() if ids else []

    result = []
    for p in projects:
        tasks = db.query(Task).filter(Task.project_id == p.id).all()
        done  = sum(1 for t in tasks if t.status == "done")
        result.append({
            "name": p.name, "status": getattr(p.status, "value", p.status),
            "progress_pct": round(done / max(len(tasks), 1) * 100),
            "start_date": str(p.start_date) if p.start_date else None,
            "end_date": str(p.end_date_planned) if p.end_date_planned else None,
            "open_tasks": sum(1 for t in tasks if t.status != "done"),
        })
    return {"projects": result}

def client_demo_response(message: str, project_data: dict) -> str:
    """Respuesta sin IA para el cliente: su proyecto, sin instrucciones internas.

    Antes le decia al cliente que configurara un proveedor en «IA &
    Conectores», una pantalla que el no tiene.
    """
    projects = project_data.get("projects", [])
    if projects:
        p = projects[0]
        return (f"El asistente no está disponible en este momento. Resumen de **{p['name']}**: "
                f"{p['progress_pct']}% completado, {p['open_tasks']} tareas pendientes. "
                "Para cualquier otra consulta, escriba a su equipo desde Mensajes.")
    return ("El asistente no está disponible en este momento. "
            "Para cualquier consulta, escriba a su equipo desde Mensajes.")

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
    # Revisión 2026-11: el interruptor «portal_ai» de Gobierno de IA no se comprobaba.
    from app.core.modulos_ia import comprobar_modulo
    comprobar_modulo(db, getattr(client_user, "organization_id", None), "portal_ai")
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
    # Revisión 2026-11: la base de conocimiento pública (antes no la miraba), y
    # la pregunta sin artículo queda en «Preguntas sin respuesta».
    from app.services.service_desk.kb_calidad import contexto as contexto_kb
    kb = contexto_kb(db, message, solo_publico=True, origen="portal_chat")
    system += kb["prompt"]

    try:
        response_text = call_ai_unified(
            db, messages, system=system,
            module="client_portal", max_tokens=800
        )
    except Exception as exc:
        from app.services.ai_provider_service import PresupuestoDeIAAgotado
        if isinstance(exc, PresupuestoDeIAAgotado):
            # Revisión 2026-11: el tope diario de la empresa; se dice, no se inventa.
            response_text = ("El asistente ha alcanzado su límite de uso de hoy. Vuelve a intentarlo mañana "
                             "o escribe al equipo desde Soporte.")
        else:
            _log.exception("Client portal chat AI call failed for session=%s", getattr(session, "id", None))
            response_text = client_demo_response(message, project_data)

    respuesta = AIClientChatMessage(session_id=session.id, role="assistant", content=response_text)
    db.add(respuesta)
    db.commit()

    return {"session_id": session.id, "response": response_text, "sources": kb["sources"],
            "message_id": respuesta.id}   # revisión 2026-11: para valorarla

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
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "created_at": str(m.created_at)[:16],
    } for m in msgs]

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
    from app.models.billing_reports import Invoice

    now   = utcnow()
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
    sxy = sum(x * y for x, y in zip(xs, ys))  # noqa: B905
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return {"error": "Degenerate data", "history": history}
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n

    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))  # noqa: B905
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
    unscheduled = q.filter(Task.status.notin_(["done", "cancelled"])).limit(payload.max_tasks).all()

    if not unscheduled:
        return {"scheduled": [], "message": "No unscheduled tasks found"}

    now   = utcnow()
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

    # Auditoria 2026-11: el prompt pedia `"task_id": <int>` y los ids son UUID;
    # el modelo devolvia 1, 2, 3 y aplicar el plan daba 500. Ahora cada tarea
    # lleva un numero y la respuesta se traduce de vuelta a su id.
    por_numero = {i: t.id for i, t in enumerate(unscheduled, 1)}
    task_list = "\n".join(
        f"- [{i}] {t.title} (priority={t.priority or 'medium'}, points={t.story_points or '?'})"
        for i, t in enumerate(unscheduled, 1)
    )
    capacity_str = "\n".join(f"  {c['name']}: ~{c['available_hours_per_week']}h/week free" for c in capacity[:10])
    today_str = now.strftime("%Y-%m-%d")

    # Item #70: prompts en español (alineado con el resto del sistema).
    from app.core.config import settings as _s_for_cap
    _weekly_cap = float(getattr(_s_for_cap, "DEFAULT_WEEKLY_CAPACITY_HOURS", 40.0) or 40.0)
    system = (
        "Eres una IA experta en planificación de proyectos. Recibes una lista "
        "de tareas sin fechas y la capacidad disponible del equipo. Genera un "
        "plan realista empezando hoy. "
        "Responde SOLO con un array JSON, sin texto adicional:\n"
        '[{"task_id": <numero entre corchetes de la tarea>, "suggested_start": "YYYY-MM-DD", '
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
        traducidas = []
        for item in scheduled if isinstance(scheduled, list) else []:
            try:
                real = por_numero.get(int(str(item.get("task_id")).strip("[] ")))
            except (TypeError, ValueError, AttributeError):
                real = None
            if real is None and item.get("task_id") in por_numero.values():
                real = item.get("task_id")
            if real is not None:
                traducidas.append({**item, "task_id": real})
        scheduled = traducidas
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
