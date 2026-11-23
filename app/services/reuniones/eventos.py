"""Línea de tiempo de la reunión y auditoría (una llamada deja las dos)."""
from __future__ import annotations
import logging

import json
from typing import Optional

from sqlalchemy.orm import Session


def evento(db: Session, reunion, tipo: str, actor=None, datos: Optional[dict] = None) -> None:
    """Apunta un evento en `ai_meeting_events`. No confirma."""
    from app.models.reuniones import AIMeetingEvent
    db.add(AIMeetingEvent(meeting_id=reunion.id, organization_id=reunion.organization_id, tipo=tipo,
                          actor_id=getattr(actor, "id", None),
                          datos=json.dumps(datos, ensure_ascii=False, default=str) if datos else None))


def auditar(db: Session, usuario, accion: str, reunion, metadata: Optional[dict] = None,
            old_values: Optional[dict] = None, new_values: Optional[dict] = None) -> None:
    """Entrada en `audit_logs` (recurso `ai_meeting`). Sin sesión de usuario
    (webhooks, trabajos) se sella con la empresa de la reunión. No confirma."""
    from app.services.audit import audit_log
    entrada = audit_log(db, usuario, accion, "ai_meeting", reunion.id if reunion is not None else None,
                        (reunion.title or "")[:200] if reunion is not None else None,
                        old_values=old_values, new_values=new_values, metadata=metadata)
    if reunion is not None and getattr(entrada, "organization_id", None) is None:
        try:
            entrada.organization_id = reunion.organization_id
        except Exception:  # noqa: S110 - modelo sin la columna en algún doble de prueba
            logging.getLogger(__name__).debug("auditar: excepcion ignorada", exc_info=True)


def cambiar_estado(db: Session, reunion, estado: str, actor=None, *, error_code: Optional[str] = None) -> None:
    if reunion.status == estado and not error_code:
        return
    anterior = reunion.status
    reunion.status = estado
    reunion.error_code = error_code if estado == "error" else None
    evento(db, reunion, "status_changed", actor, {"from": anterior, "to": estado, "error_code": error_code})
