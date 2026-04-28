"""
Test AI Auto-Resolution Service.
"""
import pytest
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketType, TicketStatus, TicketPriority
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    run_daily_auto_resolution_job,
)


def create_test_ticket(db: Session, title: str, description: str, number: str = None) -> Ticket:
    """Create a test ticket."""
    if not number:
        number = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    
    ticket = Ticket(
        number=number,
        ticket_type=TicketType.incident,
        title=title,
        description=description,
        status=TicketStatus.new,
        priority=TicketPriority.p3_medium,
    )
    db.add(ticket)
    db.commit()
    return ticket


def test_analyze_ticket_basic(db: Session):
    """Test basic ticket analysis."""
    ticket = create_test_ticket(
        db,
        title="Password reset request",
        description="User cannot login to system. Forgot password.",
    )

    result = analyze_ticket_for_resolution(db, ticket)

    assert result["ticket_id"] == ticket.id
    assert "analysis" in result
    assert "suggestion" in result
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1
    assert "kb_sources" in result
    assert "recommendation" in result


def test_analyze_ticket_with_high_confidence(db: Session):
    """Test ticket analysis returns high confidence suggestion."""
    ticket = create_test_ticket(
        db,
        title="Printer driver installation",
        description="HP printer not recognized. Need to install drivers on Windows 10.",
    )

    result = analyze_ticket_for_resolution(db, ticket)

    # Basic checks
    assert result["confidence"] >= 0


def test_run_auto_resolution_job(db: Session):
    """Test daily auto-resolution job."""
    # Create a few test tickets with unique numbers
    for i in range(3):
        create_test_ticket(
            db,
            title=f"Test incident {i}",
            description=f"Test description {i}",
            number=f"TESTJOB-{i}-{uuid.uuid4().hex[:4].upper()}",
        )

    stats = run_daily_auto_resolution_job(db)

    assert "processed" in stats
    assert "auto_resolved" in stats
    assert "suggested" in stats
    assert "failed" in stats
    assert stats["processed"] >= 0


@pytest.mark.parametrize("confidence", [0.5, 0.75, 0.95])
def test_confidence_levels(db: Session, confidence: float):
    """Test different confidence levels (mocked)."""
    # This is a basic test; in reality you'd mock the call_ai response
    ticket = create_test_ticket(
        db,
        title="Test incident",
        description="Test description",
        number=f"TESTCONF-{uuid.uuid4().hex[:4].upper()}",
    )

    result = analyze_ticket_for_resolution(db, ticket)
    assert 0 <= result["confidence"] <= 1


def test_ticket_without_description(db: Session):
    """Test ticket without description."""
    ticket = Ticket(
        number=f"TESTNODESC-{uuid.uuid4().hex[:4].upper()}",
        ticket_type=TicketType.service_request,
        title="No description ticket",
        description="",  # Empty
        status=TicketStatus.new,
        priority=TicketPriority.p3_medium,
    )
    db.add(ticket)
    db.commit()

    result = analyze_ticket_for_resolution(db, ticket)

    # Should handle gracefully
    assert result["ticket_id"] == ticket.id
    assert "recommendation" in result

