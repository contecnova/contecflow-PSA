"""Secuencias de numeracion y campos personalizados con sus valores.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.advanced_config import NumberingSequence
from app.models.advanced_config import CustomField
from app.models.advanced_config import CustomFieldValue

from app.services.advanced_config_service._comun import NotFoundError, logger
from app.services.advanced_config_service.semillas import seed_numbering
from app.core.codigos_de_error import error
from app.core.codigos_de_error import ErrorConCodigo


# ── Numbering sequences ───────────────────────────────────────────────────────

def list_numbering(db: Session) -> list:
    seed_numbering(db)
    seqs = db.query(NumberingSequence).order_by(NumberingSequence.entity).all()
    result = []
    for s in seqs:
        year = datetime.now().year
        next_val = s.current_value + 1
        year_part = f"{year}{s.separator}" if s.include_year else ""
        padded = str(next_val).zfill(s.padding)
        preview = (
            f"{s.prefix}{s.separator}{year_part}{padded}{s.suffix}"
            if s.prefix
            else f"{year_part}{padded}{s.suffix}"
        )
        result.append({
            "id": s.id, "entity": s.entity, "prefix": s.prefix, "suffix": s.suffix,
            "separator": s.separator, "include_year": s.include_year, "padding": s.padding,
            "reset_yearly": s.reset_yearly, "current_value": s.current_value,
            "example": s.example, "next_preview": preview,
        })
    return result


def update_numbering_seq(entity: str, data: dict, db: Session) -> dict:
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s:
        s = NumberingSequence(entity=entity, **data)
        db.add(s)
    else:
        for k, v in data.items():
            setattr(s, k, v)
    year = datetime.now().year
    year_part = f"{year}{data['separator']}" if data.get("include_year") else ""
    padded = "1".zfill(data.get("padding", 4))
    prefix = data.get("prefix", "")
    sep = data.get("separator", "-")
    suffix = data.get("suffix", "")
    s.example = (
        f"{prefix}{sep}{year_part}{padded}{suffix}"
        if prefix
        else f"{year_part}{padded}"
    )
    db.commit()
    db.refresh(s)
    return {"ok": True, "example": s.example}


def reset_numbering_seq(entity: str, db: Session) -> dict:
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s:
        raise NotFoundError("No encontrado")
    s.current_value = 0
    db.commit()
    return {"ok": True}


# ── Custom fields ─────────────────────────────────────────────────────────────

def list_custom_fields(entity: Optional[str], db: Session) -> list:
    q = db.query(CustomField).filter(CustomField.is_active == True)
    if entity:
        q = q.filter(CustomField.entity == entity)
    fields = q.order_by(CustomField.entity, CustomField.sort_order).all()
    return [
        {
            "id": f.id, "entity": f.entity, "name": f.name, "field_key": f.field_key,
            "field_type": f.field_type,
            "options": json.loads(f.options) if f.options else None,
            "is_required": f.is_required, "placeholder": f.placeholder,
            "default_value": f.default_value,
            "visible_to_roles": json.loads(f.visible_to_roles) if f.visible_to_roles else None,
            "sort_order": f.sort_order,
        }
        for f in fields
    ]


def create_custom_field(data: dict, db: Session) -> dict:
    if db.query(CustomField).filter(
        CustomField.entity == data["entity"],
        CustomField.field_key == data["field_key"],
    ).first():
        raise ErrorConCodigo("campo_clave_ya_existe")
    f = CustomField(**{
        **data,
        "options": json.dumps(data["options"]) if data.get("options") else None,
        "visible_to_roles": json.dumps(data["visible_to_roles"]) if data.get("visible_to_roles") else None,
    })
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id}


def update_custom_field(field_id: str, data: dict, db: Session) -> dict:
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(f, k, json.dumps(v) if k in ("options", "visible_to_roles") and v else v)
    db.commit()
    db.refresh(f)
    return {"id": f.id}


def delete_custom_field(field_id: str, db: Session) -> dict:
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f:
        raise NotFoundError("No encontrado")
    f.is_active = False
    db.commit()
    return {"ok": True}


# ── Lectura de valores: la guarda de la entidad dueña ─────────────────────────
# Segunda auditoría 2026-11: `GET /advanced-config/custom-fields/values/{id}`
# solo pedía sesión y devolvía los valores de cualquier entidad. Ahora quien lee
# tiene que poder leer la entidad, con el alcance del listado de su tipo.

#: Módulo GRC de los contratos (el primer segmento de su ruta).
MODULO_DE_CONTRATOS = "contracts"

def _ve_proyecto(db, viewer, entity_id) -> bool:
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    return scope_projects_query(db.query(Project.id), db, viewer).filter(Project.id == entity_id).first() is not None


def _ve_tarea(db, viewer, entity_id) -> bool:
    from app.services.task_service import get_task_record
    get_task_record(db, entity_id, viewer)  # 404/403 si no la ve
    return True


def _ve_persona(db, viewer, entity_id) -> bool:
    from app.models.user import User
    from app.services import politica_de_visibilidad
    objetivo = db.query(User).filter(User.id == entity_id).first()
    # Los campos extra son de la ficha completa: con la mínima, no.
    return objetivo is not None and politica_de_visibilidad.ve_ficha_completa_de(db, viewer, objetivo)


def _ve_cliente(db, viewer, entity_id) -> bool:
    from app.models.clients import Client
    return db.query(Client.id).filter(Client.id == entity_id).first() is not None


def _ve_ticket(db, viewer, entity_id) -> bool:
    from app.models.service_desk import Ticket
    from app.services.service_desk.scoping import scope_ticket_query
    return scope_ticket_query(db.query(Ticket.id), db, viewer).filter(Ticket.id == entity_id).first() is not None


def _ve_riesgo(db, viewer, entity_id) -> bool:
    from app.models.pipeline import Risk
    riesgo = db.query(Risk.project_id).filter(Risk.id == entity_id).first()
    return riesgo is not None and riesgo.project_id is not None and _ve_proyecto(db, viewer, riesgo.project_id)


def _ve_factura(db, viewer, entity_id) -> bool:
    from app.models.billing_reports import Invoice
    from app.services import politica_de_visibilidad
    from app.services.billing_reports_service._comun import _scope_invoice_query
    from app.services.cab_service.busqueda import MODULO_DE_FACTURAS
    return (politica_de_visibilidad.ve_modulo_financiero(db, viewer, MODULO_DE_FACTURAS)
            and _scope_invoice_query(db).filter(Invoice.id == entity_id).first() is not None)


def _ve_oportunidad(db, viewer, entity_id) -> bool:
    from app.models.pipeline import Opportunity
    from app.services import politica_de_visibilidad
    from app.services.pipeline_service import scope_opportunity_query
    from app.services.cab_service.busqueda import MODULO_DE_OPORTUNIDADES
    return (politica_de_visibilidad.ve_modulo_financiero(db, viewer, MODULO_DE_OPORTUNIDADES)
            and scope_opportunity_query(db.query(Opportunity), db, viewer)
            .filter(Opportunity.id == entity_id).first() is not None)


def _ve_contrato(db, viewer, entity_id) -> bool:
    from app.models.pipeline import Contract
    from app.services import politica_de_visibilidad
    from app.services.contract_service import scope_contract_query
    return (politica_de_visibilidad.ve_modulo_financiero(db, viewer, MODULO_DE_CONTRATOS)
            and scope_contract_query(db.query(Contract), db, viewer)
            .filter(Contract.id == entity_id).first() is not None)


#: Tipo de entidad (`CustomField.entity`) → ¿la ve `viewer`? Un tipo sin
#: resolutor (ausencia, documento, gasto...) solo lo lee quien escribe sus
#: valores: el administrador (`POST .../values` exige `require_admin`).
_LECTURA_POR_ENTIDAD = {
    "project": _ve_proyecto,
    "task": _ve_tarea,
    "user": _ve_persona,
    "client": _ve_cliente,
    "ticket": _ve_ticket,
    "risk": _ve_riesgo,
    "invoice": _ve_factura,
    "opportunity": _ve_oportunidad,
    "contract": _ve_contrato,
}


def exigir_lectura_de_valores(db: Session, viewer, entity_id: str) -> None:
    """404 si `viewer` no puede leer la entidad dueña de esos valores."""
    from app.models.user import UserRole
    tipos = {fila[0] for fila in db.query(CustomField.entity).join(
        CustomFieldValue, CustomFieldValue.field_id == CustomField.id,
    ).filter(CustomFieldValue.entity_id == entity_id).distinct()}
    es_admin = getattr(viewer, "is_superadmin", False) or viewer.role == UserRole.admin
    for tipo in tipos:
        resolutor = _LECTURA_POR_ENTIDAD.get(tipo)
        visible = resolutor(db, viewer, entity_id) if resolutor else es_admin
        if not visible:
            raise error(404, "no_encontrado", detail="Entidad no encontrada", que="entidad")


def get_custom_field_values(entity_id: str, db: Session) -> dict:
    values = (
        db.query(CustomFieldValue)
        .options(joinedload(CustomFieldValue.field))
        .filter(CustomFieldValue.entity_id == entity_id)
        .all()
    )
    return {v.field.field_key: v.value for v in values if v.field}


def save_custom_field_values(entity_id: str, values: dict, db: Session) -> dict:
    try:
        for field_key, value in values.items():
            field = db.query(CustomField).filter(
                CustomField.field_key == field_key,
                CustomField.is_active == True,
            ).first()
            if not field:
                continue
            existing = db.query(CustomFieldValue).filter(
                CustomFieldValue.field_id == field.id,
                CustomFieldValue.entity_id == entity_id,
            ).first()
            if existing:
                existing.value = str(value) if value is not None else None
            else:
                db.add(CustomFieldValue(
                    field_id=field.id,
                    entity_id=entity_id,
                    value=str(value) if value is not None else None,
                ))
        db.commit()
        return {"ok": True}
    except Exception:
        logger.exception("Failed to persist CustomFieldValue for entity=%s", entity_id)
        db.rollback()
        raise
