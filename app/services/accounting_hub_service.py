"""
accounting_hub_service.py — Service layer for accounting hub DB operations.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.billing_reports import Invoice, InvoiceLine
from app.models.cab import IntegrationConfig
from app.models.clients import Client

logger = logging.getLogger(__name__)


def get_accounting_config(db: Session, integration_type: str):
    """Return the active IntegrationConfig row for the given type, or None."""

    return db.query(IntegrationConfig).filter(
        IntegrationConfig.integration_type == integration_type,
        IntegrationConfig.is_active == True,
    ).first()


def get_invoice_with_lines(db: Session, invoice_id: str):
    """Return (Invoice, [InvoiceLine]) tuple; invoice is None if not found."""

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if inv is None:
        return None, []
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id).all()
    return inv, lines


def mark_invoice_synced(db: Session, inv, provider: str, sync_id: str = "") -> None:
    """Append a sync note to invoice.internal_notes and commit."""
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        inv.internal_notes = (
            (inv.internal_notes or "")
            + f"\n[{provider.upper()} sync {stamp}] ID: {sync_id}"
        )
        db.commit()
    except Exception:
        logger.warning("Failed to update internal_notes after accounting sync", exc_info=True)


def get_unsent_invoices(db: Session, limit: int = 50):
    """Return sent invoices that may not yet have been pushed to accounting."""

    return db.query(Invoice).filter(Invoice.status == "sent").limit(limit).all()


def append_bulk_sync_note(inv, provider: str) -> None:
    """Append a sync stamp to invoice.internal_notes (no commit — caller batches)."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    inv.internal_notes = (inv.internal_notes or "") + f"\n[{provider.upper()} sync {stamp}]"


def commit(db: Session) -> None:
    db.commit()


def import_xero_contacts(db: Session, contacts: list) -> int:
    """Crea clientes desde contactos Xero; omite duplicados por nombre. Devuelve el número importado."""

    imported = 0
    for c in contacts:
        existing = db.query(Client).filter(Client.name == c["name"]).first()
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
    return imported


def get_sync_status(db: Session) -> dict:
    """Return aggregated sync-status metrics and active integration configs."""

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

    active_integrations = db.query(IntegrationConfig).filter(
        IntegrationConfig.is_active == True,
        IntegrationConfig.integration_type.in_(["xero", "quickbooks"]),
    ).all()

    return {
        "invoices": {
            "total_sent": total_invoices,
            "synced_xero": synced_xero,
            "synced_qb": synced_qb,
            "pending_sync": total_invoices - max(synced_xero, synced_qb),
        },
        "active_integrations": [
            {
                "type": c.integration_type,
                "name": c.name,
                "last_sync": str(c.last_sync_at)[:16] if c.last_sync_at else None,
            }
            for c in active_integrations
        ],
    }
