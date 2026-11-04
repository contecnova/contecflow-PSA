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
from app.models.bpmn_process import BPMNInstance, BPMNInstanceStep, BPMNProcess
from app.models.user import User
from app.services import bpmn_engine as motor

procesos = APIRouter(tags=["BPMN Processes"])
router = APIRouter(tags=["BPMN Instances"])


class Variables(BaseModel):
    variables: Optional[dict] = None


def _de_mi_organizacion(q, modelo, user: User):
    if user.is_superadmin:
        return q
    return q.filter(modelo.organization_id == user.organization_id)


def _instancia(db: Session, instance_id: str, user: User) -> BPMNInstance:
    inst = _de_mi_organizacion(db.query(BPMNInstance).filter(BPMNInstance.id == instance_id),
                               BPMNInstance, user).first()
    if inst is None:
        raise HTTPException(404, "Instancia no encontrada")
    return inst


@procesos.post("/{process_id}/instances", summary="Arrancar una instancia del proceso")
def start_instance(process_id: str, payload: Variables = Body(default_factory=Variables),
                   db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    proc = _de_mi_organizacion(db.query(BPMNProcess).filter(BPMNProcess.id == process_id,
                                                            BPMNProcess.is_active.is_(True)),
                               BPMNProcess, current_user).first()
    if proc is None:
        raise HTTPException(404, "Proceso no encontrado")
    inst = motor.iniciar(db, proc, current_user, payload.variables)
    return APIResponse.ok(data=motor.serializar(inst))


@router.get("", summary="Instancias de proceso")
def list_instances(status: Optional[str] = None, process_id: Optional[str] = None,
                   limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    q = _de_mi_organizacion(db.query(BPMNInstance), BPMNInstance, current_user)
    if status:
        q = q.filter(BPMNInstance.status == status)
    if process_id:
        q = q.filter(BPMNInstance.process_id == process_id)
    filas = q.order_by(BPMNInstance.started_at.desc()).limit(limit).all()
    nombres = dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(
        BPMNProcess.id.in_({i.process_id for i in filas} or {""})).all())
    return APIListResponse.ok(items=[{**motor.serializar(i, con_pasos=False),
                                      "process_name": nombres.get(i.process_id)} for i in filas])


@router.get("/inbox", summary="Pasos humanos pendientes que puedo completar")
def inbox(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    pasos = _de_mi_organizacion(
        db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id).filter(
            BPMNInstanceStep.status == "active", BPMNInstanceStep.element_type.in_(motor.HUMANOS),
            BPMNInstance.status == "running"),
        BPMNInstanceStep, current_user).order_by(BPMNInstanceStep.created_at).all()
    mios = [p for p in pasos if motor.puede_completar(p, current_user)]
    nombres = dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(
        BPMNProcess.id.in_({p.instance.process_id for p in mios} or {""})).all())
    return APIListResponse.ok(items=[{**motor.serializar_paso(p), "process_id": p.instance.process_id,
                                      "process_name": nombres.get(p.instance.process_id),
                                      "variables": motor._variables(p.instance)} for p in mios])


@router.get("/{instance_id}", summary="Detalle de una instancia con su historial")
def get_instance(instance_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=motor.serializar(_instancia(db, instance_id, current_user)))


@router.post("/{instance_id}/steps/{step_id}/complete", summary="Completar un paso humano")
def complete_step(instance_id: str, step_id: str, payload: Variables = Body(default_factory=Variables),
                  db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    inst = motor.completar(db, _instancia(db, instance_id, current_user), step_id, current_user, payload.variables)
    return APIResponse.ok(data=motor.serializar(inst))


@router.post("/{instance_id}/cancel", summary="Cancelar una instancia")
def cancel_instance(instance_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=motor.serializar(motor.cancelar(db, _instancia(db, instance_id, current_user))))
