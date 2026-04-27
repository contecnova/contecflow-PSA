"""OKR and NPS metrics: okr_progress_by_objective, okr_kr_completion_rate,
nps_by_client, nps_trend, nps_distribution, client_health_score."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("okr_progress_by_objective")
def metric_okr_progress_by_objective(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Progreso (%) por objetivo OKR activo."""
    try:
        from app.models.okrs import Objective, OKRStatus

        q = db.query(Objective).filter(
            Objective.status.in_([OKRStatus.active, OKRStatus.at_risk])
        ).order_by(Objective.progress.desc()).limit(top_n)

        rows = []
        for obj in q.all():
            rows.append({
                "label": obj.title,
                "value": round(float(obj.progress or 0), 1),
                "status": obj.status,
                "period": f"{obj.period} {obj.year}" if obj.year else obj.period,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Progreso (%)"}


@register_metric("okr_kr_completion_rate")
def metric_okr_kr_completion_rate(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tasa de consecución de Key Results agrupada por objetivo."""
    try:
        from app.models.okrs import Objective, KeyResult

        objectives = db.query(Objective).limit(top_n).all()
        obj_ids = [o.id for o in objectives]
        obj_map = {o.id: o.title for o in objectives}

        krs = db.query(
            KeyResult.objective_id,
            func.count(KeyResult.id).label("total"),
            func.sum(KeyResult.progress).label("sum_progress"),
        ).filter(KeyResult.objective_id.in_(obj_ids)).group_by(KeyResult.objective_id).all()

        rows = []
        for r in krs:
            avg = round(float(r.sum_progress or 0) / r.total, 1) if r.total else 0
            rows.append({
                "label": obj_map.get(r.objective_id, r.objective_id),
                "value": avg,
                "kr_count": r.total,
            })
        rows.sort(key=lambda x: x["value"], reverse=True)
    except Exception:
        rows = []

    return rows, {"y_label": "Tasa consecución KR (%)"}


@register_metric("nps_by_client")
def metric_nps_by_client(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """NPS medio por cliente en el período."""
    try:
        from app.models.nps import ClientNPS
        from app.models.clients import Client

        q = db.query(
            ClientNPS.client_id,
            func.avg(ClientNPS.score).label("avg_score"),
            func.count(ClientNPS.id).label("responses"),
        ).filter(
            ClientNPS.created_at >= d_from,
            ClientNPS.created_at <= d_to,
        ).group_by(ClientNPS.client_id).order_by(func.avg(ClientNPS.score).desc()).limit(top_n)

        client_ids = [r.client_id for r in q.all()]
        clients_map = {c.id: c.name for c in db.query(Client).filter(Client.id.in_(client_ids)).all()} if client_ids else {}

        rows = []
        for r in q.all():
            rows.append({
                "label": clients_map.get(r.client_id, str(r.client_id)),
                "value": round(float(r.avg_score or 0), 1),
                "responses": r.responses,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "NPS medio"}


@register_metric("nps_trend")
def metric_nps_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Evolución mensual del NPS medio."""
    try:
        from app.models.nps import ClientNPS
        from sqlalchemy import extract

        q = db.query(
            extract("year", ClientNPS.created_at).label("year"),
            extract("month", ClientNPS.created_at).label("month"),
            func.avg(ClientNPS.score).label("avg_score"),
            func.count(ClientNPS.id).label("responses"),
        ).filter(
            ClientNPS.created_at >= d_from,
            ClientNPS.created_at <= d_to,
        ).group_by("year", "month").order_by("year", "month")

        rows = []
        for r in q.all():
            rows.append({
                "label": f"{int(r.year)}-{int(r.month):02d}",
                "value": round(float(r.avg_score or 0), 1),
                "responses": r.responses,
            })
    except Exception:
        rows = []

    return rows, {}


@register_metric("nps_distribution")
def metric_nps_distribution(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de respuestas NPS: Promotores / Pasivos / Detractores."""
    try:
        from app.models.nps import ClientNPS

        all_scores = db.query(ClientNPS.score).filter(
            ClientNPS.created_at >= d_from,
            ClientNPS.created_at <= d_to,
        ).all()

        promoters = sum(1 for (s,) in all_scores if s is not None and s >= 9)
        passives  = sum(1 for (s,) in all_scores if s is not None and 7 <= s <= 8)
        detractors = sum(1 for (s,) in all_scores if s is not None and s <= 6)
        total = promoters + passives + detractors

        rows = [
            {"label": "Promotores (9-10)", "value": promoters, "pct": round(promoters / total * 100, 1) if total else 0},
            {"label": "Pasivos (7-8)",     "value": passives,  "pct": round(passives  / total * 100, 1) if total else 0},
            {"label": "Detractores (0-6)", "value": detractors,"pct": round(detractors / total * 100, 1) if total else 0},
        ]
    except Exception:
        rows = []

    return rows, {}


@register_metric("client_health_score")
def metric_client_health_score(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Health score más reciente por cliente."""
    try:
        from app.models.nps import ClientHealthSnapshot
        from app.models.clients import Client

        # Latest snapshot per client
        subq = db.query(
            ClientHealthSnapshot.client_id,
            func.max(ClientHealthSnapshot.created_at).label("latest"),
        ).group_by(ClientHealthSnapshot.client_id).subquery()

        q = db.query(ClientHealthSnapshot).join(
            subq,
            (ClientHealthSnapshot.client_id == subq.c.client_id) &
            (ClientHealthSnapshot.created_at == subq.c.latest)
        ).order_by(ClientHealthSnapshot.health_score.desc()).limit(top_n)

        client_ids = [r.client_id for r in q.all()]
        clients_map = {c.id: c.name for c in db.query(Client).filter(Client.id.in_(client_ids)).all()} if client_ids else {}

        rows = []
        for snap in q.all():
            rows.append({
                "label": clients_map.get(snap.client_id, str(snap.client_id)),
                "value": round(float(snap.health_score or 0), 1),
                "risk_level": snap.risk_level if hasattr(snap, "risk_level") else None,
            })
    except Exception:
        rows = []

    return rows, {"y_label": "Health Score (0-100)"}
