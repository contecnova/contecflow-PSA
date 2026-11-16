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
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import cmdb_clases_propias as clases

router = APIRouter(prefix="/cmdb", tags=["Service Desk - CMDB"])


class ClaseIn(BaseModel):
    key: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=100)
    base_type: str
    description: Optional[str] = Field(None, max_length=2000)
    is_active: bool = True
    sort_order: int = Field(0, ge=0, le=10000)


@router.get("/ci-classes", summary="Clases de CI de la empresa y las clases base")
def list_ci_classes(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=clases.listar(db, current_user.organization_id))


@router.post("/ci-classes", summary="Crear clase de CI", status_code=201)
def create_ci_class(payload: ClaseIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=clases.crear(db, current_user, payload.model_dump()))


@router.put("/ci-classes/{class_id}", summary="Cambiar clase de CI (la clave no cambia)")
def update_ci_class(class_id: str, payload: ClaseIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=clases.cambiar(db, current_user, class_id, payload.model_dump()))


@router.delete("/ci-classes/{class_id}", summary="Desactivar clase de CI (sus CIs la conservan)")
def delete_ci_class(class_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    clases.desactivar(db, current_user, class_id)
    return APIResponse.ok(data={"ok": True})
