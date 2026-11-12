"""Prevision de ingresos por proyecto y de cartera.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.models.enterprise import RevenueForecast
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.enterprise import (
        RevenueForecast,
    )


def serialize_forecast(f) -> dict:
    revenue = f.revenue_forecast or f.revenue_planned or 0
    cost = f.cost_actual or f.cost_planned or 0
    margin = round((revenue - cost) / revenue * 100, 1) if revenue > 0 else None
    return {
        "id": f.id, "project_id": f.project_id, "year": f.year, "month": f.month,
        "revenue_planned": f.revenue_planned or 0,
        "revenue_actual": f.revenue_actual or 0,
        "revenue_forecast": f.revenue_forecast or 0,
        "cost_planned": f.cost_planned or 0,
        "cost_actual": f.cost_actual or 0,
        "hours_planned": f.hours_planned or 0,
        "hours_actual": f.hours_actual or 0,
        "margin_pct": margin,
        "notes": f.notes,
    }


def get_portfolio_forecast(db: Session, year: int) -> dict:
    """Aggregate revenue forecast across all projects for a given year."""

    forecasts = db.query(RevenueForecast).options(
        joinedload(RevenueForecast.project)
    ).filter(RevenueForecast.year == year).all()

    by_month: dict = {}
    for f in forecasts:
        m = f.month
        if m not in by_month:
            by_month[m] = {
                "month": m, "revenue_planned": 0, "revenue_actual": 0,
                "revenue_forecast": 0, "cost_planned": 0, "cost_actual": 0,
                "hours_planned": 0, "hours_actual": 0,
            }
        by_month[m]["revenue_planned"] += f.revenue_planned or 0
        by_month[m]["revenue_actual"] += f.revenue_actual or 0
        by_month[m]["revenue_forecast"] += f.revenue_forecast or 0
        by_month[m]["cost_planned"] += f.cost_planned or 0
        by_month[m]["cost_actual"] += f.cost_actual or 0
        by_month[m]["hours_planned"] += f.hours_planned or 0
        by_month[m]["hours_actual"] += f.hours_actual or 0

    monthly = [by_month[m] for m in sorted(by_month.keys())]
    total_forecast = sum(m["revenue_forecast"] for m in monthly)
    total_actual   = sum(m["revenue_actual"] for m in monthly)
    total_cost     = sum(m["cost_actual"] for m in monthly)
    total_margin   = round((total_forecast - total_cost) / total_forecast * 100, 1) if total_forecast else None

    return {
        "year": year,
        "monthly": monthly,
        "totals": {
            "revenue_forecast": round(total_forecast, 2),
            "revenue_actual": round(total_actual, 2),
            "cost_actual": round(total_cost, 2),
            "margin_pct": total_margin,
        },
        "projects": len(set(f.project_id for f in forecasts)),
    }


# ── Revenue Forecast ──────────────────────────────────────────────────────────

def get_project_forecast(project_id: str, year: int, db: Session) -> dict:
    forecasts = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id, RevenueForecast.year == year
    ).order_by(RevenueForecast.month).all()
    existing = {f.month: f for f in forecasts}
    result = []
    for month in range(1, 13):
        if month in existing:
            result.append(serialize_forecast(existing[month]))
        else:
            result.append({
                "id": None, "project_id": project_id, "year": year, "month": month,
                "revenue_planned": 0, "revenue_actual": 0, "revenue_forecast": 0,
                "cost_planned": 0, "cost_actual": 0, "hours_planned": 0, "hours_actual": 0,
                "margin_pct": None, "notes": None,
            })
    return {"year": year, "project_id": project_id, "monthly": result}


def upsert_forecast(project_id: str, year: int, month: int, payload, db: Session) -> dict:
    existing = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id,
        RevenueForecast.year == year,
        RevenueForecast.month == month,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        rev = existing.revenue_forecast or existing.revenue_planned or 0
        cost = existing.cost_actual or existing.cost_planned or 0
        existing.margin_pct = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        db.commit()
        return serialize_forecast(existing)
    else:
        data = payload.model_dump()
        rev = data.get("revenue_forecast") or data.get("revenue_planned") or 0
        cost = data.get("cost_actual") or data.get("cost_planned") or 0
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        forecast = RevenueForecast(project_id=project_id, year=year, month=month, margin_pct=margin, **data)
        db.add(forecast)
        db.commit()
        db.refresh(forecast)
        return serialize_forecast(forecast)
