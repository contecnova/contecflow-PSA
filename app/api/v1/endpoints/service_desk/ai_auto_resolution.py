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
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.service_desk import Ticket, TicketStatus
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    run_daily_auto_resolution_job,
    validate_auto_resolution,
    record_resolution_feedback,
    get_auto_resolution_stats,
    run_auto_close_job,
)

router = APIRouter(tags=["Service Desk - AI Auto-Resolution"])


class FeedbackBody(BaseModel):
    success: bool


@router.post(
    "/tickets/{ticket_id}/ai-analyze",
    summary="Analyze ticket for AI auto-resolution suggestions",
    response_model=dict,
    responses={
        404: {"description": "Ticket not found"},
        403: {"description": "Not authorized to view this ticket"},
    },
)
async def analyze_ticket_for_ai_resolution(
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
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

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
async def apply_ai_auto_resolution(
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

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

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
async def run_auto_resolution_job(
    limit: int = Query(100, ge=1, le=500, description="Max tickets to process"),
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

    # Run job
    stats = run_daily_auto_resolution_job(db)
    
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
async def validate_ticket_auto_resolution(
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

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

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
async def submit_auto_resolution_feedback(
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

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

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
async def get_auto_resolution_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return aggregate statistics for the auto-resolution feedback loop.

    Returns: {total_auto_resolved, total_feedback, success_rate, buckets}
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    return get_auto_resolution_stats(db)


@router.post(
    "/auto-resolution/run-close-job",
    summary="Run auto-close job for resolved tickets",
    response_model=dict,
    responses={
        403: {"description": "Admin only"},
    },
)
async def run_auto_close_job_endpoint(
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
