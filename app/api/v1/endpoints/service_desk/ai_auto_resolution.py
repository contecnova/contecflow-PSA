"""
Service Desk AI Auto-Resolution endpoints.

Routes:
  POST /sd/tickets/{ticket_id}/ai-analyze
  POST /sd/tickets/{ticket_id}/ai-auto-resolve
  POST /sd/auto-resolution/run-job
  POST /sd/tickets/{ticket_id}/auto-resolution/validate
  POST /sd/tickets/{ticket_id}/auto-resolution/feedback
  GET  /sd/auto-resolution/stats
  POST /sd/auto-resolution/run-close-job
"""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.tenancy import org_scoped_or_404
from app.models.user import User
from app.models.service_desk import Ticket, TicketStatus
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    run_daily_auto_resolution_job,
    validate_auto_resolution,
    record_resolution_feedback,
    get_auto_resolution_stats,
    get_auto_resolution_config,
    save_auto_resolution_config,
    run_auto_close_job,
)

router = APIRouter(tags=["Service Desk - AI Auto-Resolution"])
_logger = logging.getLogger("sd_auto_resolution_endpoint")


_AUTO_RES_JOB_LOCK = Lock()
_AUTO_RES_RUNTIME_KEY = "sd.auto_resolution.job_runtime"
_AUTO_RES_HISTORY_KEY = "sd.auto_resolution.job_history"
_MAX_JOB_HISTORY = 20


def _set_runtime_state(db: Session, payload: dict) -> None:
    from app.models.settings import AppSetting  # noqa: PLC0415

    row = db.query(AppSetting).filter(AppSetting.key == _AUTO_RES_RUNTIME_KEY).first()
    serialized = json.dumps(payload)
    if row:
        row.value = serialized
    else:
        db.add(AppSetting(key=_AUTO_RES_RUNTIME_KEY, value=serialized))
    db.flush()


def _get_runtime_state(db: Session) -> dict:
    from app.models.settings import AppSetting  # noqa: PLC0415

    row = db.query(AppSetting).filter(AppSetting.key == _AUTO_RES_RUNTIME_KEY).first()
    if not row or not row.value:
        return {
            "running": False,
            "status": "never_run",
            "last_job_id": None,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "stats": None,
            "error": None,
        }
    try:
        return json.loads(row.value)
    except Exception:
        return {
            "running": False,
            "status": "invalid_state",
            "last_job_id": None,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "stats": None,
            "error": "state_parse_error",
        }


def _get_job_history(db: Session) -> list:
    from app.models.settings import AppSetting  # noqa: PLC0415

    row = db.query(AppSetting).filter(AppSetting.key == _AUTO_RES_HISTORY_KEY).first()
    if not row or not row.value:
        return []
    try:
        return json.loads(row.value)
    except Exception:
        return []


def _append_job_history(db: Session, record: dict) -> None:
    """Prepend *record* to the history list and trim to _MAX_JOB_HISTORY entries."""
    from app.models.settings import AppSetting  # noqa: PLC0415

    history = _get_job_history(db)
    history.insert(0, record)
    history = history[:_MAX_JOB_HISTORY]
    serialized = json.dumps(history)
    row = db.query(AppSetting).filter(AppSetting.key == _AUTO_RES_HISTORY_KEY).first()
    if row:
        row.value = serialized
    else:
        db.add(AppSetting(key=_AUTO_RES_HISTORY_KEY, value=serialized))
    db.flush()


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
    response_model=dict,
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
    return result


@router.post(
    "/tickets/{ticket_id}/ai-auto-resolve",
    summary="Apply AI auto-resolution to a ticket",
    response_model=dict,
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

    return {
        "message": f"✅ Ticket {ticket.number} auto-resolved with {analysis['confidence']*100:.1f}% confidence",
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    }


@router.post(
    "/auto-resolution/run-job",
    summary="Run daily auto-resolution job",
    response_model=dict,
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

    safe_limit = max(1, min(int(limit), 500))

    if run_async:
        if not _AUTO_RES_JOB_LOCK.acquire(blocking=False):
            return {
                "status": "already_running",
                "message": "Auto-resolution job is already running",
                "runtime": _get_runtime_state(db),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        job_id = str(uuid4())
        started_at = datetime.now(timezone.utc)

        _set_runtime_state(
            db,
            {
                "running": True,
                "status": "running",
                "last_job_id": job_id,
                "started_at": started_at.isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "stats": None,
                "error": None,
            },
        )
        db.commit()

        def _run_job_in_background(limit_to_use: int, queued_job_id: str) -> None:
            session = SessionLocal()
            run_started = datetime.now(timezone.utc)
            try:
                stats = run_daily_auto_resolution_job(session, limit=limit_to_use)
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
                _set_runtime_state(
                    session,
                    {
                        "running": False,
                        "last_job_id": queued_job_id,
                        **run_record,
                    },
                )
                _append_job_history(session, run_record)
                session.commit()
                _logger.info(
                    "Auto-resolution background job %s finished: %s",
                    queued_job_id,
                    stats,
                )
            except Exception as exc:  # noqa: BLE001
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
                    _set_runtime_state(
                        session,
                        {
                            "running": False,
                            "last_job_id": queued_job_id,
                            **fail_record,
                        },
                    )
                    _append_job_history(session, fail_record)
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
                _AUTO_RES_JOB_LOCK.release()

        background_tasks.add_task(_run_job_in_background, safe_limit, job_id)
        return {
            "status": "queued",
            "job_id": job_id,
            "limit": safe_limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Run job
    sync_started = datetime.now(timezone.utc)
    _set_runtime_state(
        db,
        {
            "running": True,
            "status": "running",
            "last_job_id": None,
            "started_at": sync_started.isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "stats": None,
            "error": None,
        },
    )
    db.commit()

    try:
        stats = run_daily_auto_resolution_job(db, limit=safe_limit)
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
        _set_runtime_state(db, {"running": False, "last_job_id": None, **sync_record})
        _append_job_history(db, sync_record)
        db.commit()
    except Exception as exc:  # noqa: BLE001
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
        _set_runtime_state(db, {"running": False, "last_job_id": None, **fail_record})
        _append_job_history(db, fail_record)
        db.commit()
        raise
    
    return {
        **stats,
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post(
    "/tickets/{ticket_id}/auto-resolution/validate",
    summary="Validate post-resolution outcome",
    response_model=dict,
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
    return result


@router.post(
    "/tickets/{ticket_id}/auto-resolution/feedback",
    summary="Submit manual feedback on auto-resolution quality",
    response_model=dict,
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
    return {"recorded": True, "ticket_id": ticket_id, "success": body.success}


@router.get(
    "/auto-resolution/stats",
    summary="Get auto-resolution aggregate stats",
    response_model=dict,
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

    payload = get_auto_resolution_stats(db)
    payload["runtime"] = _get_runtime_state(db)
    payload["job_history"] = _get_job_history(db)
    return payload


@router.get(
    "/auto-resolution/config",
    summary="Get auto-resolution config",
    response_model=dict,
    responses={403: {"description": "Admin only"}},
)
def get_auto_resolution_config_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return get_auto_resolution_config(db)


@router.patch(
    "/auto-resolution/config",
    summary="Update auto-resolution config",
    response_model=dict,
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
    return cfg


@router.post(
    "/auto-resolution/run-close-job",
    summary="Run auto-close job for resolved tickets",
    response_model=dict,
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

    stats = run_auto_close_job(db)
    db.commit()
    return {
        **stats,
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
