"""Reloj UTC, logger y organizacion de la peticion, compartidos.

Parte de `app.services.security_observability` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from app.core.errores import ErrorDeDominio


logger = logging.getLogger("contecflow.soc")

_UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(_UTC)


# ── Tenant helpers ─────────────────────────────────────────────────────────

def get_org_id(user) -> str:
    if not user.organization_id:
        raise ErrorDeDominio(status_code=400, detail="User has no organization")
    return str(user.organization_id)
