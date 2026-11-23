"""Catálogo de cambios estándar del CAB (23-11-2026, auditoría 2026-11-22 A-SD19).

- Leer (y elegir modelo al crear un cambio): `sd.completo`.
- Proponer, editar, aprobar, suspender, reactivar y dar de baja: `sd.gestionar`.
  Aprobar además exige ser del CAB (o administrador) y no haberlo propuesto.

Lógica y reglas: `app/services/service_desk/cambios_estandar_service.py`.
Prefijo propio (`/standard-changes`): bajo `/changes/{id}` lo atraparía el detalle.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import cambios_estandar_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter(tags=["Service Desk - Cambios estándar"])


class ModeloEstandarIn(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    procedure: str = Field(..., min_length=3, max_length=20000)
    rollback_plan: Optional[str] = Field(None, max_length=20000)
    test_plan: Optional[str] = Field(None, max_length=20000)
    max_risk: str = Field("low", pattern="^(low|medium|high|critical)$")
    applies_to_ci_ids: List[str] = Field(default_factory=list, max_length=500)
    applies_to_ci_types: List[str] = Field(default_factory=list, max_length=50)
    applies_to_service_ids: List[str] = Field(default_factory=list, max_length=500)
    review_interval_days: Optional[int] = Field(None, ge=1, le=3650)


class ModeloEstandarUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    procedure: Optional[str] = Field(None, min_length=3, max_length=20000)
    rollback_plan: Optional[str] = Field(None, max_length=20000)
    test_plan: Optional[str] = Field(None, max_length=20000)
    max_risk: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    applies_to_ci_ids: Optional[List[str]] = Field(None, max_length=500)
    applies_to_ci_types: Optional[List[str]] = Field(None, max_length=50)
    applies_to_service_ids: Optional[List[str]] = Field(None, max_length=500)
    review_interval_days: Optional[int] = Field(None, ge=1, le=3650)


class SuspensionIn(BaseModel):
    reason: str = Field(..., min_length=5, max_length=2000)


@router.get("/standard-changes", summary="Catálogo de cambios estándar de la empresa")
def listar(
    solo_vigentes: bool = Query(False, description="Solo los que hoy valen como estándar (selector del alta)"),
    incluir_bajas: bool = Query(False),
    db: Session = Depends(get_db),
    cu: User = Depends(requiere_capacidad("sd.completo")),
):
    return APIListResponse.ok(items=svc.listar_modelos(db, cu, solo_vigentes=solo_vigentes, incluir_bajas=incluir_bajas))


@router.get("/standard-changes/{modelo_id}", summary="Detalle de un modelo de cambio estándar")
def detalle(modelo_id: str, db: Session = Depends(get_db), cu: User = Depends(requiere_capacidad("sd.completo"))):
    return APIResponse.ok(data=svc.serializar_modelo(svc.obtener_modelo(db, cu, modelo_id)))


@router.post("/standard-changes", summary="Proponer un modelo de cambio estándar (pendiente del CAB)", status_code=201)
def proponer(payload: ModeloEstandarIn, db: Session = Depends(get_db),
             cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.proponer_modelo(db, cu, payload.model_dump())
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))


@router.patch("/standard-changes/{modelo_id}", summary="Editar un modelo (si cambia el procedimiento, vuelve al CAB)")
def editar(modelo_id: str, payload: ModeloEstandarUpdate, db: Session = Depends(get_db),
           cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.editar_modelo(db, cu, modelo_id, payload.model_dump(exclude_unset=True))
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))


@router.post("/standard-changes/{modelo_id}/approve", summary="Aprobar el modelo como estándar (CAB)")
def aprobar(modelo_id: str, db: Session = Depends(get_db), cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.aprobar_modelo(db, cu, modelo_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))


@router.post("/standard-changes/{modelo_id}/suspend", summary="Suspender el modelo: sus cambios vuelven al CAB")
def suspender(modelo_id: str, payload: SuspensionIn, db: Session = Depends(get_db),
              cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.suspender_modelo(db, cu, svc.obtener_modelo(db, cu, modelo_id), payload.reason)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))


@router.post("/standard-changes/{modelo_id}/reactivate", summary="Reactivar un modelo suspendido (vuelve a propuesto)")
def reactivar(modelo_id: str, db: Session = Depends(get_db), cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.reactivar_modelo(db, cu, modelo_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))


@router.delete("/standard-changes/{modelo_id}", summary="Dar de baja un modelo de cambio estándar")
def retirar(modelo_id: str, db: Session = Depends(get_db), cu: User = Depends(requiere_capacidad("sd.gestionar"))):
    modelo = svc.retirar_modelo(db, cu, modelo_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=svc.serializar_modelo(modelo))
