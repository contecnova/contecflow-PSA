"""Plantillas de proyecto: alta, listado e instanciacion.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from app.models.user import User


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATES — rev. 173: delegan en `app/services/plantillas_de_proyecto.py`
# ═══════════════════════════════════════════════════════════════════════════════
#
# Aquí había una copia de «crear», «listar» e «instanciar» distinta de la de
# `advanced_config_service/plantillas.py` (instanciar no copiaba riesgos ni
# entregables). Las firmas se conservan para el endpoint de siempre.

def create_template(payload, current_user: User, db: Session) -> dict:
    from app.services.plantillas_de_proyecto import crear
    datos = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    return {"ok": True, "id": crear(db, current_user, datos).id}


def list_templates_all(db: Session, current_user: Optional[User] = None) -> list:
    from app.services.plantillas_de_proyecto import listar
    return listar(db, current_user)


def instantiate_template(template_id: str, payload: dict, current_user: User, db: Session) -> dict:
    """Crea un proyecto desde una plantilla: fases, tareas, dependencias, riesgos,
    entregables y documentos, con las fechas del planificador."""
    from app.services.plantillas_de_proyecto import instanciar
    return instanciar(db, current_user, template_id, payload or {})
