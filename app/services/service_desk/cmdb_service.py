from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.service_desk import ConfigurationItem
from app.models.user import User
from app.schemas.service_desk import CIIn
from app.services.service_desk.scoping import scope_ci_query as _scope_ci_query
from app.services.sla_service import next_ci_number as _next_ci_number


def list_cmdb_items(
    db: Session,
    current_user: User,
    page: int,
    page_size: int,
) -> list[ConfigurationItem]:
    q = db.query(ConfigurationItem).options(
        joinedload(ConfigurationItem.project),
        joinedload(ConfigurationItem.owner),
    )
    q = _scope_ci_query(q, db, current_user)
    return (
        q.order_by(ConfigurationItem.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


def serialize_cmdb_items(items: list[ConfigurationItem]) -> list[dict]:
    return [
        {
            "id": ci.id,
            "code": ci.code,
            "name": ci.name,
            "ci_type": ci.ci_type,
            "status": ci.status,
            "criticality": ci.criticality,
            "environment": ci.environment,
            "version": ci.version,
            "project_id": ci.project_id,
            "project_name": ci.project.name if ci.project else None,
            "owner_name": ci.owner.full_name if ci.owner else None,
            "open_tickets": len([]),
        }
        for ci in items
    ]


def enforce_ci_org_constraints(db: Session, current_user: User, payload: CIIn, *, is_update: bool) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if payload.project_id:
        project = db.query(Project).filter(
            Project.id == payload.project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not project:
            if is_update:
                raise HTTPException(403, "No puedes mover CIs fuera de tu organización")
            raise HTTPException(403, "No puedes crear CIs para proyectos fuera de tu organización")

    if payload.owner_user_id:
        owner = db.query(User).filter(User.id == payload.owner_user_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise HTTPException(403, "No puedes asignar owner fuera de tu organización")


def build_ci(db: Session, payload: CIIn) -> ConfigurationItem:
    ci = ConfigurationItem(code=_next_ci_number(db), **payload.model_dump())
    db.add(ci)
    return ci


def get_scoped_ci_by_id(
    db: Session,
    current_user: User,
    ci_id: str,
) -> Optional[ConfigurationItem]:
    return _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == ci_id).first()


def get_scoped_ci_or_404(
    db: Session,
    current_user: User,
    ci_id: str,
) -> ConfigurationItem:
    ci = get_scoped_ci_by_id(db, current_user, ci_id)
    if not ci:
        raise HTTPException(404)
    return ci


def apply_ci_update(ci: ConfigurationItem, payload: CIIn) -> None:
    for k, v in payload.model_dump().items():
        setattr(ci, k, v)
