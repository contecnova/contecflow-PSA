from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services import billing_reports_service

router = APIRouter(tags=["invoices"])

@router.post("/{invoice_id}/payment-link", status_code=status.HTTP_201_CREATED)
def create_payment_link(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Simulación: en un sistema real, aquí se llamaría a Stripe o similar
    invoice = billing_reports_service.get_invoice_by_id(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Simular que Stripe no está configurado
    raise HTTPException(status_code=503, detail="Stripe not configured")
