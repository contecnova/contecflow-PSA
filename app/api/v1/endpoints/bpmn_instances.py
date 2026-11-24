"""Instancias de proceso BPMN: arrancar, bandeja, completar, seguir y gobernar.

Auditoria 2026-11: /bpm no ejecutaba nada. El motor es `app/services/bpmn_engine.py`.
Guia: `docs/BPM.md`.

  POST /bpmn-processes/{id}/instances              — arrancar (variables iniciales, clave de negocio)
  GET  /bpmn-instances                             — instancias de la organizacion (filtros y busqueda)
  GET  /bpmn-instances/inbox                       — pasos humanos (tareas y decisiones) que me tocan
  GET  /bpmn-instances/metrics                     — duracion, cuellos de botella, atascadas, fuera de plazo
  POST /bpmn-instances/messages                    — entregar un mensaje por clave de negocio
  GET  /bpmn-instances/{id}                        — detalle con su historial
  POST /bpmn-instances/{id}/steps/{step}/complete  — completar un paso humano (`flow_id(s)`, `error_code`)
  POST /bpmn-instances/{id}/steps/{step}/assign    — reasignar un paso humano
  POST /bpmn-instances/{id}/steps/{step}/retry     — reintentar un incidente
  POST /bpmn-instances/{id}/messages               — entregar un mensaje a esta instancia
  POST /bpmn-instances/{id}/suspend | /resume      — suspender o reanudar
  POST /bpmn-instances/{id}/migrate                — pasar a otra version del proceso
  POST /bpmn-instances/{id}/cancel                 — cancelar

Revision BPM 2026-11-23: asignacion, formularios, suspension, migracion,
mensajes, incidentes, metricas y auditoria de cada accion.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error_http
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bpmn_engine as motor
from app.services import bpmn_gobierno

procesos = APIRouter(tags=["BPMN Processes"])
router = APIRouter(tags=["BPMN Instances"])


class Variables(BaseModel):
    variables: Optional[dict] = None


class Arranque(Variables):
    business_key: Optional[str] = Field(None, max_length=120)


class Completar(Variables):
    # Revision BPM 2026-11-16: en una decision manual, la salida elegida.
    flow_id: Optional[str] = Field(None, max_length=120)
    # 23-11-2026: decision de una compuerta inclusiva (varias salidas) y error
    # de negocio que captura el borde de error de la tarea.
    flow_ids: Optional[list[str]] = Field(None, max_length=50)
    error_code: Optional[str] = Field(None, max_length=120)


class Asignar(BaseModel):
    user_id: Optional[str] = Field(None, max_length=255)


class Migrar(BaseModel):
    version: int = Field(..., ge=1)


class Mensaje(Variables):
    message: str = Field(..., min_length=1, max_length=200)


class MensajePorClave(Mensaje):
    business_key: str = Field(..., min_length=1, max_length=120)


@procesos.post("/{process_id}/instances", summary="Arrancar una instancia del proceso")
def start_instance(process_id: str, payload: Arranque = Body(default_factory=Arranque),
                   db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    proc = motor.proceso_para_arrancar(db, process_id, current_user)
    if proc is None:
        raise error_http(404, "no_encontrado", detail="Proceso no encontrado", que="proceso")
    inst = motor.iniciar(db, proc, current_user, payload.variables, payload.business_key)
    return APIResponse.ok(data=motor.detalle(db, inst))


@router.get("", summary="Instancias de proceso")
def list_instances(status: Optional[Literal[motor.ESTADOS_DE_INSTANCIA]] = None,  # type: ignore[valid-type]
                   process_id: Optional[str] = None,
                   q: Optional[str] = Query(None, max_length=100),
                   limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("bpm.usar"))):
    return APIListResponse.ok(items=motor.listar(db, current_user, status, process_id, limit, q))


@router.get("/inbox", summary="Pasos humanos pendientes que puedo completar")
def inbox(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("bpm.usar"))):
    return APIListResponse.ok(items=motor.bandeja(db, current_user))


@router.get("/metrics", summary="Métricas: duración, cuellos de botella, instancias atascadas")
def metrics(process_id: Optional[str] = None, days: int = Query(30, ge=1, le=365),
            db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("bpm.usar"))):
    return APIResponse.ok(data=bpmn_gobierno.metricas(db, current_user, process_id, days))


@router.post("/messages", summary="Entregar un mensaje a las instancias con esa clave de negocio")
def message_by_key(payload: MensajePorClave, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    ids = motor.correlacionar(db, payload.message, current_user, business_key=payload.business_key,
                              variables=payload.variables)
    return APIResponse.ok(data={"instances": ids})


@router.get("/{instance_id}", summary="Detalle de una instancia con su historial")
def get_instance(instance_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("bpm.usar"))):
    return APIResponse.ok(data=motor.detalle(db, motor.instancia(db, instance_id, current_user)))


@router.post("/{instance_id}/steps/{step_id}/complete", summary="Completar un paso humano")
def complete_step(instance_id: str, step_id: str, payload: Completar = Body(default_factory=Completar),
                  db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("bpm.usar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    inst = motor.completar(db, inst, step_id, current_user, payload.variables, payload.flow_id,
                           payload.flow_ids, payload.error_code)
    return APIResponse.ok(data=motor.detalle(db, inst))


@router.post("/{instance_id}/steps/{step_id}/assign", summary="Reasignar un paso humano (vacío: liberarlo)")
def assign_step(instance_id: str, step_id: str, payload: Asignar, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.reasignar(db, inst, step_id, payload.user_id, current_user)))


@router.post("/{instance_id}/steps/{step_id}/retry", summary="Reintentar una acción automática en incidente")
def retry_step(instance_id: str, step_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.reintentar(db, inst, step_id, current_user)))


@router.post("/{instance_id}/messages", summary="Entregar un mensaje a esta instancia")
def message(instance_id: str, payload: Mensaje, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user)
    motor.correlacionar(db, payload.message, current_user, instancia_id=inst.id, variables=payload.variables)
    return APIResponse.ok(data=motor.detalle(db, motor.instancia(db, instance_id, current_user)))


@router.post("/{instance_id}/suspend", summary="Suspender una instancia")
def suspend_instance(instance_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.suspender(db, inst, current_user)))


@router.post("/{instance_id}/resume", summary="Reanudar una instancia suspendida")
def resume_instance(instance_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.reanudar(db, inst, current_user)))


@router.post("/{instance_id}/migrate", summary="Pasar la instancia a otra versión del proceso")
def migrate_instance(instance_id: str, payload: Migrar, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.migrar(db, inst, payload.version, current_user)))


@router.post("/{instance_id}/cancel", summary="Cancelar una instancia")
def cancel_instance(instance_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("bpm.gestionar"))):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.cancelar(db, inst, current_user)))
