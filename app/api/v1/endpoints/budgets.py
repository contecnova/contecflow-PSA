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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import require_any_manager, require_admin
from app.models.user import User
from app.core.config import settings
from app.core.responses import APIListResponse, APIResponse
import app.services.budgets_service as _budgets

router = APIRouter()


@router.get("/budgets", summary="Listar presupuestos")
def list_budgets(
    year: Optional[int] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_budgets.list_budgets(year, department, db))


class BudgetCreate(BaseModel):
    name: str
    year: int
    department: Optional[str] = None
    project_id: Optional[str] = None
    total_amount: float = 0
    currency: str = settings.DEFAULT_CURRENCY
    notes: Optional[str] = None
    monthly_planned: Optional[List[float]] = None


class BudgetEntryUpdate(BaseModel):
    """Campos editables de una entrada mensual de presupuesto."""
    month: int
    planned: Optional[float] = None
    actual: Optional[float] = None
    committed: Optional[float] = None
    notes: Optional[str] = None


@router.post("/budgets", summary="Crear presupuesto anual")
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_budgets.create_budget(payload.model_dump(), current_user.id, db))


@router.patch("/budgets/{budget_id}/entry", summary="Actualizar entrada mensual de presupuesto")
def update_budget_entry(
    budget_id: str,
    payload: BudgetEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_budgets.update_budget_entry(budget_id, payload.model_dump(exclude_unset=True), db))
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404)
        raise HTTPException(400, msg)


@router.post("/budgets/{budget_id}/approve", summary="Aprobar presupuesto")
def approve_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_budgets.approve_budget(budget_id, current_user, db))
    except ValueError:
        raise HTTPException(404)


@router.get("/budgets/summary", summary="Resumen anual de presupuestos")
def budget_summary(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_budgets.get_budget_summary(year, db))
