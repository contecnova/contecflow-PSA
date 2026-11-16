"""Clases de CI configurables (mejoras de mercado 16-11-2026, migracion 174).

Las clases de CI eran un enum fijo (`CIType`). Ahora cada empresa declara las
suyas («Firewall», «Cajero», «Licencia SaaS»…) y cada una se apoya en una
clase base, que es la que siguen entendiendo el descubrimiento, el analisis de
impacto, la topologia y los datos propios de clase. Un CI con clase propia
guarda la clave en `ci_class` y su clase base en `ci_type`.

Leer es del equipo; crear, cambiar y desactivar, de administrador.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin, require_internal_user
from app.core.errores import ErrorDeDominio
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.service_desk import CIClass, CIType, ConfigurationItem
from app.models.user import User
from app.services.audit import auditar_y_confirmar

router = APIRouter(prefix="/cmdb", tags=["Service Desk - CMDB"])

CLASES_BASE = tuple(c.value for c in CIType)


class ClaseIn(BaseModel):
    key: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=100)
    base_type: str
    description: Optional[str] = Field(None, max_length=2000)
    is_active: bool = True
    sort_order: int = Field(0, ge=0, le=10000)


def _ser(c: CIClass, en_uso: int = 0) -> dict:
    return {"id": c.id, "key": c.key, "label": c.label, "base_type": c.base_type, "description": c.description,
            "is_active": c.is_active, "sort_order": c.sort_order, "ci_count": en_uso}


def _uso(db: Session, org_id, clave: str) -> int:
    return db.query(ConfigurationItem.id).filter(ConfigurationItem.organization_id == org_id,
                                                 ConfigurationItem.ci_class == clave,
                                                 ConfigurationItem.is_active.is_(True)).count()


@router.get("/ci-classes", summary="Clases de CI de la empresa y las clases base")
def list_ci_classes(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    org = current_user.organization_id
    filas = db.query(CIClass).filter(CIClass.organization_id == org).order_by(CIClass.sort_order, CIClass.label).all()
    return APIResponse.ok(data={"base_types": list(CLASES_BASE),
                                "classes": [_ser(c, _uso(db, org, c.key)) for c in filas]})


@router.post("/ci-classes", summary="Crear clase de CI", status_code=201)
def create_ci_class(payload: ClaseIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if payload.base_type not in CLASES_BASE:
        raise ErrorDeDominio(422, "Clase base no válida")
    if payload.key in CLASES_BASE:
        raise ErrorDeDominio(422, "La clave coincide con una clase base")
    org = current_user.organization_id
    if db.query(CIClass.id).filter(CIClass.organization_id == org, CIClass.key == payload.key).first():
        raise ErrorDeDominio(409, "Ya hay una clase con esa clave")
    c = CIClass(organization_id=org, **payload.model_dump())
    db.add(c)
    db.flush()
    auditar_y_confirmar(db, current_user, "CREATE", "sd_ci_class", c.id, c.label, new_values=payload.model_dump())
    return APIResponse.ok(data=_ser(c))


@router.put("/ci-classes/{class_id}", summary="Cambiar clase de CI (la clave no cambia)")
def update_ci_class(class_id: str, payload: ClaseIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    org = current_user.organization_id
    c = db.query(CIClass).filter(CIClass.id == class_id, CIClass.organization_id == org).first()
    if c is None:
        raise ErrorDeDominio(404, "Clase no encontrada")
    if payload.base_type not in CLASES_BASE:
        raise ErrorDeDominio(422, "Clase base no válida")
    if payload.base_type != c.base_type:
        # Sus CIs pasan a la nueva clase base: es lo que leen descubrimiento e impacto.
        db.query(ConfigurationItem).filter(ConfigurationItem.organization_id == org,
                                           ConfigurationItem.ci_class == c.key).update(
            {ConfigurationItem.ci_type: payload.base_type}, synchronize_session=False)
    for k in ("label", "base_type", "description", "is_active", "sort_order"):
        setattr(c, k, getattr(payload, k))
    auditar_y_confirmar(db, current_user, "UPDATE", "sd_ci_class", c.id, c.label, new_values=payload.model_dump())
    return APIResponse.ok(data=_ser(c, _uso(db, org, c.key)))


@router.delete("/ci-classes/{class_id}", summary="Desactivar clase de CI (sus CIs la conservan)")
def delete_ci_class(class_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    c = db.query(CIClass).filter(CIClass.id == class_id, CIClass.organization_id == current_user.organization_id).first()
    if c is None:
        raise ErrorDeDominio(404, "Clase no encontrada")
    c.is_active = False
    auditar_y_confirmar(db, current_user, "DELETE", "sd_ci_class", c.id, c.label)
    return APIResponse.ok(data={"ok": True})
