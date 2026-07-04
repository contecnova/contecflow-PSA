"""
SD Advanced Reporting Service — Drill-down, Custom Fields, Excel Export
========================================================================
Sprint 15: Reporting flexible con filtros avanzados, drill-down y exportación.

Diseño sin migraciones: configuraciones de report guardadas en AppSetting blob.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_REPORT_TYPES = [
    "ticket_volume",
    "sla_compliance",
    "agent_performance",
    "asset_lifecycle",
    "resolution_time",
    "change_risk_summary",
]


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
        row = AppSetting(key=key, value=serialized, description=f"SD report config: {key}")
        db.add(row)
    db.flush()


# ── Ticket base query ─────────────────────────────────────────────────────────

def _build_ticket_query(
    db: Session,
    filters: dict,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    from app.models.service_desk import Ticket

    q = db.query(Ticket)

    if date_from:
        q = q.filter(Ticket.created_at >= date_from)
    if date_to:
        q = q.filter(Ticket.created_at <= date_to)
    if filters.get("ticket_type"):
        q = q.filter(Ticket.ticket_type == filters["ticket_type"])
    if filters.get("priority"):
        q = q.filter(Ticket.priority == filters["priority"])
    if filters.get("status"):
        q = q.filter(Ticket.status == filters["status"])
    if filters.get("assignee_id"):
        q = q.filter(Ticket.assignee_id == filters["assignee_id"])

    return q


# ── Report builders ───────────────────────────────────────────────────────────

def _ticket_volume_report(db: Session, filters: dict, date_from: str, date_to: str, group_by: str) -> list[dict]:
    from app.models.service_desk import Ticket
    from sqlalchemy import cast, Date

    q = _build_ticket_query(db, filters, date_from, date_to)

    if group_by == "day":
        rows = q.with_entities(
            cast(Ticket.created_at, Date).label("period"),
            func.count(Ticket.id).label("count"),
        ).group_by("period").order_by("period").all()
        return [{"period": str(r.period), "count": r.count} for r in rows]

    if group_by == "priority":
        rows = q.with_entities(
            Ticket.priority.label("period"),
            func.count(Ticket.id).label("count"),
        ).group_by(Ticket.priority).all()
        return [{"period": str(r.period), "count": r.count} for r in rows]

    if group_by == "type":
        rows = q.with_entities(
            Ticket.ticket_type.label("period"),
            func.count(Ticket.id).label("count"),
        ).group_by(Ticket.ticket_type).all()
        return [{"period": str(r.period), "count": r.count} for r in rows]

    # default: total
    total = q.count()
    return [{"period": "total", "count": total}]


def _sla_compliance_report(db: Session, filters: dict, date_from: str, date_to: str) -> list[dict]:
    pass

    q = _build_ticket_query(db, filters, date_from, date_to)
    tickets = q.all()

    total = len(tickets)
    met = sum(1 for t in tickets if getattr(t, "sla_met", None) is True)
    breached = sum(1 for t in tickets if getattr(t, "sla_met", None) is False)
    unknown = total - met - breached

    compliance_rate = round(met / total * 100, 1) if total > 0 else 0

    return [{
        "total_tickets": total,
        "sla_met": met,
        "sla_breached": breached,
        "sla_unknown": unknown,
        "compliance_rate_pct": compliance_rate,
    }]


def _agent_performance_report(db: Session, filters: dict, date_from: str, date_to: str) -> list[dict]:
    from app.models.service_desk import Ticket
    from app.models.auth import User

    q = _build_ticket_query(db, filters, date_from, date_to)
    rows = (
        q.with_entities(
            Ticket.assignee_id,
            func.count(Ticket.id).label("tickets_handled"),
            func.avg(Ticket.resolution_minutes).label("avg_resolution_minutes"),
        )
        .filter(Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .order_by(func.count(Ticket.id).desc())
        .all()
    )

    # Enrich with user names
    user_ids = [str(r.assignee_id) for r in rows]
    users = {str(u.id): u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}

    return [
        {
            "agent_id": str(r.assignee_id),
            "agent_name": users.get(str(r.assignee_id), "Unknown"),
            "tickets_handled": r.tickets_handled,
            "avg_resolution_minutes": round(float(r.avg_resolution_minutes or 0), 1),
        }
        for r in rows
    ]


def _resolution_time_report(db: Session, filters: dict, date_from: str, date_to: str) -> list[dict]:
    from app.models.service_desk import Ticket

    q = _build_ticket_query(db, filters, date_from, date_to).filter(
        Ticket.resolution_minutes.isnot(None)
    )
    rows = (
        q.with_entities(
            Ticket.priority.label("priority"),
            func.count(Ticket.id).label("count"),
            func.avg(Ticket.resolution_minutes).label("avg_minutes"),
            func.min(Ticket.resolution_minutes).label("min_minutes"),
            func.max(Ticket.resolution_minutes).label("max_minutes"),
        )
        .group_by(Ticket.priority)
        .all()
    )
    return [
        {
            "priority": str(r.priority),
            "count": r.count,
            "avg_resolution_minutes": round(float(r.avg_minutes or 0), 1),
            "min_resolution_minutes": int(r.min_minutes or 0),
            "max_resolution_minutes": int(r.max_minutes or 0),
        }
        for r in rows
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def build_drilldown_report(
    db: Session,
    report_type: str,
    filters: dict,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "day",
    page: int = 1,
    page_size: int = 100,
) -> dict:
    """Execute a flexible drill-down report.

    Args:
        report_type: one of ``_REPORT_TYPES``
        filters: dict with optional keys: ticket_type, priority, status, assignee_id
        date_from / date_to: ISO date strings (YYYY-MM-DD)
        group_by: day | priority | type | status
    """
    if report_type not in _REPORT_TYPES:
        raise ValueError(f"report_type must be one of {_REPORT_TYPES}")

    if not date_from:
        date_from = (datetime.now(tz=timezone.utc) - timedelta(days=30)).date().isoformat()
    if not date_to:
        date_to = datetime.now(tz=timezone.utc).date().isoformat()

    if report_type == "ticket_volume":
        data = _ticket_volume_report(db, filters, date_from, date_to, group_by)
    elif report_type == "sla_compliance":
        data = _sla_compliance_report(db, filters, date_from, date_to)
    elif report_type == "agent_performance":
        data = _agent_performance_report(db, filters, date_from, date_to)
    elif report_type == "resolution_time":
        data = _resolution_time_report(db, filters, date_from, date_to)
    else:
        data = [{"info": f"Report '{report_type}' not yet implemented"}]

    # Pagination
    total = len(data)
    offset = (page - 1) * page_size
    paginated = data[offset : offset + page_size]

    return {
        "report_type": report_type,
        "date_from": date_from,
        "date_to": date_to,
        "group_by": group_by,
        "filters": filters,
        "total_rows": total,
        "page": page,
        "page_size": page_size,
        "data": paginated,
        "generated_at": _utcnow(),
    }


def get_report_presets(db: Session, org_id: str) -> list[dict]:
    blob = _get_json(db, f"sd.reports.presets.{org_id}")
    return blob.get("presets", [])


def save_report_preset(db: Session, org_id: str, preset: dict) -> dict:
    import uuid
    blob = _get_json(db, f"sd.reports.presets.{org_id}")
    presets: list[dict] = blob.get("presets", [])

    preset["id"] = preset.get("id") or str(uuid.uuid4())
    preset["created_at"] = _utcnow()

    # Upsert by name
    presets = [p for p in presets if p.get("name") != preset.get("name")]
    presets.append(preset)

    _set_json(db, f"sd.reports.presets.{org_id}", {"presets": presets})
    db.commit()
    return preset


def export_report_excel(
    db: Session,
    report_type: str,
    filters: dict,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "day",
) -> bytes:
    """Export a report to Excel (openpyxl)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    report = build_drilldown_report(db, report_type, filters, date_from, date_to, group_by, page=1, page_size=10000)
    data = report["data"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report_type[:31]

    # Header
    if data:
        headers = list(data[0].keys())
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h.replace("_", " ").title())
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="1F4E79")
            cell.font = Font(bold=True, color="FFFFFF")

        for row_idx, row in enumerate(data, 2):
            for col, key in enumerate(headers, 1):
                ws.cell(row=row_idx, column=col, value=row.get(key))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
