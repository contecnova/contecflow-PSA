"""Instancias de proceso BPMN: arrancar, bandeja, completar y cancelar.

Auditoria 2026-11: /bpm no ejecutaba nada. El motor es `app/services/bpmn_engine.py`.

  POST /bpmn-processes/{id}/instances           — arrancar (variables iniciales)
  GET  /bpmn-instances                          — instancias de la organizacion
  GET  /bpmn-instances/inbox                    — pasos humanos (tareas y decisiones) que me tocan
  GET  /bpmn-instances/{id}                     — detalle con su historial
  POST /bpmn-instances/{id}/steps/{step}/complete — completar un paso humano (`flow_id` en las decisiones)
  POST /bpmn-instances/{id}/cancel              — cancelar
"""
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_pm, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bpmn_engine as motor
from app.core.codigos_de_error import error_http

procesos = APIRouter(tags=["BPMN Processes"])
router = APIRouter(tags=["BPMN Instances"])


class Variables(BaseModel):
    variables: Optional[dict] = None


class Completar(Variables):
    # Revision BPM 2026-11-16: en una decision manual, la salida elegida.
    flow_id: Optional[str] = Field(None, max_length=120)


@procesos.post("/{process_id}/instances", summary="Arrancar una instancia del proceso")
def start_instance(process_id: str, payload: Variables = Body(default_factory=Variables),
                   db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    proc = motor.proceso_para_arrancar(db, process_id, current_user)
    if proc is None:
        raise error_http(404, "no_encontrado", detail="Proceso no encontrado", que="proceso")
    inst = motor.iniciar(db, proc, current_user, payload.variables)
    return APIResponse.ok(data=motor.detalle(db, inst))


@router.get("", summary="Instancias de proceso")
def list_instances(status: Optional[Literal[motor.ESTADOS_DE_INSTANCIA]] = None,  # type: ignore[valid-type]
                   process_id: Optional[str] = None,
                   limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=motor.listar(db, current_user, status, process_id, limit))


@router.get("/inbox", summary="Pasos humanos pendientes que puedo completar")
def inbox(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=motor.bandeja(db, current_user))


@router.get("/{instance_id}", summary="Detalle de una instancia con su historial")
def get_instance(instance_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=motor.detalle(db, motor.instancia(db, instance_id, current_user)))


@router.post("/{instance_id}/steps/{step_id}/complete", summary="Completar un paso humano")
def complete_step(instance_id: str, step_id: str, payload: Completar = Body(default_factory=Completar),
                  db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    inst = motor.completar(db, inst, step_id, current_user, payload.variables, payload.flow_id)
    return APIResponse.ok(data=motor.detalle(db, inst))


@router.post("/{instance_id}/cancel", summary="Cancelar una instancia")
def cancel_instance(instance_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_pm)):
    inst = motor.instancia(db, instance_id, current_user, bloquear=True)
    return APIResponse.ok(data=motor.detalle(db, motor.cancelar(db, inst, current_user)))
