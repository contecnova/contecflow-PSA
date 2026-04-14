"""
accounting_hub.py — Integración contable bidireccional.
Soporta Xero y QuickBooks Online.

Endpoints:
  POST /accounting/xero/test          — Verificar conexión Xero
  POST /accounting/qb/test            — Verificar conexión QuickBooks
  POST /accounting/push-invoice       — Enviar factura a Xero/QB
  POST /accounting/push-invoices-bulk — Enviar facturas pendientes en lote
  GET  /accounting/xero/contacts      — Importar clientes desde Xero
  GET  /accounting/sync-status        — Estado de sincronización
"""
from app.core.config import settings
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)
from sqlalchemy import func
from datetime import datetime, timezone
import json

from app.db.session import get_db
from app.core.deps import require_any_manager
from app.models.user import User

router = APIRouter(prefix="/accounting", tags=["accounting"])


def _get_accounting_config(integration_type: str, db: Session) -> dict:
    """Obtiene la config de la integración contable activa."""
    from app.models.cab import IntegrationConfig
    cfg = db.query(IntegrationConfig).filter(
        IntegrationConfig.integration_type == integration_type,
        IntegrationConfig.is_active == True,
    ).first()
    if not cfg:
        raise HTTPException(404, f"Integración '{integration_type}' no configurada o inactiva. Configúrala en Enterprise → Integraciones.")
    return json.loads(cfg.config or "{}")


# ── Test de conexión ───────────────────────────────────────────────────────────

@router.post("/xero/test", summary="Verificar conexión con Xero")
def test_xero(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import test_xero_connection
    cfg = payload if payload.get("access_token") else _get_accounting_config("xero", db)
    result = test_xero_connection(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error Xero: {result.get('error')}")
    return result


@router.post("/qb/test", summary="Verificar conexión con QuickBooks")
def test_qb(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import test_quickbooks_connection
    cfg = payload if payload.get("access_token") else _get_accounting_config("quickbooks", db)
    result = test_quickbooks_connection(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error QuickBooks: {result.get('error')}")
    return result


# ── Push de facturas ───────────────────────────────────────────────────────────

@router.post("/push-invoice", summary="Enviar una factura a Xero o QuickBooks")
def push_invoice(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Envía una factura de Clarive al sistema contable configurado.
    payload: { invoice_id, provider: "xero"|"quickbooks" }
    """
    from app.services.integrations import push_invoice_to_xero, push_invoice_to_quickbooks
    from app.models.billing_reports import Invoice, InvoiceLine

    invoice_id = payload.get("invoice_id")
    provider   = payload.get("provider", "xero")

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")

    # Construir el payload de factura
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id).all()
    inv_data = {
        "number":      inv.number,
        "client_name": inv.client_name or "Cliente",
        "client_email": inv.client_email or "",
        "issue_date":  str(inv.issue_date) if inv.issue_date else "",
        "due_date":    str(inv.due_date)   if inv.due_date   else "",
        "subtotal":    inv.subtotal  or 0,
        "tax_rate":    inv.tax_rate  or settings.DEFAULT_TAX_RATE,
        "total":       inv.total     or 0,
        "notes":       inv.notes     or "",
        "lines": [
            {
                "description": l.description,
                "quantity":    l.quantity or 1,
                "unit_price":  l.unit_price or 0,
            }
            for l in lines
        ] if lines else [],
    }

    cfg = _get_accounting_config(provider, db)

    if provider == "xero":
        result = push_invoice_to_xero(cfg, inv_data)
    elif provider in ("quickbooks", "qbo"):
        result = push_invoice_to_quickbooks(cfg, inv_data)
    else:
        raise HTTPException(400, f"Proveedor '{provider}' no soportado. Usa 'xero' o 'quickbooks'.")

    if not result["ok"]:
        raise HTTPException(400, f"Error al sincronizar: {result.get('error')}")

    # Marcar la factura como sincronizada
    if True:
        try:
            inv.internal_notes = (inv.internal_notes or "") + f"\n[{provider.upper()} sync {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}] ID: {result.get('xero_invoice_id') or result.get('qb_invoice_id', '')}"
            db.commit()
        except Exception:
            logger.warning("Failed to update internal_notes after accounting sync", exc_info=True)

    return {
        "ok":         True,
        "provider":   provider,
        "invoice_id": invoice_id,
        "invoice_number": inv.number,
        **result,
    }


@router.post("/push-invoices-bulk", summary="Sincronizar facturas pendientes en lote")
def push_invoices_bulk(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Envía todas las facturas en estado 'sent' que no han sido sincronizadas aún.
    """
    from app.models.billing_reports import Invoice
    from app.services.integrations import push_invoice_to_xero, push_invoice_to_quickbooks

    provider = payload.get("provider", "xero")
    limit    = int(payload.get("limit", 50))

    # Facturas enviadas no sincronizadas (sin mención en internal_notes)
    invoices = db.query(Invoice).filter(
        Invoice.status == "sent",
    ).limit(limit).all()

    cfg = _get_accounting_config(provider, db)
    push_fn = push_invoice_to_xero if provider == "xero" else push_invoice_to_quickbooks

    results = []
    for inv in invoices:
        # Saltar si ya fue sincronizada
        if inv.internal_notes and f"[{provider.upper()} sync" in inv.internal_notes:
            results.append({"invoice_number": inv.number, "status": "already_synced"})
            continue
        inv_data = {
            "number":      inv.number,
            "client_name": inv.client_name or "Cliente",
            "issue_date":  str(inv.issue_date) if inv.issue_date else "",
            "due_date":    str(inv.due_date)   if inv.due_date   else "",
            "subtotal":    inv.subtotal or 0,
            "total":       inv.total    or 0,
            "notes":       inv.notes    or "",
            "lines":       [],
        }
        r = push_fn(cfg, inv_data)
        if r.get("ok"):
            inv.internal_notes = (inv.internal_notes or "") + f"\n[{provider.upper()} sync {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"
            results.append({"invoice_number": inv.number, "status": "synced"})
        else:
            results.append({"invoice_number": inv.number, "status": "error", "error": r.get("error")})

    db.commit()
    synced = sum(1 for r in results if r["status"] == "synced")
    return {
        "ok":       True,
        "provider": provider,
        "total":    len(results),
        "synced":   synced,
        "errors":   sum(1 for r in results if r["status"] == "error"),
        "results":  results,
    }


# ── Pull de contactos ──────────────────────────────────────────────────────────

@router.get("/xero/contacts", summary="Importar contactos/clientes desde Xero")
def pull_xero_contacts(
    import_to_clarive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Obtiene los contactos de Xero.
    Si import_to_clarive=true, los crea como Clients en Clarive.
    """
    from app.services.integrations import pull_contacts_from_xero

    cfg    = _get_accounting_config("xero", db)
    result = pull_contacts_from_xero(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error Xero: {result.get('error')}")

    if import_to_clarive:
        from app.models.clients import Client
        import uuid as _uuid
        imported = 0
        for c in result["contacts"]:
            existing = db.query(Client).filter(
                Client.name == c["name"]
            ).first()
            if not existing:
                client = Client(
                    id=str(_uuid.uuid4()),
                    name=c["name"],
                    contact_email=c.get("email"),
                    contact_phone=c.get("phone"),
                    tax_id=c.get("vat"),
                    notes=f"Importado desde Xero (ID: {c.get('xero_id')})",
                )
                db.add(client)
                imported += 1
        db.commit()
        result["imported_to_clarive"] = imported

    return result


# ── Estado de sincronización ───────────────────────────────────────────────────

@router.get("/sync-status", summary="Estado de sincronización contable")
def sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import Invoice
    from app.models.cab import IntegrationConfig

    total_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.status == "sent"
    ).scalar() or 0

    synced_xero = db.query(func.count(Invoice.id)).filter(
        Invoice.status == "sent",
        Invoice.internal_notes.like("%[XERO sync%"),
    ).scalar() or 0

    synced_qb = db.query(func.count(Invoice.id)).filter(
        Invoice.status == "sent",
        Invoice.internal_notes.like("%[QUICKBOOKS sync%"),
    ).scalar() or 0

    # Integrations activas
    active_integrations = db.query(IntegrationConfig).filter(
        IntegrationConfig.is_active == True,
        IntegrationConfig.integration_type.in_(["xero", "quickbooks"]),
    ).all()

    return {
        "invoices": {
            "total_sent":    total_invoices,
            "synced_xero":   synced_xero,
            "synced_qb":     synced_qb,
            "pending_sync":  total_invoices - max(synced_xero, synced_qb),
        },
        "active_integrations": [
            {"type": c.integration_type, "name": c.name, "last_sync": str(c.last_sync_at)[:16] if c.last_sync_at else None}
            for c in active_integrations
        ],
    }
