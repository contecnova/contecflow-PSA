"""Service Desk — calendario de cambios, ventanas de congelacion y versiones.

Prefijos propios a proposito: `/changes/calendar` seria un solo segmento y lo
atraparia `GET /changes/{change_id}` de `misc`.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import change_calendar_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter(tags=["Service Desk - Calendario de cambios"])


class CongelacionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    reason: Optional[str] = Field(None, max_length=2000)
    start_at: datetime
    end_at: datetime


class VersionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    version: Optional[str] = Field(None, max_length=50)
    status: str = "planned"
    planned_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=5000)
    owner_id: Optional[str] = None


@router.get("/change-calendar", summary="Cambios, versiones y congelaciones de un periodo, con choques")
def calendario(desde: datetime = Query(...), hasta: datetime = Query(...), db: Session = Depends(get_db),
               _: User = Depends(get_current_user), _rol: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.calendario(db, desde, hasta))


@router.get("/change-blackouts", summary="Ventanas de congelación")
def congelaciones(db: Session = Depends(get_db), _: User = Depends(get_current_user),
                  _rol: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=svc.listar_congelaciones(db))


@router.post("/change-blackouts", summary="Crear ventana de congelación", status_code=201)
def crear_congelacion(payload: CongelacionIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    b = svc.guardar_congelacion(db, payload.model_dump())
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_congelacion(b))


@router.put("/change-blackouts/{blackout_id}", summary="Editar ventana de congelación")
def editar_congelacion(blackout_id: str, payload: CongelacionIn, db: Session = Depends(get_db),
                       _: User = Depends(require_any_manager)):
    b = svc.guardar_congelacion(db, payload.model_dump(), blackout_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_congelacion(b))


@router.delete("/change-blackouts/{blackout_id}", summary="Quitar ventana de congelación")
def borrar_congelacion(blackout_id: str, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    svc.borrar_congelacion(db, blackout_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/releases", summary="Versiones y sus cambios")
def versiones(db: Session = Depends(get_db), _: User = Depends(get_current_user),
              _rol: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=svc.listar_versiones(db))


@router.post("/releases", summary="Crear versión", status_code=201)
def crear_version(payload: VersionIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    r = svc.guardar_version(db, payload.model_dump())
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_version(r, db))


@router.put("/releases/{release_id}", summary="Editar versión")
def editar_version(release_id: str, payload: VersionIn, db: Session = Depends(get_db),
                   _: User = Depends(require_any_manager)):
    r = svc.guardar_version(db, payload.model_dump(), release_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_version(r, db))


@router.delete("/releases/{release_id}", summary="Quitar versión")
def borrar_version(release_id: str, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    svc.borrar_version(db, release_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})
