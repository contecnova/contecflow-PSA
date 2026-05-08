"""Permission checks for the collaboration domain.

Multi-tenant enforcement:
  - all queries MUST filter by organization_id
  - membership rules:
    * workspace: any user of the org with active status
    * team: explicit row in collaboration_team_members
    * channel public: any team member; private/announcement: explicit channel member
    * direct: only the two participants
    * group: explicit conversation member
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.collaboration import (
    CollaborationChannel, CollaborationChannelMember,
    CollaborationConversation, CollaborationConversationMember,
    CollaborationDirectConversation, CollaborationGroupConversation,
    CollaborationTeamMember,
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _org(user) -> str:
    org = getattr(user, "organization_id", None)
    if not org:
        raise HTTPException(403, "Usuario sin organización")
    return org


def can_access_workspace(db: Session, user, workspace_id: str) -> bool:
    from app.models.collaboration import CollaborationWorkspace
    ws = db.query(CollaborationWorkspace).filter(CollaborationWorkspace.id == workspace_id).first()
    if not ws:
        return False
    return ws.organization_id == _org(user)


def is_team_member(db: Session, user, team_id: str) -> bool:
    return db.query(CollaborationTeamMember).filter(
        CollaborationTeamMember.team_id == team_id,
        CollaborationTeamMember.user_id == user.id,
        CollaborationTeamMember.organization_id == _org(user),
    ).first() is not None


def is_channel_member(db: Session, user, channel_id: str) -> bool:
    return db.query(CollaborationChannelMember).filter(
        CollaborationChannelMember.channel_id == channel_id,
        CollaborationChannelMember.user_id == user.id,
        CollaborationChannelMember.organization_id == _org(user),
    ).first() is not None


def is_conversation_participant(db: Session, user, conversation_id: str) -> bool:
    """Internal user — channel member, direct participant or group member."""
    org = _org(user)
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
    if not conv or conv.organization_id != org:
        return False
    if conv.kind == "channel":
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
        if not ch:
            return False
        # Public/announcement → team membership grants access. Private → explicit member.
        if ch.channel_type in {"public", "announcement", "project"}:
            return is_team_member(db, user, ch.team_id)
        return is_channel_member(db, user, ch.id)
    if conv.kind == "direct":
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conversation_id).first()
        if not d:
            return False
        return user.id in {d.user_a_id, d.user_b_id}
    if conv.kind == "group":
        return db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.user_id == user.id,
        ).first() is not None
    return False


def is_client_conversation_participant(db: Session, client_user, conversation_id: str) -> bool:
    """External (portal) participant access (cross-org channels only)."""
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
    if not conv:
        return False
    if conv.kind == "direct":
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conversation_id).first()
        if not d:
            return False
        return client_user.id in {d.client_user_a_id, d.client_user_b_id}
    if conv.kind == "group":
        return db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.client_user_id == client_user.id,
        ).first() is not None
    if conv.kind == "channel":
        # Future: cross-org channels with explicit invite.
        return db.query(CollaborationConversationMember).filter(
            CollaborationConversationMember.conversation_id == conversation_id,
            CollaborationConversationMember.client_user_id == client_user.id,
        ).first() is not None
    return False


def assert_conversation_access(db: Session, user, conversation_id: str) -> None:
    if not is_conversation_participant(db, user, conversation_id):
        raise HTTPException(403, "No tienes acceso a esta conversación")


def assert_team_access(db: Session, user, team_id: str) -> None:
    if not is_team_member(db, user, team_id):
        raise HTTPException(403, "No eres miembro de este equipo")


def assert_workspace(db: Session, user, workspace_id: Optional[str]) -> str:
    """Returns the workspace_id, ensuring the user can use it. If None, returns
    the user's default workspace (creates if missing)."""
    if workspace_id:
        if not can_access_workspace(db, user, workspace_id):
            raise HTTPException(403, "No tienes acceso a este workspace")
        return workspace_id
    # default workspace = the one matching the user's org
    from app.models.collaboration import CollaborationWorkspace
    ws = db.query(CollaborationWorkspace).filter(CollaborationWorkspace.organization_id == _org(user)).first()
    if ws:
        return ws.id
    raise HTTPException(404, "Workspace no inicializado")
