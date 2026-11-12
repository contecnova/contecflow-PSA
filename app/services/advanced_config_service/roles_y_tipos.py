"""Roles personalizados, tipos de tarea y configuracion de alertas.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from sqlalchemy.orm import Session
from app.core.errores import ErrorDeDominio
from app.models.advanced_config import AlertConfig
from app.models.advanced_config import TaskType
from app.models.advanced_config import CustomRole
from app.core.asignacion import es_asignable

from app.services.advanced_config_service.semillas import (
    DEFAULT_SYSTEM_ROLES,
    seed_alert_configs,
    seed_system_roles,
    seed_task_types,
)
from app.services.advanced_config_service._comun import NotFoundError


# ── Roles ─────────────────────────────────────────────────────────────────────

def list_roles(db: Session) -> list:
    seed_system_roles(db)
    roles = (
        db.query(CustomRole)
        .filter(CustomRole.is_active == True)
        .order_by(CustomRole.is_system.desc(), CustomRole.name)
        .all()
    )
    return [
        {
            "id": r.id, "name": r.name, "description": r.description, "color": r.color,
            "is_system": r.is_system,
            "module_access": json.loads(r.module_access) if r.module_access else {},
            "permissions": json.loads(r.permissions) if r.permissions else {},
        }
        for r in roles
    ]


_ROLES_BASE = {name for name, *_ in DEFAULT_SYSTEM_ROLES}


def create_role(data: dict, db: Session) -> dict:
    from app.core.modulos import validar_acceso
    if data["name"] in _ROLES_BASE:
        raise ErrorDeDominio(422, "Ese nombre es el de un rol base")
    validar_acceso(data.get("module_access"))
    r = CustomRole(
        name=data["name"],
        description=data.get("description"),
        color=data.get("color", "#7a8aaa"),
        module_access=json.dumps(data.get("module_access") or {}),
        permissions=json.dumps(data.get("permissions") or {}),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name}


def update_role(role_id: str, data: dict, db: Session) -> dict:
    from app.core.modulos import validar_acceso
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r:
        raise NotFoundError("Rol no encontrado")
    if "name" in data and r.is_system and data["name"] != r.name:
        raise ValueError("No se puede renombrar un rol del sistema")
    if "name" in data and not r.is_system and data["name"] in _ROLES_BASE:
        raise ValueError("Ese nombre es el de un rol base")
    validar_acceso(data.get("module_access"))
    for k, v in data.items():
        if k == "module_access" and v is not None:
            r.module_access = json.dumps(v)
        elif k == "permissions" and v is not None:
            r.permissions = json.dumps(v)
        elif es_asignable(r, k, ("is_system",)):
            setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name}


def delete_role(role_id: str, db: Session) -> dict:
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r:
        raise NotFoundError("Rol no encontrado")
    if r.is_system:
        raise ValueError("No se pueden eliminar roles del sistema")
    r.is_active = False
    db.commit()
    return {"ok": True}


# ── Task types ────────────────────────────────────────────────────────────────

def list_task_types(db: Session) -> list:
    seed_task_types(db)
    types = (
        db.query(TaskType)
        .filter(TaskType.is_active == True)
        .order_by(TaskType.sort_order)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "value": t.value, "icon": t.icon,
            "color": t.color, "is_billable_default": t.is_billable_default,
            "is_active": t.is_active, "sort_order": t.sort_order,
        }
        for t in types
    ]


def create_task_type(data: dict, db: Session):
    if db.query(TaskType).filter(TaskType.value == data["value"]).first():
        raise ValueError("Ya existe un tipo con ese valor")
    t = TaskType(**data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_task_type(type_id: str, data: dict, db: Session):
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


def delete_task_type(type_id: str, db: Session) -> dict:
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ── Alert configs ─────────────────────────────────────────────────────────────

def list_alert_configs(db: Session) -> list:
    seed_alert_configs(db)
    configs = db.query(AlertConfig).order_by(AlertConfig.alert_type).all()
    return [
        {
            "id": c.id, "alert_type": c.alert_type, "label": c.label,
            "description": c.description, "is_enabled": c.is_enabled,
            "threshold_value": c.threshold_value, "threshold_unit": c.threshold_unit,
            "notify_admin": c.notify_admin, "notify_pm": c.notify_pm,
            "notify_hr": c.notify_hr, "notify_employee": c.notify_employee,
            "notify_email": c.notify_email, "severity": c.severity,
        }
        for c in configs
    ]


def update_alert_config(alert_type: str, data: dict, db: Session):
    cfg = db.query(AlertConfig).filter(AlertConfig.alert_type == alert_type).first()
    if not cfg:
        raise NotFoundError("Configuración no encontrada")
    for k, v in data.items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return cfg
