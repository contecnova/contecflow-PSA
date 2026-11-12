"""Conversaciones directas y de grupo: alta, miembros, detalle y listado del usuario.

Parte de `app.services.collaboration.workspaces` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session
from app.models.collaboration import (
    CollaborationChannel,
    CollaborationConversation,
    CollaborationConversationMember,
    CollaborationDirectConversation,
    CollaborationGroupConversation,
    CollaborationNotification,
)
from app.models.user import User
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org
from app.core.errores import ErrorDeDominio

from app.services.collaboration.workspaces._comun import _nombre_de, _usuarios_por_id
from app.services.collaboration.workspaces.equipos_y_canales import (
    get_or_create_workspace,
    list_channels,
)


# ── Direct ──────────────────────────────────────────────────────────────────
def open_direct(db: Session, user, *, target_user_id: Optional[str] = None, target_client_id: Optional[str] = None) -> CollaborationDirectConversation:
    if not target_user_id and not target_client_id:
        raise ErrorDeDominio(400, "Indica user_id o client_user_id")
    if target_user_id == user.id:
        raise ErrorDeDominio(400, "No puedes abrir un chat directo contigo mismo")
    org = _org(user)
    ws = get_or_create_workspace(db, user)
    if target_user_id:
        # Validar que el target existe en la misma org
        from app.models.user import User as _U
        target = db.query(_U).filter(_U.id == target_user_id, _U.organization_id == org).first()
        if not target:
            raise ErrorDeDominio(404, "Usuario no encontrado")
        a, b = sorted([user.id, target_user_id])
        existing = db.query(CollaborationDirectConversation).filter(
            CollaborationDirectConversation.organization_id == org,
            CollaborationDirectConversation.user_a_id == a,
            CollaborationDirectConversation.user_b_id == b,
        ).first()
        if existing:
            return existing
        conv = CollaborationConversation(organization_id=org, kind="direct", workspace_id=ws.id)
        db.add(conv)
        db.flush()
        d = CollaborationDirectConversation(
            organization_id=org, workspace_id=ws.id, conversation_id=conv.id,
            user_a_id=a, user_b_id=b,
        )
        db.add(d)
        db.commit()
        return d
    # client direct
    conv = CollaborationConversation(organization_id=org, kind="direct", workspace_id=ws.id)
    db.add(conv)
    db.flush()
    d = CollaborationDirectConversation(
        organization_id=org, workspace_id=ws.id, conversation_id=conv.id,
        user_a_id=user.id, user_b_id=user.id,
        client_user_a_id=target_client_id,
    )
    db.add(d)
    db.commit()
    return d


# ── Group ────────────────────────────────────────────────────────────────────
def create_group(db: Session, user, *, title: Optional[str], user_ids: list[str], client_user_ids: list[str]) -> CollaborationGroupConversation:
    org = _org(user)
    ws = get_or_create_workspace(db, user)
    conv = CollaborationConversation(organization_id=org, kind="group", workspace_id=ws.id)
    db.add(conv)
    db.flush()
    g = CollaborationGroupConversation(
        organization_id=org, workspace_id=ws.id, conversation_id=conv.id,
        title=title or None, created_by=user.id,
    )
    db.add(g)
    db.flush()
    members = set(user_ids) | {user.id}
    for uid in members:
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conv.id, group_id=g.id,
            user_id=uid, is_admin=(uid == user.id),
        ))
    for cid in client_user_ids or []:
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conv.id, group_id=g.id,
            client_user_id=cid,
        ))
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="group.created", entity_type="group", entity_id=g.id,
        payload={"title": title, "users": list(members), "clients": client_user_ids or []},
    )
    db.commit()
    return g


# ── Conversation listing for sidebar ─────────────────────────────────────────
def list_conversations_for_user(db: Session, user) -> list[dict]:
    """Returns a unified flat list (channels + directs + groups) for sidebar."""
    org = _org(user)
    out = []

    # Build a per-conversation unread counter from unread notifications.
    # This keeps unread_count consistent across all conversation kinds.
    unread_rows = db.query(
        CollaborationNotification.conversation_id,
        func.count(CollaborationNotification.id),
    ).filter(
        CollaborationNotification.user_id == user.id,
        CollaborationNotification.is_read == False,
        CollaborationNotification.conversation_id.isnot(None),
    ).group_by(
        CollaborationNotification.conversation_id,
    ).all()
    unread_by_conv = {str(conv_id): int(cnt) for conv_id, cnt in unread_rows if conv_id}

    conv_ids = set()

    # Channels via team membership + private channel membership
    channels = list_channels(db, user)
    for ch in channels:
        conv_ids.add(str(ch.conversation_id))
        out.append({
            "id": ch.conversation_id, "kind": "channel",
            "title": f"# {ch.name}", "team_id": ch.team_id,
            "channel_type": ch.channel_type, "project_id": ch.project_id,
            "icon": None,
            "unread_count": unread_by_conv.get(str(ch.conversation_id), 0),
        })

    # Directs where user participates — bulk-load peers para evitar N+1
    direct_rows = db.query(CollaborationDirectConversation).filter(
        CollaborationDirectConversation.organization_id == org,
        or_(
            CollaborationDirectConversation.user_a_id == user.id,
            CollaborationDirectConversation.user_b_id == user.id,
        ),
    ).all()
    peer_ids = {d.user_b_id if d.user_a_id == user.id else d.user_a_id for d in direct_rows}
    peers_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_([pid for pid in peer_ids if pid])).all()
    } if peer_ids else {}
    for d in direct_rows:
        other = d.user_b_id if d.user_a_id == user.id else d.user_a_id
        u = peers_by_id.get(other)
        title = (u.full_name or u.username or "Usuario") if u else "Usuario"
        conv_ids.add(str(d.conversation_id))
        out.append({
            "id": d.conversation_id, "kind": "direct",
            "title": title, "peer_user_id": other,
            "unread_count": unread_by_conv.get(str(d.conversation_id), 0),
        })

    # Groups via membership
    group_rows = db.query(CollaborationGroupConversation).join(
        CollaborationConversationMember,
        and_(
            CollaborationConversationMember.group_id == CollaborationGroupConversation.id,
            CollaborationConversationMember.user_id == user.id,
        ),
    ).filter(CollaborationGroupConversation.organization_id == org).all()
    for g in group_rows:
        conv_ids.add(str(g.conversation_id))
        out.append({
            "id": g.conversation_id, "kind": "group",
            "title": g.title or "Grupo",
            "unread_count": unread_by_conv.get(str(g.conversation_id), 0),
        })

    if conv_ids:
        conv_meta_rows = db.query(
            CollaborationConversation.id,
            CollaborationConversation.last_activity_at,
            CollaborationConversation.last_message_id,
        ).filter(
            CollaborationConversation.organization_id == org,
            CollaborationConversation.id.in_(list(conv_ids)),
        ).all()
        meta_by_conv = {
            str(cid): {
                "last_activity_at": last_activity_at,
                "last_message_id": last_message_id,
            }
            for cid, last_activity_at, last_message_id in conv_meta_rows
        }
        for item in out:
            meta = meta_by_conv.get(str(item.get("id"))) or {}
            item["last_activity_at"] = meta.get("last_activity_at")
            item["last_message_id"] = meta.get("last_message_id")

    out.sort(
        key=lambda c: (c.get("last_activity_at").timestamp() if c.get("last_activity_at") else 0),
        reverse=True,
    )
    return out


# ── Miembros de una conversacion ─────────────────────────────────────────────

def _grupo_de_conversacion(db: Session, conversation_id: str, *, verbo: str):
    """La conversacion y su grupo, comprobando que ES un grupo.

    `verbo` entra en el mensaje de error para que diga «añadir» o «quitar», que
    es lo que distinguia los dos mensajes del endpoint.
    """
    conv = (
        db.query(CollaborationConversation)
        .filter(CollaborationConversation.id == conversation_id)
        .first()
    )
    if not conv:
        raise ErrorDeDominio(404, "Conversación no encontrada")
    if conv.kind != "group":
        if verbo == "añadir":
            raise ErrorDeDominio(
                400,
                "Solo se pueden añadir miembros a grupos. Para canales usa "
                "/channels/{id}/members.",
            )
        raise ErrorDeDominio(400, "Solo se pueden quitar miembros de grupos.")
    return conv


def list_conversation_members(db: Session, user, conversation_id: str) -> list[dict]:
    from app.services.collaboration._permissions import assert_conversation_access

    assert_conversation_access(db, user, conversation_id)
    filas = (
        db.query(CollaborationConversationMember)
        .filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.organization_id == _org(user),
        )
        .all()
    )
    usuarios = _usuarios_por_id(db, (m.user_id for m in filas))
    out = []
    for m in filas:
        if m.user_id:
            out.append({
                "id": m.id,
                "user_id": m.user_id,
                "user_name": _nombre_de(usuarios.get(m.user_id)),
                "is_admin": bool(m.is_admin),
                "kind": "user",
            })
        elif m.client_user_id:
            out.append({
                "id": m.id,
                "client_user_id": m.client_user_id,
                "is_admin": False,
                "kind": "client",
            })
    return out


def add_conversation_members(
    db: Session, user, conversation_id: str,
    user_ids: list[str], client_user_ids: list[str],
) -> int:
    """Añade miembros a un grupo. Devuelve cuantos se han añadido de verdad.

    Los que ya estaban se saltan sin contarlos, y esa comprobacion se hace de
    una vez para todos: el endpoint consultaba la existencia **por cada id**.
    """
    from app.services.collaboration._permissions import assert_conversation_access

    assert_conversation_access(db, user, conversation_id)
    conv = _grupo_de_conversacion(db, conversation_id, verbo="añadir")
    g = (
        db.query(CollaborationGroupConversation)
        .filter(CollaborationGroupConversation.conversation_id == conversation_id)
        .first()
    )
    if not g:
        raise ErrorDeDominio(404, "Grupo no encontrado")
    if not user_ids and not client_user_ids:
        raise ErrorDeDominio(400, "Indica user_ids o client_user_ids")

    org = _org(user)
    ya = db.query(
        CollaborationConversationMember.user_id,
        CollaborationConversationMember.client_user_id,
    ).filter(
        CollaborationConversationMember.conversation_id == conversation_id
    ).all()
    usuarios_ya = {u for u, _ in ya if u}
    clientes_ya = {c for _, c in ya if c}

    añadidos = 0
    for uid in user_ids:
        if uid in usuarios_ya:
            continue
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conversation_id, group_id=g.id,
            user_id=uid, is_admin=False,
        ))
        usuarios_ya.add(uid)
        añadidos += 1
    for cid in client_user_ids:
        if cid in clientes_ya:
            continue
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conversation_id, group_id=g.id,
            client_user_id=cid,
        ))
        clientes_ya.add(cid)
        añadidos += 1

    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="group.members.added", entity_type="group", entity_id=g.id,
        payload={"users": user_ids, "clients": client_user_ids},
    )
    db.commit()
    _ = conv
    return añadidos


def remove_conversation_member(
    db: Session, user, conversation_id: str, target_user_id: str
) -> None:
    """Quita a alguien de un grupo.

    **Solo un admin del grupo puede expulsar a otro; cualquiera puede salirse a
    si mismo.** Esa asimetria es deliberada y estaba en el endpoint: se conserva
    tal cual, porque uniformarla dejaria a la gente atrapada en un grupo o
    permitiria expulsiones a cualquiera.
    """
    from app.services.collaboration._permissions import assert_conversation_access

    assert_conversation_access(db, user, conversation_id)
    conv = _grupo_de_conversacion(db, conversation_id, verbo="quitar")
    member = (
        db.query(CollaborationConversationMember)
        .filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.user_id == target_user_id,
        )
        .first()
    )
    if not member:
        raise ErrorDeDominio(404, "Miembro no encontrado")

    if target_user_id != user.id:
        actor = (
            db.query(CollaborationConversationMember)
            .filter(
                CollaborationConversationMember.conversation_id == conversation_id,
                CollaborationConversationMember.user_id == user.id,
            )
            .first()
        )
        if not actor or not actor.is_admin:
            raise ErrorDeDominio(403, "Solo un admin del grupo puede quitar miembros")

    db.delete(member)
    audit_log.write(
        db, organization_id=_org(user), actor_user_id=user.id, actor_client_id=None,
        action="group.member.removed", entity_type="group", entity_id=conv.id,
        payload={"user_id": target_user_id},
    )
    db.commit()


def conversation_detail(db: Session, user, conversation_id: str) -> dict:
    """El detalle de una conversacion, con su titulo segun el tipo.

    Devuelve las claves que espera `ConversationOut`. El titulo se construye
    distinto para canal, directo y grupo, y en el caso del grupo los miembros se
    cargan **en una consulta** — el endpoint pedia un `User` por miembro.
    """
    from app.services.collaboration._permissions import assert_conversation_access

    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    conv = (
        db.query(CollaborationConversation)
        .filter(
            CollaborationConversation.id == conversation_id,
            CollaborationConversation.organization_id == org,
        )
        .first()
    )
    if not conv:
        raise ErrorDeDominio(404, "Conversación no encontrada")

    titulo = None
    extra: dict = {}
    miembros: list[dict] = []

    if conv.kind == "channel":
        ch = (
            db.query(CollaborationChannel)
            .filter(
                CollaborationChannel.conversation_id == conv.id,
                CollaborationChannel.organization_id == org,
            )
            .first()
        )
        titulo = f"# {ch.name}" if ch else None
        if ch:
            extra = {
                "team_id": ch.team_id, "channel_type": ch.channel_type,
                "topic": ch.topic, "project_id": ch.project_id,
            }
    elif conv.kind == "direct":
        d = (
            db.query(CollaborationDirectConversation)
            .filter(
                CollaborationDirectConversation.conversation_id == conv.id,
                CollaborationDirectConversation.organization_id == org,
            )
            .first()
        )
        if d:
            otro = d.user_b_id if d.user_a_id == user.id else d.user_a_id
            titulo = _nombre_de(_usuarios_por_id(db, [otro], org).get(otro)) or "Usuario"
    elif conv.kind == "group":
        g = (
            db.query(CollaborationGroupConversation)
            .filter(
                CollaborationGroupConversation.conversation_id == conv.id,
                CollaborationGroupConversation.organization_id == org,
            )
            .first()
        )
        if g:
            titulo = g.title or "Grupo"
            extra = {"icon_url": g.icon_url}
            filas = (
                db.query(CollaborationConversationMember)
                .filter(CollaborationConversationMember.conversation_id == conv.id)
                .all()
            )
            usuarios = _usuarios_por_id(db, (m.user_id for m in filas), org)
            miembros = [
                {"user_id": m.user_id, "name": _nombre_de(usuarios.get(m.user_id))}
                for m in filas if m.user_id
            ]

    return {
        "id": conv.id, "kind": conv.kind, "workspace_id": conv.workspace_id,
        "last_activity_at": conv.last_activity_at,
        "last_message_id": conv.last_message_id,
        "is_archived": conv.is_archived,
        "title": titulo, "members": miembros, "extra": extra,
    }


def conversaciones_accesibles(db: Session, user, conversation_id: Optional[str] = None) -> list[str]:
    """Los ids de conversacion en los que el usuario puede buscar.

    Si se pide una concreta, se comprueba que esté entre las suyas antes de
    acotar a ella: sin esa comprobacion, pasar un id ajeno buscaria dentro de
    una conversacion a la que no se tiene acceso.
    """
    accesibles = [c["id"] for c in list_conversations_for_user(db, user)]
    if conversation_id:
        if conversation_id not in accesibles:
            raise ErrorDeDominio(403, "No tienes acceso a esa conversación")
        return [conversation_id]
    return accesibles
