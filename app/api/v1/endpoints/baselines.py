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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, get_db, requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import baselines_service as svc

router = APIRouter()


class BaselineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_initial: bool = False
    # Rev. 173: la primera de un proyecto es la vigente; las demás, si se pide.
    make_current: Optional[bool] = None


@router.get("/projects/{project_id}/baselines", summary="List Gantt baselines for project")
def list_baselines(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filas = svc.list_baselines(db, current_user, project_id)
    return APIListResponse.ok(items=[svc.serializar(b) for b in filas])


@router.post("/projects/{project_id}/baselines", summary="Freeze current Gantt as baseline", status_code=201)
def create_baseline(
    project_id: str,
    payload: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("proyectos.responsables")),
):
    baseline = svc.crear_linea_base(
        db, current_user, project_id,
        name=payload.name, description=payload.description,
        is_initial=payload.is_initial, make_current=payload.make_current,
    )
    return APIResponse.ok(data={**svc.serializar(baseline), "created": True})


@router.post("/projects/{project_id}/baselines/{baseline_id}/make-current",
             summary="Use this baseline for the Gantt, slippage and earned value")
def make_current_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("proyectos.responsables")),
):
    return APIResponse.ok(data=svc.serializar(svc.marcar_vigente(db, current_user, project_id, baseline_id)))


@router.get("/projects/{project_id}/baselines/{baseline_id}/compare", summary="Compare current schedule (or another baseline) vs baseline")
def compare_baseline(
    project_id: str,
    baseline_id: str,
    against: Optional[str] = Query(None, description="Otra línea base del proyecto en vez del plan de hoy"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(
        data=svc.comparar_con_linea_base(db, current_user, project_id, baseline_id, against))


@router.delete("/projects/{project_id}/baselines/{baseline_id}", summary="Delete baseline", status_code=204)
def delete_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("proyectos.responsables")),
):
    enforce_abac(db, current_user, "gantt_baseline", baseline_id, action="delete")
    svc.borrar_linea_base(db, current_user, project_id, baseline_id)
    return None
