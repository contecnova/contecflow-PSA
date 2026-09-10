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
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.core.tenancy import org_scoped_or_404
from app.models.user import User
from app.models.service_desk import Ticket, TicketStatus
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    anotar_en_el_historial,
    cerrojo_del_trabajo,
    estado_del_trabajo,
    get_auto_resolution_config,
    get_auto_resolution_stats,
    guardar_estado_del_trabajo,
    historial_del_trabajo,
    record_resolution_feedback,
    run_auto_close_job,
    run_daily_auto_resolution_job,
    save_auto_resolution_config,
    validate_auto_resolution,
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
):
    """
    Apply AI-recommended resolution to a ticket.

    Only admins or L3 support can apply auto-resolution.
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Only admins/support can apply auto-resolution")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    if ticket.status in [TicketStatus.resolved, TicketStatus.closed]:
        raise HTTPException(status_code=400, detail="Ticket already resolved/closed")

    # Analyze first
    analysis = analyze_ticket_for_resolution(db, ticket, current_user)

    if analysis["confidence"] < 0.65 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Confidence too low ({analysis['confidence']*100:.1f}%). "
                   f"Use ?force=true to override.",
        )

    # Apply resolution
    ticket.status = TicketStatus.resolved
    ticket.resolution_text = analysis["suggestion"]
    ticket.resolution = analysis["suggestion"]
    ticket.root_cause = analysis.get("root_cause", "")
    ticket.auto_resolved = True
    ticket.auto_resolved_at = datetime.now(timezone.utc)
    ticket.auto_resolved_by = current_user.username
    ticket.auto_resolved_confidence = analysis["confidence"]

    if analysis["kb_sources"]:
        import json

        ticket.resolution_kb_articles = json.dumps(
            [s["number"] for s in analysis["kb_sources"]]
        )

    db.commit()

    return APIResponse.ok(data={
        "message": f"✅ Ticket {ticket.number} auto-resolved with {analysis['confidence']*100:.1f}% confidence",
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    })


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

    org = _organizacion_de(current_user)
    cerrojo = cerrojo_del_trabajo(org)
    safe_limit = max(1, min(int(limit), 500))

    if run_async:
        if not cerrojo.acquire(blocking=False):
            return APIResponse.ok(data={
                "status": "already_running",
                "message": "Auto-resolution job is already running",
                "runtime": estado_del_trabajo(db, org),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        job_id = str(uuid4())
        started_at = datetime.now(timezone.utc)

        guardar_estado_del_trabajo(db, {
                "running": True,
                "status": "running",
                "last_job_id": job_id,
                "started_at": started_at.isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "stats": None,
                "error": None,
            },
            org,
        )
        db.commit()

        def _run_job_in_background(limit_to_use: int, queued_job_id: str) -> None:
            session = SessionLocal()
            # Auditoria 2026-08 (hallazgo 22). Este es un trabajo de fondo, asi
            # que la rama de «sesion no inicializada» de `TenantSession` esta
            # pensada para el — pero **la organizacion se conoce** (`org`, del
            # sujeto que lanzo la pasada), y el trabajo la pasa explicita a
            # cada servicio. Publicarla en la sesion no cambia el
            # comportamiento y anade la capa implicita detras de la explicita,
            # que es justo lo que faltaba en los otros ocho sitios.
            if org:
                session.info["organization_id"] = org
                session.info["is_superadmin"] = False
            run_started = datetime.now(timezone.utc)
            try:
                stats = run_daily_auto_resolution_job(session, limit=limit_to_use, organization_id=org)
                run_finished = datetime.now(timezone.utc)
                duration_ms = int((run_finished - run_started).total_seconds() * 1000)
                run_record = {
                    "status": "completed",
                    "started_at": run_started.isoformat(),
                    "completed_at": run_finished.isoformat(),
                    "duration_ms": duration_ms,
                    "stats": stats,
                    "error": None,
                }
                guardar_estado_del_trabajo(session, {
                        "running": False,
                        "last_job_id": queued_job_id,
                        **run_record,
                    },
                    org,
                )
                anotar_en_el_historial(session, run_record, org)
                session.commit()
                _logger.info(
                    "Auto-resolution background job %s finished: %s",
                    queued_job_id,
                    stats,
                )
            except Exception as exc:
                run_finished = datetime.now(timezone.utc)
                duration_ms = int((run_finished - run_started).total_seconds() * 1000)
                try:
                    fail_record = {
                        "status": "failed",
                        "started_at": run_started.isoformat(),
                        "completed_at": run_finished.isoformat(),
                        "duration_ms": duration_ms,
                        "stats": None,
                        "error": str(exc)[:240],
                    }
                    guardar_estado_del_trabajo(session, {
                            "running": False,
                            "last_job_id": queued_job_id,
                            **fail_record,
                        },
                        org,
                    )
                    anotar_en_el_historial(session, fail_record, org)
                    session.commit()
                except Exception:
                    session.rollback()
                _logger.exception(
                    "Auto-resolution background job %s failed: %s",
                    queued_job_id,
                    exc,
                )
            finally:
                session.close()
                cerrojo.release()

        background_tasks.add_task(_run_job_in_background, safe_limit, job_id)
        return APIResponse.ok(data={
            "status": "queued",
            "job_id": job_id,
            "limit": safe_limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ── Camino sincrono ─────────────────────────────────────────────────────
    #
    # Auditoria 2026-08 (hallazgo 22). Dos cosas que este bloque no hacia y el
    # camino asincrono de arriba SI hace. La señal fue la asimetria: dos
    # caminos para el mismo trabajo, uno correcto y el otro no.
    #
    # 1. El guardia `already_running` protegia SOLO el camino asincrono. El lock
    #    se toma en la rama `run_async=True` y se libera en su `finally`; esta
    #    rama no lo tocaba, asi que dos llamadas con `run_async=False` podian
    #    solaparse entre si y con una asincrona ya en cola. El trabajo resuelve
    #    tickets automaticamente: solapar dos pasadas puede resolver el mismo
    #    ticket dos veces.
    #
    # 2. El `except` escribia el registro de fallo y hacia `commit()` SIN
    #    `rollback()` antes. Si el fallo original era de base —y lo probable es
    #    que lo sea, porque el trabajo escribe en base— la sesion queda en
    #    transaccion abortada: el registro del fallo no se escribia nunca, el
    #    panel se quedaba diciendo «running» para siempre, y el error real
    #    quedaba tapado por un `PendingRollbackError`.
    if not cerrojo.acquire(blocking=False):
        return APIResponse.ok(data={
            "status": "already_running",
            "message": "Auto-resolution job is already running",
            "runtime": estado_del_trabajo(db, org),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    try:
        sync_started = datetime.now(timezone.utc)
        guardar_estado_del_trabajo(db, {
                "running": True,
                "status": "running",
                "last_job_id": None,
                "started_at": sync_started.isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "stats": None,
                "error": None,
            },
            org,
        )
        db.commit()

        try:
            stats = run_daily_auto_resolution_job(db, limit=safe_limit, organization_id=org)
            sync_finished = datetime.now(timezone.utc)
            duration_ms = int((sync_finished - sync_started).total_seconds() * 1000)
            sync_record = {
                "status": "completed",
                "started_at": sync_started.isoformat(),
                "completed_at": sync_finished.isoformat(),
                "duration_ms": duration_ms,
                "stats": stats,
                "error": None,
            }
            guardar_estado_del_trabajo(db, {"running": False, "last_job_id": None, **sync_record}, org)
            anotar_en_el_historial(db, sync_record, org)
            db.commit()
        except Exception as exc:
            # Deshacer ANTES de intentar escribir el registro de fallo: si el
            # fallo era de base, la sesion esta abortada y sin este rollback el
            # `commit()` de abajo revienta con `PendingRollbackError` y tapa el
            # error real.
            db.rollback()
            sync_finished = datetime.now(timezone.utc)
            duration_ms = int((sync_finished - sync_started).total_seconds() * 1000)
            fail_record = {
                "status": "failed",
                "started_at": sync_started.isoformat(),
                "completed_at": sync_finished.isoformat(),
                "duration_ms": duration_ms,
                "stats": None,
                "error": str(exc)[:240],
            }
            try:
                guardar_estado_del_trabajo(db, {"running": False, "last_job_id": None, **fail_record}, org)
                anotar_en_el_historial(db, fail_record, org)
                db.commit()
            except Exception:
                # Si ni el registro del fallo se puede escribir, se deja la
                # sesion limpia y se propaga el error ORIGINAL, que es el que
                # tiene que ver quien lee el log.
                db.rollback()
                _logger.exception(
                    "no se pudo registrar el fallo del job de auto-resolucion"
                )
            raise

        return APIResponse.ok(data={
            **stats,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        cerrojo.release()


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
):
    """
    Check whether an auto-resolved ticket was subsequently reopened and record
    that outcome in the feedback loop.

    Returns: {validated, reopened, ticket_id, ticket_number}
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    result = validate_auto_resolution(db, ticket)
    db.commit()
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
):
    """
    Record whether the auto-resolution was successful or not.
    This feeds the historical success-rate used in composite confidence scoring.

    Body: {"success": true | false}
    """
    if current_user.role not in ["admin", "support"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    record_resolution_feedback(db, ticket, body.success)
    db.commit()
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
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    payload = body.model_dump(exclude_unset=True)
    cfg = save_auto_resolution_config(db, payload)
    db.commit()
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
):
    """
    Close tickets that have been in *resolved* status for more than
    AUTO_CLOSE_HOURS_AFTER_RESOLUTION hours, and validate those within
    VALIDATION_WINDOW_HOURS.

    Admin-only. Returns: {closed, validated, errors}
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    stats = run_auto_close_job(db, _organizacion_de(current_user))
    db.commit()
    return APIResponse.ok(data={
        **stats,
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
