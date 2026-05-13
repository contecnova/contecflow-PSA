import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.service_desk import CannedResponse
from app.schemas.service_desk import CannedResponseIn
import logging

logger = logging.getLogger(__name__)


def list_canned_responses_query(
    db: Session,
    category: Optional[str] = None,
    search: Optional[str] = None,
):
    q = db.query(CannedResponse).filter(CannedResponse.is_active == True)
    if category:
        q = q.filter(CannedResponse.category == category)
    if search:
        q = q.filter(
            or_(
                CannedResponse.title.ilike(f"%{search}%"),
                CannedResponse.body.ilike(f"%{search}%"),
                CannedResponse.shortcut.ilike(f"%{search}%"),
            )
        )
    return q


def list_canned_responses_payload(
    db: Session,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    items = list_canned_responses_query(db, category, search).order_by(
        CannedResponse.category,
        CannedResponse.title,
    ).all()
    return [serialize_canned_response(item) for item in items]


def serialize_canned_response(canned: CannedResponse) -> dict:
    return {
        "id": canned.id,
        "title": canned.title,
        "body": canned.body,
        "category": canned.category,
        "shortcut": canned.shortcut,
        "is_active": canned.is_active,
        "created_by": canned.creator.full_name if canned.creator else None,
    }


def serialize_canned_response_compact(canned: CannedResponse) -> dict:
    return {
        "id": canned.id,
        "title": canned.title,
        "body": canned.body,
        "category": canned.category,
        "shortcut": canned.shortcut,
    }


def build_canned_response(payload: CannedResponseIn, created_by: str) -> CannedResponse:
    return CannedResponse(id=str(uuid.uuid4()), created_by=created_by, **payload.model_dump())


def get_canned_response_by_id(db: Session, canned_id: str) -> CannedResponse:
    canned = db.query(CannedResponse).filter(
        CannedResponse.id == canned_id,
        CannedResponse.is_active == True,
    ).first()
    if not canned:
        raise HTTPException(404, "Respuesta rápida no encontrada")
    return canned


def apply_canned_response_update(canned: CannedResponse, payload: CannedResponseIn) -> None:
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(canned, k, v)


def create_canned_response_record(db, payload: CannedResponseIn, created_by: str) -> CannedResponse:
    c = build_canned_response(payload, created_by)
    db.add(c)
    return c


def update_canned_response_record(db: Session, canned_id: str, payload: CannedResponseIn) -> CannedResponse:
    canned = get_canned_response_by_id(db, canned_id)
    apply_canned_response_update(canned, payload)
    return canned


def get_canned_response_for_delete(db: Session, canned_id: str) -> CannedResponse:
    return get_canned_response_by_id(db, canned_id)


def delete_canned_response(db: Session, canned_id: str) -> None:
    c = get_canned_response_by_id(db, canned_id)
    c.is_active = False
