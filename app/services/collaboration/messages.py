"""
Message service: send, edit, delete, history, threads, reactions, mentions, reads, pins, saves, drafts.
Emits realtime events on the bus and writes audit entries.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.models.collaboration import (
    CollaborationAttachment,
    CollaborationChannel, CollaborationConversation,
    CollaborationDirectConversation,
    CollaborationDraft, CollaborationGroupConversation,
    CollaborationMention,
    CollaborationMessage, CollaborationMessageVersion, CollaborationConversationMember,
    CollaborationNotification, CollaborationPinnedMessage, CollaborationRead,
    CollaborationReaction, CollaborationSavedMessage, CollaborationThread,
)
from app.models.user import User
from app.services.collaboration import audit_log, bus
from app.services.collaboration._bus import (
    conv_channel, user_channel, client_user_channel,
)
from app.services.collaboration._permissions import (
    _org, assert_conversation_access,
)
from app.services.collaboration._search import search_engine
from app.services.collaboration._storage import scan_dlp
import logging
from app.core.background import spawn

logger = logging.getLogger(__name__)


MENTION_RE = re.compile(r"@([a-zA-Z0-9_.\-]+)")


def _aware(dt: datetime) -> datetime:
    """Devuelve un datetime tz-aware (UTC) para comparaciones consistentes."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _resolve_conversation(db: Session, *, conversation_id: Optional[str], channel_id: Optional[str], direct_id: Optional[str], group_id: Optional[str]) -> CollaborationConversation:
    if conversation_id:
        c = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
        if not c:
            raise HTTPException(404, "Conversación no encontrada")
        return c
    if channel_id:
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == channel_id).first()
        if not ch:
            raise HTTPException(404, "Canal no encontrado")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == ch.conversation_id).first()
    if direct_id:
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.id == direct_id).first()
        if not d:
            raise HTTPException(404, "Direct no encontrada")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == d.conversation_id).first()
    if group_id:
        g = db.query(CollaborationGroupConversation).filter(CollaborationGroupConversation.id == group_id).first()
        if not g:
            raise HTTPException(404, "Grupo no encontrado")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == g.conversation_id).first()
    raise HTTPException(400, "Indica conversation_id / channel_id / direct_id / group_id")


# ── Notifications fan-out ────────────────────────────────────────────────────
def _notify_recipients(db: Session, *, organization_id: str, conv: CollaborationConversation, message: CollaborationMessage, mentions: list[CollaborationMention]) -> None:
    """Crea CollaborationNotification para los participantes, respetando:
        • Channel/Group membership: `notify_level` ('all' | 'mentions' | 'none')
          y `is_muted` por miembro.
        • Reglas globales (`CollaborationNotificationRule`) con scope='conversation'
          y target_id = conv.id por usuario; si `notify_messages='none'` se silencia
          ese usuario para esa conversación.
    Cada recipiente entra como (user_id, client_user_id, notify_level, is_muted).
    Las menciones siempre rompen el filtro 'mentions'.
    """
    from app.models.collaboration import CollaborationNotificationRule

    recipients: list[tuple[str | None, str | None, str, bool]] = []
    if conv.kind == "channel":
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conv.id).first()
        if not ch:
            return
        if ch.channel_type in {"public", "announcement", "project"}:
            from app.models.collaboration import CollaborationTeamMember
            # Team members → notify_level por defecto = 'all', no muted
            for tm in db.query(CollaborationTeamMember).filter(
                CollaborationTeamMember.team_id == ch.team_id,
            ).all():
                recipients.append((tm.user_id, None, "all", False))
        else:
            from app.models.collaboration import CollaborationChannelMember
            for cm in db.query(CollaborationChannelMember).filter(
                CollaborationChannelMember.channel_id == ch.id,
            ).all():
                recipients.append((cm.user_id, None, cm.notify_level or "all", bool(cm.is_muted)))
    elif conv.kind == "direct":
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conv.id).first()
        if d:
            for uid in {d.user_a_id, d.user_b_id}:
                if uid:
                    recipients.append((uid, None, "all", False))
            for cid in [d.client_user_a_id, d.client_user_b_id]:
                if cid:
                    recipients.append((None, cid, "all", False))
    elif conv.kind == "group":
        members = db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conv.id,
        ).all()
        for m in members:
            recipients.append((m.user_id, m.client_user_id, "all", bool(getattr(m, "is_muted", False))))

    mentioned_users = {m.mentioned_user_id for m in mentions if m.mentioned_user_id}
    mentioned_clients = {m.mentioned_client_user_id for m in mentions if m.mentioned_client_user_id}
    is_everyone = any(m.is_everyone for m in mentions)

    # Reglas por-conversación: { user_id: notify_messages }
    rule_rows = db.query(CollaborationNotificationRule).filter(
        CollaborationNotificationRule.organization_id == organization_id,
        CollaborationNotificationRule.scope == "conversation",
        CollaborationNotificationRule.target_id == conv.id,
    ).all()
    rule_by_user = {r.user_id: r.notify_messages for r in rule_rows if r.user_id}

    for u_id, c_id, notify_level, is_muted in recipients:
        # Excluir al autor
        if message.user_id and u_id == message.user_id:
            continue
        if message.client_user_id and c_id == message.client_user_id:
            continue
        is_mention = (u_id and u_id in mentioned_users) or (c_id and c_id in mentioned_clients) or is_everyone
        # Per-conversation rule manda — pero las menciones rompen el silencio
        per_conv = rule_by_user.get(u_id) if u_id else None
        if per_conv == "none" and not is_mention:
            continue
        if per_conv == "mentions" and not is_mention:
            continue
        # Membership-level
        if is_muted and not is_mention:
            continue
        if notify_level == "none" and not is_mention:
            continue
        if notify_level == "mentions" and not is_mention:
            continue
        kind = "mention" if is_mention else "message"
        db.add(CollaborationNotification(
            organization_id=organization_id,
            user_id=u_id, client_user_id=c_id,
            kind=kind,
            conversation_id=conv.id, message_id=message.id,
            title=("Mención en chat" if is_mention else "Nuevo mensaje"),
            body=(message.body or "")[:200],
            payload={"conversation_id": conv.id, "message_id": message.id},
        ))


def _publish_async(channel: str, event: dict) -> None:
    """Fire-and-forget publish."""
    try:
        loop = asyncio.get_event_loop()
        # auditoría 2026-08, P2-15: referencia fuerte para el publish.
        spawn(bus.publish(channel, event), name="collab-publish", loop=loop)
    except RuntimeError:
        # No loop (test mode) — best-effort
        asyncio.run(bus.publish(channel, event))


# ── Send / edit / delete ─────────────────────────────────────────────────────
def send_message(
    db: Session, user, *,
    body: str,
    conversation_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    direct_id: Optional[str] = None,
    group_id: Optional[str] = None,
    parent_message_id: Optional[str] = None,
    type: str = "text",
    metadata_json: Optional[dict] = None,
    mention_user_ids: Optional[list[str]] = None,
    mention_client_ids: Optional[list[str]] = None,
    is_everyone: bool = False,
    scheduled_for: Optional[datetime] = None,
    linked_task_id: Optional[str] = None,
    linked_ticket_id: Optional[str] = None,
    bot_id: Optional[str] = None,
) -> CollaborationMessage:
    org = _org(user)
    conv = _resolve_conversation(db, conversation_id=conversation_id, channel_id=channel_id, direct_id=direct_id, group_id=group_id)

    if not bot_id:
        assert_conversation_access(db, user, conv.id)
        enforce_abac(db, user, "collaboration_message", resource_id=conv.id, action="send")

    # DLP scan on body
    dlp_status, dlp_findings = scan_dlp(body)
    is_redacted = dlp_status == "blocked"

    msg = CollaborationMessage(
        organization_id=org,
        conversation_id=conv.id,
        thread_id=None,
        parent_message_id=parent_message_id,
        user_id=None if bot_id else user.id,
        bot_id=bot_id,
        type=type,
        status="visible",
        body="[REDACTED — DLP]" if is_redacted else body,
        body_html=None,
        metadata_json=metadata_json or {},
        is_redacted=is_redacted,
        scheduled_for=scheduled_for,
        sent_at=scheduled_for or datetime.now(timezone.utc),
        linked_task_id=linked_task_id,
        linked_ticket_id=linked_ticket_id,
    )
    db.add(msg)
    db.flush()

    # Thread root assignment
    if parent_message_id:
        thread = db.query(CollaborationThread).filter(
            CollaborationThread.root_message_id == parent_message_id,
        ).first()
        if not thread:
            thread = CollaborationThread(
                organization_id=org, conversation_id=conv.id,
                root_message_id=parent_message_id,
            )
            db.add(thread)
            db.flush()
        msg.thread_id = thread.id
        thread.reply_count = (thread.reply_count or 0) + 1
        thread.last_reply_at = datetime.now(timezone.utc)

    # Mentions
    mentions: list[CollaborationMention] = []
    for uid in (mention_user_ids or []):
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, mentioned_user_id=uid,
        )
        db.add(m)
        mentions.append(m)
    for cid in (mention_client_ids or []):
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, mentioned_client_user_id=cid,
        )
        db.add(m)
        mentions.append(m)
    if is_everyone:
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, is_everyone=True,
        )
        db.add(m)
        mentions.append(m)

    # Update conv last activity
    conv.last_activity_at = datetime.now(timezone.utc)
    conv.last_message_id = msg.id

    # Notifications fan-out — sólo si NO es programado al futuro
    _is_future = bool(scheduled_for) and _aware(scheduled_for) > datetime.now(timezone.utc)
    if not _is_future:
        _notify_recipients(db, organization_id=org, conv=conv, message=msg, mentions=mentions)

    # Audit + index
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.sent", entity_type="message", entity_id=msg.id,
        payload={"conversation_id": conv.id, "type": type, "dlp": dlp_status, "redacted": is_redacted},
    )
    db.commit()
    search_engine.index(db, msg.id)

    # Si está programado para el futuro: NO hacemos fan-out ni publish ahora.
    # El scheduler (_scheduler.py) entregará cuando llegue scheduled_for.
    if _is_future:
        return msg

    # Realtime publish
    event = {
        "type": "message.created",
        "conversation_id": conv.id,
        "message_id": msg.id,
        "payload": _serialize_message(db, msg),
    }
    _publish_async(conv_channel(conv.id), event)
    # User channels for unread badges + Web Push
    from app.services.collaboration import _push as push_svc
    for n in db.query(CollaborationNotification).filter(CollaborationNotification.message_id == msg.id).all():
        if n.user_id:
            _publish_async(user_channel(n.user_id), {"type": "notification.new", "payload": {"id": n.id}})
            try:
                delivered = push_svc.push_to_user(db, n.user_id, {
                    "title": n.title or "Contecflow Chat",
                    "body": (n.body or "")[:200],
                    "url": f"/chat?conversation={n.conversation_id or ''}",
                    "tag": n.conversation_id or "",
                    "notification_id": n.id,
                })
                if delivered:
                    n.delivered_push = True
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:
                logger.debug("send_message: fallo best-effort ignorado", exc_info=True)
        if n.client_user_id:
            _publish_async(client_user_channel(n.client_user_id), {"type": "notification.new", "payload": {"id": n.id}})
    db.commit()
    return msg


def edit_message(db: Session, user, message_id: str, body: str, metadata_json: Optional[dict] = None) -> CollaborationMessage:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if msg.user_id != user.id:
        raise HTTPException(403, "Solo puedes editar tus propios mensajes")
    if msg.status == "deleted":
        raise HTTPException(409, "Mensaje borrado")
    # Save version
    db.add(CollaborationMessageVersion(
        organization_id=org, message_id=msg.id, body=msg.body, body_html=msg.body_html,
        metadata_json=msg.metadata_json or {}, edited_by_user_id=user.id,
    ))
    msg.body = body
    if metadata_json is not None:
        msg.metadata_json = metadata_json
    msg.edited_at = datetime.now(timezone.utc)
    msg.status = "edited"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.edited", entity_type="message", entity_id=msg.id, payload={},
    )
    db.commit()
    search_engine.index(db, msg.id)
    _publish_async(conv_channel(msg.conversation_id), {
        "type": "message.updated", "conversation_id": msg.conversation_id,
        "message_id": msg.id, "payload": _serialize_message(db, msg),
    })
    return msg


def delete_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if msg.user_id != user.id and not getattr(user, "is_superadmin", False):
        # team_lead and admin can delete others' messages — relax later via policy
        if getattr(user, "role", None) not in ("admin",):
            raise HTTPException(403, "No puedes borrar mensajes de otros")
    msg.status = "deleted"
    msg.deleted_at = datetime.now(timezone.utc)
    msg.body = "[mensaje eliminado]"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.deleted", entity_type="message", entity_id=msg.id, payload={},
    )
    db.commit()
    search_engine.remove(db, msg.id)
    _publish_async(conv_channel(msg.conversation_id), {
        "type": "message.deleted", "conversation_id": msg.conversation_id,
        "message_id": msg.id, "payload": {"id": msg.id},
    })


def list_messages(db: Session, user, conversation_id: str, *, before: Optional[str] = None, limit: int = 50, thread_root: Optional[str] = None) -> list[CollaborationMessage]:
    assert_conversation_access(db, user, conversation_id)
    enforce_abac(db, user, "collaboration_message", resource_id=conversation_id, action="read")
    org = _org(user)
    q = db.query(CollaborationMessage).filter(
        CollaborationMessage.organization_id == org,
        CollaborationMessage.conversation_id == conversation_id,
    )
    if thread_root:
        q = q.filter(or_(CollaborationMessage.parent_message_id == thread_root, CollaborationMessage.id == thread_root))
    else:
        q = q.filter(CollaborationMessage.parent_message_id == None)
    if before:
        anchor = db.query(CollaborationMessage).filter(CollaborationMessage.id == before).first()
        if anchor:
            q = q.filter(CollaborationMessage.sent_at < anchor.sent_at)
    rows = q.order_by(CollaborationMessage.sent_at.desc()).limit(min(limit, 200)).all()
    rows.reverse()
    return rows


def get_message_versions(db: Session, user, message_id: str) -> list[CollaborationMessageVersion]:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    return db.query(CollaborationMessageVersion).filter(CollaborationMessageVersion.message_id == message_id).order_by(CollaborationMessageVersion.edited_at.asc()).all()


# ── Reactions ────────────────────────────────────────────────────────────────
def toggle_reaction(db: Session, user, message_id: str, emoji: str) -> dict:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    existing = db.query(CollaborationReaction).filter(
        CollaborationReaction.message_id == message_id,
        CollaborationReaction.user_id == user.id,
        CollaborationReaction.emoji == emoji,
    ).first()
    if existing:
        db.delete(existing)
        action = "reaction.removed"
    else:
        db.add(CollaborationReaction(
            organization_id=org, message_id=message_id, user_id=user.id, emoji=emoji,
        ))
        action = "reaction.added"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action=action, entity_type="message", entity_id=message_id, payload={"emoji": emoji},
    )
    db.commit()
    _publish_async(conv_channel(msg.conversation_id), {
        "type": action, "conversation_id": msg.conversation_id, "message_id": message_id,
        "payload": {"emoji": emoji, "user_id": user.id, "added": existing is None},
    })
    return {"toggled": True, "added": existing is None}


# ── Read markers ─────────────────────────────────────────────────────────────
def mark_read(db: Session, user, conversation_id: str, last_message_id: str) -> None:
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    row = db.query(CollaborationRead).filter(
        CollaborationRead.conversation_id == conversation_id,
        CollaborationRead.user_id == user.id,
    ).first()
    if row:
        row.last_message_id = last_message_id
        row.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(CollaborationRead(
            organization_id=org, conversation_id=conversation_id,
            user_id=user.id, last_message_id=last_message_id,
        ))

    # Keep notification-based unread counters in sync with read markers.
    # As soon as a user reads a conversation, unread notifications for that
    # conversation should disappear immediately.
    db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == user.id,
        CollaborationNotification.conversation_id == conversation_id,
        CollaborationNotification.is_read == False,
    ).update({
        "is_read": True,
        "read_at": datetime.now(timezone.utc),
    }, synchronize_session=False)

    db.commit()
    _publish_async(conv_channel(conversation_id), {
        "type": "read.updated", "conversation_id": conversation_id,
        "payload": {"user_id": user.id, "last_message_id": last_message_id},
    })


# ── Pin ──────────────────────────────────────────────────────────────────────
def pin_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    if not db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == msg.conversation_id,
        CollaborationPinnedMessage.message_id == message_id,
    ).first():
        db.add(CollaborationPinnedMessage(
            organization_id=org, conversation_id=msg.conversation_id,
            message_id=message_id, pinned_by=user.id,
        ))
        msg.is_pinned = True
        audit_log.write(
            db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
            action="message.pinned", entity_type="message", entity_id=message_id, payload={},
        )
        db.commit()
        _publish_async(conv_channel(msg.conversation_id), {
            "type": "message.pinned", "conversation_id": msg.conversation_id, "message_id": message_id,
            "payload": {"is_pinned": True},
        })


def unpin_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    row = db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == msg.conversation_id,
        CollaborationPinnedMessage.message_id == message_id,
    ).first()
    if row:
        db.delete(row)
        msg.is_pinned = False
        audit_log.write(
            db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
            action="message.unpinned", entity_type="message", entity_id=message_id, payload={},
        )
        db.commit()
        _publish_async(conv_channel(msg.conversation_id), {
            "type": "message.unpinned", "conversation_id": msg.conversation_id, "message_id": message_id,
            "payload": {"is_pinned": False},
        })


def list_pins(db: Session, user, conversation_id: str) -> list[dict]:
    assert_conversation_access(db, user, conversation_id)
    rows = db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == conversation_id,
    ).order_by(CollaborationPinnedMessage.pinned_at.desc()).all()
    out = []
    for r in rows:
        msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == r.message_id).first()
        if msg and msg.status != "deleted":
            out.append({
                "id": r.id, "message_id": r.message_id, "pinned_at": r.pinned_at,
                "preview": (msg.body or "")[:200], "user_id": msg.user_id,
            })
    return out


# ── Saved (per-user bookmark) ────────────────────────────────────────────────
def save_message(db: Session, user, message_id: str, note: Optional[str] = None) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    if not db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
        CollaborationSavedMessage.message_id == message_id,
    ).first():
        db.add(CollaborationSavedMessage(
            organization_id=org, user_id=user.id, message_id=message_id, note=note,
        ))
        db.commit()


def unsave_message(db: Session, user, message_id: str) -> None:
    row = db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
        CollaborationSavedMessage.message_id == message_id,
    ).first()
    if row:
        db.delete(row)
        db.commit()


def list_saved(db: Session, user) -> list[CollaborationSavedMessage]:
    return db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
    ).order_by(CollaborationSavedMessage.saved_at.desc()).limit(200).all()


# ── Drafts ──────────────────────────────────────────────────────────────────
def upsert_draft(db: Session, user, conversation_id: str, body: str, metadata_json: Optional[dict] = None, parent_message_id: Optional[str] = None) -> None:
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    row = db.query(CollaborationDraft).filter(
        CollaborationDraft.user_id == user.id,
        CollaborationDraft.conversation_id == conversation_id,
        CollaborationDraft.parent_message_id == parent_message_id,
    ).first()
    if row:
        row.body = body
        row.metadata_json = metadata_json or {}
    else:
        db.add(CollaborationDraft(
            organization_id=org, user_id=user.id, conversation_id=conversation_id,
            body=body, metadata_json=metadata_json or {}, parent_message_id=parent_message_id,
        ))
    db.commit()


def get_draft(db: Session, user, conversation_id: str, parent_message_id: Optional[str] = None) -> Optional[CollaborationDraft]:
    return db.query(CollaborationDraft).filter(
        CollaborationDraft.user_id == user.id,
        CollaborationDraft.conversation_id == conversation_id,
        CollaborationDraft.parent_message_id == parent_message_id,
    ).first()


# ── Serialize ────────────────────────────────────────────────────────────────
def _serialize_message(db: Session, msg: CollaborationMessage) -> dict:
    author_name = None
    author_avatar = None
    if msg.user_id:
        u = db.query(User).filter(User.id == msg.user_id).first()
        if u:
            author_name = u.full_name or u.username or u.email
            author_avatar = getattr(u, "avatar_url", None)
    elif msg.bot_id:
        from app.models.collaboration import CollaborationBotApp
        b = db.query(CollaborationBotApp).filter(CollaborationBotApp.id == msg.bot_id).first()
        if b:
            author_name = b.display_name
            author_avatar = b.avatar_url
    elif msg.client_user_id:
        from app.models.client_portal import ClientUser
        c = db.query(ClientUser).filter(ClientUser.id == msg.client_user_id).first()
        if c:
            author_name = c.full_name or c.email
    reactions = [
        {"emoji": r.emoji, "user_id": r.user_id, "client_user_id": r.client_user_id}
        for r in db.query(CollaborationReaction).filter(CollaborationReaction.message_id == msg.id).all()
    ]
    attachments = [
        {
            "id": a.id, "name": a.name, "mime_type": a.mime_type,
            "size_bytes": a.size_bytes, "av_status": a.av_status,
            "dlp_status": a.dlp_status, "is_quarantined": a.is_quarantined,
        }
        for a in db.query(CollaborationAttachment).filter(CollaborationAttachment.message_id == msg.id).all()
    ]
    return {
        "id": msg.id, "conversation_id": msg.conversation_id,
        "thread_id": msg.thread_id, "parent_message_id": msg.parent_message_id,
        "user_id": msg.user_id, "client_user_id": msg.client_user_id, "bot_id": msg.bot_id,
        "author_name": author_name, "author_avatar": author_avatar,
        "type": msg.type, "status": msg.status,
        "body": msg.body, "body_html": msg.body_html,
        "metadata_json": msg.metadata_json or {},
        "has_attachments": bool(attachments), "attachments": attachments,
        "reactions": reactions,
        "is_pinned": msg.is_pinned, "is_redacted": msg.is_redacted,
        "linked_task_id": msg.linked_task_id, "linked_ticket_id": msg.linked_ticket_id,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
    }
