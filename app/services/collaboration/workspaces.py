"""Workspace + Team + Channel + Conversation services."""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

from fastapi import HTTPException
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from app.models.collaboration import (
    BotKind,
    CollaborationBotApp,
    CollaborationChannel, CollaborationChannelMember,
    CollaborationConversation,
    CollaborationConversationMember,
    CollaborationDirectConversation, CollaborationGroupConversation,
    CollaborationNotification,
    CollaborationNotificationRule,
    CollaborationPresenceState,
    CollaborationTeam, CollaborationTeamMember,
    CollaborationWorkspace,
)
from app.core.timeutil import utcnow
from app.models.user import User
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import (
    _org, assert_team_access, invalidate_membership,
    is_team_member,
)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return s or "general"


# ── Workspaces ───────────────────────────────────────────────────────────────
def get_or_create_workspace(db: Session, user) -> CollaborationWorkspace:
    org = _org(user)
    ws = db.query(CollaborationWorkspace).filter(CollaborationWorkspace.organization_id == org).first()
    if ws:
        return ws
    # Fetch organization name via DB (avoid lazy-load on a possibly detached user).
    from app.models.mfa import Organization
    org_row = db.query(Organization).filter(Organization.id == org).first()
    name = (org_row.name if org_row else None) or "Contecflow Workspace"
    ws = CollaborationWorkspace(organization_id=org, name=name)
    db.add(ws)
    db.flush()
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="workspace.created", entity_type="workspace", entity_id=ws.id,
        payload={"name": name},
    )
    # Bootstrap default bots
    seed_default_bots(db, org, ws.id)
    # Bootstrap default team + general channel
    team = CollaborationTeam(
        organization_id=org, workspace_id=ws.id, name="General",
        slug="general", description="Equipo principal", created_by=user.id,
    )
    db.add(team)
    db.flush()
    db.add(CollaborationTeamMember(organization_id=org, team_id=team.id, user_id=user.id, role="owner"))
    db.flush()  # ensure membership is queryable for subsequent assert_team_access
    create_channel(
        db, user, team_id=team.id,
        name="General", slug="general", description="Canal principal",
        channel_type="public", is_default=True, initial_member_ids=[user.id],
    )
    db.commit()
    return ws


def seed_default_bots(db: Session, organization_id: str, workspace_id: str) -> None:
    bots = [
        ("nexus", "Nexus AI", "Pregunta libre con contexto del proyecto. Si no resuelve, escala a ticket."),
        ("oracle", "Oracle", "Insights del PSA: estado de proyectos, recursos, riesgos."),
        ("pulse", "Pulse", "Standups, recordatorios y resúmenes post-reunión."),
        ("watcher", "Watcher", "Avisos de SLA, hitos, riesgos y vencimientos."),
        ("bridge", "Bridge", "Conector a Jira, GitHub/GitLab, Service Desk, M365 y Google."),
        ("compliance", "Compliance", "Retención, legal hold, auditoría, eDiscovery."),
    ]
    for handle, name, desc in bots:
        if db.query(CollaborationBotApp).filter(
            CollaborationBotApp.workspace_id == workspace_id,
            CollaborationBotApp.handle == handle,
        ).first():
            continue
        db.add(CollaborationBotApp(
            organization_id=organization_id, workspace_id=workspace_id,
            kind=BotKind(handle), handle=handle, display_name=name,
            description=desc, is_enabled=True,
            permissions=["read.public_channels", "send.bot_messages"],
        ))


# ── Teams ────────────────────────────────────────────────────────────────────
def list_teams(db: Session, user) -> list[CollaborationTeam]:
    org = _org(user)
    # User sees teams where they are members (or public-org-wide if not strictly private)
    member_team_ids = {
        r[0] for r in db.query(CollaborationTeamMember.team_id).filter(
            CollaborationTeamMember.user_id == user.id,
            CollaborationTeamMember.organization_id == org,
        ).all()
    }
    rows = db.query(CollaborationTeam).filter(
        CollaborationTeam.organization_id == org,
        CollaborationTeam.is_archived == False,
        or_(
            CollaborationTeam.id.in_(list(member_team_ids) or [""]),
            CollaborationTeam.is_private == False,
        ),
    ).order_by(CollaborationTeam.name.asc()).all()
    return rows


def create_team(db: Session, user, *, name: str, slug: Optional[str], description: Optional[str], is_private: bool, project_id: Optional[str]) -> CollaborationTeam:
    ws = get_or_create_workspace(db, user)
    org = _org(user)
    final_slug = slug or slugify(name)
    if db.query(CollaborationTeam).filter(
        CollaborationTeam.workspace_id == ws.id,
        CollaborationTeam.slug == final_slug,
    ).first():
        raise HTTPException(409, "Ya existe un equipo con ese slug")
    team = CollaborationTeam(
        organization_id=org, workspace_id=ws.id,
        name=name, slug=final_slug, description=description,
        is_private=is_private, project_id=project_id, created_by=user.id,
    )
    db.add(team)
    db.flush()
    db.add(CollaborationTeamMember(organization_id=org, team_id=team.id, user_id=user.id, role="owner"))
    # Default channel
    create_channel(
        db, user, team_id=team.id, name="General", slug="general",
        description="Canal por defecto", channel_type="public", is_default=True,
        initial_member_ids=[user.id],
    )
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="team.created", entity_type="team", entity_id=team.id,
        payload={"name": name, "slug": final_slug, "is_private": is_private, "project_id": project_id},
    )
    db.commit()
    return team


def add_team_members(db: Session, user, team_id: str, user_ids: list[str], role: str = "member") -> int:
    assert_team_access(db, user, team_id)
    org = _org(user)
    added = 0
    for uid in user_ids:
        if not db.query(User).filter(User.id == uid, User.organization_id == org).first():
            continue
        if db.query(CollaborationTeamMember).filter(
            CollaborationTeamMember.team_id == team_id,
            CollaborationTeamMember.user_id == uid,
        ).first():
            continue
        db.add(CollaborationTeamMember(organization_id=org, team_id=team_id, user_id=uid, role=role))
        added += 1
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="team.members_added", entity_type="team", entity_id=team_id,
        payload={"added": added, "role": role, "user_ids": user_ids},
    )
    db.commit()
    for uid in user_ids:
        invalidate_membership(uid)
    return added


def remove_team_member(db: Session, user, team_id: str, target_user_id: str) -> None:
    assert_team_access(db, user, team_id)
    org = _org(user)
    row = db.query(CollaborationTeamMember).filter(
        CollaborationTeamMember.team_id == team_id,
        CollaborationTeamMember.user_id == target_user_id,
        CollaborationTeamMember.organization_id == org,
    ).first()
    if not row:
        raise HTTPException(404, "No es miembro")
    db.delete(row)
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="team.member_removed", entity_type="team", entity_id=team_id,
        payload={"removed_user": target_user_id},
    )
    db.commit()


# ── Channels ─────────────────────────────────────────────────────────────────
def create_channel(
    db: Session, user, *,
    team_id: str,
    name: str,
    slug: Optional[str] = None,
    topic: Optional[str] = None,
    description: Optional[str] = None,
    channel_type: str = "public",
    is_default: bool = False,
    project_id: Optional[str] = None,
    initial_member_ids: Optional[list[str]] = None,
) -> CollaborationChannel:
    org = _org(user)
    team = db.query(CollaborationTeam).filter(CollaborationTeam.id == team_id, CollaborationTeam.organization_id == org).first()
    if not team:
        raise HTTPException(404, "Equipo no encontrado")
    if not is_team_member(db, user, team_id):
        raise HTTPException(403, "No eres miembro del equipo")

    final_slug = slug or slugify(name)
    if db.query(CollaborationChannel).filter(CollaborationChannel.team_id == team_id, CollaborationChannel.slug == final_slug).first():
        raise HTTPException(409, "Ya existe un canal con ese slug en este equipo")

    conv = CollaborationConversation(
        organization_id=org, kind="channel", workspace_id=team.workspace_id,
    )
    db.add(conv)
    db.flush()

    ch = CollaborationChannel(
        organization_id=org, workspace_id=team.workspace_id, team_id=team_id,
        conversation_id=conv.id, name=name, slug=final_slug,
        topic=topic, description=description, channel_type=channel_type,
        is_default=is_default, project_id=project_id, created_by=user.id,
    )
    db.add(ch)
    db.flush()

    members_to_add = set(initial_member_ids or []) | {user.id}
    for uid in members_to_add:
        db.add(CollaborationChannelMember(
            organization_id=org, channel_id=ch.id, user_id=uid,
            role="owner" if uid == user.id else "member",
        ))

    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="channel.created", entity_type="channel", entity_id=ch.id,
        payload={"name": name, "team_id": team_id, "type": channel_type, "project_id": project_id},
    )
    db.commit()
    return ch


def list_channels(db: Session, user, team_id: Optional[str] = None) -> list[CollaborationChannel]:
    org = _org(user)
    member_channel_ids = {
        r[0] for r in db.query(CollaborationChannelMember.channel_id).filter(
            CollaborationChannelMember.user_id == user.id,
            CollaborationChannelMember.organization_id == org,
        ).all()
    }
    member_team_ids = {
        r[0] for r in db.query(CollaborationTeamMember.team_id).filter(
            CollaborationTeamMember.user_id == user.id,
            CollaborationTeamMember.organization_id == org,
        ).all()
    }
    q = db.query(CollaborationChannel).filter(CollaborationChannel.organization_id == org)
    if team_id:
        q = q.filter(CollaborationChannel.team_id == team_id)
    rows = q.order_by(CollaborationChannel.name.asc()).all()
    visible = []
    for ch in rows:
        if ch.is_archived:
            continue
        if ch.channel_type in {"public", "announcement", "project"}:
            if ch.team_id in member_team_ids:
                visible.append(ch)
        else:
            if ch.id in member_channel_ids:
                visible.append(ch)
    return visible


def add_channel_members(db: Session, user, channel_id: str, user_ids: list[str]) -> int:
    org = _org(user)
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == channel_id, CollaborationChannel.organization_id == org).first()
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    assert_team_access(db, user, ch.team_id)
    added = 0
    for uid in user_ids:
        if db.query(CollaborationChannelMember).filter(
            CollaborationChannelMember.channel_id == channel_id,
            CollaborationChannelMember.user_id == uid,
        ).first():
            continue
        db.add(CollaborationChannelMember(organization_id=org, channel_id=channel_id, user_id=uid, role="member"))
        added += 1
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="channel.members_added", entity_type="channel", entity_id=channel_id,
        payload={"added": added, "user_ids": user_ids},
    )
    db.commit()
    return added


# ── Direct ──────────────────────────────────────────────────────────────────
def open_direct(db: Session, user, *, target_user_id: Optional[str] = None, target_client_id: Optional[str] = None) -> CollaborationDirectConversation:
    if not target_user_id and not target_client_id:
        raise HTTPException(400, "Indica user_id o client_user_id")
    if target_user_id == user.id:
        raise HTTPException(400, "No puedes abrir un chat directo contigo mismo")
    org = _org(user)
    ws = get_or_create_workspace(db, user)
    if target_user_id:
        # Validar que el target existe en la misma org
        from app.models.user import User as _U
        target = db.query(_U).filter(_U.id == target_user_id, _U.organization_id == org).first()
        if not target:
            raise HTTPException(404, "Usuario no encontrado")
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


# ── Lo que antes hacia el endpoint ───────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). `endpoints/collaboration/workspaces.py` tenia
# **52 puntos de acceso directo a base** —el 17 % de los 299 de toda la capa
# API—, y este servicio ya existia con trece funciones: la mitad de las
# operaciones pasaba por aqui y la otra mitad hablaba con la base desde el
# endpoint. Ahora todas pasan por aqui.
#
# El contrato que se respeta, porque es el que ya tenia el fichero: el servicio
# devuelve **datos** —objetos del modelo o diccionarios planos— y el endpoint los
# convierte a su esquema de respuesta. El servicio no sabe de Pydantic ni de
# codigos HTTP salvo para los errores de negocio, que ya lanzaba `HTTPException`.
#
# ## Cinco N+1 que aparecieron al mover
#
# Ninguno se veia leyendo el endpoint, porque las consultas estaban dentro de un
# bucle que construia la respuesta:
#
#   · `list_teams` hacia DOS `count()` por equipo;
#   · `list_channels`, uno por canal;
#   · `list_channel_members`, una consulta de `User` **por miembro**;
#   · `list_conversation_members`, otra por miembro;
#   · y el detalle de una conversacion de grupo, otra por miembro.
#
# Todos loteados con `group_by` o `in_`, que es lo que ya hacia
# `list_conversations_for_user` en este mismo fichero para el contador de no
# leidos. Con veinte miembros en un canal se pasa de 21 consultas a 2.


class EquipoConRecuentos(NamedTuple):
    """Un equipo con sus dos contadores ya resueltos."""

    equipo: CollaborationTeam
    miembros: int
    canales: int


class CanalConRecuento(NamedTuple):
    canal: CollaborationChannel
    miembros: int


def _usuarios_por_id(db: Session, ids, organization_id: Optional[str] = None) -> dict:
    """Los usuarios de esos ids, en una sola consulta.

    Devuelve diccionario vacio sin consultar si no hay ids: un `in_([])` es una
    consulta que siempre devuelve nada.

    `organization_id` acota explicitamente. Los ids salen de filas que ya estan
    acotadas, asi que en una peticion real el ambito llega por ahi; el filtro
    explicito es defensa en profundidad y no depende del filtro global de tenant,
    que es una capa de respaldo y estuvo roto (ver `app/db/session.py`).
    """
    ids = [i for i in ids if i]
    if not ids:
        return {}
    q = db.query(User).filter(User.id.in_(ids))
    if organization_id:
        q = q.filter(User.organization_id == organization_id)
    return {u.id: u for u in q.all()}


def _nombre_de(u) -> Optional[str]:
    """El nombre que se muestra de un usuario, con el mismo orden de respaldo
    que usaba el endpoint: nombre completo, luego usuario."""
    if u is None:
        return None
    return u.full_name or u.username


# ── Workspace ────────────────────────────────────────────────────────────────

def update_workspace(db: Session, user, cambios: dict) -> CollaborationWorkspace:
    """Aplica cambios al workspace del usuario, creandolo si no existe."""
    ws = get_or_create_workspace(db, user)
    for k, v in cambios.items():
        setattr(ws, k, v)
    db.commit()
    return ws


# ── Equipos ──────────────────────────────────────────────────────────────────

def list_teams_con_recuentos(db: Session, user) -> list[EquipoConRecuentos]:
    """Los equipos del usuario con su numero de miembros y de canales.

    Los dos recuentos van en **una consulta cada uno** agrupando por equipo. El
    endpoint los pedia dentro del bucle: con quince equipos eran 30 consultas.
    """
    equipos = list_teams(db, user)
    if not equipos:
        return []
    ids = [t.id for t in equipos]

    miembros = dict(
        db.query(
            CollaborationTeamMember.team_id,
            func.count(CollaborationTeamMember.id),
        )
        .filter(CollaborationTeamMember.team_id.in_(ids))
        .group_by(CollaborationTeamMember.team_id)
        .all()
    )
    canales = dict(
        db.query(
            CollaborationChannel.team_id,
            func.count(CollaborationChannel.id),
        )
        .filter(CollaborationChannel.team_id.in_(ids))
        .group_by(CollaborationChannel.team_id)
        .all()
    )
    return [
        EquipoConRecuentos(
            equipo=t,
            miembros=int(miembros.get(t.id, 0)),
            canales=int(canales.get(t.id, 0)),
        )
        for t in equipos
    ]


def update_team(db: Session, user, team_id: str, cambios: dict) -> CollaborationTeam:
    assert_team_access(db, user, team_id)
    t = (
        db.query(CollaborationTeam)
        .filter(
            CollaborationTeam.id == team_id,
            CollaborationTeam.organization_id == _org(user),
        )
        .first()
    )
    if not t:
        raise HTTPException(404, "Equipo no encontrado")
    for k, v in cambios.items():
        setattr(t, k, v)
    db.commit()
    return t


def list_team_members(db: Session, user, team_id: str) -> list[dict]:
    """Los miembros de un equipo con el nombre y el correo de cada uno."""
    assert_team_access(db, user, team_id)
    filas = (
        db.query(CollaborationTeamMember)
        .filter(
            CollaborationTeamMember.team_id == team_id,
            CollaborationTeamMember.organization_id == _org(user),
        )
        .all()
    )
    usuarios = _usuarios_por_id(db, (m.user_id for m in filas))
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "user_name": _nombre_de(usuarios.get(m.user_id)),
            "user_email": getattr(usuarios.get(m.user_id), "email", None),
            "role": m.role,
            "joined_at": m.joined_at,
        }
        for m in filas
    ]


# ── Canales ──────────────────────────────────────────────────────────────────

def list_channels_con_recuentos(
    db: Session, user, team_id: Optional[str] = None
) -> list[CanalConRecuento]:
    """Los canales accesibles con su numero de miembros, en una sola consulta.

    El `_org(user)` de la primera linea no es decorativo: es la guarda que lanza
    403 si el usuario no tiene organizacion, y el endpoint la llamaba a
    proposito antes de listar.
    """
    _org(user)
    canales = list_channels(db, user, team_id=team_id)
    if not canales:
        return []
    ids = [c.id for c in canales]
    miembros = dict(
        db.query(
            CollaborationChannelMember.channel_id,
            func.count(CollaborationChannelMember.id),
        )
        .filter(CollaborationChannelMember.channel_id.in_(ids))
        .group_by(CollaborationChannelMember.channel_id)
        .all()
    )
    return [
        CanalConRecuento(canal=c, miembros=int(miembros.get(c.id, 0)))
        for c in canales
    ]


def update_channel(db: Session, user, channel_id: str, cambios: dict) -> CollaborationChannel:
    ch = (
        db.query(CollaborationChannel)
        .filter(
            CollaborationChannel.id == channel_id,
            CollaborationChannel.organization_id == _org(user),
        )
        .first()
    )
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    if not is_team_member(db, user, ch.team_id):
        raise HTTPException(403, "No eres miembro del equipo")
    for k, v in cambios.items():
        setattr(ch, k, v)
    db.commit()
    return ch


def list_channel_members(db: Session, user, channel_id: str) -> list[dict]:
    ch = (
        db.query(CollaborationChannel)
        .filter(
            CollaborationChannel.id == channel_id,
            CollaborationChannel.organization_id == _org(user),
        )
        .first()
    )
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    filas = (
        db.query(CollaborationChannelMember)
        .filter(CollaborationChannelMember.channel_id == channel_id)
        .all()
    )
    usuarios = _usuarios_por_id(db, (m.user_id for m in filas))
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "user_name": _nombre_de(usuarios.get(m.user_id)),
            "role": m.role,
            "notify_level": m.notify_level,
            "is_starred": m.is_starred,
            "is_muted": m.is_muted,
            "last_read_at": m.last_read_at,
        }
        for m in filas
    ]


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
        raise HTTPException(404, "Conversación no encontrada")
    if conv.kind != "group":
        if verbo == "añadir":
            raise HTTPException(
                400,
                "Solo se pueden añadir miembros a grupos. Para canales usa "
                "/channels/{id}/members.",
            )
        raise HTTPException(400, "Solo se pueden quitar miembros de grupos.")
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
        raise HTTPException(404, "Grupo no encontrado")
    if not user_ids and not client_user_ids:
        raise HTTPException(400, "Indica user_ids o client_user_ids")

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
        raise HTTPException(404, "Miembro no encontrado")

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
            raise HTTPException(403, "Solo un admin del grupo puede quitar miembros")

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
        raise HTTPException(404, "Conversación no encontrada")

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
        raise HTTPException(404, "Notificación no encontrada")
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


# ── Busquedas guardadas ──────────────────────────────────────────────────────

def list_saved_searches(db: Session, user) -> list[dict]:
    """Las busquedas guardadas: primero las fijadas, luego por uso reciente.

    `nullslast()` importa: una busqueda guardada y nunca usada tiene
    `last_used_at` a nulo, y sin eso quedaria arriba en algunos motores y abajo
    en otros.
    """
    from app.models.collaboration import CollaborationSavedSearch

    filas = (
        db.query(CollaborationSavedSearch)
        .filter(CollaborationSavedSearch.user_id == user.id)
        .order_by(
            CollaborationSavedSearch.is_pinned.desc(),
            CollaborationSavedSearch.last_used_at.desc().nullslast(),
        )
        .all()
    )
    return [
        {
            "id": r.id, "name": r.name, "query": r.query,
            "parsed": r.parsed or {}, "is_pinned": r.is_pinned,
            "use_count": r.use_count, "last_used_at": r.last_used_at,
        }
        for r in filas
    ]


def save_search(db: Session, user, *, name: str, query: str, is_pinned: bool) -> dict:
    from app.models.collaboration import CollaborationSavedSearch
    from app.services.collaboration._search_query import parse as parse_query

    name = (name or "").strip()
    query = (query or "").strip()
    if not name or not query:
        raise HTTPException(400, "name + query requeridos")
    parsed = parse_query(query).to_dict()
    fila = CollaborationSavedSearch(
        organization_id=_org(user), user_id=user.id,
        name=name, query=query, parsed=parsed, is_pinned=bool(is_pinned),
    )
    db.add(fila)
    db.commit()
    return {"id": fila.id, "name": fila.name, "query": fila.query, "parsed": parsed}


def delete_saved_search(db: Session, user, saved_id: str) -> None:
    """Borra una busqueda guardada del usuario.

    No lanza si no existe: borrar dos veces lo mismo no es un error, y el
    endpoint ya se comportaba asi.
    """
    from app.models.collaboration import CollaborationSavedSearch

    fila = (
        db.query(CollaborationSavedSearch)
        .filter(
            CollaborationSavedSearch.id == saved_id,
            CollaborationSavedSearch.user_id == user.id,
        )
        .first()
    )
    if fila:
        db.delete(fila)
        db.commit()


def registrar_uso_de_busqueda(db: Session, user, saved_id: str) -> str:
    """Suma un uso a la busqueda guardada y devuelve su texto de consulta."""
    from app.models.collaboration import CollaborationSavedSearch

    fila = (
        db.query(CollaborationSavedSearch)
        .filter(
            CollaborationSavedSearch.id == saved_id,
            CollaborationSavedSearch.user_id == user.id,
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "No encontrada")
    consulta = fila.query
    fila.use_count = (fila.use_count or 0) + 1
    fila.last_used_at = utcnow()
    db.commit()
    return consulta


# ── Sugerencias de mencion ───────────────────────────────────────────────────

#: Cuantos usuarios se traen de base antes de filtrar por pertenencia al canal.
#: Se piden mas de los que se devuelven porque el filtro por miembros del equipo
#: se aplica en memoria: si se pidieran justo `limit`, un canal pequeño dentro de
#: una organizacion grande devolveria menos sugerencias de las que hay.
_CANDIDATOS_A_MENCIONAR = 50

#: Los tres grupos especiales, con su etiqueta. Se ofrecen cuando lo que se ha
#: escrito es prefijo de su nombre.
GRUPOS_DE_MENCION = (
    ("here", "@here · personas online"),
    ("channel", "@channel · todo el canal"),
    ("everyone", "@everyone · toda la conversación"),
)


def mention_suggestions(
    db: Session, user, *, q: str = "", conversation_id: Optional[str] = None,
    limit: int = 8,
) -> dict:
    """Usuarios mencionables y grupos especiales.

    Si se pasa `conversation_id` y es un canal, las sugerencias se limitan a los
    miembros de su equipo. Y **se excluye a quien pregunta**: nadie se menciona a
    si mismo.
    """
    org = _org(user)
    ids_permitidos: Optional[set] = None
    if conversation_id:
        ch = (
            db.query(CollaborationChannel)
            .filter(CollaborationChannel.conversation_id == conversation_id)
            .first()
        )
        if ch:
            ids_permitidos = {
                r[0] for r in db.query(CollaborationTeamMember.user_id).filter(
                    CollaborationTeamMember.team_id == ch.team_id
                ).all()
            }

    consulta = db.query(User).filter(User.organization_id == org)
    if q:
        ql = q.lstrip("@").lower()
        consulta = consulta.filter(or_(
            func.lower(User.username).like(f"{ql}%"),
            func.lower(User.full_name).like(f"%{ql}%"),
            func.lower(User.email).like(f"{ql}%"),
        ))
    filas = consulta.limit(_CANDIDATOS_A_MENCIONAR).all()
    if ids_permitidos is not None:
        filas = [u for u in filas if u.id in ids_permitidos]
    filas = [u for u in filas if u.id != user.id]

    usuarios = [
        {
            "id": u.id,
            "username": getattr(u, "username", None),
            "full_name": getattr(u, "full_name", None) or getattr(u, "username", None),
            "email": u.email,
        }
        for u in filas[:limit]
    ]
    qm = (q or "").lstrip("@").lower()
    grupos = [
        {"id": tag, "username": tag, "full_name": label, "is_group": True}
        for tag, label in GRUPOS_DE_MENCION
        if not qm or tag.startswith(qm)
    ]
    return {"users": usuarios, "groups": grupos}


# ── Busqueda global ──────────────────────────────────────────────────────────

#: Tope de resultados de una busqueda guardada. Tiene su propia constante y no
#: reusa `MAX_NOTIFICACIONES` aunque hoy valgan lo mismo: son dos limites de
#: cosas distintas, y compartir la constante haria que cambiar el tope del buzon
#: cambiara en silencio el de las busquedas.
MAX_RESULTADOS_DE_BUSQUEDA = 200


def conversaciones_accesibles(db: Session, user, conversation_id: Optional[str] = None) -> list[str]:
    """Los ids de conversacion en los que el usuario puede buscar.

    Si se pide una concreta, se comprueba que esté entre las suyas antes de
    acotar a ella: sin esa comprobacion, pasar un id ajeno buscaria dentro de
    una conversacion a la que no se tiene acceso.
    """
    accesibles = [c["id"] for c in list_conversations_for_user(db, user)]
    if conversation_id:
        if conversation_id not in accesibles:
            raise HTTPException(403, "No tienes acceso a esa conversación")
        return [conversation_id]
    return accesibles
