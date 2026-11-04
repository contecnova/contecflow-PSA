"""Instancias de proceso BPMN: arrancar, bandeja, completar y cancelar.

Auditoria 2026-11: /bpm no ejecutaba nada. El motor es `app/services/bpmn_engine.py`.

  POST /bpmn-processes/{id}/instances           — arrancar (variables iniciales)
  GET  /bpmn-instances                          — instancias de la organizacion
  GET  /bpmn-instances/inbox                    — pasos humanos que me tocan
  GET  /bpmn-instances/{id}                     — detalle con su historial
  POST /bpmn-instances/{id}/steps/{step}/complete — completar un paso humano
  POST /bpmn-instances/{id}/cancel              — cancelar
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin_or_pm, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bpmn_engine as motor

procesos = APIRouter(tags=["BPMN Processes"])
router = APIRouter(tags=["BPMN Instances"])


class Variables(BaseModel):
    variables: Optional[dict] = None


@procesos.post("/{process_id}/instances", summary="Arrancar una instancia del proceso")
def start_instance(process_id: str, payload: Variables = Body(default_factory=Variables),
                   db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    proc = motor.proceso_para_arrancar(db, process_id, current_user)
    if proc is None:
        raise HTTPException(404, "Proceso no encontrado")
    inst = motor.iniciar(db, proc, current_user, payload.variables)
    return APIResponse.ok(data=motor.serializar(inst))


@router.get("", summary="Instancias de proceso")
def list_instances(status: Optional[str] = None, process_id: Optional[str] = None,
                   limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=motor.listar(db, current_user, status, process_id, limit))


@router.get("/inbox", summary="Pasos humanos pendientes que puedo completar")
def inbox(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIListResponse.ok(items=motor.bandeja(db, current_user))


@router.get("/{instance_id}", summary="Detalle de una instancia con su historial")
def get_instance(instance_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=motor.serializar(motor.instancia(db, instance_id, current_user)))


@router.post("/{instance_id}/steps/{step_id}/complete", summary="Completar un paso humano")
def complete_step(instance_id: str, step_id: str, payload: Variables = Body(default_factory=Variables),
                  db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    inst = motor.completar(db, motor.instancia(db, instance_id, current_user), step_id, current_user, payload.variables)
    return APIResponse.ok(data=motor.serializar(inst))


@router.post("/{instance_id}/cancel", summary="Cancelar una instancia")
def cancel_instance(instance_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=motor.serializar(motor.cancelar(db, motor.instancia(db, instance_id, current_user))))
