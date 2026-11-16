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
    # Sin autoflush en la sesión: `build_internal_ticket` cumple la petición justo
    # después (`alm_integracion.catalogo.registrar` lee estos campos con
    # `get_ticket_dynamic_fields`) y sin flush los veía vacíos.
    db.flush()


def _decodificar(valor) -> dict:
    if not valor:
        return {}
    try:
        data = json.loads(valor)
        return data if isinstance(data, dict) else {}
    except Exception:
        logging.getLogger(__name__).debug("get_ticket_dynamic_fields: excepcion ignorada", exc_info=True)
        return {}


def get_ticket_dynamic_fields(db: Session, ticket_id: str) -> dict:
    key = _key(ticket_id)
    row = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id == _org_del_ticket(db, ticket_id)).first()
    return _decodificar(row.value if row else None)


def get_tickets_dynamic_fields(db: Session, tickets) -> dict:
    """``{ticket_id: campos}`` de varios tickets ya cargados, en UNA consulta.

    Segunda auditoria 2026-11 (N+1): el listado llamaba a
    ``get_ticket_dynamic_fields`` por fila, que son dos consultas (organizacion
    del ticket y ajuste). La organizacion ya viene en el ticket cargado.
    """
    if not tickets:
        return {}
    org_de = {t.id: t.organization_id for t in tickets}
    filas = db.query(AppSetting.key, AppSetting.organization_id, AppSetting.value).filter(
        AppSetting.key.in_([_key(i) for i in org_de])).all()
    prefijo = len(_key(""))
    resultado = {i: {} for i in org_de}
    for clave, org, valor in filas:
        tid = clave[prefijo:]
        if tid in org_de and org == org_de[tid]:
            resultado[tid] = _decodificar(valor)
    return resultado
