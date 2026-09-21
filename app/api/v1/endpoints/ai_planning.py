"""Planificacion asistida: estimacion y triaje.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_internal_user
from app.models.user import User
from app.core.responses import APIResponse
# Auditoría 2026-08 (hallazgo 22). Antes esto era un único
# `import app.services.mfa_service as _svc`, porque toda la lógica de estos
# ocho dominios vivía en un fichero llamado `mfa_service`. Ahora cada dominio
# tiene su módulo y la llamada dice a qué servicio va.
import app.services.ai_planning_service as _ai_plan
from app.schemas.auth_payloads import (
    AcceptFlagIn,
)

router = APIRouter()


@router.post("/ai-planning/estimate/{task_id}", summary="Estimar horas de tarea con IA")
def estimate_task_hours(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_ai_plan.estimate_task_hours(task_id, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/ai-planning/estimate/{task_id}/accept", summary="Aceptar o rechazar estimación IA")
def accept_estimate(
    task_id: str,
    payload: AcceptFlagIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_ai_plan.accept_task_estimate(task_id, payload.accepted, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/ai-planning/triage/{ticket_id}", summary="Triaje automático de ticket con IA")
def ai_triage_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    try:
        return APIResponse.ok(data=_ai_plan.triage_ticket(ticket_id, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/ai-planning/triage/{ticket_id}/accept", summary="Aplicar triaje IA al ticket")
def accept_triage(
    ticket_id: str,
    payload: AcceptFlagIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_ai_plan.accept_ticket_triage(ticket_id, payload.accepted, current_user.id, db))
    except ValueError:
        raise HTTPException(404)
