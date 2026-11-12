"""Actividad y menciones: eventos, avisos de mencion y feeds.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.activity import ActivityEvent
from app.models.enterprise import Notification
from app.models.enterprise import NotificationType
from app.models.epics import Mention
from app.models.task import Task
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL HELPERS (emit_activity, create_notification, parse_and_store_mentions)
# ═══════════════════════════════════════════════════════════════════════════════

def emit_activity(
    db: Session,
    entity_type: str,
    entity_id: str,
    entity_code: Optional[str],
    actor: User,
    verb: str,
    detail: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_name: Optional[str] = None,
) -> None:
    event = ActivityEvent(
        organization_id=getattr(actor, "organization_id", None),
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=entity_code,
        actor_id=actor.id,
        actor_name=actor.full_name or actor.email,
        verb=verb,
        detail=detail,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
    )
    db.add(event)


def create_notification(
    db: Session,
    user_id: str,
    notif_type,
    title: str,
    body: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
) -> None:
    n = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        resource=resource,
        resource_id=resource_id,
        action_url=action_url,
        icon="💬",
        color="#7c3aed",
    )
    db.add(n)


def parse_and_store_mentions(
    db: Session,
    content: str,
    actor: User,
    entity_type: str,
    entity_id: str,
    action_url: Optional[str] = None,
) -> List[str]:
    """
    Extract @<user_id> or @<username> tags from content, persist Mention rows
    and create Notifications for each mentioned user.
    Returns list of mentioned user_ids found.
    """

    pattern = r"@([A-Za-z0-9_\-\.]+)"
    tokens = re.findall(pattern, content)
    if not tokens:
        return []

    mentioned_ids: List[str] = []
    for token in tokens:
        user = (
            db.query(User).filter(
                (User.id == token) | (User.username == token)
            ).first()
        )
        if not user or user.id == actor.id:
            continue
        if user.id in mentioned_ids:
            continue
        mentioned_ids.append(user.id)

        mention = Mention(
            mentioned_user=user.id,
            mentioned_by=actor.id,
            entity_type=entity_type,
            entity_id=entity_id,
            context_text=content[:500],
        )
        db.add(mention)

        snippet = content[:120] + ("…" if len(content) > 120 else "")
        create_notification(
            db, user.id, NotificationType.mention,
            title=f"{actor.full_name or actor.email} te ha mencionado",
            body=snippet,
            resource=entity_type,
            resource_id=entity_id,
            action_url=action_url,
        )

    if mentioned_ids:
        db.commit()
    return mentioned_ids


# ═══════════════════════════════════════════════════════════════════════════════
# SSE LIVE UPDATES HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_new_notifications(db: Session, user_id: str, since: datetime) -> list:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.created_at > since)
        .order_by(Notification.created_at)
        .all()
    )


def get_new_activity_events(db: Session, user_id: str, since: datetime) -> list:
    return (
        db.query(ActivityEvent)
        .filter(ActivityEvent.created_at > since, ActivityEvent.actor_id != user_id)
        .limit(20)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY FEED
# ═══════════════════════════════════════════════════════════════════════════════

def activity_feed_payload(
    db: Session,
    entity_type: str,
    entity_id: str,
    limit: int,
    before: Optional[str],
) -> list:
    q = db.query(ActivityEvent).filter(
        ActivityEvent.entity_type == entity_type,
        ActivityEvent.entity_id == entity_id,
    )
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
            q = q.filter(ActivityEvent.created_at < before_dt)
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            pass
    events = q.order_by(ActivityEvent.created_at.desc()).limit(limit).all()
    return [{
        "id": e.id,
        "actor_name": e.actor_name,
        "actor_id": e.actor_id,
        "verb": e.verb,
        "detail": e.detail,
        "target_type": e.target_type,
        "target_name": e.target_name,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


def project_activity_payload(db: Session, project_id: str, limit: int) -> list:
    task_ids = [t.id for t in db.query(Task.id).filter(Task.project_id == project_id).all()]
    q = db.query(ActivityEvent).filter(
        ((ActivityEvent.entity_type == "project") & (ActivityEvent.entity_id == project_id)) |
        ((ActivityEvent.entity_type == "task") & (ActivityEvent.entity_id.in_(task_ids)))
    ).order_by(ActivityEvent.created_at.desc()).limit(limit)
    events = q.all()
    return [{
        "id": e.id,
        "entity_type": e.entity_type,
        "entity_code": e.entity_code,
        "actor_name": e.actor_name,
        "verb": e.verb,
        "detail": e.detail,
        "target_name": e.target_name,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


# ═══════════════════════════════════════════════════════════════════════════════
# MENTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def my_mentions_payload(
    db: Session,
    current_user: User,
    unread_only: bool,
    limit: int,
) -> list:
    q = db.query(Mention).filter(Mention.mentioned_user == current_user.id)
    if unread_only:
        q = q.filter(Mention.is_read == False)
    mentions = q.order_by(Mention.created_at.desc()).limit(limit).all()

    actor_ids = {m.mentioned_by for m in mentions if m.mentioned_by}
    actors = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(actor_ids)).all()}

    return [{
        "id": m.id,
        "entity_type": m.entity_type,
        "entity_id": m.entity_id,
        "mentioned_by_name": actors.get(m.mentioned_by, "—"),
        "context": m.context_text,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in mentions]


def mark_mention_read_record(db: Session, mention_id: str, current_user: User) -> dict:
    m = db.query(Mention).filter(
        Mention.id == mention_id,
        Mention.mentioned_user == current_user.id,
    ).first()
    if not m:
        raise ErrorDeDominio(404)
    m.is_read = True
    db.commit()
    return {"ok": True}
