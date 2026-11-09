"""Presupuestos por departamento y ejercicio.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import app.services.budgets_service as _budgets
from app.core.deps import require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User

router = APIRouter()

# Revisión 2026-11: presupuestos con partidas, real calculado, versiones y
# aprobación. Leer es de los responsables (`require_any_manager`); crear, editar
# y aprobar lo deciden `BUDGET_MANAGER_ROLES` y `BUDGET_APPROVER_ROLES` dentro
# del servicio. Ver `app/services/budgets_service.py`.


class PresupuestoIn(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    ambito: Optional[str] = Field(None, pattern="^(proyecto|proyecto_previsto|departamento|area)$")
    department: Optional[str] = Field(None, max_length=100)
    area: Optional[str] = Field(None, max_length=255)
    project_id: Optional[str] = None
    cliente_id: Optional[str] = None
    tipo_proyecto: Optional[str] = Field(None, max_length=30)
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    currency: Optional[str] = Field(None, max_length=3)
    notes: Optional[str] = None


class PartidaIn(BaseModel):
    tipo: Optional[str] = Field(None, max_length=30)
    descripcion: Optional[str] = Field(None, max_length=500)
    user_id: Optional[str] = None
    perfil: Optional[str] = Field(None, max_length=120)
    horas: Optional[float] = Field(None, ge=0)
    coste_hora: Optional[float] = Field(None, ge=0)
    importe: Optional[float] = Field(None, ge=0)
    meses: Optional[dict[str, float]] = None


class DecisionIn(BaseModel):
    aprobado: bool
    motivo: Optional[str] = Field(None, max_length=2000)


class VinculoIn(BaseModel):
    project_id: str


@router.get("/budgets", summary="Presupuestos (última versión de cada uno) con plan, real y previsión")
def list_budgets(year: Optional[int] = None, ambito: Optional[str] = None, estado: Optional[str] = None,
                 db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    items = _budgets.listar(db, current_user, year=year, ambito=ambito, estado=estado)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/budgets/summary", summary="Resumen del ejercicio: plan, real y previsión por mes")
def budget_summary(year: Optional[int] = Query(default=None), db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.resumen(db, current_user, year))


@router.post("/budgets", summary="Crear presupuesto (proyecto, proyecto previsto, departamento o área)")
def create_budget(body: PresupuestoIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.crear(db, current_user, body.model_dump(exclude_unset=True)))


@router.get("/budgets/{budget_id}", summary="Ficha: partidas, seguimiento, versiones y aprobación")
def get_budget(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.detalle(db, current_user, budget_id))


@router.patch("/budgets/{budget_id}", summary="Editar la cabecera (borrador o rechazado)")
def update_budget(budget_id: str, body: PresupuestoIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.editar(db, current_user, budget_id, body.model_dump(exclude_unset=True)))


@router.post("/budgets/{budget_id}/lines", summary="Añadir una partida")
def add_line(budget_id: str, body: PartidaIn, db: Session = Depends(get_db),
             current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.crear_linea(db, current_user, budget_id, body.model_dump(exclude_unset=True)))


@router.patch("/budgets/{budget_id}/lines/{line_id}", summary="Editar una partida")
def update_line(budget_id: str, line_id: str, body: PartidaIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.editar_linea(db, current_user, budget_id, line_id,
                                                     body.model_dump(exclude_unset=True)))


@router.delete("/budgets/{budget_id}/lines/{line_id}", summary="Quitar una partida")
def delete_line(budget_id: str, line_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.borrar_linea(db, current_user, budget_id, line_id))


@router.post("/budgets/{budget_id}/submit", summary="Enviar a aprobación")
def submit_budget(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.enviar(db, current_user, budget_id))


@router.post("/budgets/{budget_id}/decision", summary="Aprobar o rechazar (BUDGET_APPROVER_ROLES)")
def decide_budget(budget_id: str, body: DecisionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.decidir(db, current_user, budget_id, body.aprobado, body.motivo))


@router.post("/budgets/{budget_id}/new-version", summary="Reprevisión: versión nueva a partir de ésta")
def new_version(budget_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.nueva_version(db, current_user, budget_id))


@router.post("/budgets/{budget_id}/link-project", summary="Vincular un proyecto previsto al proyecto ya creado")
def link_project(budget_id: str, body: VinculoIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_any_manager)):
    return APIResponse.ok(data=_budgets.vincular_proyecto(db, current_user, budget_id, body.project_id))
