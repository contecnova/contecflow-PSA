from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import AgentGroup, AgentGroupMember
from app.models.user import User
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def serialize_group(group: AgentGroup) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "support_level": group.support_level,
        "ola_hours": group.ola_hours,
        "members": [
            {
                "id": member.user_id,
                "full_name": member.user.full_name,
                "is_lead": member.is_lead,
            }
            for member in group.members
            if member.user
        ],
    }


def list_groups_payload(db: Session) -> list[dict]:
    groups = (
        db.query(AgentGroup)
        .options(joinedload(AgentGroup.members).joinedload(AgentGroupMember.user))
        .filter(AgentGroup.is_active == True)
        .all()
    )
    return [serialize_group(group) for group in groups]


def create_group_record(db, payload) -> AgentGroup:
    g = AgentGroup(**payload.model_dump())
    db.add(g)
    return g


def get_group_or_404(db: Session, group_id: str) -> AgentGroup:
    group = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
    if not group:
        raise ErrorDeDominio(404, "Grupo no encontrado")
    return group


def update_group_record(db: Session, group_id: str, payload) -> AgentGroup:
    group = get_group_or_404(db, group_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    return group


def deactivate_group_record(db: Session, group_id: str) -> None:
    group = get_group_or_404(db, group_id)
    group.is_active = False


def add_group_member_record(db: Session, group_id: str, user_id: str, is_lead: bool = False) -> None:
    get_group_or_404(db, group_id)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ErrorDeDominio(404, "Usuario no encontrado")

    existing = db.query(AgentGroupMember).filter(
        AgentGroupMember.group_id == group_id,
        AgentGroupMember.user_id == user_id,
    ).first()
    if existing:
        raise ErrorDeDominio(400, "Ya es miembro")

    db.add(AgentGroupMember(group_id=group_id, user_id=user_id, is_lead=is_lead))


def remove_group_member_record(db: Session, group_id: str, user_id: str) -> None:
    member = db.query(AgentGroupMember).filter(
        AgentGroupMember.group_id == group_id,
        AgentGroupMember.user_id == user_id,
    ).first()
    if not member:
        raise ErrorDeDominio(404)
    db.delete(member)
