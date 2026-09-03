"""
Capacity Planning Service — Predictive ITSM Workload Forecasting
================================================================
Sprint 15: Predicción de volumen de tickets, carga por agente, recomendaciones de staffing.

Usa sklearn LinearRegression (si disponible) o media móvil simple como fallback.
Sin migraciones — configuración en AppSetting blob ``sd.capacity.config.<org_id>``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── AppSetting helpers ────────────────────────────────────────────────────────

def _get_json(db: Session, key: str) -> dict:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_json(db: Session, key: str, data: dict) -> None:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(data, ensure_ascii=False)
    if row:
        row.value = serialized
    else:
        row = AppSetting(key=key, value=serialized, description=f"Capacity planning: {key}")
        db.add(row)
    db.flush()


# ── Historical data helpers ───────────────────────────────────────────────────

def _get_daily_ticket_counts(db: Session, days: int = 90) -> list[int]:
    """Return list of ticket counts per day for the last ``days`` days."""
    from app.models.service_desk import Ticket
    from sqlalchemy import cast, Date

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            cast(Ticket.created_at, Date).label("day"),
            func.count(Ticket.id).label("cnt"),
        )
        .filter(Ticket.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [int(r.cnt) for r in rows]


def _get_agent_ticket_counts(db: Session, days: int = 30) -> dict[str, int]:
    """Return {agent_id: ticket_count} for the last ``days`` days."""
    from app.models.service_desk import Ticket

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = (
        db.query(Ticket.assignee_id, func.count(Ticket.id).label("cnt"))
        .filter(Ticket.created_at >= cutoff, Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .all()
    )
    return {str(r.assignee_id): int(r.cnt) for r in rows}


# ── Linear regression helper (sklearn or fallback) ───────────────────────────

def _linear_forecast(values: list[float], days_ahead: int) -> list[float]:
    """Return ``days_ahead`` future values using simple linear regression or mean."""
    if not values:
        return [0.0] * days_ahead

    # Try sklearn first
    try:
        from sklearn.linear_model import LinearRegression
        import numpy as np

        X = np.arange(len(values)).reshape(-1, 1)
        y = np.array(values, dtype=float)
        model = LinearRegression()
        model.fit(X, y)
        future_X = np.arange(len(values), len(values) + days_ahead).reshape(-1, 1)
        preds = model.predict(future_X).tolist()
        return [max(0.0, round(p, 1)) for p in preds]
    except ImportError:
        pass

    # Fallback: weighted moving average (last 14 days)
    window = min(14, len(values))
    recent = values[-window:]
    weights = list(range(1, window + 1))
    wma = sum(v * w for v, w in zip(recent, weights)) / sum(weights)  # noqa: B905
    # Apply light linear trend from first half to second half of history
    half = max(1, len(values) // 2)
    trend = (sum(values[-half:]) / half - sum(values[:half]) / half) / half if len(values) >= 4 else 0
    return [max(0.0, round(wma + trend * i, 1)) for i in range(1, days_ahead + 1)]


# ── Capacity limits from config ───────────────────────────────────────────────

def _get_capacity_config(db: Session, org_id: str) -> dict:
    blob = _get_json(db, f"sd.capacity.config.{org_id}")
    return {
        "tickets_per_agent_per_day": blob.get("tickets_per_agent_per_day", 8),
        "target_agents": blob.get("target_agents", 5),
        "burnout_threshold_per_week": blob.get("burnout_threshold_per_week", 60),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def predict_ticket_volume(db: Session, org_id: str, days_ahead: int = 30) -> dict:
    """Predict daily ticket volume for the next ``days_ahead`` days."""
    historical = _get_daily_ticket_counts(db, days=90)
    forecast = _linear_forecast([float(v) for v in historical], days_ahead)

    today = datetime.now(tz=timezone.utc).date()
    forecast_with_dates = [
        {"date": (today + timedelta(days=i + 1)).isoformat(), "predicted_tickets": v}
        for i, v in enumerate(forecast)
    ]

    avg_forecast = round(sum(forecast) / len(forecast), 1) if forecast else 0
    trend = "rising" if forecast[-1] > forecast[0] else ("falling" if forecast[-1] < forecast[0] else "stable") if len(forecast) > 1 else "stable"

    return {
        "org_id": org_id,
        "days_ahead": days_ahead,
        "historical_days": len(historical),
        "avg_daily_forecast": avg_forecast,
        "trend": trend,
        "forecast": forecast_with_dates,
        "generated_at": _utcnow(),
    }


def predict_agent_load(db: Session, org_id: str, days_ahead: int = 14) -> dict:
    """Forecast per-agent load for the next ``days_ahead`` days."""
    config = _get_capacity_config(db, org_id)
    capacity_per_agent = config["tickets_per_agent_per_day"]

    agent_counts = _get_agent_ticket_counts(db, days=30)

    # Enrich with user names
    # `app.models.auth` no existe: `User` esta en `app.models.user`. Importe
    # diferido, asi que esta funcion fallaba en CADA llamada. Auditoria 2026-08.
    from app.models.user import User
    user_ids = list(agent_counts.keys())
    users = {str(u.id): getattr(u, "full_name", u.email) for u in db.query(User).filter(User.id.in_(user_ids)).all()}

    agents = []
    for agent_id, count_30d in agent_counts.items():
        avg_daily = count_30d / 30
        forecast = _linear_forecast([avg_daily] * 30, days_ahead)
        avg_forecasted = round(sum(forecast) / len(forecast), 1) if forecast else avg_daily
        load_pct = round(avg_forecasted / capacity_per_agent * 100, 1)
        agents.append({
            "agent_id": agent_id,
            "agent_name": users.get(agent_id, "Unknown"),
            "avg_daily_last_30d": round(avg_daily, 1),
            "avg_daily_forecasted": avg_forecasted,
            "capacity_per_day": capacity_per_agent,
            "load_pct": load_pct,
            "status": "overloaded" if load_pct > 100 else ("high" if load_pct > 80 else "normal"),
        })

    agents.sort(key=lambda x: x["load_pct"], reverse=True)
    return {
        "org_id": org_id,
        "days_ahead": days_ahead,
        "agents": agents,
        "generated_at": _utcnow(),
    }


def get_capacity_recommendations(db: Session, org_id: str) -> dict:
    """Staffing recommendations based on forecast vs current capacity."""
    config = _get_capacity_config(db, org_id)
    forecast_data = predict_ticket_volume(db, org_id, days_ahead=30)
    avg_forecast = forecast_data["avg_daily_forecast"]

    tickets_per_agent = config["tickets_per_agent_per_day"]
    agents_needed = max(1, round(avg_forecast / tickets_per_agent))
    current_agents = config["target_agents"]
    delta = agents_needed - current_agents

    recs = []
    if delta > 0:
        recs.append(f"Se necesitan {delta} agente(s) adicional(es) para cubrir la demanda prevista.")
    elif delta < 0:
        recs.append(f"Capacidad sobrante de {abs(delta)} agente(s). Considera redistribuir carga.")
    else:
        recs.append("La capacidad actual se alinea con la demanda prevista.")

    if forecast_data["trend"] == "rising":
        recs.append("Tendencia alcista detectada. Planifica incorporaciones con 2-3 semanas de antelación.")
    if forecast_data["trend"] == "falling":
        recs.append("Tendencia bajista. Evalúa rotaciones o formaciones para los períodos de baja demanda.")

    return {
        "org_id": org_id,
        "avg_daily_forecast": avg_forecast,
        "agents_currently_configured": current_agents,
        "agents_needed": agents_needed,
        "delta": delta,
        "recommendations": recs,
        "generated_at": _utcnow(),
    }


def calculate_burnout_risk(db: Session, user_id: str, org_id: str) -> dict:
    """Estimate burnout risk for a specific agent."""
    config = _get_capacity_config(db, org_id)
    weekly_threshold = config["burnout_threshold_per_week"]

    from app.models.service_desk import Ticket

    cutoff_4w = datetime.now(tz=timezone.utc) - timedelta(weeks=4)
    weekly_counts: list[int] = []
    for week in range(4):
        w_start = cutoff_4w + timedelta(weeks=week)
        w_end = w_start + timedelta(weeks=1)
        count = (
            db.query(func.count(Ticket.id))
            .filter(
                Ticket.assignee_id == user_id,
                Ticket.created_at >= w_start,
                Ticket.created_at < w_end,
            )
            .scalar()
            or 0
        )
        weekly_counts.append(int(count))

    avg_weekly = sum(weekly_counts) / 4 if weekly_counts else 0
    max_weekly = max(weekly_counts) if weekly_counts else 0
    overload_weeks = sum(1 for c in weekly_counts if c > weekly_threshold)

    risk_score = 0
    if avg_weekly > weekly_threshold:
        risk_score += 40
    if max_weekly > weekly_threshold * 1.5:
        risk_score += 30
    if overload_weeks >= 3:
        risk_score += 30

    risk_level = "critical" if risk_score >= 70 else ("high" if risk_score >= 40 else ("medium" if risk_score >= 20 else "low"))

    return {
        "user_id": user_id,
        "weekly_ticket_counts": weekly_counts,
        "avg_weekly_tickets": round(avg_weekly, 1),
        "max_weekly_tickets": max_weekly,
        "overload_weeks": overload_weeks,
        "weekly_threshold": weekly_threshold,
        "burnout_risk_score": risk_score,
        "burnout_risk_level": risk_level,
        "assessed_at": _utcnow(),
    }


def get_capacity_config(db: Session, org_id: str) -> dict:
    return _get_json(db, f"sd.capacity.config.{org_id}") or _get_capacity_config(db, org_id)


def save_capacity_config(db: Session, org_id: str, config: dict) -> dict:
    _set_json(db, f"sd.capacity.config.{org_id}", config)
    db.commit()
    return config
