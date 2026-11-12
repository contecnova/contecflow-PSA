from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response, status, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_any_manager
from app.models.user import User, UserRole
from app.schemas.billing_reports import InvoiceCreate, InvoiceOut, InvoiceSummaryOut
from app.services import billing_reports_service
from app.services.psa_flows import build_invoice_preview_from_timesheets_flow
from app.core.responses import APIListResponse, APIResponse

router = APIRouter(tags=["Invoices"])


@router.post("/from-timesheets", response_model=APIResponse[Dict[str, Any]], summary="Generar preview de factura desde timesheets aprobados")
def invoice_from_timesheets(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: facturacion
):
    return APIResponse.ok(data=build_invoice_preview_from_timesheets_flow(
        db=db,
        project_id=payload.get("project_id"),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        tax_rate=payload.get("tax_rate"),
    ))


@router.post("", response_model=APIResponse[InvoiceOut], status_code=201, summary="Crear factura")
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: facturacion
):
    return APIResponse.ok(data=billing_reports_service.create_invoice(payload, current_user, db))


@router.get("", response_model=APIListResponse[InvoiceOut])
def list_invoices(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # revisión 2026-11: un empleado listaba todas las facturas
):
    q, total = billing_reports_service.query_invoices(db, project_id=project_id, status=status)
    invoices = q.offset(skip).limit(limit).all()
    items = [billing_reports_service.invoice_out(inv) for inv in invoices]
    return APIListResponse.ok(items=items, total=total)


@router.get("/summary", response_model=APIResponse[InvoiceSummaryOut])
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # revisión 2026-11: un empleado veía los totales de la empresa
):
    return APIResponse.ok(data=billing_reports_service.get_invoice_summary(db))




# ── Ficha, edición y borrado (revisión 2026-11) ─────────────────────────────
class LineaDeFacturaIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(1, ge=0)
    unit: str = Field("h", max_length=20)
    unit_price: float = Field(..., ge=0)
    discount_pct: float = Field(0, ge=0, le=100)
    source_type: Optional[str] = Field(None, max_length=20)
    source_ids: Optional[Any] = None


class EdicionDeFacturaIn(BaseModel):
    client_name: Optional[str] = Field(None, max_length=255)
    client_address: Optional[str] = None
    client_vat: Optional[str] = Field(None, max_length=50)
    client_email: Optional[str] = Field(None, max_length=255)
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    currency: Optional[str] = Field(None, max_length=3)
    notes: Optional[str] = None
    po_reference: Optional[str] = Field(None, max_length=100)
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    lines: Optional[List[LineaDeFacturaIn]] = None


@router.get("/{invoice_id}", response_model=APIResponse[InvoiceOut], summary="Ficha de una factura con sus líneas")
def get_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                _rol: User = Depends(require_any_manager)):
    return APIResponse.ok(data=billing_reports_service.obtener_factura(db, invoice_id))


@router.patch("/{invoice_id}", response_model=APIResponse[InvoiceOut], summary="Editar un borrador (cabecera y líneas)")
def edit_invoice(invoice_id: str, payload: EdicionDeFacturaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user), _rol: User = Depends(require_any_manager)):
    datos = payload.model_dump(exclude_unset=True)
    if "lines" in datos:
        datos["lines"] = [dict(l) for l in datos["lines"] or []]
    return APIResponse.ok(data=billing_reports_service.editar_factura(db, current_user, invoice_id, datos))


@router.delete("/{invoice_id}", summary="Borrar un borrador")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                   _rol: User = Depends(require_any_manager)):
    billing_reports_service.borrar_factura(db, current_user, invoice_id)
    return APIResponse.ok(data={"deleted": invoice_id})

@router.post("/stripe/webhook", summary="Webhook de Stripe (cobro de facturas)")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # Sin usuario: lo autentica la firma `Stripe-Signature` (payments_service).
    from app.core.async_db import run_db
    from app.services import payments_service
    cuerpo = await request.body()
    return await run_db(payments_service.handle_stripe_webhook, cuerpo, request.headers.get("stripe-signature"), db)


@router.post("/{invoice_id}/payment-link", status_code=status.HTTP_201_CREATED)
def create_payment_link(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_any_manager),  # auditoria 2026-09: dominio: facturacion
):
    return APIResponse.ok(data=billing_reports_service.crear_enlace_de_pago(db, invoice_id))


# ── La descarga de factura que usa la interfaz ───────────────────────────────
#
# Auditoria 2026-08 (hallazgo 32, y lo peor que salio de el). Habia DOS
# generadores de PDF de factura, independientes:
#
#   · `app/services/invoice_pdf.py`, con trazado completo, paleta de marca,
#     paginacion y los datos fiscales, detras de
#     `GET /billing-reports/invoices/{id}/pdf` — ruta que **no llamaba nadie**:
#     ni el frontend, ni otro modulo del backend;
#   · y este, dibujado a mano con `rl_canvas` en unas setenta lineas, que es
#     **el que llama la interfaz** (`_core.ts`: `api.get('/invoices/${id}/pdf')`).
#
# El que descargaba el usuario NO llevaba el NIF del cliente, ni su direccion,
# ni el nombre del emisor, ni la referencia de pedido, ni el periodo facturado,
# ni las notas — y truncaba la descripcion de cada linea a 50 caracteres con un
# `[:50]` silencioso. Una factura sin identificacion fiscal de las dos partes no
# es una factura valida, y ademas todo el trabajo de trazado del otro generador
# —incluido el arreglo del `NOSPLIT` que impedia emitir facturas de 29 lineas o
# mas— vivia en una ruta que nadie pedia.
#
# Ahora esta ruta delega en el generador bueno. Se conserva lo suyo: la
# comprobacion de rol, el 404 y la descarga como adjunto con el nombre saneado.
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

    from app.services import invoice_pdf as _invoice_pdf
    from app.services._pdf_marca import PALETA_DE_FACTURA, marca_de_organizacion

    # La marca del tenant, no la de la plataforma: decision de producto del
    # hallazgo 32. Degrada a la paleta de producto si la organizacion no tiene
    # marca configurada.
    marca = marca_de_organizacion(
        db, getattr(current_user, "organization_id", None),
        base=PALETA_DE_FACTURA,
        nombre_por_defecto=settings.PROJECT_NAME,
    )

    pdf_bytes = _invoice_pdf.pdf_de_factura(
        db, inv, org_id=current_user.organization_id,
        company_name=marca.nombre, paleta=marca.paleta,
    )

    safe_number = (inv.number or invoice_id).replace("/", "-").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=factura_{safe_number}.pdf"},
    )
