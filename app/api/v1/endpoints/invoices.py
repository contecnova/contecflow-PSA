from typing import Any, Dict, List, Optional
import io

from fastapi import APIRouter, Body, HTTPException, Query, Response, status, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User, UserRole
from app.models.billing_reports import Invoice, InvoiceLine
from app.schemas.billing_reports import InvoiceCreate, InvoiceOut, InvoiceSummaryOut
from app.services import billing_reports_service
from app.services.psa_flows import build_invoice_preview_from_timesheets_flow
from app.core.responses import APIListResponse

router = APIRouter(tags=["Invoices"])


@router.post("/from-timesheets", response_model=Dict[str, Any], summary="Generar preview de factura desde timesheets aprobados")
def invoice_from_timesheets(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return build_invoice_preview_from_timesheets_flow(
        db=db,
        project_id=payload.get("project_id"),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        tax_rate=payload.get("tax_rate"),
    )


@router.post("", response_model=InvoiceOut, status_code=201, summary="Crear factura")
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = billing_reports_service.next_invoice_number(db)
    subtotal = sum(line.get("amount", 0) for line in payload.lines)
    tax_amount = round(subtotal * payload.tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)
    inv = Invoice(
        number=number,
        project_id=payload.project_id,
        contract_id=payload.contract_id,
        client_name=payload.client_name,
        client_address=payload.client_address,
        client_vat=payload.client_vat,
        client_email=payload.client_email,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        tax_rate=payload.tax_rate,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        currency=payload.currency,
        notes=payload.notes,
        po_reference=payload.po_reference,
        period_from=payload.period_from,
        period_to=payload.period_to,
        created_by=current_user.id,
    )
    db.add(inv)
    db.flush()
    for i, line in enumerate(payload.lines):
        db.add(InvoiceLine(
            invoice_id=inv.id,
            order=i,
            description=line.get("description", ""),
            quantity=line.get("quantity", 1),
            unit=line.get("unit", "u"),
            unit_price=line.get("unit_price", 0),
            discount_pct=line.get("discount_pct", 0),
            amount=line.get("amount", 0),
        ))
    db.commit()
    db.refresh(inv)
    return billing_reports_service.invoice_out(inv)


@router.get("", response_model=APIListResponse[InvoiceOut])
def list_invoices(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q, total = billing_reports_service.query_invoices(db, project_id=project_id, status=status)
    invoices = q.offset(skip).limit(limit).all()
    items = [billing_reports_service.invoice_out(inv) for inv in invoices]
    return APIListResponse.ok(items=items, total=total)


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


@router.get("/{invoice_id}/pdf", summary="Descargar factura en PDF")
def download_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role in (UserRole.employee, UserRole.subcontractor):
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar facturas")
    inv = billing_reports_service.get_invoice_by_id(db, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, height - 2 * cm, f"FACTURA {inv.number or ''}")

    c.setFont("Helvetica", 10)
    y = height - 3.5 * cm
    c.drawString(2 * cm, y, f"Cliente: {inv.client_name or ''}")
    y -= 0.6 * cm
    c.drawString(2 * cm, y, f"Fecha: {inv.issue_date}")
    if inv.due_date:
        y -= 0.6 * cm
        c.drawString(2 * cm, y, f"Vencimiento: {inv.due_date}")

    y -= 1.2 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Descripción")
    c.drawString(11 * cm, y, "Cantidad")
    c.drawString(14 * cm, y, "Precio")
    c.drawString(17 * cm, y, "Importe")
    y -= 0.1 * cm
    c.line(2 * cm, y, 19 * cm, y)
    y -= 0.5 * cm
    c.setFont("Helvetica", 9)
    for line in inv.lines:
        c.drawString(2 * cm, y, str(line.description or "")[:50])
        c.drawRightString(13 * cm, y, str(line.quantity))
        c.drawRightString(16 * cm, y, f"{line.unit_price:.2f}")
        c.drawRightString(19 * cm, y, f"{line.amount:.2f}")
        y -= 0.55 * cm
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm

    y -= 0.3 * cm
    c.line(2 * cm, y, 19 * cm, y)
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    c.drawRightString(19 * cm, y, f"Base imponible: {inv.subtotal:.2f} {inv.currency}")
    y -= 0.55 * cm
    c.drawRightString(19 * cm, y, f"IVA ({inv.tax_rate:.0f}%): {inv.tax_amount:.2f} {inv.currency}")
    y -= 0.55 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(19 * cm, y, f"TOTAL: {inv.total:.2f} {inv.currency}")

    c.save()
    pdf_bytes = buf.getvalue()
    safe_number = (inv.number or invoice_id).replace("/", "-").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=factura_{safe_number}.pdf"},
    )
