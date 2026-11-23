"""Escenarios de simulacion.

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
from fastapi import APIRouter, Depends, HTTPException
from app.core.codigos_de_error import error_http
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from pydantic import BaseModel
from app.db.session import get_db
from app.core.deps import requiere_capacidad
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
import app.services.scenarios_service as _scenarios

router = APIRouter()


@router.get("/scenarios", summary="Listar escenarios what-if")
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("recursos.gestionar")),
):
    return APIListResponse.ok(items=_scenarios.list_scenarios(db))


class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_date: Optional[date] = None
    horizon_weeks: int = 12
    projects: Optional[List[dict]] = None


@router.post("/scenarios", summary="Crear escenario what-if")
def create_scenario(
    payload: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("recursos.gestionar")),
):
    return APIResponse.ok(data=_scenarios.create_scenario(payload.model_dump(), current_user.id, db))


@router.post("/scenarios/{scenario_id}/compute", summary="Calcular impacto del escenario")
def compute_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("recursos.gestionar")),
):
    try:
        return APIResponse.ok(data=_scenarios.compute_scenario(scenario_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado", que="escenario")


@router.get("/scenarios/{scenario_id}", summary="Detalle de escenario")
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("recursos.gestionar")),
):
    try:
        return APIResponse.ok(data=_scenarios.get_scenario(scenario_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado", que="escenario")


@router.delete("/scenarios/{scenario_id}", summary="Eliminar escenario")
def delete_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("recursos.gestionar")),
):
    enforce_abac(db, current_user, "scenario", scenario_id, action="delete")
    try:
        return APIResponse.ok(data=_scenarios.delete_scenario(scenario_id, db))
    except ValueError:
        raise error_http(404, "no_encontrado", que="escenario")
