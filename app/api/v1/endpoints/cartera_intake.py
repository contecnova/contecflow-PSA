"""Cartera: intake de propuestas, puntuación, fases y conversión (rev. 173).

    GET/POST/PATCH   /portfolio-intake/criteria[/{id}]      criterios de puntuación
    GET/POST/PATCH   /portfolio-intake/gates[/{id}]         fases (stage-gate)
    GET/POST         /portfolio-intake/proposals            propuestas
    GET/PATCH        /portfolio-intake/proposals/{id}
    POST             /portfolio-intake/proposals/{id}/submit     enviar a la siguiente fase
    POST             /portfolio-intake/proposals/{id}/decision   decidir (sin flujo de aprobación)
    POST             /portfolio-intake/proposals/{id}/convert    convertir en proyecto
    GET              /portfolio-intake/proposals/{id}/capacity   horas pedidas frente a libres

Lógica en `app/services/cartera_service.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin_or_pm, require_internal_user
from app.core.paginacion import Paginacion, lista_paginada, paginacion
from app.core.responses import APIResponse
from app.models.user import User
from app.services import cartera_service as svc
from app.core.codigos_de_error import error

router = APIRouter()


class CriterioIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    weight: Optional[float] = Field(default=None, ge=0)
    inverse: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FaseIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    sort_order: Optional[int] = None
    workflow_id: Optional[str] = None
    min_score: Optional[float] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None


class RolPedido(BaseModel):
    role: str = Field(..., min_length=1, max_length=100)
    hours: float = Field(..., ge=0)


class PropuestaIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=10000)
    portfolio_id: Optional[str] = None
    sponsor_id: Optional[str] = None
    client_id: Optional[str] = None
    template_id: Optional[str] = None
    estimated_budget: Optional[float] = Field(default=None, ge=0)
    estimated_hours: Optional[float] = Field(default=None, ge=0)
    wanted_start: Optional[date] = None
    wanted_end: Optional[date] = None
    roles_needed: Optional[list[RolPedido]] = Field(default=None, max_length=50)
    scores: Optional[dict[str, float]] = None


class DecisionIn(BaseModel):
    approved: bool
    note: Optional[str] = Field(default=None, max_length=2000)


class ConvertirIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    pm_id: Optional[str] = None


# ── Configuración ────────────────────────────────────────────────────────────

@router.get("/criteria", summary="Criterios de puntuación de la empresa")
def list_criteria(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=[svc.criterio_dict(c) for c in svc.criterios(db, current_user)])


@router.post("/criteria", summary="Crear criterio", status_code=201)
def create_criterion(payload: CriterioIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_or_pm)):
    if not payload.name:
        from app.core.errores import ErrorDeDominio
        raise error(422, "criterio_sin_nombre")
    return APIResponse.ok(data=svc.guardar_criterio(db, current_user, payload.model_dump(exclude_unset=True)))


@router.patch("/criteria/{criterion_id}", summary="Cambiar criterio")
def update_criterion(criterion_id: str, payload: CriterioIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.guardar_criterio(db, current_user, payload.model_dump(exclude_unset=True),
                                                    criterion_id))


@router.get("/gates", summary="Fases (stage-gate) de la empresa")
def list_gates(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=[svc.fase_dict(g) for g in svc.fases(db, current_user, solo_activas=False)])


@router.post("/gates", summary="Crear fase", status_code=201)
def create_gate(payload: FaseIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin_or_pm)):
    if not payload.name:
        from app.core.errores import ErrorDeDominio
        raise error(422, "fase_sin_nombre")
    return APIResponse.ok(data=svc.guardar_fase(db, current_user, payload.model_dump(exclude_unset=True)))


@router.patch("/gates/{gate_id}", summary="Cambiar fase")
def update_gate(gate_id: str, payload: FaseIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.guardar_fase(db, current_user, payload.model_dump(exclude_unset=True), gate_id))


# ── Propuestas ───────────────────────────────────────────────────────────────

@router.get("/proposals", summary="Propuestas de la empresa")
def list_proposals(response: Response, status: Optional[str] = None,
                   pagina: Paginacion = Depends(paginacion), db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    lista_fases = svc.fases(db, current_user)
    resultado = svc.listar(db, current_user, status, pagina).mapear(
        lambda p: svc.propuesta_dict(db, p, lista_fases))
    return lista_paginada(response, resultado)


@router.post("/proposals", summary="Nueva propuesta (intake)", status_code=201)
def create_proposal(payload: PropuestaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    datos = payload.model_dump(exclude_unset=True)
    if not datos.get("title"):
        from app.core.errores import ErrorDeDominio
        raise error(422, "propuesta_sin_titulo")
    return APIResponse.ok(data=svc.guardar(db, current_user, datos))


@router.get("/proposals/{proposal_id}", summary="Detalle de propuesta")
def get_proposal(proposal_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    p = svc.obtener(db, current_user, proposal_id)
    return APIResponse.ok(data=svc.propuesta_dict(db, p, svc.fases(db, current_user)))


@router.patch("/proposals/{proposal_id}", summary="Cambiar propuesta o su puntuación")
def update_proposal(proposal_id: str, payload: PropuestaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.guardar(db, current_user, payload.model_dump(exclude_unset=True), proposal_id))


@router.post("/proposals/{proposal_id}/submit", summary="Enviar a la siguiente fase")
def submit_proposal(proposal_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=svc.enviar_a_fase(db, current_user, proposal_id))


@router.post("/proposals/{proposal_id}/decision", summary="Decidir la fase (sin flujo de aprobación)")
def decide_proposal(proposal_id: str, payload: DecisionIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.decidir_en_pantalla(db, current_user, proposal_id, payload.approved, payload.note))


@router.post("/proposals/{proposal_id}/convert", summary="Convertir en proyecto")
def convert_proposal(proposal_id: str, payload: ConvertirIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=svc.convertir_en_proyecto(db, current_user, proposal_id, payload.model_dump()))


@router.get("/proposals/{proposal_id}/capacity", summary="Capacidad que pide frente a la libre del equipo")
def proposal_capacity(proposal_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=svc.capacidad(db, current_user, proposal_id))
