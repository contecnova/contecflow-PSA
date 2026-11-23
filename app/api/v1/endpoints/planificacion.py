"""Proyectos — planificador, nivelación, valor ganado y vistas guardadas (rev. 173).

    GET  /planning/projects/{id}/schedule           camino crítico con calendarios
    POST /planning/projects/{id}/schedule/apply     mover tareas a sus fechas tempranas
    GET  /planning/projects/{id}/leveling           propuesta de nivelación
    POST /planning/projects/{id}/leveling/apply     aplicar (toda o algunas tareas)
    GET  /planning/projects/{id}/evm                valor ganado (línea base + avance real)
    GET  /planning/projects/{id}/evm/curve          curva S histórica y prevista
    POST /planning/projects/{id}/evm/snapshot       guardar el punto de hoy
    GET  /planning/workload                         carga por persona y semana
    GET/POST/PATCH/DELETE /planning/views           vistas guardadas

La lógica vive en `app/services/planificador`, `evm_service` y `vistas_guardadas`.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, get_db, requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import evm_service, vistas_guardadas
from app.services.planificador import nivelacion
from app.services.planificador.servicio import aplicar_plan, calcular_plan, proyecto_visible
from app.core.codigos_de_error import error

router = APIRouter()


# ── Camino crítico ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/schedule", summary="Plan del proyecto: CPM con FS/SS/FF/SF, desfases, calendarios y restricciones")
def get_schedule(project_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    enforce_abac(db, current_user, "task", action="read")
    return APIResponse.ok(data=calcular_plan(db, current_user, project_id))


@router.post("/projects/{project_id}/schedule/apply", summary="Replanificar: mover las tareas pendientes a sus fechas tempranas")
def apply_schedule(project_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("proyectos.dirigir"))):
    enforce_abac(db, current_user, "task", action="update")
    return APIResponse.ok(data=aplicar_plan(db, current_user, project_id))


# ── Nivelación ───────────────────────────────────────────────────────────────

class AplicarNivelacion(BaseModel):
    task_ids: Optional[list[str]] = Field(default=None, max_length=500)


@router.get("/projects/{project_id}/leveling", summary="Propuesta de nivelación dentro de la holgura")
def get_leveling(project_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("proyectos.dirigir"))):
    return APIResponse.ok(data=nivelacion.proponer(db, current_user, project_id))


@router.post("/projects/{project_id}/leveling/apply", summary="Aplicar la nivelación (todas o las tareas pedidas)")
def apply_leveling(project_id: str, payload: AplicarNivelacion, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("proyectos.dirigir"))):
    enforce_abac(db, current_user, "task", action="update")
    return APIResponse.ok(data=nivelacion.aplicar(db, current_user, project_id, payload.task_ids))


# ── Carga por persona ────────────────────────────────────────────────────────

@router.get("/workload", summary="Carga por persona y semana desde las tareas (calendario de cada persona)")
def get_workload(project_id: Optional[str] = None, desde: Optional[date] = Query(None, alias="from"),
                 weeks: Optional[int] = Query(None, ge=1, le=26),
                 db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("proyectos.usar"))):
    from app.services.planificador.carga import carga_por_semana
    return APIResponse.ok(data=carga_por_semana(db, current_user, project_id, desde, weeks))


# ── Valor ganado ─────────────────────────────────────────────────────────────

def _exigir_finanzas(db: Session, user) -> None:
    from app.core.errores import ErrorDeDominio
    from app.services.politica_de_visibilidad import ve_modulo_financiero
    if not ve_modulo_financiero(db, user, "budgets"):
        raise error(403, "valor_ganado_financiero")


@router.get("/projects/{project_id}/evm", summary="Valor ganado: PV de la línea base vigente, EV por avance real")
def get_evm(project_id: str, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    _exigir_finanzas(db, current_user)
    proyecto = proyecto_visible(db, current_user, project_id)
    d = evm_service.evm_de_proyecto(db, proyecto)
    d.pop("_partidas", None)
    return APIResponse.ok(data=d)


@router.get("/projects/{project_id}/evm/curve", summary="Curva S: histórico diario y PV previsto")
def get_evm_curve(project_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    _exigir_finanzas(db, current_user)
    return APIResponse.ok(data=evm_service.curva_s(db, current_user, project_id))


@router.post("/projects/{project_id}/evm/snapshot", summary="Guardar hoy un punto de la curva S")
def post_evm_snapshot(project_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("proyectos.dirigir"))):
    proyecto = proyecto_visible(db, current_user, project_id)
    evm_service.guardar_punto_de_hoy(db, proyecto)
    return APIResponse.ok(data={"saved": True})


# ── Vistas guardadas ─────────────────────────────────────────────────────────

class VistaIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    entity_type: str = Field(default="task", max_length=30)
    view_type: Optional[str] = Field(default=None, max_length=20)
    project_id: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    nql_query: Optional[str] = Field(default=None, max_length=4000)
    is_shared: bool = False


class VistaPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    view_type: Optional[str] = Field(default=None, max_length=20)
    config: Optional[dict[str, Any]] = None
    nql_query: Optional[str] = Field(default=None, max_length=4000)
    is_shared: Optional[bool] = None


@router.get("/views", summary="Vistas guardadas propias y compartidas")
def list_views(entity_type: str = Query("task", max_length=30), project_id: Optional[str] = None,
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = vistas_guardadas.listar(db, current_user, entity_type, project_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/views", summary="Guardar una vista", status_code=201)
def create_view(payload: VistaIn, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("proyectos.usar"))):
    return APIResponse.ok(data=vistas_guardadas.crear(db, current_user, payload.model_dump()))


@router.patch("/views/{view_id}", summary="Cambiar una vista guardada")
def update_view(view_id: str, payload: VistaPatch = Body(...), db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("proyectos.usar"))):
    return APIResponse.ok(data=vistas_guardadas.actualizar(db, current_user, view_id,
                                                          payload.model_dump(exclude_unset=True)))


@router.delete("/views/{view_id}", summary="Borrar una vista guardada")
def delete_view(view_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("proyectos.usar"))):
    return APIResponse.ok(data=vistas_guardadas.borrar(db, current_user, view_id))
