"""
Analytics service — business logic extracted from analytics.py endpoint.
Covers: caching utilities, filter helpers, hours-by-week, advanced utilization, metric breaches.
"""
from __future__ import annotations

import json
import time
import logging
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.models.bookings import ResourceBooking, BookingType
from app.models.clients import Client
from app.models.documents import Document
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.resources import ResourceUtilizationSnapshot
from app.models.user import User
from app.services.metrics import METRICS_REGISTRY as MODULAR_METRICS_REGISTRY
from fastapi import HTTPException
from sqlalchemy import func

logger = logging.getLogger(__name__)

# ── In-process cache ──────────────────────────────────────────────────────────

_ANALYTICS_CACHE: dict[str, tuple[float, dict]] = {}
_ANALYTICS_CACHE_LOCK = Lock()
_ANALYTICS_CACHE_TTL_SECONDS = 60
_REDIS_CACHE_CLIENT = None
_REDIS_CACHE_INIT_ATTEMPTED = False

METRIC_CACHE_TTL = {
    "margin_by_project": 300, "margin_evolution": 300, "cost_by_project": 300,
    "cost_by_person": 300, "cost_by_month": 300, "cost_vs_budget": 300,
    "budget_consumption": 300, "revenue_by_client": 300,
    "tickets_by_status": 60, "tickets_by_type": 60, "tickets_by_agent": 60,
    "tickets_by_priority": 60, "tasks_by_status": 60, "tasks_by_project": 60,
    "projects_by_status": 60, "projects_by_type": 60, "tasks_blocked_by_project": 60, "tasks_overdue": 60,
    "hours_by_person": 120, "hours_by_week": 120, "hours_by_month": 120,
    "hours_by_department": 120, "load_by_week": 120, "productivity_by_person": 120,
    "license_cost_by_vendor": 3600, "license_utilization": 3600,
    "license_expiry_timeline": 3600, "assets_by_type": 3600,
}


def get_metric_cache_ttl(metric_id: str) -> int:
    return METRIC_CACHE_TTL.get(metric_id, 300)


def _get_redis_client():
    global _REDIS_CACHE_CLIENT, _REDIS_CACHE_INIT_ATTEMPTED
    if _REDIS_CACHE_CLIENT is not None:
        return _REDIS_CACHE_CLIENT
    if _REDIS_CACHE_INIT_ATTEMPTED or not settings.REDIS_URL:
        return None
    _REDIS_CACHE_INIT_ATTEMPTED = True
    try:
        import redis
        _REDIS_CACHE_CLIENT = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _REDIS_CACHE_CLIENT.ping()
        return _REDIS_CACHE_CLIENT
    except Exception as exc:
        logger.warning("Analytics cache: Redis unavailable (%s), using in-memory fallback", exc)
        _REDIS_CACHE_CLIENT = None
        return None


def cache_get(key: str) -> Optional[dict]:
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            value = redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception as exc:
            logger.warning("Analytics cache get failed on Redis: %s", exc)
    now = time.time()
    with _ANALYTICS_CACHE_LOCK:
        hit = _ANALYTICS_CACHE.get(key)
        if not hit:
            return None
        expires_at, value = hit
        if expires_at < now:
            _ANALYTICS_CACHE.pop(key, None)
            return None
        return value


def cache_set(key: str, value: dict, ttl_seconds: int = None) -> None:
    if ttl_seconds is None:
        ttl_seconds = _ANALYTICS_CACHE_TTL_SECONDS
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_client.setex(key, ttl_seconds, json.dumps(value, default=str, separators=(",", ":")))
        except Exception as exc:
            logger.warning("Analytics cache set failed on Redis: %s", exc)
    with _ANALYTICS_CACHE_LOCK:
        _ANALYTICS_CACHE[key] = (time.time() + ttl_seconds, value)


def build_cache_key(namespace: str, current_user, payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    org_id = getattr(current_user, "organization_id", None) or current_user.id
    return f"{namespace}:{org_id}:{serialized}"


# ── Date helpers ──────────────────────────────────────────────────────────────

def parse_date_range(date_from: Optional[str], date_to: Optional[str]):
    d_from = date.fromisoformat(date_from) if date_from else date.today().replace(day=1) - timedelta(days=90)
    d_to   = date.fromisoformat(date_to)   if date_to   else date.today()
    return d_from, d_to


def month_label(d) -> str:
    months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    if hasattr(d, 'month'):
        return f"{months[d.month - 1]} {d.year}"
    return str(d)


def week_label(d) -> str:
    if hasattr(d, 'strftime'):
        return d.strftime('%d/%m')
    return str(d)[:10]


# ── Project filter helper ─────────────────────────────────────────────────────

def get_filtered_project_ids(db, current_user, *, project_id=None, project_type=None, client_id=None):
    if not current_user.organization_id:
        return None  # None = no org filter (super-admin / unscoped user sees all)
    scoped_q = db.query(Project.id).filter(Project.organization_id == current_user.organization_id)
    if project_id:
        proj = db.query(Project).filter(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not proj:
            return []
        return [project_id]
    q = scoped_q
    if project_type:
        q = q.filter(Project.project_type == project_type)
    if client_id:
        q = q.filter(Project.client_id == client_id)
    return [r.id for r in q.all()]


# ── Compute summary ───────────────────────────────────────────────────────────

def compute_summary(rows: list) -> dict:
    if not rows:
        return {}
    values = [r.get("value", 0) for r in rows if isinstance(r.get("value"), (int, float))]
    if not values:
        return {}
    return {
        "total": round(sum(values), 2),
        "max":   round(max(values), 2),
        "min":   round(min(values), 2),
        "avg":   round(sum(values) / len(values), 2),
        "count": len(values),
    }


# ── Hours by week ─────────────────────────────────────────────────────────────

def get_hours_by_week(weeks: int, current_user, db) -> dict:
    today  = date.today()
    result = []
    for i in range(weeks - 1, -1, -1):
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        week_end   = week_start + timedelta(days=6)
        q = db.query(func.sum(Imputation.hours)).join(
            Project, Project.id == Imputation.project_id,
        ).filter(Imputation.date >= week_start, Imputation.date <= week_end)
        if current_user.organization_id:
            q = q.filter(Project.organization_id == current_user.organization_id)
        if current_user.role not in ["admin", "pm", "hr", "team_lead"]:
            q = q.filter(Imputation.user_id == current_user.id)
        result.append({
            "week": week_start.strftime("S%V"),
            "week_start": str(week_start),
            "week_end": str(week_end),
            "hours": round(float(q.scalar() or 0), 1),
        })
    return {"data": result, "weeks": weeks}


# ── Advanced utilization ──────────────────────────────────────────────────────

def get_advanced_utilization(weeks_ahead: int, project_id, project_type, client_id, current_user, db) -> dict:
    today = date.today()
    period_start = today - timedelta(days=today.weekday())
    period_end   = period_start + timedelta(days=6)
    project_ids  = get_filtered_project_ids(db, current_user,
                                             project_id=project_id, project_type=project_type, client_id=client_id)
    if project_id and project_ids == []:
        raise HTTPException(403, "No tienes acceso a este proyecto")
    if project_ids == []:
        return {
            "window":  {"week_start": str(period_start), "week_end": str(period_end), "weeks_ahead": weeks_ahead},
            "filters": {"project_id": project_id, "project_type": project_type, "client_id": client_id},
            "summary": {"capacity_hours": 0, "actual_hours": 0, "booked_hours": 0,
                        "actual_utilization_pct": 0, "booked_utilization_pct": 0},
            "team": [],
        }
    users_q = db.query(User).filter(User.is_active == True)
    if current_user.organization_id:
        users_q = users_q.filter(User.organization_id == current_user.organization_id)
    users = users_q.all()
    team_rows = []
    total_capacity = total_actual = total_booked = 0.0
    for u in users:
        weekly_capacity = float(u.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS)
        current_hours_q = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == u.id,
            Imputation.date >= period_start,
            Imputation.date <= period_end,
        )
        if project_ids:
            current_hours_q = current_hours_q.filter(Imputation.project_id.in_(project_ids))
        current_hours = float(current_hours_q.scalar() or 0.0)
        booking_q = db.query(ResourceBooking).filter(
            ResourceBooking.user_id == u.id,
            ResourceBooking.booking_type == BookingType.hard,
            ResourceBooking.start_date <= period_end,
            ResourceBooking.end_date >= period_start,
        )
        if project_ids:
            booking_q = booking_q.filter(ResourceBooking.project_id.in_(project_ids))
        booked_hours = 0.0
        for b in booking_q.all():
            overlap_start = max(period_start, b.start_date)
            overlap_end   = min(period_end,   b.end_date)
            days = (overlap_end - overlap_start).days + 1
            if days > 0:
                booked_hours += days * float(b.hours_per_day or 0)
        projected_weeks = []
        for i in range(1, weeks_ahead + 1):
            ws = period_start + timedelta(days=7 * i)
            we = ws + timedelta(days=6)
            q_w = db.query(ResourceBooking).filter(
                ResourceBooking.user_id == u.id,
                ResourceBooking.booking_type == BookingType.hard,
                ResourceBooking.start_date <= we,
                ResourceBooking.end_date >= ws,
            )
            if project_ids:
                q_w = q_w.filter(ResourceBooking.project_id.in_(project_ids))
            week_booked = 0.0
            for b in q_w.all():
                ov_s = max(ws, b.start_date)
                ov_e = min(we, b.end_date)
                d    = (ov_e - ov_s).days + 1
                if d > 0:
                    week_booked += d * float(b.hours_per_day or 0)
            projected_weeks.append({
                "week_start": str(ws),
                "booked_hours": round(week_booked, 1),
                "capacity_hours": round(weekly_capacity, 1),
                "utilization_pct": round((week_booked / weekly_capacity) * 100, 1) if weekly_capacity > 0 else 0,
            })
        total_capacity += weekly_capacity
        total_actual   += current_hours
        total_booked   += booked_hours
        team_rows.append({
            "user_id": u.id,
            "full_name": u.full_name,
            "department": u.department,
            "capacity_hours": round(weekly_capacity, 1),
            "actual_hours": round(current_hours, 1),
            "booked_hours": round(booked_hours, 1),
            "actual_utilization_pct": round((current_hours / weekly_capacity) * 100, 1) if weekly_capacity > 0 else 0,
            "booked_utilization_pct": round((booked_hours / weekly_capacity) * 100, 1) if weekly_capacity > 0 else 0,
            "projected": projected_weeks,
        })
    team_rows.sort(key=lambda x: x["actual_utilization_pct"], reverse=True)
    return {
        "window":  {"week_start": str(period_start), "week_end": str(period_end), "weeks_ahead": weeks_ahead},
        "filters": {"project_id": project_id, "project_type": project_type, "client_id": client_id},
        "summary": {
            "capacity_hours": round(total_capacity, 1),
            "actual_hours":   round(total_actual, 1),
            "booked_hours":   round(total_booked, 1),
            "actual_utilization_pct": round((total_actual / total_capacity) * 100, 1) if total_capacity > 0 else 0,
            "booked_utilization_pct": round((total_booked / total_capacity) * 100, 1) if total_capacity > 0 else 0,
        },
        "team": team_rows,
    }


# ── Metric breaches ───────────────────────────────────────────────────────────

def get_metric_breaches(margin_threshold_pct: float, top_n: int, current_user, db) -> dict:
    d_from, d_to = parse_date_range(None, None)
    rows = []
    if "margin_by_project" in MODULAR_METRICS_REGISTRY:
        handler = MODULAR_METRICS_REGISTRY["margin_by_project"]
        result = handler(
            db=db, d_from=d_from, d_to=d_to, top_n=top_n,
            project_ids=get_filtered_project_ids(db, current_user, project_id=None, project_type=None, client_id=None),
            user_id=None,
        )
        rows = result[0] if isinstance(result, tuple) else result
    breaches = [
        {
            "project_code": r.get("label"),
            "margin_pct": r.get("margin", 0),
            "margin":  r.get("margin", 0),
            "revenue": r.get("revenue", 0),
            "cost":    r.get("cost", 0),
            "severity": "critical" if r.get("margin", 0) < 0 else "warning",
            "title": f"Margen bajo en {r.get('label')}",
            "description": f"El margen está en {r.get('margin', 0)}% (umbral {margin_threshold_pct}%)",
        }
        for r in rows if r.get("margin", 0) < margin_threshold_pct
    ]
    breaches.sort(key=lambda x: x["margin_pct"])
    return {"threshold": margin_threshold_pct, "total": len(breaches), "items": breaches}


# ── Filter options ────────────────────────────────────────────────────────────

def get_filter_options_data(current_user, db) -> dict:
    projects = db.query(Project.id, Project.name, Project.code, Project.project_type, Project.client_id).filter(
        Project.status.in_(["active", "closed"]),
        Project.organization_id == current_user.organization_id,
    ).order_by(Project.name).all()
    users = db.query(User.id, User.full_name, User.department).filter(
        User.is_active == True,
        User.organization_id == current_user.organization_id,
    ).order_by(User.full_name).all()
    departments = db.query(User.department).filter(
        User.department.isnot(None),
        User.organization_id == current_user.organization_id,
    ).distinct().all()
    tenant_client_ids = {p.client_id for p in projects if p.client_id}
    clients_q = db.query(Client.id, Client.name).filter(Client.is_active == True)
    if tenant_client_ids:
        clients_q = clients_q.filter(Client.id.in_(tenant_client_ids))
    else:
        clients_q = clients_q.filter(False)
    clients = clients_q.order_by(Client.name).all()
    project_types = sorted({str(p.project_type).replace("ProjectType.", "") for p in projects if p.project_type})
    return {
        "projects": [{"id": p.id, "label": f"{p.code} — {p.name}",
                      "project_type": str(p.project_type).replace("ProjectType.", "") if p.project_type else None,
                      "client_id": p.client_id} for p in projects],
        "users": [{"id": u.id, "label": u.full_name, "department": u.department} for u in users],
        "departments": [d.department for d in departments if d.department],
        "project_types": project_types,
        "clients": [{"id": c.id, "label": c.name} for c in clients],
    }


# ── analytics_extended service functions ─────────────────────────────────────

def get_imputations_for_analytics(db: Session, user_id: str, cutoff_date: date):
    """Fetch imputations for a user on or after cutoff_date."""
    return (
        db.query(Imputation)
        .filter(and_(Imputation.user_id == user_id, Imputation.date >= cutoff_date))
        .all()
    )


def get_documents_for_analytics(db: Session, cutoff_dt: datetime):
    """Fetch non-archived documents created on or after cutoff_dt."""
    return (
        db.query(Document)
        .filter(Document.created_at >= cutoff_dt, Document.is_archived == False)
        .all()
    )


def get_active_users(db: Session):
    """Return all active users."""
    return db.query(User).filter(User.is_active == True).all()


def get_resource_snapshots_for_user(db: Session, user_id: str, limit: int):
    """Return ordered resource utilization snapshots for a user up to limit rows."""
    return (
        db.query(ResourceUtilizationSnapshot)
        .filter(ResourceUtilizationSnapshot.user_id == user_id)
        .order_by(ResourceUtilizationSnapshot.week_iso)
        .limit(limit)
        .all()
    )


def get_imputations_for_export(
    db: Session, user_id: str, date_from: Optional[date], date_to: Optional[date]
):
    """Fetch imputations for CSV export with optional date filters."""
    q = db.query(Imputation).filter(Imputation.user_id == user_id)
    if date_from:
        q = q.filter(Imputation.date >= date_from)
    if date_to:
        q = q.filter(Imputation.date <= date_to)
    return q.order_by(Imputation.date.desc()).all()


def get_all_resource_snapshots(db: Session):
    """Return all resource utilization snapshots ordered by week descending."""
    return (
        db.query(ResourceUtilizationSnapshot)
        .order_by(ResourceUtilizationSnapshot.week_iso.desc())
        .all()
    )
