"""SLA Service — business logic for SLA calculations.

Extracted from app/api/v1/endpoints/service_desk.py so it can be unit-tested
independently of the HTTP layer.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import cast, func, Integer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client_portal import ClientUser
from app.models.service_desk import Ticket
from app.models.service_desk import Problem
from app.models.service_desk import KBArticle
from app.models.service_desk import ConfigurationItem
from app.models.service_desk import SDSLAHoliday
from app.models.service_desk import TicketHistory
from jose import jwt, JWTError

if TYPE_CHECKING:
    from app.models.service_desk import SLAPolicy, Ticket, TicketHistory
    from app.models.client_portal import ClientUser

logger = logging.getLogger(__name__)

# ── Label / display dictionaries (shared with endpoint) ──────────────────────

PRIORITY_MATRIX = {
    ("critical", "enterprise"): "p1_critical",
    ("critical", "department"): "p1_critical",
    ("critical", "user"):       "p2_high",
    ("critical", "minimal"):    "p3_medium",
    ("high",     "enterprise"): "p1_critical",
    ("high",     "department"): "p2_high",
    ("high",     "user"):       "p2_high",
    ("high",     "minimal"):    "p3_medium",
    ("medium",   "enterprise"): "p2_high",
    ("medium",   "department"): "p3_medium",
    ("medium",   "user"):       "p3_medium",
    ("medium",   "minimal"):    "p4_low",
    ("low",      "enterprise"): "p3_medium",
    ("low",      "department"): "p3_medium",
    ("low",      "user"):       "p4_low",
    ("low",      "minimal"):    "p4_low",
}

TICKET_PREFIXES = {
    "incident": "INC",
    "service_request": "REQ",
    "change": "CHG",
    "problem": "PRB",
    "question": "QST",
}

PRIORITY_LABELS = {
    "p1_critical": {"label": "P1 Crítico", "color": "#ff4757"},
    "p2_high":     {"label": "P2 Alto",    "color": "#ff6b35"},
    "p3_medium":   {"label": "P3 Medio",   "color": "#ffb800"},
    "p4_low":      {"label": "P4 Bajo",    "color": "#00e5a0"},
}

STATUS_LABELS = {
    "new":            {"label": "Nuevo",              "color": "#7a8aaa"},
    "assigned":       {"label": "Asignado",           "color": "#00d4ff"},
    "in_progress":    {"label": "En progreso",        "color": "#7c3aed"},
    "pending_client": {"label": "Pendiente cliente",  "color": "#ffb800"},
    "pending_third":  {"label": "Pendiente tercero",  "color": "#f97316"},
    "resolved":       {"label": "Resuelto",           "color": "#00e5a0"},
    "closed":         {"label": "Cerrado",            "color": "#3d4f6e"},
    "cancelled":      {"label": "Cancelado",          "color": "#3d4f6e"},
}

TYPE_LABELS = {
    "incident":        {"label": "Incidencia", "icon": "🔥"},
    "service_request": {"label": "Solicitud",  "icon": "📋"},
    "change":          {"label": "Cambio",     "icon": "🔀"},
    "problem":         {"label": "Problema",   "icon": "🔍"},
    "question":        {"label": "Consulta",   "icon": "❓"},
}

SLA_HOURS: dict[str, tuple[float, float]] = {
    "p1_critical": (settings.SLA_P1_RESPONSE_HOURS, settings.SLA_P1_RESOLUTION_HOURS),
    "p2_high":     (settings.SLA_P2_RESPONSE_HOURS, settings.SLA_P2_RESOLUTION_HOURS),
    "p3_medium":   (settings.SLA_P3_RESPONSE_HOURS, settings.SLA_P3_RESOLUTION_HOURS),
    "p4_low":      (settings.SLA_P4_RESPONSE_HOURS, settings.SLA_P4_RESOLUTION_HOURS),
}


# ── Pure utilities ────────────────────────────────────────────────────────────

def norm_enum(val) -> str:
    """Normalize an enum value or string to lowercase for PRIORITY_MATRIX lookup."""
    if hasattr(val, 'value'):
        return val.value.lower()
    return str(val).lower()


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize naive datetime → timezone-aware UTC. Safe with None."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def advisory_lock_key(name: str) -> int:
    """Return a deterministic 64-bit positive integer from *name* for pg_advisory_xact_lock."""
    return int(hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()[:15], 16) % (2 ** 63)


def add_working_hours(
    start_dt: datetime,
    hours: float,
    work_start: dt_time = dt_time(8, 0),
    work_end: dt_time = dt_time(18, 0),
    holidays: Optional[set] = None,
) -> datetime:
    """Advance *start_dt* by *hours* of working time.

    Respects:
    - Business-hour window (work_start..work_end)
    - Weekends (Saturday=5, Sunday=6)
    - Holiday dates passed as a set of :class:`datetime.date` objects
    """
    if holidays is None:
        holidays = set()

    day_seconds = (
        datetime.combine(date.today(), work_end)
        - datetime.combine(date.today(), work_start)
    ).total_seconds()
    if day_seconds <= 0:
        raise ValueError("work_end must be after work_start")

    current = start_dt
    _tz = current.tzinfo

    def _is_workday(d: date) -> bool:
        return d.weekday() < 5 and d not in holidays

    def _day_start(d: date) -> datetime:
        return datetime.combine(d, work_start).replace(tzinfo=_tz)

    def _day_end(d: date) -> datetime:
        return datetime.combine(d, work_end).replace(tzinfo=_tz)

    # Advance to next working day start if current is outside window
    while True:
        cur_date = current.date()
        if not _is_workday(cur_date):
            current = _day_start(cur_date + timedelta(days=1))
            continue
        if current.time() >= work_end:
            current = _day_start(cur_date + timedelta(days=1))
            continue
        if current.time() < work_start:
            current = _day_start(cur_date)
        break

    remaining_hours = hours
    while remaining_hours > 0:
        cur_date = current.date()
        if not _is_workday(cur_date):
            current = _day_start(cur_date + timedelta(days=1))
            continue
        day_end_dt = _day_end(cur_date)
        available_h = (day_end_dt - current).total_seconds() / 3600.0
        if remaining_hours <= available_h:
            current = current + timedelta(hours=remaining_hours)
            remaining_hours = 0
        else:
            remaining_hours -= available_h
            current = _day_start(cur_date + timedelta(days=1))

    return current


def compute_sla_status(
    due: Optional[datetime],
    pause_minutes: int = 0,
    total_hours: Optional[float] = None,
) -> str:
    """Return 'breached', 'at_risk', or 'ok' based on remaining SLA time."""
    if not due:
        return "ok"
    now = datetime.now(timezone.utc)
    due_aware = due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due
    effective_due = due_aware + timedelta(minutes=pause_minutes or 0)
    if now > effective_due:
        return "breached"
    remaining = (effective_due - now).total_seconds()
    if total_hours and total_hours > 0 and remaining < total_hours * 3600 * 0.25:
        return "at_risk"
    return "ok"


# ── DB-coupled helpers ────────────────────────────────────────────────────────

def calculate_sla_due(
    priority: str,
    policy: "Optional[SLAPolicy]" = None,
    db: Optional[Session] = None,
) -> tuple[datetime, datetime]:
    """Return (response_due, resolution_due) using working-hours arithmetic."""
    now = datetime.now(timezone.utc)
    if policy:
        pmap = {
            "p1_critical": (policy.p1_response_hours, policy.p1_resolution_hours),
            "p2_high":     (policy.p2_response_hours, policy.p2_resolution_hours),
            "p3_medium":   (policy.p3_response_hours, policy.p3_resolution_hours),
            "p4_low":      (policy.p4_response_hours, policy.p4_resolution_hours),
        }
        resp_h, res_h = pmap.get(priority, (8, 24))
    else:
        resp_h, res_h = SLA_HOURS.get(priority, (8, 24))

    holidays: set = set()
    if db is not None and policy is not None:
        rows = db.query(SDSLAHoliday).filter(
            (SDSLAHoliday.sla_policy_id == policy.id)
            | (SDSLAHoliday.sla_policy_id == None)  # noqa: E711
        ).all()
        for r in rows:
            try:
                holidays.add(date.fromisoformat(r.holiday_date))
            except (ValueError, TypeError):
                pass

    resp_due = add_working_hours(now, resp_h, holidays=holidays)
    res_due = add_working_hours(now, res_h, holidays=holidays)
    return resp_due, res_due


def next_ticket_number(ticket_type: str, db: Session) -> str:
    """Generate the next sequential ticket number (advisory-locked on PostgreSQL)."""
    prefix = TICKET_PREFIXES.get(ticket_type, "TKT")
    try:
        lock_key = advisory_lock_key(f"ticket_number_{ticket_type}")
        db.execute(func.pg_advisory_xact_lock(lock_key))
    except Exception:
        pass  # SQLite / non-PG — best-effort
    last_num = (
        db.query(func.max(cast(func.substr(Ticket.number, len(prefix) + 2), Integer)))
        .filter(Ticket.number.like(f"{prefix}-%"))
        .scalar()
    ) or 0
    return f"{prefix}-{(last_num + 1):04d}"


def next_problem_number(db: Session) -> str:
    try:
        db.execute(func.pg_advisory_xact_lock(advisory_lock_key("problem_number")))
    except Exception:
        pass
    last = db.query(func.max(cast(func.substr(Problem.number, 5), Integer))).scalar() or 0
    return f"PRB-{(last + 1):04d}"


def next_kb_number(db: Session) -> str:
    try:
        db.execute(func.pg_advisory_xact_lock(advisory_lock_key("kb_number")))
    except Exception:
        pass
    last = db.query(func.max(cast(func.substr(KBArticle.number, 4), Integer))).scalar() or 0
    return f"KB-{(last + 1):04d}"


def next_ci_number(db: Session) -> str:
    last = db.query(func.max(cast(func.substr(ConfigurationItem.code, 4), Integer))).scalar() or 0
    return f"CI-{(last + 1):04d}"


def log_history(
    db: Session, ticket_id: str, field: str, old_val, new_val, user_id: str = None
) -> None:
    """Add a TicketHistory row when a field value changes."""
    if str(old_val or "") != str(new_val or ""):
        db.add(TicketHistory(
            ticket_id=ticket_id,
            field_name=field,
            old_value=str(old_val or ""),
            new_value=str(new_val or ""),
            changed_by_user_id=user_id,
        ))


def get_client_from_token(authorization: Optional[str], db: Session) -> "Optional[ClientUser]":
    """Validate a client portal JWT and return the ClientUser, or None.

    Accepts either a standard "Bearer <token>" header value or the raw token.
    """
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None


    try:
        payload = jwt.decode(
            token,
            settings.CLIENT_PORTAL_SECRET,
            algorithms=["HS256"],
        )
        if payload.get("type") != "client":
            return None
        return db.query(ClientUser).filter(
            ClientUser.id == payload.get("sub"),
            ClientUser.is_active == True,
        ).first()
    except JWTError as exc:
        logger.debug("Client token validation failed: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected error in get_client_from_token")
        raise


def ticket_out(t: "Ticket", include_comments: bool = False) -> dict:
    """Serialize a Ticket ORM object to a response dict."""
    pri = PRIORITY_LABELS.get(t.priority, {"label": t.priority, "color": "#7a8aaa"})
    sta = STATUS_LABELS.get(t.status, {"label": t.status, "color": "#7a8aaa"})
    typ = TYPE_LABELS.get(t.ticket_type, {"label": t.ticket_type, "icon": "📋"})

    now = datetime.now(timezone.utc)
    _resp_h, _res_h = SLA_HOURS.get(t.priority, (8, 24))
    resp_sla = (
        compute_sla_status(t.sla_response_due, t.sla_pause_minutes, _resp_h)
        if t.sla_response_due and not t.first_response_at
        else "ok"
    )
    res_sla = (
        compute_sla_status(t.sla_resolution_due, t.sla_pause_minutes, _res_h)
        if t.sla_resolution_due and t.status not in ["resolved", "closed", "cancelled"]
        else "ok"
    )

    time_to_response = None
    if t.first_response_at and t.created_at:
        # Use pre-computed value when available (set at response time), fall back to live calc
        if getattr(t, "first_response_minutes", None) is not None:
            time_to_response = round(t.first_response_minutes / 60, 1)
        else:
            time_to_response = round(
                (aware(t.first_response_at) - aware(t.created_at)).total_seconds() / 3600, 1
            )

    time_to_resolution = None
    if t.resolved_at and t.created_at:
        # Use pre-computed value when available (set at resolution time), fall back to live calc
        if getattr(t, "resolution_minutes", None) is not None:
            time_to_resolution = round(t.resolution_minutes / 60, 1)
        else:
            time_to_resolution = round(
                (aware(t.resolved_at) - aware(t.created_at)).total_seconds() / 3600, 1
            )

    created_at_aware = aware(t.created_at)
    age_hours = round((now - created_at_aware).total_seconds() / 3600, 1) if created_at_aware else 0

    result = {
        "id": t.id,
        "number": t.number,
        "ticket_type": t.ticket_type,
        "type_label": typ["label"],
        "type_icon": typ["icon"],
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "status_label": sta["label"],
        "status_color": sta["color"],
        "priority": t.priority,
        "priority_label": pri["label"],
        "priority_color": pri["color"],
        "urgency": t.urgency,
        "impact": t.impact,
        "support_level": t.support_level,
        "source": t.source,
        "tags": t.tags,
        "requester_name": (
            t.requester_user.full_name if t.requester_user
            else (t.requester_client.full_name if t.requester_client else t.requester_name)
        ),
        "requester_email": (
            t.requester_user.email if t.requester_user
            else (t.requester_client.email if t.requester_client else t.requester_email)
        ),
        "requester_type": (
            "internal" if t.requester_user_id
            else ("client" if t.requester_client_id else "phone")
        ),
        "assigned_to_id": t.assigned_to_user_id,
        "assigned_to_name": t.assigned_to.full_name if t.assigned_to else None,
        "assigned_group_id": t.assigned_group_id,
        "assigned_group_name": t.assigned_group.name if t.assigned_group else None,
        "project_id": t.project_id,
        "project_name": t.project.name if t.project else None,
        "client_id": t.client_id,
        "client_name": (t.client.name if t.client else None) if hasattr(t, "client") else None,
        "ci_id": t.ci_id,
        "ci_name": t.ci.name if t.ci else None,
        "problem_id": t.problem_id,
        "sla_response_due": str(t.sla_response_due)[:16] if t.sla_response_due else None,
        "sla_resolution_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
        "sla_response_status": resp_sla,
        "sla_resolution_status": res_sla,
        "sla_response_breached": getattr(t, "sla_response_breached", False) or False,
        "sla_resolution_breached": getattr(t, "sla_resolution_breached", False) or False,
        "time_spent_minutes": t.time_spent_minutes,
        "time_to_response_hours": time_to_response,
        "time_to_resolution_hours": time_to_resolution,
        "age_hours": age_hours,
        "resolution": t.resolution,
        "resolution_code": t.resolution_code,
        "kb_article_id": t.kb_article_id,
        "csat_score": t.csat_score,
        "csat_comment": t.csat_comment,
        "created_at": str(t.created_at)[:16] if t.created_at else None,
        "updated_at": str(t.updated_at)[:16] if t.updated_at else None,
        "first_response_at": str(t.first_response_at)[:16] if t.first_response_at else None,
        "resolved_at": str(t.resolved_at)[:16] if t.resolved_at else None,
    }

    if include_comments:
        result["comments"] = [
            {
                "id": c.id,
                "body": c.body,
                "is_public": c.is_public,
                "is_solution": c.is_solution,
                "author_name": (
                    c.author_user.full_name if c.author_user
                    else (c.author_client.full_name if c.author_client else c.author_name)
                ),
                "author_type": "agent" if c.author_user_id else "client",
                "created_at": str(c.created_at)[:16],
            }
            for c in t.comments
            if c.is_public
        ]
        result["history"] = [
            {
                "field": h.field_name,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "changed_by": h.changed_by.full_name if h.changed_by else "Sistema",
                "changed_at": str(h.changed_at)[:16],
            }
            for h in t.history
        ]

    return result
