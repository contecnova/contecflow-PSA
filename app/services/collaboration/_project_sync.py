"""Sincronización Project ↔ collaboration team/channel.

Hooks:
  on_project_created(db, project, creator)  → crea team+canal proj-<code>
  sync_project_members(db, project)         → idempotente (futuro: PATCH miembros)

El team/canal usa channel_type='project' y guarda project_id para back-pointer.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "project"


def on_project_created(db: Session, project, creator) -> None:
    if not creator or not getattr(project, "id", None):
        return
    from app.models.collaboration import (
        CollaborationChannel, CollaborationChannelMember, CollaborationConversation,
        CollaborationTeam, CollaborationTeamMember,
    )
    from app.services.collaboration import audit_log
    from app.services.collaboration._permissions import invalidate_membership
    from app.services.collaboration.workspaces import get_or_create_workspace

    ws = get_or_create_workspace(db, creator)
    org_id = getattr(creator, "organization_id", None) or getattr(project, "organization_id", None)
    if not org_id:
        return

    # ¿Ya existe un team para este proyecto?
    existing_team = db.query(CollaborationTeam).filter(CollaborationTeam.project_id == project.id).first()
    if existing_team:
        team = existing_team
    else:
        slug = f"proj-{_slug(project.code or project.name or project.id)[:80]}"
        # Evitar colisión de slug
        if db.query(CollaborationTeam).filter(
            CollaborationTeam.workspace_id == ws.id,
            CollaborationTeam.slug == slug,
        ).first():
            slug = f"{slug}-{project.id[:6]}"
        team = CollaborationTeam(
            organization_id=org_id, workspace_id=ws.id,
            name=project.name or f"Proyecto {project.code}",
            slug=slug, description=f"Equipo del proyecto {project.code or ''}".strip(),
            project_id=project.id, created_by=creator.id,
        )
        db.add(team)
        db.flush()
        db.add(CollaborationTeamMember(
            organization_id=org_id, team_id=team.id, user_id=creator.id, role="owner",
        ))
        invalidate_membership(creator.id)
        # Si el proyecto tiene PM diferente al creator, añadirlo
        pm_id = getattr(project, "pm_id", None)
        if pm_id and pm_id != creator.id:
            db.add(CollaborationTeamMember(
                organization_id=org_id, team_id=team.id, user_id=pm_id, role="admin",
            ))
            invalidate_membership(pm_id)

    # Canal por defecto del proyecto
    existing_chan = db.query(CollaborationChannel).filter(CollaborationChannel.project_id == project.id).first()
    if existing_chan:
        return

    conv = CollaborationConversation(organization_id=org_id, kind="channel", workspace_id=ws.id)
    db.add(conv); db.flush()
    chan = CollaborationChannel(
        organization_id=org_id, workspace_id=ws.id, team_id=team.id,
        conversation_id=conv.id,
        name="general",
        slug="general",
        description=f"Canal por defecto del proyecto {project.code or ''}".strip(),
        channel_type="project",
        is_default=True,
        project_id=project.id,
        created_by=creator.id,
    )
    db.add(chan); db.flush()
    db.add(CollaborationChannelMember(
        organization_id=org_id, channel_id=chan.id, user_id=creator.id, role="owner",
    ))
    invalidate_membership(creator.id)
    audit_log.write(
        db, organization_id=org_id, actor_user_id=creator.id, actor_client_id=None,
        action="channel.auto_created", entity_type="channel", entity_id=chan.id,
        payload={"project_id": project.id, "code": project.code},
    )

