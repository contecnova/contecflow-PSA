from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket
from app.models.user import User
from app.services.service_desk.metrics_service import compute_itil_metrics


def _parse_range(date_from: Optional[str], date_to: Optional[str]):
    d_from = (
        datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        if date_from
        else datetime.now(timezone.utc) - timedelta(days=30)
    )
    d_to = (
        datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
        if date_to
        else datetime.now(timezone.utc)
    )
    return d_from, d_to


def get_itil_metrics_payload(
    db: Session,
    date_from: Optional[str],
    date_to: Optional[str],
    client_id: Optional[str],
) -> dict:
    d_from, d_to = _parse_range(date_from, date_to)

    q = db.query(Ticket).options(joinedload(Ticket.comments)).filter(
        Ticket.created_at.between(d_from, d_to)
    )
    if client_id:
        q = q.filter(Ticket.client_id == client_id)
    tickets = q.all()

    total = len(tickets)
    resolved = [t for t in tickets if t.resolved_at]
    open_t = [t for t in tickets if t.status.value not in ("resolved", "closed", "cancelled")]
    breached = [
        t
        for t in tickets
        if t.sla_resolution_status and t.sla_resolution_status.value == "breached"
    ]

    metrics = compute_itil_metrics(tickets)

    sla_compliant = [
        t
        for t in resolved
        if t.sla_resolution_status and t.sla_resolution_status.value == "ok"
    ]
    sla_pct = round(len(sla_compliant) / len(resolved) * 100, 1) if resolved else 100.0

    by_type = {}
    for t in tickets:
        key = t.ticket_type.value
        by_type[key] = by_type.get(key, 0) + 1

    by_priority = {}
    for t in tickets:
        key = t.priority.value
        by_priority[key] = by_priority.get(key, 0) + 1

    csat_scores = [t.csat_score for t in tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    breach_by_priority = {}
    for t in breached:
        key = t.priority.value
        breach_by_priority[key] = breach_by_priority.get(key, 0) + 1

    return {
        "period": {"from": str(d_from.date()), "to": str(d_to.date())},
        "volume": {
            "total": total,
            "open": len(open_t),
            "resolved": len(resolved),
            "breached_sla": len(breached),
        },
        "sla_compliance_pct": sla_pct,
        "mttr_minutes": metrics["mttr_minutes"],
        "mttr_hours": metrics["mttr_hours"],
        "fcr_percent": metrics["fcr_percent"],
        "avg_csat": avg_csat,
        "by_type": by_type,
        "by_priority": by_priority,
        "breach_by_priority": breach_by_priority,
    }


def get_agent_performance_payload(
    db: Session,
    date_from: Optional[str],
    date_to: Optional[str],
) -> list[dict]:
    d_from, d_to = _parse_range(date_from, date_to)

    agents = db.query(User).filter(User.is_active == True).all()
    result = []

    for agent in agents:
        agent_tickets = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == agent.id,
            Ticket.created_at.between(d_from, d_to),
        ).all()
        if not agent_tickets:
            continue

        resolved = [t for t in agent_tickets if t.resolved_at and t.created_at]
        mttr = 0
        if resolved:
            def _safe_dt(dt):
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

            mttr = round(
                sum(
                    (_safe_dt(t.resolved_at) - _safe_dt(t.created_at)).total_seconds() / 60
                    for t in resolved
                )
                / len(resolved),
                0,
            )

        csat_scores = [t.csat_score for t in agent_tickets if t.csat_score]
        breached = sum(
            1
            for t in agent_tickets
            if t.sla_resolution_status and t.sla_resolution_status.value == "breached"
        )

        result.append(
            {
                "agent_id": agent.id,
                "agent_name": agent.full_name,
                "total": len(agent_tickets),
                "resolved": len(resolved),
                "open": len(agent_tickets) - len(resolved),
                "mttr_minutes": mttr,
                "avg_csat": round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None,
                "sla_breaches": breached,
            }
        )

    result.sort(key=lambda x: -x["resolved"])
    return result


# ── Phase 3 — Advanced Analytics + BI Storytelling (Sprint 19-20) ────────────

import logging as _logging

_bi_logger = _logging.getLogger(__name__)


def persist_metric_snapshot(db: Session) -> dict:
    """Compute current ITSM KPIs and persist an hourly snapshot PER COMPANY.

    Snapshot stored in ``sd_itsm_metric_snapshots``.
    Called from Celery beat task ``analytics_snapshot`` every hour.

    Revisión 2026-11: calculaba UNA fila con los tickets de todas las empresas
    y sin empresa (medido en una copia: filas que ninguna empresa podía ver y
    que mezclaban datos de todas). Ahora una por empresa con tickets.
    """
    from app.db.session import sin_filtro_de_tenant
    from app.models.service_desk import Ticket
    with sin_filtro_de_tenant(db):
        orgs = [o for (o,) in db.query(Ticket.organization_id).filter(
            Ticket.organization_id.isnot(None)).distinct()]
    resumenes = [_snapshot_de_empresa(db, org) for org in orgs]
    db.commit()
    total = sum(r["tickets_total"] for r in resumenes)
    return {
        "snapshots": len(resumenes),
        "tickets_total": total,
        "sla_compliance_pct": round(sum(r["sla_compliance_pct"] for r in resumenes) / len(resumenes), 1)
        if resumenes else 100.0,
        "by_organization": resumenes,
    }


def _snapshot_de_empresa(db: Session, org: str) -> dict:
    from app.db.session import sin_filtro_de_tenant
    from app.models.service_desk import ITSMMetricSnapshot
    from app.services.service_desk.metrics_service import compute_itil_metrics
    import uuid as _uuid

    now = datetime.now(tz=timezone.utc)
    since_24h = now - timedelta(hours=24)
    with sin_filtro_de_tenant(db):
        tickets_24h = db.query(Ticket).filter(Ticket.organization_id == org, Ticket.created_at >= since_24h).all()
        open_count = db.query(Ticket).filter(
            Ticket.organization_id == org,
            Ticket.status.notin_(["resolved", "closed", "cancelled"])).count()

    metrics = compute_itil_metrics(tickets_24h)
    resolved = [t for t in tickets_24h if t.resolved_at]
    sla_ok = [t for t in resolved if getattr(t, "sla_resolution_status", None)
              and t.sla_resolution_status.value == "ok"]
    sla_pct = round(len(sla_ok) / len(resolved) * 100, 1) if resolved else 100.0
    csat_scores = [t.csat_score for t in tickets_24h if t.csat_score]

    db.add(ITSMMetricSnapshot(
        id=str(_uuid.uuid4()),
        organization_id=org,
        snapshot_at=now,
        period_hours=24,
        tickets_total=len(tickets_24h),
        tickets_open=open_count,
        tickets_resolved=len(resolved),
        sla_compliance_pct=sla_pct,
        mttr_minutes=metrics.get("mttr_minutes") or 0,
        fcr_pct=metrics.get("fcr_percent") or 0.0,
        avg_csat=round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None,
        breached_sla=sum(1 for t in tickets_24h
                         if getattr(t, "sla_resolution_status", None)
                         and t.sla_resolution_status.value == "breached"),
    ))
    _bi_logger.info("Metric snapshot saved: org=%s total=%d open=%d sla=%.1f%%",
                    org, len(tickets_24h), open_count, sla_pct)
    return {"organization_id": org, "tickets_total": len(tickets_24h), "sla_compliance_pct": sla_pct,
            "mttr_minutes": metrics.get("mttr_minutes")}

