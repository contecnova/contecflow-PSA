"""Service Desk dynamic ticket fields persistence on top of AppSetting.

Uses per-ticket keys so no schema migration is required for MVP persistence.
"""
from __future__ import annotations
import logging

import json
from sqlalchemy.orm import Session

from app.models.settings import AppSetting


def _key(ticket_id: str) -> str:
    return f"sd.ticket.dynamic_fields.{ticket_id}"


def _org_del_ticket(db: Session, ticket_id: str):
    """La organizacion del ticket. Revision multitenant 2026-11: el ajuste se
    guardaba con organizacion vacia (= global) y los campos de un ticket salian
    en los ajustes generales de todas las empresas."""
    from app.models.service_desk import Ticket
    fila = db.query(Ticket.organization_id).filter(Ticket.id == ticket_id).first()
    return fila[0] if fila else None


def save_ticket_dynamic_fields(db: Session, ticket_id: str, fields: dict | None) -> None:
    payload = fields or {}
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
    except Exception:
        logging.getLogger(__name__).debug("save_ticket_dynamic_fields: excepcion ignorada", exc_info=True)
        serialized = "{}"

    key = _key(ticket_id)
    org = _org_del_ticket(db, ticket_id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == org).first()
    if row:
        row.value = serialized
        row.description = "Service Desk dynamic fields for ticket"
    else:
        db.add(AppSetting(
            key=key,
            organization_id=org,
            value=serialized,
            description="Service Desk dynamic fields for ticket",
        ))


def get_ticket_dynamic_fields(db: Session, ticket_id: str) -> dict:
    key = _key(ticket_id)
    row = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id == _org_del_ticket(db, ticket_id)).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        logging.getLogger(__name__).debug("get_ticket_dynamic_fields: excepcion ignorada", exc_info=True)
        return {}
