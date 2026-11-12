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
        raise ValueError("Ya existe un campo con esa clave para esa entidad")
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
