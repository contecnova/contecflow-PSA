"""Service Desk — Autonomous Agents REST API.

Bot-driven ticket resolution, playbook management, and execution audit log.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.service_desk.autonomous_agent_service import (
    create_playbook,
    deactivate_playbook,
    evaluate_ticket_for_autonomy,
    get_execution_log,
    get_execution_stats,
    list_playbooks,
    run_autonomous_resolution,
    run_autonomous_scan,
    update_playbook,
)

router = APIRouter(prefix="/autonomous", tags=["Autonomous Agents"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class PlaybookCreateIn(BaseModel):
    name: str
    playbook_type: Optional[str] = None
    description: Optional[str] = None
    steps: list[dict] = []
    conditions: dict = {}


class PlaybookUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[dict]] = None
    conditions: Optional[dict] = None
    is_active: Optional[bool] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/playbooks", summary="Listar playbooks activos (built-in + custom)")
def get_playbooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"playbooks": list_playbooks(db)}


@router.post("/playbooks", summary="Crear nuevo playbook personalizado")
def post_playbook(
    payload: PlaybookCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = create_playbook(db, payload.model_dump())
    db.commit()
    return result


@router.put("/playbooks/{playbook_id}", summary="Actualizar playbook personalizado")
def put_playbook(
    playbook_id: str,
    payload: PlaybookUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = update_playbook(db, playbook_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return result


@router.delete("/playbooks/{playbook_id}", summary="Desactivar playbook personalizado")
def delete_playbook(
    playbook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "sd_playbook", playbook_id, action="delete")
    result = deactivate_playbook(db, playbook_id)
    db.commit()
    return result


@router.post("/tickets/{ticket_id}/evaluate", summary="Evaluar si un ticket es apto para resolución autónoma")
def evaluate_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket
    from fastapi import HTTPException

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    return evaluate_ticket_for_autonomy(db, ticket)


@router.post("/tickets/{ticket_id}/resolve", summary="Ejecutar resolución autónoma en un ticket")
def resolve_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return run_autonomous_resolution(db, ticket_id, acting_user_id=current_user.id)


@router.get("/scan", summary="Escanear y procesar todos los tickets nuevos con el agente autónomo")
def autonomous_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger the same scan that runs every 5 minutes via Celery."""
    return run_autonomous_scan(db)


@router.get("/stats", summary="Estadísticas de ejecución del agente autónomo")
def agent_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_execution_stats(db)


@router.get("/log", summary="Log de auditoría de ejecuciones del agente autónomo")
def execution_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_execution_log(db, page=page, page_size=page_size)
