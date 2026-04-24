"""
v238 Features Service — Business logic extracted from v238_features.py router.
Covers: Pipeline stage configs, forecast, booking conflicts, gantt leveling,
automation trigger/action types, custom field trigger test, BI ad-hoc,
drilldown, cross-filter, Stripe payments, CRDT collab snapshots.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
import json
import logging
import hmac
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.core.config import settings
from app.models.user import User
from app.models.bookings import ResourceBooking as Booking
from app.models.pipeline import PipelineStageConfig, Opportunity
from app.models.billing_reports import Invoice
from app.models.document_collab import DocumentCollabSnapshot
from app.models.documents import Document
from app.models.custom_fields import ProjectCustomField, ProjectCustomFieldValue
from app.models.imputation import Imputation
from app.models.service_desk import Ticket
from app.models.task import Task
from collections import defaultdict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE — stage configs + forecast
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_STAGE_CONFIGS = [
    {"stage_key": "lead", "label": "Lead", "color": "#6B7280", "order": 0, "probability_default": 10, "is_terminal": False, "is_won": False},
    {"stage_key": "qualification", "label": "Calificación", "color": "#3B82F6", "order": 1, "probability_default": 25, "is_terminal": False, "is_won": False},
    {"stage_key": "proposal", "label": "Propuesta", "color": "#8B5CF6", "order": 2, "probability_default": 50, "is_terminal": False, "is_won": False},
    {"stage_key": "negotiation", "label": "Negociación", "color": "#F59E0B", "order": 3, "probability_default": 75, "is_terminal": False, "is_won": False},
    {"stage_key": "won", "label": "Ganada", "color": "#10B981", "order": 4, "probability_default": 100, "is_terminal": True, "is_won": True},
    {"stage_key": "lost", "label": "Perdida", "color": "#EF4444", "order": 5, "probability_default": 0, "is_terminal": True, "is_won": False},
]


def get_stage_configs(db: Session) -> dict:
    configs = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.is_active == True
    ).order_by(PipelineStageConfig.order).all()
    if not configs:
        return {"configs": _DEFAULT_STAGE_CONFIGS, "source": "defaults"}
    return {
        "configs": [
            {
                "id": c.id, "stage_key": c.stage_key, "label": c.label,
                "description": c.description, "color": c.color, "order": c.order,
                "probability_default": c.probability_default,
                "is_terminal": c.is_terminal, "is_won": c.is_won,
            }
            for c in configs
        ],
        "source": "custom",
    }


def create_stage_config_record(
    stage_key: str,
    label: str,
    description: Optional[str],
    color: Optional[str],
    order: Optional[int],
    probability_default: Optional[float],
    is_terminal: Optional[bool],
    is_won: Optional[bool],
    db: Session,
) -> dict:
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == stage_key
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stage key '{stage_key}' already exists")
    config = PipelineStageConfig(
        stage_key=stage_key,
        label=label,
        description=description,
        color=color or "#6B7280",
        order=order or 0,
        probability_default=probability_default or 50,
        is_terminal=is_terminal or False,
        is_won=is_won or False,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "stage_key": config.stage_key, "label": config.label, "created": True}


def delete_stage_config_record(stage_key: str, db: Session) -> None:
    config = db.query(PipelineStageConfig).filter(PipelineStageConfig.stage_key == stage_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Stage config not found")
    config.is_active = False
    db.commit()


def get_pipeline_forecast(months_ahead: int, db: Session) -> dict:
    terminal = {"won", "lost", "cancelled"}
    opps = db.query(Opportunity).filter(
        Opportunity.stage.notin_(list(terminal)),
        Opportunity.expected_close_date.isnot(None),
    ).all()

    today = date.today()
    months = []
    for i in range(months_ahead):
        yr = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1).year
        mo = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1).month
        months.append((yr, mo))

    result = []
    for yr, mo in months:
        month_opps = [
            o for o in opps
            if o.expected_close_date and o.expected_close_date.year == yr and o.expected_close_date.month == mo
        ]
        weighted = sum((o.expected_revenue or 0) * (o.probability / 100) for o in month_opps)
        best_case = sum(o.expected_revenue or 0 for o in month_opps)
        result.append({
            "month": f"{yr}-{mo:02d}",
            "opportunities_count": len(month_opps),
            "weighted_revenue": round(weighted, 0),
            "best_case_revenue": round(best_case, 0),
            "opportunities": [
                {
                    "id": o.id, "name": o.name,
                    "stage": str(o.stage.value) if hasattr(o.stage, 'value') else str(o.stage),
                    "probability": o.probability,
                    "expected_revenue": o.expected_revenue,
                    "weighted": round((o.expected_revenue or 0) * (o.probability / 100), 0),
                }
                for o in month_opps
            ],
        })

    total_weighted = sum(r["weighted_revenue"] for r in result)
    total_best = sum(r["best_case_revenue"] for r in result)
    return {
        "months": result,
        "totals": {
            "weighted_revenue": round(total_weighted, 0),
            "best_case_revenue": round(total_best, 0),
            "months_ahead": months_ahead,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# CAPACITY — conflict detection + gantt leveling
# ──────────────────────────────────────────────────────────────────────────────

def get_booking_conflicts(
    user_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    threshold_pct: float,
    db: Session,
) -> dict:

    q = db.query(Booking)
    if user_id:
        q = q.filter(Booking.user_id == user_id)
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    bookings = q.all()
    user_bookings: dict = defaultdict(list)
    for b in bookings:
        user_bookings[b.user_id].append(b)

    conflicts = []
    capacity_per_day = settings.DEFAULT_WORKING_HOURS_PER_DAY

    for uid, user_bks in user_bookings.items():
        daily: dict = defaultdict(float)
        for b in user_bks:
            d = b.start_date
            while d <= b.end_date:
                daily[d] += (b.hours_per_day or 8.0)
                d += timedelta(days=1)

        overloaded_days = [
            {"date": str(d), "hours": round(h, 1), "utilization_pct": round(h / capacity_per_day * 100, 1)}
            for d, h in daily.items()
            if h / capacity_per_day * 100 > threshold_pct
        ]
        if overloaded_days:
            user_obj = db.query(User).filter(User.id == uid).first()
            conflicts.append({
                "user_id": uid,
                "user_name": user_obj.full_name if user_obj else uid,
                "overloaded_days": sorted(overloaded_days, key=lambda x: x["date"]),
                "max_utilization_pct": max(d["utilization_pct"] for d in overloaded_days),
                "bookings_count": len(user_bks),
            })

    return {
        "threshold_pct": threshold_pct,
        "conflicts_count": len(conflicts),
        "conflicts": sorted(conflicts, key=lambda x: x["max_utilization_pct"], reverse=True),
    }


def get_gantt_leveling(
    project_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    db: Session,
) -> dict:

    q = db.query(Booking)
    if project_id:
        q = q.filter(Booking.project_id == project_id)
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    bookings = q.order_by(Booking.start_date).all()
    capacity = settings.DEFAULT_WORKING_HOURS_PER_DAY
    user_bookings: dict = defaultdict(list)
    for b in bookings:
        user_bookings[b.user_id].append(b)

    proposals = []
    for uid, user_bks in user_bookings.items():
        sorted_bks = sorted(user_bks, key=lambda x: x.start_date)
        user_obj = db.query(User).filter(User.id == uid).first()
        daily: dict = defaultdict(float)
        for b in sorted_bks:
            d = b.start_date
            while d <= b.end_date:
                daily[d] += (b.hours_per_day or 8.0)
                d += timedelta(days=1)

        overloaded = {d for d, h in daily.items() if h / capacity * 100 > 100}
        if not overloaded:
            continue

        for b in sorted_bks:
            bk_days = set()
            d = b.start_date
            while d <= b.end_date:
                bk_days.add(d)
                d += timedelta(days=1)
            conflict_days = bk_days & overloaded
            if conflict_days:
                latest_conflict = max(conflict_days)
                suggested_start = latest_conflict + timedelta(days=1)
                duration_days = (b.end_date - b.start_date).days
                suggested_end = suggested_start + timedelta(days=duration_days)
                proposals.append({
                    "booking_id": b.id,
                    "user_id": uid,
                    "user_name": user_obj.full_name if user_obj else uid,
                    "project_id": b.project_id,
                    "current_start": str(b.start_date),
                    "current_end": str(b.end_date),
                    "suggested_start": str(suggested_start),
                    "suggested_end": str(suggested_end),
                    "conflict_days_count": len(conflict_days),
                    "reason": f"Resource overloaded on {len(conflict_days)} day(s)",
                })

    return {
        "analysis_period": {
            "start": str(start_date or "all"),
            "end": str(end_date or "all"),
        },
        "overloaded_users": len(set(p["user_id"] for p in proposals)),
        "proposals_count": len(proposals),
        "proposals": proposals,
    }


# ──────────────────────────────────────────────────────────────────────────────
# AUTOMATIONS — trigger/action type metadata + custom field trigger test
# ──────────────────────────────────────────────────────────────────────────────

def list_trigger_types_data() -> dict:
    return {
        "triggers": [
            {"type": "task_status_changed", "label": "Task status changed", "category": "tasks",
             "params": [{"name": "from_status", "type": "string", "required": False}, {"name": "to_status", "type": "string", "required": False}]},
            {"type": "task_overdue", "label": "Task becomes overdue", "category": "tasks",
             "params": [{"name": "days_overdue", "type": "number", "required": False}]},
            {"type": "budget_threshold", "label": "Budget threshold reached", "category": "projects",
             "params": [{"name": "threshold_pct", "type": "number", "required": True}]},
            {"type": "sprint_started", "label": "Sprint started", "category": "sprints", "params": []},
            {"type": "sprint_ended", "label": "Sprint ended", "category": "sprints", "params": []},
            {"type": "ticket_created", "label": "Ticket created", "category": "service_desk",
             "params": [{"name": "priority", "type": "string", "required": False}]},
            {"type": "ticket_sla_at_risk", "label": "Ticket SLA at risk", "category": "service_desk",
             "params": [{"name": "minutes_before_breach", "type": "number", "required": False}]},
            {"type": "risk_score_high", "label": "Risk score high", "category": "risks",
             "params": [{"name": "min_score", "type": "number", "required": False}]},
            {"type": "expense_submitted", "label": "Expense submitted", "category": "expenses",
             "params": [{"name": "min_amount", "type": "number", "required": False}]},
            {"type": "project_status_changed", "label": "Project status changed", "category": "projects",
             "params": [{"name": "to_status", "type": "string", "required": False}]},
            {"type": "date_reached", "label": "Specific date reached", "category": "schedule",
             "params": [{"name": "date", "type": "date", "required": True}]},
            {"type": "custom_field_changed", "label": "Custom field value changed", "category": "custom",
             "params": [
                 {"name": "field_key", "type": "string", "required": True, "description": "The custom field key/slug"},
                 {"name": "operator", "type": "enum", "options": ["equals", "not_equals", "contains", "greater_than", "less_than"], "required": False},
                 {"name": "value", "type": "string", "required": False},
             ]},
            {"type": "opportunity_stage_changed", "label": "Pipeline opportunity stage changed", "category": "pipeline",
             "params": [{"name": "to_stage", "type": "string", "required": False}]},
        ]
    }


def list_action_types_data() -> dict:
    return {
        "actions": [
            {"type": "send_alert", "label": "Send in-app alert", "category": "notifications",
             "params": [{"name": "title", "type": "string", "required": True}, {"name": "message", "type": "string", "required": True}, {"name": "severity", "type": "enum", "options": ["info", "warning", "critical"]}]},
            {"type": "change_task_status", "label": "Change task status", "category": "tasks",
             "params": [{"name": "status", "type": "string", "required": True}]},
            {"type": "assign_task", "label": "Assign task to user", "category": "tasks",
             "params": [{"name": "user_id", "type": "string", "required": True}]},
            {"type": "create_task", "label": "Create new task", "category": "tasks",
             "params": [{"name": "title", "type": "string", "required": True}, {"name": "assignee_role", "type": "string", "required": False}]},
            {"type": "escalate_ticket", "label": "Escalate ticket", "category": "service_desk",
             "params": [{"name": "to_level", "type": "string", "required": True}]},
            {"type": "change_ticket_status", "label": "Change ticket status", "category": "service_desk",
             "params": [{"name": "status", "type": "string", "required": True}]},
            {"type": "notify_role", "label": "Notify all users with role", "category": "notifications",
             "params": [{"name": "role", "type": "string", "required": True}, {"name": "message", "type": "string", "required": True}]},
            {"type": "notify_user", "label": "Notify specific user", "category": "notifications",
             "params": [{"name": "user_id", "type": "string", "required": True}, {"name": "message", "type": "string", "required": True}]},
            {"type": "send_email", "label": "Send email", "category": "integrations",
             "params": [{"name": "to", "type": "string", "required": True}, {"name": "subject", "type": "string", "required": True}, {"name": "body", "type": "text", "required": True}]},
            {"type": "call_webhook", "label": "Call external webhook", "category": "integrations",
             "params": [{"name": "url", "type": "string", "required": True}, {"name": "method", "type": "enum", "options": ["POST", "PUT", "PATCH"], "required": False}, {"name": "payload_template", "type": "json", "required": False}]},
            {"type": "send_slack_message", "label": "Send Slack message", "category": "integrations",
             "params": [{"name": "channel", "type": "string", "required": True}, {"name": "message", "type": "string", "required": True}]},
            {"type": "send_teams_message", "label": "Send Teams message", "category": "integrations",
             "params": [{"name": "channel", "type": "string", "required": False}, {"name": "message", "type": "string", "required": True}]},
            {"type": "create_jira_issue", "label": "Create Jira issue", "category": "integrations",
             "params": [
                 {"name": "project_key", "type": "string", "required": True},
                 {"name": "issue_type", "type": "string", "required": True},
                 {"name": "summary", "type": "string", "required": True},
                 {"name": "description_template", "type": "text", "required": False},
                 {"name": "priority", "type": "string", "required": False},
             ]},
            {"type": "update_jira_issue", "label": "Update Jira issue", "category": "integrations",
             "params": [{"name": "issue_key", "type": "string", "required": True}, {"name": "fields", "type": "json", "required": True}]},
            {"type": "create_hubspot_deal", "label": "Create HubSpot deal", "category": "integrations",
             "params": [{"name": "dealname", "type": "string", "required": True}, {"name": "dealstage", "type": "string", "required": False}, {"name": "amount", "type": "number", "required": False}]},
        ]
    }


def test_custom_field_trigger_record(payload: dict, db: Session) -> dict:

    field_key = payload.get("field_key")
    entity_type = payload.get("entity_type", "task")
    entity_id = payload.get("entity_id")
    operator = payload.get("operator", "equals")
    expected_value = payload.get("value")

    if not field_key or not entity_id:
        raise HTTPException(status_code=400, detail="field_key and entity_id are required")

    cf = db.query(ProjectCustomField).filter(ProjectCustomField.field_key == field_key).first()
    actual_value = None
    if cf:
        cfv = db.query(ProjectCustomFieldValue).filter(
            ProjectCustomFieldValue.field_id == cf.id,
            ProjectCustomFieldValue.task_id == entity_id,
        ).first()
        actual_value = cfv.value if cfv else None

    matched = False
    if actual_value is not None:
        if operator == "equals":
            matched = str(actual_value) == str(expected_value)
        elif operator == "not_equals":
            matched = str(actual_value) != str(expected_value)
        elif operator == "contains":
            matched = str(expected_value).lower() in str(actual_value).lower()
        elif operator == "greater_than":
            try:
                matched = float(actual_value) > float(expected_value)
            except (ValueError, TypeError):
                matched = False
        elif operator == "less_than":
            try:
                matched = float(actual_value) < float(expected_value)
            except (ValueError, TypeError):
                matched = False

    return {
        "field_key": field_key,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actual_value": actual_value,
        "expected_value": expected_value,
        "operator": operator,
        "matched": matched,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BI — ad-hoc query, drilldown, cross-filter
# ──────────────────────────────────────────────────────────────────────────────

def run_adhoc_query(
    metric: str,
    dimensions: List[str],
    filters: dict,
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
    db: Session,
) -> dict:

    results = []

    if metric == "hours_logged":
        q = db.query(Imputation)
        if date_from:
            q = q.filter(Imputation.date >= date_from)
        if date_to:
            q = q.filter(Imputation.date <= date_to)
        if filters.get("project_id"):
            q = q.filter(Imputation.project_id == filters["project_id"])
        if filters.get("user_id"):
            q = q.filter(Imputation.user_id == filters["user_id"])
        rows = q.limit(limit).all()
        if "month" in dimensions:
            grouped: dict = {}
            for row in rows:
                key = str(row.date)[:7] if row.date else "unknown"
                grouped[key] = grouped.get(key, 0) + (row.hours or 0)
            results = [{"month": k, "hours": round(v, 2)} for k, v in sorted(grouped.items())]
        elif "user_id" in dimensions:
            grouped = {}
            for row in rows:
                k = row.user_id or "unknown"
                grouped[k] = grouped.get(k, 0) + (row.hours or 0)
            results = [{"user_id": k, "hours": round(v, 2)} for k, v in sorted(grouped.items(), key=lambda x: -x[1])]
        elif "project_id" in dimensions:
            grouped = {}
            for row in rows:
                k = row.project_id or "unknown"
                grouped[k] = grouped.get(k, 0) + (row.hours or 0)
            results = [{"project_id": k, "hours": round(v, 2)} for k, v in sorted(grouped.items(), key=lambda x: -x[1])]
        else:
            total = sum(row.hours or 0 for row in rows)
            results = [{"total_hours": round(total, 2)}]

    elif metric == "revenue":
        q = db.query(Invoice).filter(Invoice.status != "cancelled")
        if date_from:
            q = q.filter(Invoice.issue_date >= date_from)
        if date_to:
            q = q.filter(Invoice.issue_date <= date_to)
        if filters.get("project_id"):
            q = q.filter(Invoice.project_id == filters["project_id"])
        rows = q.limit(limit).all()
        if "month" in dimensions:
            grouped = {}
            for row in rows:
                key = str(row.issue_date)[:7] if row.issue_date else "unknown"
                grouped[key] = grouped.get(key, 0) + (row.total or 0)
            results = [{"month": k, "revenue": round(v, 2)} for k, v in sorted(grouped.items())]
        elif "status" in dimensions:
            grouped = {}
            for row in rows:
                k = str(row.status.value) if hasattr(row.status, 'value') else str(row.status)
                grouped[k] = grouped.get(k, 0) + (row.total or 0)
            results = [{"status": k, "revenue": round(v, 2)} for k, v in grouped.items()]
        else:
            results = [{"total_revenue": round(sum(r.total or 0 for r in rows), 2)}]

    elif metric == "task_count":
        q = db.query(Task)
        if filters.get("project_id"):
            q = q.filter(Task.project_id == filters["project_id"])
        if filters.get("status"):
            q = q.filter(Task.status == filters["status"])
        rows = q.limit(limit).all()
        if "status" in dimensions:
            grouped = {}
            for row in rows:
                k = str(row.status.value) if hasattr(row.status, 'value') else str(row.status)
                grouped[k] = grouped.get(k, 0) + 1
            results = [{"status": k, "count": v} for k, v in grouped.items()]
        elif "priority" in dimensions:
            grouped = {}
            for row in rows:
                k = str(row.priority.value) if hasattr(row.priority, 'value') else str(row.priority)
                grouped[k] = grouped.get(k, 0) + 1
            results = [{"priority": k, "count": v} for k, v in grouped.items()]
        else:
            results = [{"total_tasks": len(rows)}]

    elif metric == "ticket_count":
        q = db.query(Ticket)
        if date_from:
            q = q.filter(Ticket.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            q = q.filter(Ticket.created_at <= datetime.combine(date_to, datetime.max.time()))
        rows = q.limit(limit).all()
        if "status" in dimensions:
            grouped = {}
            for row in rows:
                k = str(row.status.value) if hasattr(row.status, 'value') else str(row.status)
                grouped[k] = grouped.get(k, 0) + 1
            results = [{"status": k, "count": v} for k, v in grouped.items()]
        else:
            results = [{"total_tickets": len(rows)}]

    return {
        "metric": metric,
        "dimensions": dimensions,
        "filters": filters,
        "results": results[:limit],
        "total_rows": len(results),
    }


def run_analytics_drilldown(
    metric: str,
    dimension: str,
    value: str,
    date_from: Optional[date],
    date_to: Optional[date],
    page: int,
    page_size: int,
    db: Session,
) -> dict:

    offset = (page - 1) * page_size
    rows = []

    if metric == "hours_logged":
        q = db.query(Imputation)
        if dimension == "project_id":
            q = q.filter(Imputation.project_id == value)
        elif dimension == "user_id":
            q = q.filter(Imputation.user_id == value)
        elif dimension == "month" and len(value) == 7:
            yr, mo = int(value[:4]), int(value[5:7])
            q = q.filter(
                func.strftime('%Y', Imputation.date) == str(yr),
                func.strftime('%m', Imputation.date) == f"{mo:02d}",
            )
        if date_from:
            q = q.filter(Imputation.date >= date_from)
        if date_to:
            q = q.filter(Imputation.date <= date_to)
        q.count()
        items = q.offset(offset).limit(page_size).all()
        rows = [
            {"id": i.id, "date": str(i.date), "hours": i.hours,
             "project_id": i.project_id, "user_id": i.user_id,
             "description": i.description}
            for i in items
        ]
    elif metric == "revenue":
        q = db.query(Invoice).filter(Invoice.status != "cancelled")
        if dimension == "project_id":
            q = q.filter(Invoice.project_id == value)
        elif dimension == "month" and len(value) == 7:
            yr, mo = int(value[:4]), int(value[5:7])
            q = q.filter(
                func.strftime('%Y', Invoice.issue_date) == str(yr),
                func.strftime('%m', Invoice.issue_date) == f"{mo:02d}",
            )
        elif dimension == "status":
            q = q.filter(Invoice.status == value)
        q.count()
        items = q.offset(offset).limit(page_size).all()
        rows = [
            {"id": i.id, "number": i.number, "total": i.total,
             "currency": i.currency,
             "status": str(i.status.value) if hasattr(i.status, 'value') else str(i.status),
             "issue_date": str(i.issue_date), "client_name": i.client_name}
            for i in items
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Metric '{metric}' not supported for drilldown")

    return {
        "metric": metric,
        "dimension": dimension,
        "value": value,
        "page": page,
        "page_size": page_size,
        "rows": rows,
    }


def run_analytics_cross_filter(payload: dict, db: Session) -> dict:

    active = payload.get("active_filters", {})
    metrics = payload.get("metrics", ["task_count"])
    result = {}

    if "task_count" in metrics:
        q = db.query(Task)
        if active.get("project_id"):
            q = q.filter(Task.project_id == active["project_id"])
        if active.get("status"):
            q = q.filter(Task.status == active["status"])
        if active.get("assignee_id"):
            q = q.filter(Task.assignee_id == active["assignee_id"])
        tasks = q.all()
        result["task_count"] = {"total": len(tasks), "by_status": {}, "by_priority": {}}
        for t in tasks:
            s = str(t.status.value) if hasattr(t.status, 'value') else str(t.status)
            p = str(t.priority.value) if hasattr(t.priority, 'value') else str(t.priority)
            result["task_count"]["by_status"][s] = result["task_count"]["by_status"].get(s, 0) + 1
            result["task_count"]["by_priority"][p] = result["task_count"]["by_priority"].get(p, 0) + 1

    if "hours_logged" in metrics:
        q = db.query(Imputation)
        if active.get("project_id"):
            q = q.filter(Imputation.project_id == active["project_id"])
        if active.get("user_id"):
            q = q.filter(Imputation.user_id == active["user_id"])
        imps = q.all()
        total_h = sum(i.hours or 0 for i in imps)
        by_proj: dict = {}
        for i in imps:
            by_proj[i.project_id or "N/A"] = by_proj.get(i.project_id or "N/A", 0) + (i.hours or 0)
        result["hours_logged"] = {
            "total": round(total_h, 2),
            "by_project": {k: round(v, 2) for k, v in sorted(by_proj.items(), key=lambda x: -x[1])[:20]},
        }

    return {"active_filters": active, "results": result}


# ──────────────────────────────────────────────────────────────────────────────
# STRIPE — payment links + webhook
# ──────────────────────────────────────────────────────────────────────────────

def create_payment_link_record(invoice_id: str, db: Session) -> dict:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured (missing STRIPE_SECRET_KEY). Add it to your environment."
        )
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("sent", "overdue"):
        raise HTTPException(status_code=400, detail=f"Invoice status must be 'sent' or 'overdue', got '{inv.status}'")
    if not inv.total or inv.total <= 0:
        raise HTTPException(status_code=400, detail="Invoice total must be greater than 0")

    if inv.stripe_payment_link_url:
        return {
            "invoice_id": invoice_id,
            "payment_link_url": inv.stripe_payment_link_url,
            "stripe_payment_link_id": inv.stripe_payment_link_id,
            "already_existed": True,
        }

    import httpx
    amount_cents = int(inv.total * 100)
    currency = (inv.currency or settings.DEFAULT_CURRENCY).lower()

    try:
        with httpx.Client(timeout=10.0) as client:
            price_resp = client.post(
                "https://api.stripe.com/v1/prices",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                data={
                    "unit_amount": str(amount_cents),
                    "currency": currency,
                    "product_data[name]": f"Factura {inv.number}",
                },
            )
            if price_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe price creation failed: {price_resp.text}")
            price_id = price_resp.json()["id"]

            link_resp = client.post(
                "https://api.stripe.com/v1/payment_links",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                data={
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": "1",
                    "metadata[invoice_id]": invoice_id,
                    "metadata[invoice_number]": inv.number,
                    "after_completion[type]": "redirect",
                    "after_completion[redirect][url]": f"{settings.FRONTEND_URL}/invoices?paid={invoice_id}",
                },
            )
            if link_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe payment link creation failed: {link_resp.text}")
            link_data = link_resp.json()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe API error: {str(e)}")

    inv.stripe_payment_link_id = link_data["id"]
    inv.stripe_payment_link_url = link_data["url"]
    db.commit()

    return {
        "invoice_id": invoice_id,
        "invoice_number": inv.number,
        "payment_link_url": link_data["url"],
        "stripe_payment_link_id": link_data["id"],
        "amount": inv.total,
        "currency": currency,
    }


def handle_stripe_webhook(raw_body: bytes, stripe_signature: Optional[str], db: Session) -> dict:
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if webhook_secret and stripe_signature:
        try:
            parts = {p.split("=")[0]: p.split("=")[1] for p in stripe_signature.split(",")}
            timestamp = parts.get("t", "")
            sig = parts.get("v1", "")
            signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Signature verification failed")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        invoice_id = (data.get("metadata") or {}).get("invoice_id")
        if invoice_id:
            inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if inv and inv.status != "paid":
                inv.status = "paid"
                inv.paid_date = date.today()
                inv.stripe_paid_at = datetime.now(timezone.utc)
                if data.get("payment_intent"):
                    inv.stripe_payment_intent_id = data["payment_intent"]
                db.commit()
                logger.info(f"Invoice {invoice_id} marked as paid via Stripe webhook")

    return {"received": True, "event_type": event_type}


# ──────────────────────────────────────────────────────────────────────────────
# COLLABORATIVE DOCS — CRDT snapshot persistence
# ──────────────────────────────────────────────────────────────────────────────

def save_collab_snapshot_record(document_id: str, body: bytes, user_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not body:
        raise HTTPException(status_code=400, detail="Request body must be the Yjs binary state vector")

    db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).update({"is_current": False})

    last = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()
    clock = (last.clock or 0) + 1 if last else 1

    snapshot = DocumentCollabSnapshot(
        document_id=document_id,
        state_vector=body,
        clock=clock,
        size_bytes=len(body),
        is_current=True,
        created_by=user_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "document_id": document_id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "created_at": str(snapshot.created_at),
    }


def load_collab_snapshot_record(document_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()

    if not snapshot:
        return {"document_id": document_id, "snapshot": None, "clock": 0}

    import base64
    return {
        "document_id": document_id,
        "id": snapshot.id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "state_vector_b64": base64.b64encode(snapshot.state_vector).decode("utf-8"),
        "created_at": str(snapshot.created_at),
    }


def list_collab_snapshots_records(document_id: str, limit: int, db: Session) -> list:
    snapshots = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).limit(limit).all()
    return [
        {"id": s.id, "clock": s.clock, "size_bytes": s.size_bytes,
         "is_current": s.is_current, "created_at": str(s.created_at)}
        for s in snapshots
    ]


# ── SCIM helpers ───────────────────────────────────────────────────────────────

def scim_bulk_error(bulk_id, status, detail) -> dict:
    return {
        "method": "UNKNOWN",
        "bulkId": bulk_id,
        "status": str(status),
        "response": {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": str(status),
            "detail": detail,
        }
    }
