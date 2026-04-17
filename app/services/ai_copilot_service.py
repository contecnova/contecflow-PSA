"""AI Copilot contextual suggestions service.

Provides inline AI suggestions for Gantt scheduling, timesheet anomaly
detection and service-desk KB article recommendations.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket, KBArticle
from app.models.task import Task

logger = logging.getLogger(__name__)


def get_ai_gantt_suggestions(project_id: str, db: Session) -> dict:

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    today = date.today()
    suggestions = []

    for t in tasks:
        status_val = str(getattr(t.status, "value", t.status))
        if status_val in ("done", "closed", "cancelled"):
            continue

        if t.due_date and t.due_date < today:
            overdue_days = (today - t.due_date).days
            suggestions.append({
                "task_id": t.id, "task_title": t.title,
                "type": "overdue",
                "severity": "high" if overdue_days > 7 else "medium",
                "message": f"Task is {overdue_days} day(s) overdue.",
                "suggestions": [
                    "Reassign to available resource",
                    "Split into smaller tasks to unblock progress",
                    "Review scope — consider deferring non-critical items",
                ],
            })
        elif (hasattr(t, "start_date") and t.start_date and t.due_date
              and t.start_date < today < t.due_date):
            total_days = (t.due_date - t.start_date).days or 1
            elapsed_pct = (today - t.start_date).days / total_days
            progress = getattr(t, "progress", None) or 0
            if elapsed_pct >= 0.5 and progress < 20:
                suggestions.append({
                    "task_id": t.id, "task_title": t.title,
                    "type": "stalled",
                    "severity": "medium",
                    "message": f"{int(elapsed_pct*100)}% of duration elapsed but only {progress}% complete.",
                    "suggestions": [
                        "Check for blockers in comments",
                        "Schedule a quick sync with the assignee",
                        "Consider parallel execution if dependencies allow",
                    ],
                })

    return {
        "project_id": project_id,
        "project_name": proj.name,
        "suggestions_count": len(suggestions),
        "suggestions": suggestions,
        "analysed_at": str(datetime.utcnow()),
    }


def get_ai_timesheet_anomalies(user_id: str, db: Session) -> dict:

    cutoff = date.today() - timedelta(days=30)
    entries = db.query(Imputation).filter(
        Imputation.user_id == user_id,
        Imputation.date >= cutoff,
    ).order_by(Imputation.date).all()

    anomalies = []
    daily_hours: Dict[str, float] = {}
    for e in entries:
        k = str(e.date)
        daily_hours[k] = daily_hours.get(k, 0) + (e.hours or 0)

    for day, hours in daily_hours.items():
        if hours > 12:
            anomalies.append({
                "type": "high_hours", "date": day, "value": hours,
                "message": f"{hours}h logged on {day} — exceeds 12h threshold",
                "suggestion": "Verify these hours are correct or split across days if entered in bulk",
            })

    if entries:
        prev_date = entries[0].date
        for e in entries[1:]:
            gap_days = (e.date - prev_date).days
            if gap_days > 7:
                anomalies.append({
                    "type": "gap", "date": str(prev_date), "value": gap_days,
                    "message": f"{gap_days}-day gap in timesheet entries",
                    "suggestion": "Missing time entries for the period? Please fill in timesheets.",
                })
            prev_date = e.date

    proj_ids = {e.project_id for e in entries if e.project_id}
    closed_projs = db.query(Project).filter(
        Project.id.in_(list(proj_ids)),
        Project.status.in_(["closed", "cancelled", "archived"]),
    ).all()
    closed_ids = {p.id for p in closed_projs}
    if closed_ids:
        anomalies.append({
            "type": "closed_project_billing",
            "project_ids": list(closed_ids),
            "message": "Time entries found on closed/cancelled projects",
            "suggestion": "Review and reassign to the correct active project",
        })

    return {
        "user_id": user_id,
        "period": {"from": str(cutoff), "to": str(date.today())},
        "total_entries": len(entries),
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "analysed_at": str(datetime.utcnow()),
    }


def get_ai_ticket_kb_suggestions(ticket_id: str, db: Session) -> dict:

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    text = f"{ticket.title or ''} {ticket.description or ''}".lower()
    words = set(w for w in text.split() if len(w) > 3)
    articles = db.query(KBArticle).filter(KBArticle.is_published == True).limit(200).all()

    scored = []
    for art in articles:
        art_text = f"{art.title or ''} {art.content or ''}".lower()
        matches = sum(1 for w in words if w in art_text)
        if matches > 0:
            scored.append({
                "article_id": art.id,
                "title": art.title,
                "score": matches,
                "url": f"/api/v1/sd/kb/articles/{art.id}",
            })
    scored.sort(key=lambda x: -x["score"])

    return {
        "ticket_id": ticket_id,
        "ticket_title": ticket.title,
        "suggestions": scored[:5],
        "analysed_at": str(datetime.utcnow()),
    }
