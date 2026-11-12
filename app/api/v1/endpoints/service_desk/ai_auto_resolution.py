"""
Service Desk AI Auto-Resolution endpoints.

Auditoria 2026-08 (hallazgo 22, tanda 2). Los 17 puntos de acceso a base de este
fichero estan en `services/service_desk/ai_auto_resolution_service.py`, y con
ellos salieron cuatro cosas de la misma familia —algo que deberia ser por cliente
y no lo era—:

1. **El trabajo procesaba tickets de TODAS las organizaciones.**
   `run_daily_auto_resolution_job` acepta `organization_id` y su docstring dice
   que sin el «procesa todos». El endpoint no lo pasaba, y en el camino asincrono
   la sesion es un `SessionLocal()` recien creado —sin contexto de tenant—, asi
   que el filtro se salta por diseño. Un administrador de un cliente lanzaba la
   auto-resolucion sobre los tickets de todos los demas, resolviendolos y
   comentandolos: escritura cruzada, no lectura.
2. **La configuracion era global**: cualquier administrador cambiaba los umbrales
   de confianza, el auto-cierre y el tope del trabajo para todos los clientes.
3. **El estado y el historial del trabajo eran globales**: un cliente veia el
   `job_id`, los tiempos, las estadisticas y los errores de otro.
4. **El cerrojo era uno para todo el proceso**: con el trabajo de un cliente en
   marcha, el de otro recibia `already_running`.

Routes:
  POST /sd/tickets/{ticket_id}/ai-analyze
  POST /sd/tickets/{ticket_id}/ai-auto-resolve
  POST /sd/auto-resolution/run-job
  POST /sd/tickets/{ticket_id}/auto-resolution/validate
  POST /sd/tickets/{ticket_id}/auto-resolution/feedback
  GET  /sd/auto-resolution/stats
  POST /sd/auto-resolution/run-close-job
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_internal_user
from app.core.responses import APIResponse
from app.core.tenancy import org_scoped_or_404
from app.models.user import User
from app.models.service_desk import Ticket
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    estado_del_trabajo,
    get_auto_resolution_config,
    get_auto_resolution_stats,
    historial_del_trabajo,
)
from app.services.service_desk.auto_resolucion_operaciones import (
    aplicar_auto_resolucion,
    cerrar_resueltos,
    guardar_configuracion,
    lanzar_trabajo,
    registrar_valoracion,
    validar_auto_resolucion,
)

router = APIRouter(tags=["Service Desk - AI Auto-Resolution"])
_logger = logging.getLogger("sd_auto_resolution_endpoint")


def _organizacion_de(user) -> str | None:
    """La organizacion del sujeto, o `None` para una ejecucion de plataforma.

    `None` no es un descuido: es la semantica que el servicio documenta para
    `organization_id` —sin organizacion recorre todo, que es lo que quiere un
    cron global—. Un superadmin de plataforma no tiene organizacion asignada, y
    para el esa es la lectura correcta. Lo que estaba mal era que el endpoint no
    pasara NADA teniendo delante a un administrador de un cliente concreto.
    """
    return getattr(user, "organization_id", None)


class FeedbackBody(BaseModel):
    success: bool


class AutoResolutionConfigPatch(BaseModel):
    threshold_auto: float | None = None
    threshold_suggest: float | None = None
    auto_close_hours_after_resolution: int | None = None
    validation_window_hours: int | None = None
    default_job_limit: int | None = None


@router.post(
    "/tickets/{ticket_id}/ai-analyze",
    summary="Analyze ticket for AI auto-resolution suggestions",
    response_model=APIResponse[dict],
    responses={
        404: {"description": "Ticket not found"},
        403: {"description": "Not authorized to view this ticket"},
    },
)
def analyze_ticket_for_ai_resolution(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    """
    Analyze a ticket and get AI-powered resolution suggestions.

    Returns:
    {
        "ticket_id": str,
        "analysis": str,
        "suggestion": str,
        "confidence": float (0-1),
        "kb_sources": list[dict],
        "action_taken": str ("auto-resolved" | "suggested" | "none"),
        "recommendation": str,
    }
    """
    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    # Authorization: user must be assigned to ticket or be admin
    if (
        ticket.assigned_to_user_id != current_user.id
        and current_user.role not in ["admin", "support"]
    ):
        raise HTTPException(status_code=403, detail="Not authorized")

    result = analyze_ticket_for_resolution(db, ticket, current_user)
    return APIResponse.ok(data=result)


@router.post(
    "/tickets/{ticket_id}/ai-auto-resolve",
    summary="Apply AI auto-resolution to a ticket",
    response_model=APIResponse[dict],
    responses={
        404: {"description": "Ticket not found"},
        403: {"description": "Not authorized"},
        400: {"description": "Ticket already resolved or analysis confidence too low"},
    },
)
def apply_ai_auto_resolution(
    ticket_id: str,
    force: bool = Query(False, description="Force apply even if low confidence"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    """
    Apply AI-recommended resolution to a ticket.

    Only admins or L3 support can apply auto-resolution.
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Only admins/support can apply auto-resolution")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    return APIResponse.ok(data=aplicar_auto_resolucion(db, ticket, current_user, force))


@router.post(
    "/auto-resolution/run-job",
    summary="Run daily auto-resolution job",
    response_model=APIResponse[dict],
    responses={
        403: {"description": "Only admins can run jobs"},
    },
)
def run_auto_resolution_job(
    background_tasks: BackgroundTasks,
    limit: int = Query(100, ge=1, le=500, description="Max tickets to process"),
    run_async: bool = Query(True, description="Run in background and return immediately"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: automatismos que resuelven solos
):
    """
    Run the daily auto-resolution job.

    Admin-only. Analyzes open tickets and resolves if high confidence.

    Returns job stats:
    {
        "processed": count,
        "auto_resolved": count,
        "suggested": count,
        "failed": count,
    }
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can run this job")

    return APIResponse.ok(data=lanzar_trabajo(
        db, _organizacion_de(current_user), limit, run_async, background_tasks.add_task))


@router.post(
    "/tickets/{ticket_id}/auto-resolution/validate",
    summary="Validate post-resolution outcome",
    response_model=APIResponse[dict],
    responses={
        404: {"description": "Ticket not found"},
        403: {"description": "Not authorized"},
    },
)
def validate_ticket_auto_resolution(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: operacion diaria del service desk
):
    """
    Check whether an auto-resolved ticket was subsequently reopened and record
    that outcome in the feedback loop.

    Returns: {validated, reopened, ticket_id, ticket_number}
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    result = validar_auto_resolucion(db, ticket)
    return APIResponse.ok(data=result)


@router.post(
    "/tickets/{ticket_id}/auto-resolution/feedback",
    summary="Submit manual feedback on auto-resolution quality",
    response_model=APIResponse[dict],
    responses={
        404: {"description": "Ticket not found"},
        403: {"description": "Not authorized"},
    },
)
def submit_auto_resolution_feedback(
    ticket_id: str,
    body: FeedbackBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: operacion diaria del service desk
):
    """
    Record whether the auto-resolution was successful or not.
    This feeds the historical success-rate used in composite confidence scoring.

    Body: {"success": true | false}
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    registrar_valoracion(db, ticket, body.success)
    return APIResponse.ok(data={"recorded": True, "ticket_id": ticket_id, "success": body.success})


@router.get(
    "/auto-resolution/stats",
    summary="Get auto-resolution aggregate stats",
    response_model=APIResponse[dict],
    responses={
        403: {"description": "Admin only"},
    },
)
def get_auto_resolution_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return aggregate statistics for the auto-resolution feedback loop.

    Returns: {total_auto_resolved, total_feedback, success_rate, buckets}
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    org = _organizacion_de(current_user)
    payload = get_auto_resolution_stats(db)
    payload["runtime"] = estado_del_trabajo(db, org)
    payload["job_history"] = historial_del_trabajo(db, org)
    return APIResponse.ok(data=payload)


@router.get(
    "/auto-resolution/config",
    summary="Get auto-resolution config",
    response_model=APIResponse[dict],
    responses={403: {"description": "Admin only"}},
)
def get_auto_resolution_config_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return APIResponse.ok(data=get_auto_resolution_config(db))


@router.patch(
    "/auto-resolution/config",
    summary="Update auto-resolution config",
    response_model=APIResponse[dict],
    responses={403: {"description": "Admin only"}},
)
def update_auto_resolution_config_endpoint(
    body: AutoResolutionConfigPatch,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: configuracion: la forma de la ruta manda sobre el fichero
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    payload = body.model_dump(exclude_unset=True)
    cfg = guardar_configuracion(db, payload)
    return APIResponse.ok(data=cfg)


@router.post(
    "/auto-resolution/run-close-job",
    summary="Run auto-close job for resolved tickets",
    response_model=APIResponse[dict],
    responses={
        403: {"description": "Admin only"},
    },
)
def run_auto_close_job_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: automatismos que resuelven solos
):
    """
    Close tickets that have been in *resolved* status for more than
    AUTO_CLOSE_HOURS_AFTER_RESOLUTION hours, and validate those within
    VALIDATION_WINDOW_HOURS.

    Admin-only. Returns: {closed, validated, errors}
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    stats = cerrar_resueltos(db, _organizacion_de(current_user))
    return APIResponse.ok(data={
        **stats,
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
