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

import json as _json
import logging as _logging
from collections import defaultdict

_bi_logger = _logging.getLogger(__name__)

_WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def get_trend_analysis(
    db: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
) -> dict:
    """Compare current period metrics vs previous period of same length.

    Returns deltas so the frontend can render trend arrows (↑↓).

    Structure::

        {
          "current":  {volume, sla_pct, mttr_minutes, fcr_pct, avg_csat},
          "previous": {volume, sla_pct, mttr_minutes, fcr_pct, avg_csat},
          "deltas":   {volume_delta_pct, sla_delta, mttr_delta_pct, ...},
          "period_days": int,
        }
    """
    from app.services.service_desk.metrics_service import compute_itil_metrics

    d_from, d_to = _parse_range(date_from, date_to)
    period_len = d_to - d_from
    prev_from = d_from - period_len
    prev_to = d_from

    def _fetch(start, end):
        q = db.query(Ticket).filter(Ticket.created_at.between(start, end))
        if client_id:
            q = q.filter(Ticket.client_id == client_id)
        return q.all()

    def _summarise(tickets):
        resolved = [t for t in tickets if t.resolved_at]
        sla_ok = [t for t in resolved if getattr(t, "sla_resolution_status", None) and t.sla_resolution_status.value == "ok"]
        sla_pct = round(len(sla_ok) / len(resolved) * 100, 1) if resolved else 100.0
        metrics = compute_itil_metrics(tickets)
        csat_scores = [t.csat_score for t in tickets if t.csat_score]
        return {
            "volume": len(tickets),
            "sla_pct": sla_pct,
            "mttr_minutes": metrics["mttr_minutes"],
            "fcr_pct": metrics["fcr_percent"],
            "avg_csat": round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None,
        }

    current_tickets = _fetch(d_from, d_to)
    previous_tickets = _fetch(prev_from, prev_to)

    curr = _summarise(current_tickets)
    prev = _summarise(previous_tickets)

    def _delta_pct(cur, pre):
        if pre == 0:
            return None
        return round((cur - pre) / pre * 100, 1)

    deltas = {
        "volume_delta_pct": _delta_pct(curr["volume"], prev["volume"]),
        "sla_delta": round(curr["sla_pct"] - prev["sla_pct"], 1),
        "mttr_delta_pct": _delta_pct(curr["mttr_minutes"], prev["mttr_minutes"]),
        "fcr_delta": round(curr["fcr_pct"] - prev["fcr_pct"], 1),
    }

    return {
        "current": curr,
        "previous": prev,
        "deltas": deltas,
        "period_days": period_len.days,
    }


def get_heatmap_data(
    db: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
) -> dict:
    """Return ticket volume heatmap: day-of-week × hour-of-day.

    Returns::

        {
          "matrix": [[count_dow0_h0, ...], ...],   # 7 rows × 24 cols
          "max_count": int,
          "labels": {"rows": ["Lunes",...], "cols": ["00:00",...]}
        }
    """
    d_from, d_to = _parse_range(date_from, date_to)

    q = db.query(Ticket.created_at).filter(Ticket.created_at.between(d_from, d_to))
    if client_id:
        q = q.filter(Ticket.client_id == client_id)

    matrix: list[list[int]] = [[0] * 24 for _ in range(7)]

    for (ts,) in q.all():
        if ts is None:
            continue
        ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
        matrix[ts_utc.weekday()][ts_utc.hour] += 1

    max_count = max((max(row) for row in matrix), default=0)
    col_labels = [f"{h:02d}:00" for h in range(24)]

    return {
        "matrix": matrix,
        "max_count": max_count,
        "labels": {"rows": _WEEKDAYS, "cols": col_labels},
    }


def get_volume_trend_series(
    db: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    granularity: str = "day",
    client_id: Optional[str] = None,
) -> list[dict]:
    """Return daily or weekly ticket volume as a time series.

    Args:
        granularity: "day" | "week"

    Returns:
        [{"date": "YYYY-MM-DD", "total": int, "resolved": int, "breached": int}, ...]
    """
    d_from, d_to = _parse_range(date_from, date_to)

    q = db.query(Ticket).filter(Ticket.created_at.between(d_from, d_to))
    if client_id:
        q = q.filter(Ticket.client_id == client_id)
    tickets = q.all()

    # Group by date bucket
    buckets: dict[str, dict] = defaultdict(lambda: {"total": 0, "resolved": 0, "breached": 0})

    for t in tickets:
        if t.created_at is None:
            continue
        ts = t.created_at.replace(tzinfo=timezone.utc) if t.created_at.tzinfo is None else t.created_at
        if granularity == "week":
            # ISO week start (Monday)
            day_start = ts.date() - timedelta(days=ts.weekday())
        else:
            day_start = ts.date()
        key = str(day_start)
        buckets[key]["total"] += 1
        if t.resolved_at:
            buckets[key]["resolved"] += 1
        if getattr(t, "sla_resolution_status", None) and t.sla_resolution_status.value == "breached":
            buckets[key]["breached"] += 1

    series = [{"date": k, **v} for k, v in sorted(buckets.items())]
    return series


def generate_bi_story(
    db: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
) -> dict:
    """Generate an AI-powered narrative summary of ITSM performance.

    Computes metrics, then calls the AI provider to generate a 3-paragraph
    executive summary with key insights and recommendations.

    Returns::

        {
          "narrative": str,      # AI-generated text (3 paragraphs)
          "metrics_used": dict,  # raw metrics fed to AI
          "generated_at": str,
        }
    """
    from app.services.ai_provider_service import call_ai

    metrics = get_itil_metrics_payload(db, date_from, date_to, client_id)
    trend = get_trend_analysis(db, date_from, date_to, client_id)

    metrics_summary = (
        f"Período: {metrics['period']['from']} a {metrics['period']['to']}.\n"
        f"Tickets totales: {metrics['volume']['total']} "
        f"(abiertos: {metrics['volume']['open']}, resueltos: {metrics['volume']['resolved']}).\n"
        f"SLA compliance: {metrics['sla_compliance_pct']}%.\n"
        f"MTTR: {metrics.get('mttr_hours', 'N/A')} horas.\n"
        f"FCR: {metrics.get('fcr_percent', 'N/A')}%.\n"
        f"CSAT promedio: {metrics.get('avg_csat', 'N/A')}.\n"
        f"SLA breaches: {metrics['volume']['breached_sla']}.\n"
        f"Cambio vs período anterior — volumen: {trend['deltas'].get('volume_delta_pct', 'N/A')}%, "
        f"SLA: {trend['deltas'].get('sla_delta', 'N/A')} pts.\n"
        f"Tickets por tipo: {_json.dumps(metrics.get('by_type', {}), ensure_ascii=False)}.\n"
        f"Tickets por prioridad: {_json.dumps(metrics.get('by_priority', {}), ensure_ascii=False)}."
    )

    system_prompt = (
        "Eres un analista de ITSM experto. Tu tarea es generar un informe ejecutivo "
        "conciso (3 párrafos) a partir de las métricas de Service Desk que se te proporcionan. "
        "Párrafo 1: resumen del período. Párrafo 2: áreas de mejora con datos concretos. "
        "Párrafo 3: recomendaciones accionables. Sé directo, usa datos, evita relleno."
    )

    messages = [{"role": "user", "content": f"Analiza estas métricas de Service Desk:\n\n{metrics_summary}"}]

    narrative = ""
    try:
        result = call_ai(db, messages=messages, system=system_prompt, max_tokens=600)
        narrative = result if isinstance(result, str) else str(result)
    except Exception as exc:
        _bi_logger.warning("BI story AI call failed: %s", exc)
        # Fallback: template-based narrative
        sla = metrics["sla_compliance_pct"]
        vol = metrics["volume"]["total"]
        mttr = metrics.get("mttr_hours", "N/A")
        narrative = (
            f"Durante el período analizado se registraron {vol} tickets con un "
            f"cumplimiento SLA del {sla}% y un MTTR de {mttr} horas. "
            f"{'El SLA mejoró' if trend['deltas'].get('sla_delta', 0) > 0 else 'El SLA empeoró'} "
            f"{abs(trend['deltas'].get('sla_delta', 0))} puntos respecto al período anterior.\n\n"
            f"Los tipos de ticket más frecuentes son: "
            f"{', '.join(f'{k}={v}' for k,v in metrics.get('by_type', {}).items())}. "
            f"Se registraron {metrics['volume']['breached_sla']} incumplimientos SLA.\n\n"
            "Se recomienda revisar los procesos de escalado y ampliar el catálogo de "
            "resoluciones automáticas para reducir el MTTR."
        )

    return {
        "narrative": narrative,
        "metrics_used": {**metrics, "trend": trend},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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

