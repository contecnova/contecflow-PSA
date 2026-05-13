from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import ServiceCategory, ServiceItem
import logging

logger = logging.getLogger(__name__)


def list_catalog_payload(db: Session, public_only: bool = False) -> list[dict]:
    categories = (
        db.query(ServiceCategory)
        .options(joinedload(ServiceCategory.services))
        .filter(ServiceCategory.is_active == True)
        .order_by(ServiceCategory.sort_order)
        .all()
    )

    result = []
    for category in categories:
        services = [
            service
            for service in category.services
            if service.is_active and (not public_only or service.is_visible_to_clients)
        ]
        if not services:
            continue

        result.append(
            {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "icon": category.icon,
                "color": category.color,
                "services": [
                    {
                        "id": service.id,
                        "name": service.name,
                        "description": service.description,
                        "ticket_type": service.ticket_type,
                        "default_priority": service.default_priority,
                        "sla_response_hours": service.sla_response_hours,
                        "sla_resolution_hours": service.sla_resolution_hours,
                        "requires_approval": service.requires_approval,
                    }
                    for service in sorted(services, key=lambda item: item.sort_order)
                ],
            }
        )

    return result


def create_category_record(db: Session, payload) -> ServiceCategory:
    c = ServiceCategory(**payload.model_dump())
    db.add(c)
    return c


def get_category_or_404(db: Session, cat_id: str) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.id == cat_id).first()
    if not category:
        raise HTTPException(404, "Categoria no encontrada")
    return category


def update_category_record(db: Session, cat_id: str, payload) -> ServiceCategory:
    category = get_category_or_404(db, cat_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    return category


def deactivate_category_record(db: Session, cat_id: str) -> None:
    category = get_category_or_404(db, cat_id)
    category.is_active = False


def create_service_record(db: Session, payload) -> ServiceItem:
    s = ServiceItem(**payload.model_dump())
    db.add(s)
    return s


def get_service_or_404(db: Session, service_id: str) -> ServiceItem:
    service = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not service:
        raise HTTPException(404, "No encontrado")
    return service


def update_service_record(db: Session, service_id: str, payload) -> ServiceItem:
    service = get_service_or_404(db, service_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    return service


def deactivate_service_record(db: Session, service_id: str) -> None:
    service = get_service_or_404(db, service_id)
    service.is_active = False
