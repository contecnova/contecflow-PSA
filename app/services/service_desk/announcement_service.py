from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.service_desk import Announcement
from app.schemas.service_desk import AnnouncementIn
from app.services.pagination_service import paginate_query
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def list_active_announcements(
    db: Session,
    page: int,
    page_size: int,
    response: Optional[Response] = None,
    solo_clientes: bool = False,
) -> List[Announcement]:
    now = datetime.now(timezone.utc)
    q = db.query(Announcement).filter(
        Announcement.is_active == True,
        or_(Announcement.ends_at == None, Announcement.ends_at > now),
    )
    if solo_clientes:
        q = q.filter(Announcement.show_to_clients == True)
    q = q.order_by(Announcement.created_at.desc())
    announcements, _, _ = paginate_query(q, page, page_size, response)
    return announcements


def serialize_announcements(announcements: List[Announcement]) -> list[dict]:
    return [
        {
            "id": a.id,
            "title": a.title,
            "body": a.body,
            "type": a.type,
            "show_to_clients": a.show_to_clients,
            "ci_name": a.ci.name if a.ci else None,
            "starts_at": str(a.starts_at)[:16] if a.starts_at else None,
            "ends_at": str(a.ends_at)[:16] if a.ends_at else None,
        }
        for a in announcements
    ]


def build_announcement(db, payload: AnnouncementIn, created_by: str) -> Announcement:
    a = Announcement(created_by=created_by, **payload.model_dump())
    db.add(a)
    return a


def get_announcement_by_id(db: Session, ann_id: str) -> Optional[Announcement]:
    return db.query(Announcement).filter(Announcement.id == ann_id).first()


def deactivate_announcement_record(db: Session, ann_id: str) -> Announcement:
    announcement = get_announcement_by_id(db, ann_id)
    if not announcement:
        raise ErrorDeDominio(404)
    announcement.is_active = False
    return announcement
