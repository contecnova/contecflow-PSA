"""Panel de SLA, rendimiento de agentes y pausa del reloj de SLA.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from app.models.service_desk._enums import ESTADOS_DE_TICKET_ABIERTOS, ESTADOS_DE_TICKET_RESUELTOS, PRIORIDADES_DE_TICKET
from app.models.service_desk import Ticket
from app.core.errores import ErrorDeDominio
from app.services.sla_service import ventana_de_riesgo_sla


# ═══════════════════════════════════════════════════════════════════════════════
# SLA HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def business_minutes_between(start: datetime, end: datetime) -> int:
    """Roughly calculate elapsed minutes in business days (Mon-Fri)."""
    if start >= end:
        return 0
    total = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            segment_end = min(end, next_day)
            total += int((segment_end - current).total_seconds() / 60)
            current = segment_end
        else:
            days_to_monday = 7 - current.weekday()
            current = (current + timedelta(days=days_to_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# ITSM METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def get_sla_dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    open_statuses = ESTADOS_DE_TICKET_ABIERTOS
    open_tickets = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).all()

    breached = [t for t in open_tickets if t.sla_resolution_due and t.sla_resolution_due < now]
    # Ventana de riesgo: ajuste SLA_AT_RISK_WINDOW_HOURS (2 h); la segunda franja llega al doble.
    # Las claves `at_risk_2h`/`at_risk_4h` se mantienen por compatibilidad.
    ventana = ventana_de_riesgo_sla(db)
    at_risk_2h = [t for t in open_tickets if t.sla_resolution_due and now < t.sla_resolution_due <= now + ventana]
    at_risk_4h = [t for t in open_tickets if t.sla_resolution_due and now + ventana < t.sla_resolution_due <= now + 2 * ventana]

    def ticket_mini(t):
        breach_minutes = int((now - t.sla_resolution_due).total_seconds() / 60) if t.sla_resolution_due and t.sla_resolution_due < now else None
        remaining_minutes = int((t.sla_resolution_due - now).total_seconds() / 60) if t.sla_resolution_due and t.sla_resolution_due > now else None
        return {
            "id": t.id, "number": t.number, "title": t.title[:60],
            "priority": t.priority, "status": t.status,
            "assigned_to": t.assigned_to_user_id,
            "sla_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
            "breach_minutes": breach_minutes,
            "remaining_minutes": remaining_minutes,
            "requester": t.requester_name,
        }

    since = now - timedelta(days=30)
    past_tickets = db.query(Ticket).filter(Ticket.created_at >= since).all()
    compliance_by_priority: dict = {}
    for pri in PRIORIDADES_DE_TICKET:
        t_pri = [t for t in past_tickets if t.priority == pri]
        breached_pri = sum(1 for t in t_pri if t.sla_resolution_status == "breached" or (
            t.sla_resolution_due and t.resolved_at and t.resolved_at > t.sla_resolution_due))
        compliance_by_priority[pri] = {
            "total": len(t_pri),
            "breached": breached_pri,
            "compliance_pct": round((len(t_pri) - breached_pri) / max(len(t_pri), 1) * 100, 1),
        }

    heatmap: dict = {}
    for t in past_tickets:
        if t.created_at:
            key = f"{t.created_at.weekday()}_{t.created_at.hour}"
            heatmap[key] = heatmap.get(key, 0) + 1

    return {
        "real_time": {
            "open": len(open_tickets),
            "breached": len(breached),
            "at_risk_2h": len(at_risk_2h),
            "at_risk_4h": len(at_risk_4h),
            "healthy": len([t for t in open_tickets if not t.sla_resolution_due or t.sla_resolution_due > now + 2 * ventana]),
        },
        "breached_tickets": [ticket_mini(t) for t in sorted(breached, key=lambda x: x.sla_resolution_due or now)[:10]],
        "at_risk_tickets": [ticket_mini(t) for t in sorted(at_risk_2h + at_risk_4h, key=lambda x: x.sla_resolution_due or now)[:10]],
        "compliance_by_priority": compliance_by_priority,
        "volume_heatmap": [{"day": int(k.split("_")[0]), "hour": int(k.split("_")[1]), "count": v} for k, v in heatmap.items()],
    }


def get_agent_performance(days: int, db: Session) -> list:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tickets = db.query(Ticket).options(joinedload(Ticket.assigned_to)).filter(
        Ticket.created_at >= since,
        Ticket.assigned_to_user_id != None,
    ).all()

    by_agent: dict = {}
    for t in tickets:
        aid = t.assigned_to_user_id
        if aid not in by_agent:
            by_agent[aid] = {
                "user_id": aid,
                "user_name": t.assigned_to.full_name if t.assigned_to else "—",
                "total": 0, "resolved": 0, "breached": 0,
                "total_mttr": 0, "csat_sum": 0, "csat_count": 0, "open": 0,
            }
        a = by_agent[aid]
        a["total"] += 1
        if t.status in ESTADOS_DE_TICKET_RESUELTOS:
            a["resolved"] += 1
            if t.resolved_at and t.created_at:
                a["total_mttr"] += (t.resolved_at - t.created_at).total_seconds() / 3600
        else:
            a["open"] += 1
        if t.sla_resolution_status == "breached":
            a["breached"] += 1
        if t.csat_score:
            a["csat_sum"] += t.csat_score
            a["csat_count"] += 1

    result = []
    for a in by_agent.values():
        result.append({
            **a,
            "avg_mttr_hours": round(a["total_mttr"] / max(a["resolved"], 1), 1),
            "avg_csat": round(a["csat_sum"] / max(a["csat_count"], 1), 1) if a["csat_count"] else None,
            "sla_compliance_pct": round((a["total"] - a["breached"]) / max(a["total"], 1) * 100, 1),
            "resolution_rate_pct": round(a["resolved"] / max(a["total"], 1) * 100, 1),
        })
    return sorted(result, key=lambda x: -x["total"])


def pause_resume_sla(ticket_id: str, payload: dict, db: Session) -> dict:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404)

    action = payload.get("action", "pause")
    now = datetime.now(timezone.utc)

    if action == "pause" and not ticket.sla_paused_at:
        ticket.sla_paused_at = now
        ticket.sla_resolution_status = "paused"
        msg = "SLA pausado — esperando respuesta del cliente"
    elif action == "resume" and ticket.sla_paused_at:
        paused_minutes = business_minutes_between(ticket.sla_paused_at, now)
        ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_minutes
        if ticket.sla_resolution_due:
            ticket.sla_resolution_due = ticket.sla_resolution_due + timedelta(minutes=paused_minutes)
        if ticket.sla_response_due:
            ticket.sla_response_due = ticket.sla_response_due + timedelta(minutes=paused_minutes)
        ticket.sla_paused_at = None
        ticket.sla_resolution_status = "ok"
        msg = f"SLA reanudado. {paused_minutes} minutos de horario laboral añadidos al plazo."
    else:
        return {"ok": False, "message": "Estado SLA no permite esta acción"}

    db.commit()
    return {
        "ok": True, "message": msg,
        "sla_resolution_due": str(ticket.sla_resolution_due)[:16] if ticket.sla_resolution_due else None,
    }
