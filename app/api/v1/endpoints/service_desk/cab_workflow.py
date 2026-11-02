from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import cab_workflow_service as svc
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

router = APIRouter()


class CABStartIn(BaseModel):
    manager_user_id: Optional[str] = Field(None, max_length=120)
    # Vacio: los miembros de la cola CAB de la organizacion (SD_CAB_GROUP_ID).
    cab_members: Optional[list[str]] = None
    quorum: Optional[int] = Field(None, ge=1)


class CABMeetingIn(BaseModel):
    scheduled_at: str = Field(..., min_length=10, max_length=40)
    agenda: str = Field(..., min_length=5, max_length=2000)


class CABVoteIn(BaseModel):
    approve: bool
    note: str = Field('', max_length=500)


class CABExecutorIn(BaseModel):
    executor_user_id: str = Field(..., min_length=1, max_length=120)


@router.post('/changes/{change_id}/cab/workflow', summary='Iniciar workflow formal CAB', status_code=201)
def start_workflow(
    change_id: str,
    payload: CABStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        state = svc.start_cab_workflow(
            db,
            change_id=change_id,
            requester=current_user,
            manager_user_id=payload.manager_user_id,
            cab_members=payload.cab_members,
            quorum=payload.quorum,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'workflow': state})


@router.get('/changes/{change_id}/cab/workflow', summary='Consultar estado workflow CAB')
def get_workflow(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state = svc.get_workflow(db, change_id=change_id)
    if not state:
        raise HTTPException(status_code=404, detail='workflow_cab_not_found')
    return APIResponse.ok(data=state)


@router.post('/changes/{change_id}/cab/meeting', summary='Programar meeting CAB')
def schedule_meeting(
    change_id: str,
    payload: CABMeetingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        state = svc.schedule_cab_meeting(
            db,
            change_id=change_id,
            manager=current_user,
            when_iso=payload.scheduled_at,
            agenda=payload.agenda,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'workflow': state})


@router.post('/changes/{change_id}/cab/vote', summary='Emitir voto CAB')
def cast_vote(
    change_id: str,
    payload: CABVoteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: excepcion revisada: vota el miembro del CAB designado, y el endpoint comprueba que lo eres
):
    try:
        state = svc.cast_cab_vote(
            db,
            change_id=change_id,
            voter=current_user,
            approve=payload.approve,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'workflow': state})


@router.post('/changes/{change_id}/cab/executor', summary='Asignar executor tras aprobación CAB')
def assign_executor(
    change_id: str,
    payload: CABExecutorIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        state = svc.assign_executor(
            db,
            change_id=change_id,
            executor_user_id=payload.executor_user_id,
            manager=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={'ok': True, 'workflow': state})


@router.get('/changes/cab/templates', summary='Templates CAB predefinidos (testing/comms)')
def cab_templates(
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return APIResponse.ok(data=svc.default_templates())
