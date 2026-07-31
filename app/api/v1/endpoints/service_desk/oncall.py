"""Service Desk — On-Call Schedules subdomain router."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import OnCallScheduleIn, OnCallEntryIn
from app.services.service_desk.oncall_service import (
    list_oncall_schedules_payload, create_oncall_schedule_record,
    update_oncall_schedule_record, delete_oncall_schedule as delete_oncall_schedule_svc,
    create_oncall_entry_record, delete_oncall_entry as delete_oncall_entry_svc,
    list_current_oncall_payload,
)

router = APIRouter()


@router.get("/oncall/schedules", summary="Listar schedules de guardia")
def list_oncall_schedules(group_id: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_oncall_schedules_payload(db, group_id))


@router.post("/oncall/schedules", summary="Crear schedule de guardia", status_code=201)
def create_oncall_schedule(payload: OnCallScheduleIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    s = create_oncall_schedule_record(db, payload)
    _commit_or_rollback(db); db.refresh(s)
    return APIResponse.ok(data={"id": s.id, "name": s.name})


@router.patch("/oncall/schedules/{schedule_id}", summary="Actualizar schedule")
def update_oncall_schedule(schedule_id: str, payload: OnCallScheduleIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    update_oncall_schedule_record(db, schedule_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.delete("/oncall/schedules/{schedule_id}", summary="Eliminar schedule")
def delete_oncall_schedule(schedule_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_oncall_schedule", schedule_id, action="delete")
    delete_oncall_schedule_svc(db, schedule_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/oncall/schedules/{schedule_id}/entries", summary="Añadir turno de guardia", status_code=201)
def add_oncall_entry(schedule_id: str, payload: OnCallEntryIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    entry = create_oncall_entry_record(db, schedule_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": entry.id})


@router.delete("/oncall/entries/{entry_id}", summary="Eliminar turno de guardia")
def delete_oncall_entry(entry_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    enforce_abac(db, current_user, "sd_oncall_entry", entry_id, action="delete")
    delete_oncall_entry_svc(db, entry_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/oncall/current", summary="¿Quién está de guardia ahora?")
def get_current_oncall(group_id: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_current_oncall_payload(db, group_id))
