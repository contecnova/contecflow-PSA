"""Service Desk dynamic ticket fields persistence on top of AppSetting.

Uses per-ticket keys so no schema migration is required for MVP persistence.
"""
from __future__ import annotations

import json
from sqlalchemy.orm import Session

from app.models.settings import AppSetting


def _key(ticket_id: str) -> str:
    return f"sd.ticket.dynamic_fields.{ticket_id}"


def save_ticket_dynamic_fields(db: Session, ticket_id: str, fields: dict | None) -> None:
    payload = fields or {}
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
    except Exception:
        serialized = "{}"

    key = _key(ticket_id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == None).first()  # noqa: E711
    if row:
        row.value = serialized
        row.description = "Service Desk dynamic fields for ticket"
    else:
        db.add(AppSetting(
            key=key,
            organization_id=None,
            value=serialized,
            description="Service Desk dynamic fields for ticket",
        ))


def get_ticket_dynamic_fields(db: Session, ticket_id: str) -> dict:
    key = _key(ticket_id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == None).first()  # noqa: E711
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
