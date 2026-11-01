"""
notifications.py — In-app notification service.

Usage:
    from app.services.notifications import notify_user, notify_role
    notify_user(db, user_id, "task_assigned", "Nueva tarea asignada",
                "Luis te asignó: Fix login bug", resource="tasks", resource_id=task.id)

Multi-worker WebSocket delivery:
    When REDIS_URL is set, notify_user also publishes the notification payload
    to the Redis channel "contecflow:ws:<user_id>" so every worker can push it
    to the client immediately, regardless of which process holds the WS connection.
    Without Redis, the WS polling loop delivers it within ~15 seconds.
"""
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.enterprise import Notification
from app.models.user import User
from app.core.config import settings
from app.models.enterprise import ProjectPermission

logger = logging.getLogger(__name__)
_REDIS_URL: Optional[str] = settings.REDIS_URL or ""


def _push_ws_notification(user_id: str, payload: dict) -> None:
    """Fire-and-forget: publish notification to Redis WS channel if available."""
    if not _REDIS_URL:
        return
    try:
        import redis as sync_redis
        r = sync_redis.from_url(_REDIS_URL, decode_responses=True)
        r.publish(f"contecflow:ws:{user_id}", json.dumps(payload))
        r.close()
    except Exception as exc:
        logger.debug(f"WS Redis push failed (non-critical): {exc}")


NOTIFICATION_ICONS = {
    "task_assigned":     ("🎯", "#00d4ff"),
    "task_mentioned":    ("💬", "#7c3aed"),
    "task_due_soon":     ("⏰", "#ffb800"),
    "task_overdue":      ("🔴", "#ff4757"),
    "sprint_started":    ("⚡", "#00d4ff"),
    "sprint_ending":     ("🏁", "#ffb800"),
    "expense_approved":  ("✅", "#00e5a0"),
    "expense_rejected":  ("❌", "#ff4757"),
    "ticket_assigned":   ("🎫", "#00d4ff"),
    "ticket_replied":    ("💬", "#7c3aed"),
    "ticket_resolved":   ("✓",  "#00e5a0"),
    "ticket_created":    ("🎫", "#7a8aaa"),
    "ticket_updated":    ("🔄", "#7a8aaa"),
    "ticket_sla_warning":("⏳", "#ffb800"),
    "ticket_sla_breached":("🔴", "#ff4757"),
    "ticket_escalated":  ("⬆️", "#ff6b35"),
    "approval_requested":("📝", "#7c3aed"),
    "project_risk_high": ("⚠️", "#ff4757"),
    "timesheet_reminder":("📋", "#ffb800"),
    "timesheet_approved":("✅", "#00e5a0"),
    "budget_warning":    ("💰", "#ffb800"),
    "mention":           ("@",  "#7c3aed"),
    "automation":        ("⚙️", "#00d4ff"),
    "system":            ("🔔", "#7a8aaa"),
}


def notify_user(
    db: Session,
    user_id: str,
    ntype: str,
    title: str,
    body: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
) -> Notification:
    icon, color = NOTIFICATION_ICONS.get(ntype, ("🔔", "#7a8aaa"))
    n = Notification(
        user_id=user_id,
        type=ntype,
        title=title,
        body=body,
        icon=icon,
        color=color,
        resource=resource,
        resource_id=resource_id,
        action_url=action_url,
    )
    db.add(n)
    # Push to WS immediately via Redis (cross-worker) if available.
    # This is best-effort — the WS polling loop is the guaranteed fallback.
    _push_ws_notification(user_id, {
        "type": "notification_push",
        "ntype": ntype,
        "title": title,
        "body": body,
        "resource": resource,
        "resource_id": resource_id,
        "action_url": action_url,
    })
    return n


def notify_role(
    db: Session,
    role: str,
    ntype: str,
    title: str,
    body: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
) -> int:
    """Notify all active users with a given role. Returns count notified."""
    users = db.query(User).filter(User.role == role, User.is_active == True).all()
    for u in users:
        notify_user(db, u.id, ntype, title, body, resource, resource_id, action_url)
    return len(users)


def notify_project_team(
    db: Session,
    project_id: str,
    ntype: str,
    title: str,
    body: Optional[str] = None,
    exclude_user_id: Optional[str] = None,
) -> int:
    """Notify everyone with access to a project."""
    # Get all users with explicit project permissions
    perms = db.query(ProjectPermission).filter(
        ProjectPermission.project_id == project_id
    ).all()
    notified = set()
    for p in perms:
        if p.user_id != exclude_user_id:
            notify_user(db, p.user_id, ntype, title, body,
                       resource="projects", resource_id=project_id,
                       action_url=f"/projects?id={project_id}")
            notified.add(p.user_id)
    return len(notified)
