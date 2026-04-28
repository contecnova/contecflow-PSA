"""
Service Desk AI Auto-Resolution endpoints.

Routes:
  POST /sd/tickets/{ticket_id}/ai-analyze
  POST /sd/tickets/{ticket_id}/ai-auto-resolve
  POST /sd/auto-resolution/run-job
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.service_desk import Ticket, TicketStatus
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    run_daily_auto_resolution_job,
)

router = APIRouter(prefix="/sd", tags=["Service Desk - AI Auto-Resolution"])


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
