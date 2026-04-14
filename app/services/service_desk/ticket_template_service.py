import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import TicketTemplate


def list_ticket_templates_query(db: Session, ticket_type=None):
    q = db.query(TicketTemplate).filter(TicketTemplate.is_active == True)
    if ticket_type:
        q = q.filter(TicketTemplate.ticket_type == ticket_type)
    return q


def list_ticket_templates_payload(db: Session, ticket_type=None) -> list[dict]:
    templates = list_ticket_templates_query(db, ticket_type).all()
    return [serialize_ticket_template(template) for template in templates]


def serialize_ticket_template(template: TicketTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "ticket_type": template.ticket_type.value,
        "custom_fields": template.custom_fields,
        "default_priority": template.default_priority.value if template.default_priority else None,
        "description_template": template.description_template,
    }


def build_ticket_template(payload: dict) -> TicketTemplate:
    if not payload.get("name") or not payload.get("ticket_type"):
        raise HTTPException(422, "name y ticket_type son obligatorios")

    return TicketTemplate(
        name=payload["name"],
        ticket_type=payload["ticket_type"],
        category_id=payload.get("category_id"),
        custom_fields=json.dumps(payload.get("custom_fields", [])),
        default_priority=payload.get("default_priority", "p3_medium"),
        default_group_id=payload.get("default_group_id"),
        description_template=payload.get("description_template"),
        auto_assign_to_id=payload.get("auto_assign_to_id"),
    )


def get_ticket_template_by_id(db: Session, template_id: str):
    return db.query(TicketTemplate).filter(TicketTemplate.id == template_id).first()


def get_ticket_template_or_404(db: Session, template_id: str, detail: str = "Plantilla no encontrada") -> TicketTemplate:
    template = get_ticket_template_by_id(db, template_id)
    if not template:
        raise HTTPException(404, detail)
    return template


def apply_ticket_template_update(template: TicketTemplate, payload: dict) -> None:
    for field in ("name", "is_active", "default_priority", "description_template"):
        if field in payload:
            setattr(template, field, payload[field])
    if "custom_fields" in payload:
        template.custom_fields = json.dumps(payload["custom_fields"])


def create_ticket_template_record(payload: dict) -> TicketTemplate:
    return build_ticket_template(payload)


def update_ticket_template_record(db: Session, template_id: str, payload: dict) -> TicketTemplate:
    template = get_ticket_template_or_404(db, template_id, detail="Plantilla no encontrada")
    apply_ticket_template_update(template, payload)
    return template


def get_ticket_template_for_delete_or_404(db: Session, template_id: str) -> TicketTemplate:
    return get_ticket_template_or_404(db, template_id, detail="Plantilla no encontrada")
