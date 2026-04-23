from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.billing_reports import InvoiceOut, InvoiceSummaryOut
from app.services import billing_reports_service

router = APIRouter(tags=["Invoices"])


@router.get("", response_model=List[InvoiceOut])
def list_invoices(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q, _ = billing_reports_service.query_invoices(db, project_id=project_id, status=status)
    invoices = q.offset(skip).limit(limit).all()
    return [billing_reports_service.invoice_out(inv) for inv in invoices]


@router.get("/summary", response_model=InvoiceSummaryOut)
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return billing_reports_service.get_invoice_summary(db)


@router.post("/{invoice_id}/payment-link", status_code=status.HTTP_201_CREATED)
def create_payment_link(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = billing_reports_service.get_invoice_by_id(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    raise HTTPException(status_code=503, detail="Stripe not configured")
