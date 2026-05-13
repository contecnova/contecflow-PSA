from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.clients import Client
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.service_desk import ConfigurationItem, KBArticle, Problem, SLAPolicy, Ticket
from app.models.user import User, UserRole
import logging

logger = logging.getLogger(__name__)


def resolve_sla_policy_for_ticket(
    db: Session,
    *,
    contract_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> Optional[SLAPolicy]:
    """Resolve SLA by precedence: contract -> client -> default active policy."""
    if contract_id:
        ctr = db.query(Contract).filter(Contract.id == contract_id).first()
        if ctr and getattr(ctr, "sla_policy_id", None):
            p = db.query(SLAPolicy).filter(
                SLAPolicy.id == ctr.sla_policy_id,
                SLAPolicy.is_active == True,
            ).first()
            if p:
                return p

    if client_id:
        cli = db.query(Client).filter(Client.id == client_id).first()
        if cli and getattr(cli, "sla_policy_id", None):
            p = db.query(SLAPolicy).filter(
                SLAPolicy.id == cli.sla_policy_id,
                SLAPolicy.is_active == True,
            ).first()
            if p:
                return p

    return db.query(SLAPolicy).filter(
        SLAPolicy.is_default == True,
        SLAPolicy.is_active == True,
    ).first()


def _org_user_ids_subquery(db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return None
    return db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()


def _org_project_ids_subquery(db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return None
    return db.query(Project.id).filter(
        Project.organization_id == current_user.organization_id
    ).scalar_subquery()


def scope_ticket_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        return q.filter(
            or_(
                Ticket.requester_user_id == current_user.id,
                Ticket.assigned_to_user_id == current_user.id,
            )
        )
    if current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        return q.filter(
            or_(
                Ticket.requester_user_id.in_(org_user_ids),
                Ticket.assigned_to_user_id.in_(org_user_ids),
                Ticket.created_by_user_id.in_(org_user_ids),
            )
        )
    return q


def scope_problem_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    org_project_ids = _org_project_ids_subquery(db, current_user)
    if org_user_ids is None or org_project_ids is None:
        return q.filter(False)
    return q.filter(
        or_(
            Problem.owner_user_id.in_(org_user_ids),
            Problem.project_id.in_(org_project_ids),
            Problem.ci_id.in_(
                db.query(ConfigurationItem.id).filter(
                    ConfigurationItem.project_id.in_(org_project_ids)
                ).scalar_subquery()
            ),
        )
    )


def scope_ci_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    org_project_ids = _org_project_ids_subquery(db, current_user)
    if org_user_ids is None or org_project_ids is None:
        return q.filter(False)
    return q.filter(
        or_(
            ConfigurationItem.owner_user_id.in_(org_user_ids),
            ConfigurationItem.project_id.in_(org_project_ids),
        )
    )


def scope_kb_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    if org_user_ids is None:
        return q.filter(False)
    return q.filter(KBArticle.author_id.in_(org_user_ids))
