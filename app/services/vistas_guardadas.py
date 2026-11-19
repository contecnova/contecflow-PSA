"""Vistas guardadas: un solo modelo para filtros NQL y vistas de trabajo.

Proyectos — vistas (16-11-2026, rev. 173). `/epics/filters` guardaba filtros NQL
y no tenía pantalla; las vistas de Tareas (tabla, línea temporal, calendario,
carga por persona) necesitaban guardar su disposición. En vez de una segunda
tabla, `saved_filters` ganó `view_type`, `config` (JSON) y `project_id`: un
filtro NQL es una vista sin disposición.

Reglas:
  · cualquiera interno guarda vistas **suyas**; compartirlas con la empresa
    (`is_shared`) es de admin o PM;
  · se ve lo propio y lo compartido;
  · solo su autor (o un admin) la cambia o la borra.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.epics import SavedFilter
from app.core.codigos_de_error import error

TIPOS_DE_VISTA = ("kanban", "list", "table", "timeline", "calendar", "workload")
_ROLES_QUE_COMPARTEN = ("admin", "pm")


def _rol(user) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or "")


def _puede_compartir(user) -> bool:
    return bool(getattr(user, "is_superadmin", False)) or _rol(user) in _ROLES_QUE_COMPARTEN


def serializar(v: SavedFilter) -> dict:
    try:
        config = json.loads(v.config) if v.config else {}
    except ValueError:
        config = {}
    return {
        "id": v.id, "name": v.name, "entity_type": v.entity_type, "view_type": v.view_type,
        "project_id": v.project_id, "config": config, "nql_query": v.nql_query or "",
        "is_shared": bool(v.is_shared), "created_by": v.created_by,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def listar(db: Session, user, entity_type: str = "task", project_id: Optional[str] = None) -> list[dict]:
    q = db.query(SavedFilter).filter(
        SavedFilter.is_active.is_(True), SavedFilter.entity_type == entity_type,
        or_(SavedFilter.created_by == user.id, SavedFilter.is_shared.is_(True)),
    )
    if project_id:
        q = q.filter(or_(SavedFilter.project_id == project_id, SavedFilter.project_id.is_(None)))
    return [serializar(v) for v in q.order_by(SavedFilter.name).all()]


def _validar(datos: dict) -> None:
    if datos.get("view_type") and datos["view_type"] not in TIPOS_DE_VISTA:
        raise error(422, "valor_no_valido", detail=f"Tipo de vista no válido: {datos['view_type']}", valor=datos['view_type'])
    if "config" in datos and datos["config"] is not None and not isinstance(datos["config"], dict):
        raise error(422, "vista_config_no_objeto")


def crear(db: Session, user, datos: dict) -> dict:
    from app.services.audit import audit_log
    _validar(datos)
    if datos.get("is_shared") and not _puede_compartir(user):
        raise error(403, "vista_compartir_solo_admin_pm")
    if datos.get("project_id"):
        from app.services.planificador.servicio import proyecto_visible
        proyecto_visible(db, user, datos["project_id"])
    v = SavedFilter(
        organization_id=getattr(user, "organization_id", None),
        name=datos["name"].strip(), entity_type=datos.get("entity_type") or "task",
        nql_query=datos.get("nql_query") or "", is_shared=bool(datos.get("is_shared")),
        view_type=datos.get("view_type"), project_id=datos.get("project_id"),
        config=json.dumps(datos.get("config") or {}), created_by=user.id,
    )
    db.add(v)
    db.flush()
    audit_log(db, user, "CREATE", "saved_view", v.id, v.name)
    db.commit()
    db.refresh(v)
    return serializar(v)


def _propia(db: Session, user, view_id: str) -> SavedFilter:
    v = db.query(SavedFilter).filter(SavedFilter.id == view_id, SavedFilter.is_active.is_(True)).first()
    if not v or (v.created_by != user.id and not v.is_shared):
        raise error(404, "no_encontrado", detail="Vista no encontrada", que="vista")
    if v.created_by != user.id and _rol(user) != "admin" and not getattr(user, "is_superadmin", False):
        raise error(403, "vista_solo_autor")
    return v


def actualizar(db: Session, user, view_id: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    _validar(datos)
    v = _propia(db, user, view_id)
    if datos.get("is_shared") and not _puede_compartir(user):
        raise error(403, "vista_compartir_solo_admin_pm")
    for campo in ("name", "nql_query", "view_type", "is_shared"):
        if datos.get(campo) is not None:
            setattr(v, campo, datos[campo])
    if datos.get("config") is not None:
        v.config = json.dumps(datos["config"])
    audit_log(db, user, "UPDATE", "saved_view", v.id, v.name)
    db.commit()
    db.refresh(v)
    return serializar(v)


def borrar(db: Session, user, view_id: str) -> dict:
    from app.services.audit import audit_log
    v = _propia(db, user, view_id)
    v.is_active = False
    audit_log(db, user, "DELETE", "saved_view", v.id, v.name)
    db.commit()
    return {"deleted": True}
