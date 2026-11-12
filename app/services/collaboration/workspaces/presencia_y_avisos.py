"""Presencia de los usuarios, avisos de colaboracion y sus reglas.

Parte de `app.services.collaboration.workspaces` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.models.collaboration import (
    CollaborationNotification,
    CollaborationNotificationRule,
    CollaborationPresenceState,
)
from app.core.timeutil import utcnow
from app.services.collaboration._permissions import _org
from app.core.errores import ErrorDeDominio

from app.services.collaboration.workspaces._comun import _usuarios_por_id


# ── Presencia ────────────────────────────────────────────────────────────────

def list_presence(db: Session, user) -> list[dict]:
    filas = (
        db.query(CollaborationPresenceState)
        .filter(CollaborationPresenceState.organization_id == _org(user))
        .all()
    )
    usuarios = _usuarios_por_id(db, (r.user_id for r in filas))
    out = []
    for r in filas:
        u = usuarios.get(r.user_id)
        out.append({
            "user_id": r.user_id,
            "client_user_id": r.client_user_id,
            # Aqui el respaldo llega hasta el correo, a diferencia del resto:
            # una lista de presencia sin nombre no sirve de nada.
            "user_name": (u.full_name or u.username or u.email) if u else None,
            "status": r.status,
            "custom_message": r.custom_message,
            "is_in_call": r.is_in_call,
            "last_seen_at": r.last_seen_at,
        })
    return out


def update_presence(db: Session, user, *, status: str, custom_message) -> str:
    fila = (
        db.query(CollaborationPresenceState)
        .filter(CollaborationPresenceState.user_id == user.id)
        .first()
    )
    if not fila:
        fila = CollaborationPresenceState(organization_id=_org(user), user_id=user.id)
        db.add(fila)
    fila.status = status
    fila.custom_message = custom_message
    fila.last_seen_at = utcnow()
    db.commit()
    return fila.status


# ── Notificaciones ───────────────────────────────────────────────────────────

#: Tope de notificaciones que se devuelven de una vez. El buzon se lee de arriba
#: abajo y nadie baja de doscientas; sin tope, una cuenta antigua descarga miles.
MAX_NOTIFICACIONES = 200


def list_notifications(db: Session, user, *, unread_only: bool = False) -> list[dict]:
    q = db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == user.id
    )
    if unread_only:
        q = q.filter(CollaborationNotification.is_read == False)  # noqa: E712
    filas = (
        q.order_by(CollaborationNotification.created_at.desc())
        .limit(MAX_NOTIFICACIONES)
        .all()
    )
    return [
        {
            "id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
            "conversation_id": n.conversation_id, "message_id": n.message_id,
            "is_read": n.is_read, "payload": n.payload, "created_at": n.created_at,
        }
        for n in filas
    ]


def mark_all_notifications_read(db: Session, user) -> int:
    """Marca todas las no leidas. Devuelve cuantas.

    Es un `UPDATE` masivo a proposito: cargarlas para marcarlas una a una serian
    tantas consultas como notificaciones.
    """
    n = db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == user.id,
        CollaborationNotification.is_read == False,  # noqa: E712
    ).update({"is_read": True, "read_at": utcnow()})
    db.commit()
    return int(n)


def mark_notification_read(db: Session, user, notif_id: str) -> None:
    n = (
        db.query(CollaborationNotification)
        .filter(
            CollaborationNotification.id == notif_id,
            CollaborationNotification.user_id == user.id,
        )
        .first()
    )
    if not n:
        raise ErrorDeDominio(404, "Notificación no encontrada")
    n.is_read = True
    n.read_at = utcnow()
    db.commit()


# ── Reglas de notificacion ───────────────────────────────────────────────────

def list_notification_rules(db: Session, user) -> list[dict]:
    filas = (
        db.query(CollaborationNotificationRule)
        .filter(CollaborationNotificationRule.user_id == user.id)
        .all()
    )
    return [
        {
            "id": r.id, "scope": r.scope, "target_id": r.target_id,
            "notify_messages": r.notify_messages, "desktop_push": r.desktop_push,
            "email_digest": r.email_digest,
            "do_not_disturb_from": r.do_not_disturb_from,
            "do_not_disturb_to": r.do_not_disturb_to,
        }
        for r in filas
    ]


def upsert_notification_rule(db: Session, user, cambios: dict) -> str:
    """Crea o actualiza la regla de ese ambito y objetivo. Devuelve su id.

    `scope` y `target_id` son la clave: los cambios se aplican encima de la fila
    que ya exista, no crean una segunda.
    """
    org = _org(user)
    fila = (
        db.query(CollaborationNotificationRule)
        .filter(
            CollaborationNotificationRule.user_id == user.id,
            CollaborationNotificationRule.scope == cambios.get("scope"),
            CollaborationNotificationRule.target_id == cambios.get("target_id"),
        )
        .first()
    )
    if not fila:
        fila = CollaborationNotificationRule(
            organization_id=org, user_id=user.id,
            scope=cambios.get("scope"), target_id=cambios.get("target_id"),
        )
        db.add(fila)
    for k, v in cambios.items():
        setattr(fila, k, v)
    db.commit()
    return fila.id
