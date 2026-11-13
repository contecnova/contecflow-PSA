"""Pipeline comercial (oportunidad a proyecto, prevision) e informes operativos (antiguedad de tickets, wallboard).

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from app.services.sla_service import ventana_de_riesgo_sla
from app.models.service_desk._enums import ESTADOS_DE_TICKET_ABIERTOS, ESTADOS_DE_TICKET_RESUELTOS, PRIORIDADES_DE_TICKET
from app.core.config import settings
from app.models.pipeline import Opportunity, OpportunityStage
from app.models.project import Project, ProjectStatus
from app.models.service_desk import Ticket
from app.services.audit import audit_log as _audit
from datetime import time as _time
from sqlalchemy.orm import joinedload
from app.core import timeutil
from app.core.errores import ErrorDeDominio


# ── Pipeline Ops ──────────────────────────────────────────────────────────────

def convert_opportunity_to_project_record(opportunity_id: str, payload: dict, current_user, db) -> dict:
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp: raise ErrorDeDominio(404, "Oportunidad no encontrada")
    # `OpportunityStage` no tiene `closed_won`: el valor es `won`. Auditoria
    # 2026-08: la referencia se evaluaba SIEMPRE, asi que convertir una
    # oportunidad en proyecto reventaba con `AttributeError` en la primera
    # linea util de la funcion. La cadena `"closed_won"` de la lista tampoco
    # coincidia nunca con ningun valor de la columna.
    if opp.stage not in [OpportunityStage.won, OpportunityStage.won.value]:
        opp.stage = OpportunityStage.won
    last = db.query(Project).order_by(Project.created_at.desc()).first()
    next_num = 1
    if last and last.code and last.code.startswith("PRJ-"):
        parts = last.code.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            next_num = int(parts[1]) + 1
    code    = payload.get("code") or f"PRJ-{next_num:03d}"
    from app.services.settings_service import get_runtime_str
    _proj_type = get_runtime_str(db, "DEFAULT_PROJECT_TYPE", db.info.get("organization_id")) or settings.DEFAULT_PROJECT_TYPE
    _bill_type = get_runtime_str(db, "DEFAULT_BILLING_TYPE", db.info.get("organization_id")) or settings.DEFAULT_BILLING_TYPE
    _curr      = get_runtime_str(db, "DEFAULT_CURRENCY", db.info.get("organization_id")) or settings.DEFAULT_CURRENCY
    project = Project(
        code=code,
        name=payload.get("name") or opp.name,
        client_name=opp.client_name,
        client_id=getattr(opp, "client_id", None),
        project_type=payload.get("project_type", _proj_type),
        status=ProjectStatus.planning,
        start_date=date.fromisoformat(payload["start_date"]) if payload.get("start_date") else timeutil.today(),
        end_date_planned=date.fromisoformat(payload["end_date"]) if payload.get("end_date") else None,
        # Auditoria 2026-08: `Opportunity` no tiene `amount`; el importe es
        # `expected_revenue`. Reventaba con `AttributeError` en las tres lineas
        # de abajo. Era el **segundo** defecto de esta funcion: el primero
        # —`OpportunityStage.closed_won`, que tampoco existe— la abortaba antes
        # de llegar aqui, asi que este solo se veia al arreglar aquel.
        budget_amount=opp.expected_revenue,
        billing_type=payload.get("billing_type", _bill_type),
        is_billable=True,
        pm_id=payload.get("pm_id"),
        contract_amount=opp.expected_revenue,
        currency=payload.get("currency", _curr),
        description=opp.description,
        created_by=current_user.id,
    )
    db.add(project)
    opp.project_id = project.id
    _audit(db, current_user, "CONVERT_OPPORTUNITY", "projects", project.id, project.name,
           new_values={"opportunity_id": opportunity_id,
                       "amount": opp.expected_revenue})
    db.commit()
    return {"ok": True, "project_id": project.id, "project_code": project.code, "project_name": project.name}


def get_pipeline_revenue_forecast(db) -> dict:
    opps = db.query(Opportunity).filter(Opportunity.stage.notin_(["won", "lost", "cancelled"])).all()
    by_month: dict = {}
    total_weighted = 0
    total_pipeline = 0
    for opp in opps:
        if not opp.expected_close_date or not opp.amount: continue
        prob     = (opp.probability_pct or 0) / 100
        weighted = round(opp.amount * prob, 2)
        total_weighted += weighted
        total_pipeline += opp.amount or 0
        month_key = opp.expected_close_date.strftime("%Y-%m")
        if month_key not in by_month:
            by_month[month_key] = {"month": month_key, "pipeline": 0, "weighted": 0, "count": 0}
        by_month[month_key]["pipeline"] += opp.amount or 0
        by_month[month_key]["weighted"] += weighted
        by_month[month_key]["count"]    += 1
    return {
        "total_pipeline": round(total_pipeline, 2),
        "total_weighted": round(total_weighted, 2),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"]),
        "opportunities": len(opps),
        "avg_probability": round(sum(o.probability_pct or 0 for o in opps) / max(len(opps), 1), 1),
    }


# ── ITSM Aging ────────────────────────────────────────────────────────────────

def get_ticket_aging_report(db) -> dict:
    open_statuses = ESTADOS_DE_TICKET_ABIERTOS
    tickets = db.query(Ticket).options(joinedload(Ticket.assigned_to)).filter(Ticket.status.in_(open_statuses)).all()
    now = datetime.now(timezone.utc)
    aging_buckets = {
        "0-4h":  {"label": "0-4 horas",  "color": "#00e5a0", "tickets": []},
        "4-8h":  {"label": "4-8 horas",  "color": "#7a8aaa", "tickets": []},
        "8-24h": {"label": "8-24 horas", "color": "#ffb800", "tickets": []},
        "1-3d":  {"label": "1-3 días",   "color": "#f97316", "tickets": []},
        "3d+":   {"label": "+3 días",    "color": "#ff4757", "tickets": []},
    }
    for t in tickets:
        age_hours = (now - t.created_at).total_seconds() / 3600 if t.created_at else 0
        mini = {
            "id": t.id, "number": t.number, "title": t.title[:50],
            "priority": t.priority, "status": t.status,
            "assignee": t.assigned_to.full_name if t.assigned_to else "Sin asignar",
            "age_hours": round(age_hours, 1),
            "age_label": f"{int(age_hours)}h" if age_hours < 48 else f"{int(age_hours/24)}d",
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
            "sla_breached": t.sla_resolution_due and t.sla_resolution_due < now,
        }
        if age_hours < 4:    aging_buckets["0-4h"]["tickets"].append(mini)
        elif age_hours < 8:  aging_buckets["4-8h"]["tickets"].append(mini)
        elif age_hours < 24: aging_buckets["8-24h"]["tickets"].append(mini)
        elif age_hours < 72: aging_buckets["1-3d"]["tickets"].append(mini)
        else:                aging_buckets["3d+"]["tickets"].append(mini)
    for bucket in aging_buckets.values():
        bucket["count"] = len(bucket["tickets"])
        bucket["tickets"].sort(key=lambda x: -x["age_hours"])
    wall_board = {
        "open_total": len(tickets),
        "sla_breached": sum(1 for t in tickets if t.sla_resolution_due and t.sla_resolution_due < now),
        "unassigned": sum(1 for t in tickets if not t.assigned_to_user_id),
        "oldest_hours": round(max(((now - t.created_at).total_seconds() / 3600 for t in tickets), default=0), 1),
    }
    return {"aging_buckets": aging_buckets, "wall_board": wall_board, "generated_at": now.isoformat()}


def get_wallboard_data(db) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    open_statuses = ESTADOS_DE_TICKET_ABIERTOS
    tickets_open  = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).all()
    today_start   = datetime.combine(today, _time(0, 0, 0), tzinfo=timezone.utc)
    today_end     = today_start + timedelta(days=1)
    tickets_today = db.query(Ticket).filter(Ticket.created_at >= today_start, Ticket.created_at < today_end).all()
    resolved_today = db.query(Ticket).filter(
        Ticket.resolved_at >= today_start, Ticket.resolved_at < today_end,
        Ticket.status.in_(ESTADOS_DE_TICKET_RESUELTOS)
    ).all()
    sla_breached = [t for t in tickets_open if t.sla_resolution_due and t.sla_resolution_due < now]
    sla_at_risk  = [t for t in tickets_open if t.sla_resolution_due and now < t.sla_resolution_due <= now + ventana_de_riesgo_sla(db)]
    by_priority  = {pri: sum(1 for t in tickets_open if t.priority == pri)
                    for pri in PRIORIDADES_DE_TICKET}
    by_agent: dict = {}
    for t in tickets_open:
        if t.assigned_to_user_id:
            name = t.assigned_to.full_name if t.assigned_to else t.assigned_to_user_id
            by_agent[name] = by_agent.get(name, 0) + 1
    return {
        "timestamp": now.isoformat(),
        "open": len(tickets_open),
        "created_today": len(tickets_today),
        "resolved_today": len(resolved_today),
        "sla_breached": len(sla_breached),
        "sla_at_risk": len(sla_at_risk),
        "unassigned": sum(1 for t in tickets_open if not t.assigned_to_user_id),
        "by_priority": by_priority,
        "by_agent": sorted(by_agent.items(), key=lambda x: -x[1])[:8],
        "critical_tickets": [{
            "number": t.number, "title": t.title[:50],
            "priority": t.priority,
            "age_hours": round((now - t.created_at).total_seconds() / 3600, 1),
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
        } for t in sorted(sla_breached, key=lambda x: x.priority)[:5]],
    }
