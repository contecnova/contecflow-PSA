"""Workspace + Teams + Channels + Conversations + Presence + Search + Notifications endpoints."""
from datetime import datetime
from app.core.timeutil import utcnow
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.models.collaboration import (
    CollaborationChannel, CollaborationChannelMember,
    CollaborationConversation,
    CollaborationDirectConversation, CollaborationGroupConversation,
    CollaborationConversationMember,
    CollaborationDraft, CollaborationNotification, CollaborationNotificationRule,
    CollaborationPresenceState, CollaborationTeam, CollaborationTeamMember,
)
from app.schemas.collaboration import (
    ChannelCreate, ChannelMemberOut, ChannelOut, ChannelUpdate,
    ConversationOut, DirectOpenIn, DraftIn,
    GroupCreate, NotificationRuleIn, PresenceIn, PresenceOut,
    SearchHit, SearchResponse,
    TeamCreate, TeamMemberOut, TeamMemberUpsert, TeamOut, TeamUpdate,
    WorkspaceOut, WorkspaceUpdate,
)
from app.services.collaboration import audit_log
from app.services.collaboration._bus import bus, user_channel
from app.services.collaboration._permissions import (
    _org, assert_team_access, is_team_member,
)
from app.services.collaboration._search import search_engine
from app.services.collaboration import workspaces as ws_svc
from app.core.responses import APIListResponse

router = APIRouter()


# ── Workspace ───────────────────────────────────────────────────────────────
@router.get("/workspace", response_model=WorkspaceOut, summary="Mi workspace (lazy-create)")
def my_workspace(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = ws_svc.get_or_create_workspace(db, current_user)
    return WorkspaceOut(
        id=ws.id, organization_id=ws.organization_id, name=ws.name,
        icon_url=ws.icon_url, primary_color=ws.primary_color,
        settings=ws.settings or {}, is_active=ws.is_active,
    )


@router.patch("/workspace", response_model=WorkspaceOut, summary="Actualizar workspace")
def update_workspace(payload: WorkspaceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = ws_svc.get_or_create_workspace(db, current_user)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ws, k, v)
    db.commit()
    return WorkspaceOut(
        id=ws.id, organization_id=ws.organization_id, name=ws.name,
        icon_url=ws.icon_url, primary_color=ws.primary_color,
        settings=ws.settings or {}, is_active=ws.is_active,
    )


# ── Teams ────────────────────────────────────────────────────────────────────
@router.get("/teams", response_model=APIListResponse[TeamOut], summary="Listar mis equipos")
def list_teams(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    teams = ws_svc.list_teams(db, current_user)
    out: List[TeamOut] = []
    for t in teams:
        out.append(TeamOut(
            id=t.id, name=t.name, slug=t.slug, description=t.description,
            is_private=t.is_private, project_id=t.project_id, is_archived=t.is_archived,
            member_count=db.query(CollaborationTeamMember).filter(CollaborationTeamMember.team_id == t.id).count(),
            channel_count=db.query(CollaborationChannel).filter(CollaborationChannel.team_id == t.id).count(),
            created_at=t.created_at,
        ))
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/teams", response_model=TeamOut, summary="Crear equipo")
def create_team(payload: TeamCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = ws_svc.create_team(
        db, current_user,
        name=payload.name, slug=payload.slug, description=payload.description,
        is_private=payload.is_private, project_id=payload.project_id,
    )
    return TeamOut(
        id=t.id, name=t.name, slug=t.slug, description=t.description,
        is_private=t.is_private, project_id=t.project_id, is_archived=t.is_archived,
        member_count=1, channel_count=1, created_at=t.created_at,
    )


@router.patch("/teams/{team_id}", response_model=TeamOut, summary="Actualizar equipo")
def update_team(team_id: str, payload: TeamUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_team_access(db, current_user, team_id)
    org = _org(current_user)
    t = db.query(CollaborationTeam).filter(CollaborationTeam.id == team_id, CollaborationTeam.organization_id == org).first()
    if not t:
        raise HTTPException(404, "Equipo no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    return TeamOut(
        id=t.id, name=t.name, slug=t.slug, description=t.description,
        is_private=t.is_private, project_id=t.project_id, is_archived=t.is_archived,
        created_at=t.created_at,
    )


@router.get("/teams/{team_id}/members", response_model=APIListResponse[TeamMemberOut], summary="Miembros del equipo")
def list_team_members(team_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_team_access(db, current_user, team_id)
    org = _org(current_user)
    rows = db.query(CollaborationTeamMember).filter(
        CollaborationTeamMember.team_id == team_id,
        CollaborationTeamMember.organization_id == org,
    ).all()
    # Eager-load todos los Users en una sola query (evita N+1)
    user_ids = [m.user_id for m in rows if m.user_id]
    users_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    out = []
    for m in rows:
        u = users_by_id.get(m.user_id)
        out.append(TeamMemberOut(
            id=m.id, user_id=m.user_id,
            user_name=(u.full_name or u.username) if u else None,
            user_email=u.email if u else None,
            role=m.role, joined_at=m.joined_at,
        ))
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/teams/{team_id}/members", summary="Añadir miembros al equipo")
def add_team_members(team_id: str, payload: TeamMemberUpsert, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = ws_svc.add_team_members(db, current_user, team_id, payload.user_ids, role=payload.role)
    return {"added": n}


@router.delete("/teams/{team_id}/members/{user_id}", summary="Quitar miembro del equipo")
def remove_team_member(team_id: str, user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_team", team_id, action="delete")
    ws_svc.remove_team_member(db, current_user, team_id, user_id)
    return {"removed": True}


# ── Channels ─────────────────────────────────────────────────────────────────
@router.get("/channels", response_model=APIListResponse[ChannelOut], summary="Listar canales accesibles")
def list_channels(team_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    chs = ws_svc.list_channels(db, current_user, team_id=team_id)
    out: List[ChannelOut] = []
    for c in chs:
        unread = 0
        # naive unread: messages after last_read or last 24h
        out.append(ChannelOut(
            id=c.id, conversation_id=c.conversation_id, team_id=c.team_id,
            name=c.name, slug=c.slug, topic=c.topic, description=c.description,
            channel_type=c.channel_type, is_default=c.is_default, is_archived=c.is_archived,
            project_id=c.project_id,
            member_count=db.query(CollaborationChannelMember).filter(CollaborationChannelMember.channel_id == c.id).count(),
            unread_count=unread,
            last_activity_at=None,
        ))
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/channels", response_model=ChannelOut, summary="Crear canal")
def create_channel(payload: ChannelCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = ws_svc.create_channel(
        db, current_user,
        team_id=payload.team_id, name=payload.name, slug=payload.slug,
        topic=payload.topic, description=payload.description,
        channel_type=payload.channel_type, is_default=payload.is_default,
        project_id=payload.project_id, initial_member_ids=payload.initial_member_ids,
    )
    return ChannelOut(
        id=c.id, conversation_id=c.conversation_id, team_id=c.team_id,
        name=c.name, slug=c.slug, topic=c.topic, description=c.description,
        channel_type=c.channel_type, is_default=c.is_default, is_archived=c.is_archived,
        project_id=c.project_id, member_count=1,
    )


@router.patch("/channels/{channel_id}", response_model=ChannelOut, summary="Actualizar canal")
def update_channel(channel_id: str, payload: ChannelUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == channel_id, CollaborationChannel.organization_id == org).first()
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    if not is_team_member(db, current_user, ch.team_id):
        raise HTTPException(403, "No eres miembro del equipo")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ch, k, v)
    db.commit()
    return ChannelOut(
        id=ch.id, conversation_id=ch.conversation_id, team_id=ch.team_id,
        name=ch.name, slug=ch.slug, topic=ch.topic, description=ch.description,
        channel_type=ch.channel_type, is_default=ch.is_default, is_archived=ch.is_archived,
        project_id=ch.project_id,
    )


@router.post("/channels/{channel_id}/members", summary="Añadir miembros al canal")
def add_channel_members(channel_id: str, payload: TeamMemberUpsert, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = ws_svc.add_channel_members(db, current_user, channel_id, payload.user_ids)
    return {"added": n}


@router.get("/channels/{channel_id}/members", response_model=APIListResponse[ChannelMemberOut], summary="Miembros del canal")
def list_channel_members(channel_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == channel_id, CollaborationChannel.organization_id == org).first()
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    rows = db.query(CollaborationChannelMember).filter(CollaborationChannelMember.channel_id == channel_id).all()
    out = []
    for m in rows:
        u = db.query(User).filter(User.id == m.user_id).first()
        out.append(ChannelMemberOut(
            id=m.id, user_id=m.user_id,
            user_name=(u.full_name or u.username) if u else None,
            role=m.role, notify_level=m.notify_level,
            is_starred=m.is_starred, is_muted=m.is_muted,
            last_read_at=m.last_read_at,
        ))
    return APIListResponse.ok(items=out, total=len(out))


# ── Direct + Group ───────────────────────────────────────────────────────────
@router.post("/direct/open", summary="Abrir o reusar conversación 1:1")
def open_direct(payload: DirectOpenIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = ws_svc.open_direct(
        db, current_user,
        target_user_id=payload.user_id,
        target_client_id=payload.client_user_id,
    )
    return {"id": d.id, "conversation_id": d.conversation_id}


@router.post("/groups", summary="Crear grupo ad-hoc")
def create_group(payload: GroupCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = ws_svc.create_group(
        db, current_user,
        title=payload.title,
        user_ids=payload.user_ids, client_user_ids=payload.client_user_ids,
    )
    return {"id": g.id, "conversation_id": g.conversation_id}


# ── Conversation members (group + private channel via conversation_id) ──────
@router.get("/conversations/{conversation_id}/members", summary="Listar miembros de la conversación")
def list_conversation_members(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.collaboration._permissions import assert_conversation_access
    assert_conversation_access(db, current_user, conversation_id)
    rows = db.query(CollaborationConversationMember).filter(
        CollaborationConversationMember.conversation_id == conversation_id,
        CollaborationConversationMember.organization_id == _org(current_user),
    ).all()
    out = []
    for m in rows:
        if m.user_id:
            u = db.query(User).filter(User.id == m.user_id).first()
            out.append({
                "id": m.id, "user_id": m.user_id,
                "user_name": (u.full_name or u.username) if u else None,
                "is_admin": bool(m.is_admin), "kind": "user",
            })
        elif m.client_user_id:
            out.append({
                "id": m.id, "client_user_id": m.client_user_id,
                "is_admin": False, "kind": "client",
            })
    return out


@router.post("/conversations/{conversation_id}/members", summary="Añadir miembros a un grupo")
def add_conversation_members(
    conversation_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.collaboration._permissions import assert_conversation_access
    assert_conversation_access(db, current_user, conversation_id)
    conv = db.query(CollaborationConversation).filter(
        CollaborationConversation.id == conversation_id,
    ).first()
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if conv.kind != "group":
        raise HTTPException(400, "Solo se pueden añadir miembros a grupos. Para canales usa /channels/{id}/members.")
    g = db.query(CollaborationGroupConversation).filter(
        CollaborationGroupConversation.conversation_id == conversation_id,
    ).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")

    user_ids = payload.get("user_ids") or []
    client_user_ids = payload.get("client_user_ids") or []
    if not user_ids and not client_user_ids:
        raise HTTPException(400, "Indica user_ids o client_user_ids")

    org = _org(current_user)
    added = 0
    for uid in user_ids:
        exists = db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.user_id == uid,
        ).first()
        if exists:
            continue
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conversation_id, group_id=g.id,
            user_id=uid, is_admin=False,
        ))
        added += 1
    for cid in client_user_ids:
        exists = db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.client_user_id == cid,
        ).first()
        if exists:
            continue
        db.add(CollaborationConversationMember(
            organization_id=org, conversation_id=conversation_id, group_id=g.id,
            client_user_id=cid,
        ))
        added += 1

    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="group.members.added", entity_type="group", entity_id=g.id,
        payload={"users": user_ids, "clients": client_user_ids},
    )
    db.commit()
    return {"added": added}


@router.delete("/conversations/{conversation_id}/members/{user_id}", summary="Quitar miembro de un grupo")
def remove_conversation_member(
    conversation_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_abac(db, current_user, "collaboration_conversation", conversation_id, action="delete")
    from app.services.collaboration._permissions import assert_conversation_access
    assert_conversation_access(db, current_user, conversation_id)
    conv = db.query(CollaborationConversation).filter(
        CollaborationConversation.id == conversation_id,
    ).first()
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if conv.kind != "group":
        raise HTTPException(400, "Solo se pueden quitar miembros de grupos.")
    member = db.query(CollaborationConversationMember).filter(
        CollaborationConversationMember.conversation_id == conversation_id,
        CollaborationConversationMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(404, "Miembro no encontrado")

    # Solo un admin puede expulsar a otro miembro; cualquiera puede salirse a sí mismo.
    if user_id != current_user.id:
        actor = db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.user_id == current_user.id,
        ).first()
        if not actor or not actor.is_admin:
            raise HTTPException(403, "Solo un admin del grupo puede quitar miembros")

    db.delete(member)
    audit_log.write(
        db, organization_id=_org(current_user), actor_user_id=current_user.id, actor_client_id=None,
        action="group.member.removed", entity_type="group", entity_id=conv.id,
        payload={"user_id": user_id},
    )
    db.commit()
    return {"ok": True}


# ── Conversation listing (sidebar) ───────────────────────────────────────────
@router.get("/conversations", summary="Lista unificada de conversaciones (sidebar)")
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ws_svc.list_conversations_for_user(db, current_user)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut, summary="Detalle de conversación")
def get_conversation(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration._permissions import assert_conversation_access
    assert_conversation_access(db, current_user, conversation_id)
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
    title = None
    extra = {}
    members = []
    if conv.kind == "channel":
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conv.id).first()
        title = f"# {ch.name}" if ch else None
        if ch:
            extra = {"team_id": ch.team_id, "channel_type": ch.channel_type, "topic": ch.topic, "project_id": ch.project_id}
    elif conv.kind == "direct":
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conv.id).first()
        if d:
            other = d.user_b_id if d.user_a_id == current_user.id else d.user_a_id
            u = db.query(User).filter(User.id == other).first()
            title = (u.full_name or u.username) if u else "Usuario"
    elif conv.kind == "group":
        g = db.query(CollaborationGroupConversation).filter(CollaborationGroupConversation.conversation_id == conv.id).first()
        if g:
            title = g.title or "Grupo"
            extra = {"icon_url": g.icon_url}
            for m in db.query(CollaborationConversationMember).filter(CollaborationConversationMember.conversation_id == conv.id).all():
                if m.user_id:
                    u = db.query(User).filter(User.id == m.user_id).first()
                    members.append({"user_id": m.user_id, "name": (u.full_name or u.username) if u else None})
    return ConversationOut(
        id=conv.id, kind=conv.kind, workspace_id=conv.workspace_id,
        last_activity_at=conv.last_activity_at, last_message_id=conv.last_message_id,
        is_archived=conv.is_archived, title=title, members=members, extra=extra,
    )


# ── Presence ─────────────────────────────────────────────────────────────────
@router.get("/presence", summary="Presencia de mi org (con nombre de usuario)")
def list_presence(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    rows = db.query(CollaborationPresenceState).filter(CollaborationPresenceState.organization_id == org).all()
    user_ids = [r.user_id for r in rows if r.user_id]
    users_by_id = {}
    if user_ids:
        users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    out = []
    for r in rows:
        u = users_by_id.get(r.user_id)
        out.append({
            "user_id": r.user_id,
            "client_user_id": r.client_user_id,
            "user_name": (u.full_name or u.username or u.email) if u else None,
            "status": r.status,
            "custom_message": r.custom_message,
            "is_in_call": r.is_in_call,
            "last_seen_at": r.last_seen_at,
        })
    return out


@router.post("/presence/me", summary="Actualizar mi presencia")
def update_presence(payload: PresenceIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    row = db.query(CollaborationPresenceState).filter(CollaborationPresenceState.user_id == current_user.id).first()
    if not row:
        row = CollaborationPresenceState(organization_id=org, user_id=current_user.id)
        db.add(row)
    row.status = payload.status
    row.custom_message = payload.custom_message
    row.last_seen_at = utcnow()
    db.commit()
    return {"status": row.status}


# ── Drafts ──────────────────────────────────────────────────────────────────
@router.put("/conversations/{conversation_id}/draft", summary="Guardar borrador")
def upsert_draft(conversation_id: str, payload: DraftIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.messages import upsert_draft as _upsert
    _upsert(db, current_user, conversation_id, payload.body, payload.metadata_json, payload.parent_message_id)
    return {"ok": True}


@router.get("/conversations/{conversation_id}/draft", summary="Leer mi borrador")
def get_draft(conversation_id: str, parent_message_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.messages import get_draft as _get
    d = _get(db, current_user, conversation_id, parent_message_id)
    if not d:
        return {"body": "", "metadata_json": {}}
    return {"body": d.body, "metadata_json": d.metadata_json or {}}


# ── Notifications ────────────────────────────────────────────────────────────
@router.get("/notifications", summary="Mis notificaciones")
def list_notifications(unread_only: bool = False, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(CollaborationNotification).filter(CollaborationNotification.user_id == current_user.id)
    if unread_only:
        q = q.filter(CollaborationNotification.is_read == False)
    rows = q.order_by(CollaborationNotification.created_at.desc()).limit(200).all()
    return [{
        "id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
        "conversation_id": n.conversation_id, "message_id": n.message_id,
        "is_read": n.is_read, "payload": n.payload, "created_at": n.created_at,
    } for n in rows]


@router.post("/notifications/mark-all-read", summary="Marcar todas como leídas")
def mark_all_notifications_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == current_user.id,
        CollaborationNotification.is_read == False,
    ).update({"is_read": True, "read_at": utcnow()})
    db.commit()
    return {"marked": n}


@router.post("/notifications/{notif_id}/read", summary="Marcar notificación leída")
def mark_notif_read(notif_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(CollaborationNotification).filter(
        CollaborationNotification.id == notif_id, CollaborationNotification.user_id == current_user.id,
    ).first()
    if not n:
        raise HTTPException(404, "Notificación no encontrada")
    n.is_read = True
    n.read_at = utcnow()
    db.commit()
    return {"ok": True}


# ── Notification rules ──────────────────────────────────────────────────────
@router.get("/notification-rules", summary="Mis reglas de notificación")
def list_rules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationNotificationRule).filter(
        CollaborationNotificationRule.user_id == current_user.id,
    ).all()
    return [{
        "id": r.id, "scope": r.scope, "target_id": r.target_id,
        "notify_messages": r.notify_messages, "desktop_push": r.desktop_push,
        "email_digest": r.email_digest,
        "do_not_disturb_from": r.do_not_disturb_from, "do_not_disturb_to": r.do_not_disturb_to,
    } for r in rows]


@router.put("/notification-rules", summary="Crear / actualizar regla")
def upsert_rule(payload: NotificationRuleIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    row = db.query(CollaborationNotificationRule).filter(
        CollaborationNotificationRule.user_id == current_user.id,
        CollaborationNotificationRule.scope == payload.scope,
        CollaborationNotificationRule.target_id == payload.target_id,
    ).first()
    if not row:
        row = CollaborationNotificationRule(
            organization_id=org, user_id=current_user.id, scope=payload.scope, target_id=payload.target_id,
        )
        db.add(row)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    return {"id": row.id}


# ── Search ───────────────────────────────────────────────────────────────────
@router.get("/search/saved", summary="Mis búsquedas guardadas")
def list_saved_searches(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.collaboration import CollaborationSavedSearch
    rows = db.query(CollaborationSavedSearch).filter(
        CollaborationSavedSearch.user_id == current_user.id,
    ).order_by(CollaborationSavedSearch.is_pinned.desc(), CollaborationSavedSearch.last_used_at.desc().nullslast()).all()
    return [{
        "id": r.id, "name": r.name, "query": r.query,
        "parsed": r.parsed or {}, "is_pinned": r.is_pinned,
        "use_count": r.use_count, "last_used_at": r.last_used_at,
    } for r in rows]


@router.post("/search/saved", summary="Guardar búsqueda")
def save_search(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.collaboration import CollaborationSavedSearch
    from app.services.collaboration._search_query import parse as parse_query
    name = (payload.get("name") or "").strip()
    query = (payload.get("query") or "").strip()
    if not name or not query:
        raise HTTPException(400, "name + query requeridos")
    parsed = parse_query(query).to_dict()
    row = CollaborationSavedSearch(
        organization_id=_org(current_user), user_id=current_user.id,
        name=name, query=query, parsed=parsed,
        is_pinned=bool(payload.get("is_pinned", False)),
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "query": row.query, "parsed": parsed}


@router.delete("/search/saved/{saved_id}", summary="Eliminar búsqueda guardada")
def delete_saved_search(saved_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_saved_search", saved_id, action="delete")
    from app.models.collaboration import CollaborationSavedSearch
    row = db.query(CollaborationSavedSearch).filter(
        CollaborationSavedSearch.id == saved_id,
        CollaborationSavedSearch.user_id == current_user.id,
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.post("/search/saved/{saved_id}/run", response_model=SearchResponse, summary="Ejecutar búsqueda guardada")
def run_saved_search(saved_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.collaboration import CollaborationSavedSearch
    row = db.query(CollaborationSavedSearch).filter(
        CollaborationSavedSearch.id == saved_id,
        CollaborationSavedSearch.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(404, "No encontrada")
    accessible = [c["id"] for c in ws_svc.list_conversations_for_user(db, current_user)]
    hits = search_engine.search(
        db, organization_id=_org(current_user), query=row.query,
        conversation_ids=accessible, limit=200,
    )
    row.use_count = (row.use_count or 0) + 1
    row.last_used_at = utcnow()
    db.commit()
    return SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits))


@router.get("/mention-suggestions", summary="Sugerencias para autocomplete @")
def mention_suggestions(
    q: str = Query("", max_length=80),
    conversation_id: Optional[str] = None,
    limit: int = Query(8, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve users mencionables (limitados a la org y a los miembros del canal
    si se pasa conversation_id) + grupos `everyone`/`channel`/`here`."""
    from app.models.collaboration import CollaborationChannel
    org = _org(current_user)
    user_ids: set[str] | None = None
    if conversation_id:
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
        if ch:
            tm_q = db.query(CollaborationTeamMember.user_id).filter(
                CollaborationTeamMember.team_id == ch.team_id,
            )
            user_ids = {r[0] for r in tm_q.all()}

    qx = db.query(User).filter(User.organization_id == org)
    if q:
        ql = q.lstrip("@").lower()
        from sqlalchemy import or_, func
        qx = qx.filter(or_(
            func.lower(User.username).like(f"{ql}%"),
            func.lower(User.full_name).like(f"%{ql}%"),
            func.lower(User.email).like(f"{ql}%"),
        ))
    rows = qx.limit(50).all()
    if user_ids is not None:
        rows = [u for u in rows if u.id in user_ids]
    # Excluir al usuario actual de las sugerencias
    rows = [u for u in rows if u.id != current_user.id]
    out = [{
        "id": u.id,
        "username": getattr(u, "username", None),
        "full_name": getattr(u, "full_name", None) or getattr(u, "username", None),
        "email": u.email,
    } for u in rows[:limit]]
    # Grupos especiales si encajan en el query
    extras = []
    qm = (q or "").lstrip("@").lower()
    for tag, label in (("here", "@here · personas online"),
                       ("channel", "@channel · todo el canal"),
                       ("everyone", "@everyone · toda la conversación")):
        if not qm or tag.startswith(qm):
            extras.append({"id": tag, "username": tag, "full_name": label, "is_group": True})
    return {"users": out, "groups": extras}


@router.get("/search", response_model=SearchResponse, summary="Búsqueda global")
def search(
    q: str = Query("", min_length=0, max_length=500),
    conversation_id: Optional[str] = None,
    author_user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _org(current_user)
    # Restrict to conversations the user can access (channels they are member of, etc.)
    accessible = [c["id"] for c in ws_svc.list_conversations_for_user(db, current_user)]
    if conversation_id:
        if conversation_id not in accessible:
            raise HTTPException(403, "No tienes acceso a esa conversación")
        accessible = [conversation_id]
    hits = search_engine.search(
        db, organization_id=org, query=q,
        conversation_ids=accessible, author_user_id=author_user_id,
        date_from=date_from, date_to=date_to, limit=limit,
    )
    return SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits))
