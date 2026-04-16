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
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
import logging
import json

from app.db.session import get_db
from app.core.deps import require_any_manager
from app.models.user import User
from app.core.config import settings
from app.services import accounting_hub_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounting", tags=["accounting"])


def _get_cfg(integration_type: str, db: Session) -> dict:
    """Return config dict for the active integration, raise 404 if missing."""
    cfg = accounting_hub_service.get_accounting_config(db, integration_type)
    if not cfg:
        raise HTTPException(
            404,
            f"Integración '{integration_type}' no configurada o inactiva. "
            "Configúrala en Enterprise → Integraciones.",
        )
    return json.loads(cfg.config or "{}")


# ── Test de conexión ───────────────────────────────────────────────────────────

@router.post("/xero/test", summary="Verificar conexión con Xero")
def test_xero(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import test_xero_connection

    cfg = payload if payload.get("access_token") else _get_cfg("xero", db)
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

    cfg = payload if payload.get("access_token") else _get_cfg("quickbooks", db)
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

    invoice_id = payload.get("invoice_id")
    provider   = payload.get("provider", "xero")

    inv, lines = accounting_hub_service.get_invoice_with_lines(db, invoice_id)
    if not inv:
        raise HTTPException(404, "Factura no encontrada")

    inv_data = {
        "number":       inv.number,
        "client_name":  inv.client_name or "Cliente",
        "client_email": inv.client_email or "",
        "issue_date":   str(inv.issue_date) if inv.issue_date else "",
        "due_date":     str(inv.due_date)   if inv.due_date   else "",
        "subtotal":     inv.subtotal  or 0,
        "tax_rate":     inv.tax_rate  or settings.DEFAULT_TAX_RATE,
        "total":        inv.total     or 0,
        "notes":        inv.notes     or "",
        "lines": [
            {
                "description": l.description,
                "quantity":    l.quantity or 1,
                "unit_price":  l.unit_price or 0,
            }
            for l in lines
        ] if lines else [],
    }

    cfg = _get_cfg(provider, db)

    if provider == "xero":
        result = push_invoice_to_xero(cfg, inv_data)
    elif provider in ("quickbooks", "qbo"):
        result = push_invoice_to_quickbooks(cfg, inv_data)
    else:
        raise HTTPException(400, f"Proveedor '{provider}' no soportado. Usa 'xero' o 'quickbooks'.")

    if not result["ok"]:
        raise HTTPException(400, f"Error al sincronizar: {result.get('error')}")

    sync_id = result.get("xero_invoice_id") or result.get("qb_invoice_id", "")
    accounting_hub_service.mark_invoice_synced(db, inv, provider, sync_id)

    return {
        "ok":             True,
        "provider":       provider,
        "invoice_id":     invoice_id,
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
    from app.services.integrations import push_invoice_to_xero, push_invoice_to_quickbooks

    provider = payload.get("provider", "xero")
    limit    = int(payload.get("limit", 50))

    invoices = accounting_hub_service.get_unsent_invoices(db, limit)
    cfg      = _get_cfg(provider, db)
    push_fn  = push_invoice_to_xero if provider == "xero" else push_invoice_to_quickbooks

    results = []
    for inv in invoices:
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
            accounting_hub_service.append_bulk_sync_note(inv, provider)
            results.append({"invoice_number": inv.number, "status": "synced"})
        else:
            results.append({"invoice_number": inv.number, "status": "error", "error": r.get("error")})

    accounting_hub_service.commit(db)

    synced = sum(1 for r in results if r["status"] == "synced")
    return {
        "ok":      True,
        "provider": provider,
        "total":   len(results),
        "synced":  synced,
        "errors":  sum(1 for r in results if r["status"] == "error"),
        "results": results,
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

    cfg    = _get_cfg("xero", db)
    result = pull_contacts_from_xero(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error Xero: {result.get('error')}")

    if import_to_clarive:
        imported = accounting_hub_service.import_xero_contacts(db, result["contacts"])
        result["imported_to_clarive"] = imported

    return result


# ── Estado de sincronización ───────────────────────────────────────────────────

@router.get("/sync-status", summary="Estado de sincronización contable")
def sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return accounting_hub_service.get_sync_status(db)
