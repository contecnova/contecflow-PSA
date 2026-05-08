"""Workspace + Team + Channel + Conversation services."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.models.collaboration import (
    BotKind,
    CollaborationBotApp,
    CollaborationChannel, CollaborationChannelMember,
    CollaborationConversation,
    CollaborationConversationMember,
    CollaborationDirectConversation, CollaborationGroupConversation,
    CollaborationTeam, CollaborationTeamMember,
    CollaborationWorkspace,
)
from app.models.user import User
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import (
    _org, assert_team_access, assert_workspace,
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
    org = _org(user)
    ws = get_or_create_workspace(db, user)
    if target_user_id:
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

    # Channels via team membership + private channel membership
    channels = list_channels(db, user)
    for ch in channels:
        out.append({
            "id": ch.conversation_id, "kind": "channel",
            "title": f"# {ch.name}", "team_id": ch.team_id,
            "channel_type": ch.channel_type, "project_id": ch.project_id,
            "icon": None,
        })

    # Directs where user participates
    direct_rows = db.query(CollaborationDirectConversation).filter(
        CollaborationDirectConversation.organization_id == org,
        or_(
            CollaborationDirectConversation.user_a_id == user.id,
            CollaborationDirectConversation.user_b_id == user.id,
        ),
    ).all()
    for d in direct_rows:
        other = d.user_b_id if d.user_a_id == user.id else d.user_a_id
        u = db.query(User).filter(User.id == other).first()
        title = (u.full_name or u.username or "Usuario") if u else "Usuario"
        out.append({
            "id": d.conversation_id, "kind": "direct",
            "title": title, "peer_user_id": other,
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
        out.append({
            "id": g.conversation_id, "kind": "group",
            "title": g.title or "Grupo",
        })
    return out
