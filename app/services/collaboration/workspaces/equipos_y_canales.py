"""Espacio de trabajo, equipos, canales y sus miembros.

Parte de `app.services.collaboration.workspaces` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from app.models.collaboration import (
    BotKind,
    CollaborationBotApp,
    CollaborationChannel,
    CollaborationChannelMember,
    CollaborationConversation,
    CollaborationTeam,
    CollaborationTeamMember,
    CollaborationWorkspace,
)
from app.models.user import User
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import (
    _org, assert_team_access, invalidate_membership,
    is_team_member,
)
from app.core.errores import ErrorDeDominio

from app.services.collaboration.workspaces._comun import _nombre_de, _usuarios_por_id


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
        raise ErrorDeDominio(409, "Ya existe un equipo con ese slug")
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
        raise ErrorDeDominio(404, "No es miembro")
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
        raise ErrorDeDominio(404, "Equipo no encontrado")
    if not is_team_member(db, user, team_id):
        raise ErrorDeDominio(403, "No eres miembro del equipo")

    final_slug = slug or slugify(name)
    if db.query(CollaborationChannel).filter(CollaborationChannel.team_id == team_id, CollaborationChannel.slug == final_slug).first():
        raise ErrorDeDominio(409, "Ya existe un canal con ese slug en este equipo")

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
        raise ErrorDeDominio(404, "Canal no encontrado")
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
        raise ErrorDeDominio(404, "Equipo no encontrado")
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
        raise ErrorDeDominio(404, "Canal no encontrado")
    if not is_team_member(db, user, ch.team_id):
        raise ErrorDeDominio(403, "No eres miembro del equipo")
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
        raise ErrorDeDominio(404, "Canal no encontrado")
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
