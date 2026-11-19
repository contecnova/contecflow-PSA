from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import ServiceCategory, ServiceItem
import logging
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def _servicio(service, interno: bool) -> dict:
    from app.services.service_desk.fulfillment_service import tareas_de
    datos = {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "ticket_type": service.ticket_type,
        "default_priority": service.default_priority,
        "sla_response_hours": service.sla_response_hours,
        "sla_resolution_hours": service.sla_resolution_hours,
        "requires_approval": service.requires_approval,
    }
    if interno:
        # Sin estos campos el formulario de edicion arrancaba con «visible» y
        # sin aprobador: guardar un servicio oculto lo publicaba en el portal.
        # No van al portal: el id del aprobador es interno.
        datos.update({
            "approval_user_id": service.approval_user_id,
            "approval_mode": service.approval_mode or "single",
            "approval_workflow_id": service.approval_workflow_id,
            "fulfillment_tasks": tareas_de(service),
            "is_visible_to_clients": service.is_visible_to_clients,
            "default_support_level": getattr(service.default_support_level, "value",
                                             service.default_support_level),
        })
    return datos


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
                    _servicio(service, interno=not public_only)
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
        raise error(404, "no_encontrado", detail="Categoria no encontrada", que="categoria")
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
    from app.services.service_desk.fulfillment_service import validar_tareas
    from app.services.service_desk.fulfillment_service import guardar_tareas
    datos = payload.model_dump()
    _exigir_modo_de_aprobacion(db, datos)
    tareas = validar_tareas(db, datos.pop("fulfillment_tasks", None))
    s = ServiceItem(**datos)
    db.add(s)
    db.flush()
    guardar_tareas(db, s, tareas)
    return s


def _exigir_modo_de_aprobacion(db: Session, datos: dict) -> None:
    """Mejoras de mercado 16-11-2026: `single` necesita aprobador; `engine`,
    un flujo activo de la empresa (el elegido, o uno por defecto para
    `catalog_request`)."""
    from app.services.service_desk.catalog_approval_service import exigir_aprobador, exigir_flujo
    modo = datos.get("approval_mode") or "single"
    if modo not in ("single", "engine"):
        raise error(422, "catalogo_modo_aprobacion_no_valido")
    if not datos.get("requires_approval"):
        return
    if modo == "engine":
        exigir_flujo(db, datos.get("approval_workflow_id"))
    else:
        exigir_aprobador(db, True, datos.get("approval_user_id"))


def get_service_or_404(db: Session, service_id: str) -> ServiceItem:
    service = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not service:
        raise error(404, "no_encontrado_generico")
    return service


def update_service_record(db: Session, service_id: str, payload) -> ServiceItem:
    from app.services.service_desk.fulfillment_service import validar_tareas
    from app.services.service_desk.fulfillment_service import guardar_tareas
    service = get_service_or_404(db, service_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "fulfillment_tasks":
            guardar_tareas(db, service, validar_tareas(db, value))
            continue
        setattr(service, key, value)
    _exigir_modo_de_aprobacion(db, {
        "approval_mode": service.approval_mode, "requires_approval": service.requires_approval,
        "approval_user_id": service.approval_user_id, "approval_workflow_id": service.approval_workflow_id})
    return service


def deactivate_service_record(db: Session, service_id: str) -> None:
    service = get_service_or_404(db, service_id)
    service.is_active = False
