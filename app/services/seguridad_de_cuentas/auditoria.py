"""Auditoría de las acciones de seguridad: siempre actor, IP, agente y empresa."""
from __future__ import annotations
import logging

from dataclasses import dataclass
from typing import Optional


@dataclass
class Origen:
    """De dónde viene la acción (lo pone el endpoint a partir de la petición)."""
    ip: Optional[str] = None
    agente: Optional[str] = None

    @classmethod
    def de(cls, request) -> "Origen":
        if request is None:
            return cls()
        from app.core.network import extract_client_ip
        try:
            ip = extract_client_ip(request)
        except Exception:
            logging.getLogger(__name__).debug("de: excepcion ignorada", exc_info=True)
            ip = getattr(getattr(request, "client", None), "host", None)
        return cls(ip=ip, agente=(request.headers.get("user-agent") or "")[:500] or None)


def auditar(db, actor, accion: str, objetivo=None, *, org_id: Optional[str] = None,
            origen: Optional[Origen] = None, antes: Optional[dict] = None, despues: Optional[dict] = None,
            datos: Optional[dict] = None, recurso: str = "users"):
    """Entrada de `audit_log` con la empresa explícita. No confirma."""
    from app.services.audit import audit_log
    origen = origen or Origen()
    empresa = org_id or getattr(objetivo, "organization_id", None) or getattr(actor, "organization_id", None)
    entrada = audit_log(
        db, actor, accion, recurso,
        getattr(objetivo, "id", None) if objetivo is not None and not isinstance(objetivo, str) else objetivo,
        (getattr(objetivo, "email", None) or getattr(objetivo, "full_name", None)) if objetivo is not None and not isinstance(objetivo, str) else None,
        old_values=antes, new_values=despues, metadata=datos,
        ip_address=(origen.ip or None) and str(origen.ip)[:45], user_agent=origen.agente,
    )
    if empresa:
        entrada.organization_id = empresa
    return entrada
