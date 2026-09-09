"""Líneas base del Gantt: congelar el cronograma y comparar contra él.

Auditoría 2026-08 (hallazgo 22). Este módulo estaba en
`app/api/v1/endpoints/v239/`, un directorio nombrado por número de versión. El
fichero ya se llamaba por su dominio; lo que agrupaba por versión era la
carpeta. Las rutas no han cambiado: el prefijo lo pone el registro en
`routers/`, no la ruta del fichero.

Y sus nueve consultas y escrituras están ahora en
`app/services/baselines_service.py`. Al bajarlas apareció que los cuatro
endpoints anclan en `project_id` y **ninguno comprobaba de quién es el
proyecto**: todo lo demás cuelga de ahí, así que el proyecto era el único punto
donde la tenencia se podía verificar y era el que faltaba.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, get_db, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import baselines_service as svc

router = APIRouter()


class BaselineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_initial: bool = False


@router.get("/projects/{project_id}/baselines", summary="List Gantt baselines for project")
def list_baselines(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filas = svc.list_baselines(db, current_user, project_id)
    return APIListResponse.ok(items=[
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "baseline_date": str(b.baseline_date),
            "total_tasks": b.total_tasks,
            "completed_tasks": b.completed_tasks,
            "total_hours": b.total_hours,
            "budget_at_freeze": b.budget_at_freeze,
            "is_initial": b.is_initial,
            "created_at": str(b.created_at) if b.created_at else None,
        }
        for b in filas
    ])


@router.post("/projects/{project_id}/baselines", summary="Freeze current Gantt as baseline", status_code=201)
def create_baseline(
    project_id: str,
    payload: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    baseline = svc.crear_linea_base(
        db, current_user, project_id,
        name=payload.name, description=payload.description,
        is_initial=payload.is_initial,
    )
    return APIResponse.ok(data={
        "id": baseline.id,
        "name": baseline.name,
        "baseline_date": str(baseline.baseline_date),
        "total_tasks": baseline.total_tasks,
        "total_hours": baseline.total_hours,
        "created": True,
    })


@router.get("/projects/{project_id}/baselines/{baseline_id}/compare", summary="Compare current schedule vs baseline")
def compare_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(
        data=svc.comparar_con_linea_base(db, current_user, project_id, baseline_id))


@router.delete("/projects/{project_id}/baselines/{baseline_id}", summary="Delete baseline", status_code=204)
def delete_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "gantt_baseline", baseline_id, action="delete")
    svc.borrar_linea_base(db, current_user, project_id, baseline_id)
    return None
