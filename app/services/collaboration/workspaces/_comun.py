"""Ayudantes compartidos: usuarios por id y su nombre visible.

Parte de `app.services.collaboration.workspaces` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User


def _usuarios_por_id(db: Session, ids, organization_id: Optional[str] = None) -> dict:
    """Los usuarios de esos ids, en una sola consulta.

    Devuelve diccionario vacio sin consultar si no hay ids: un `in_([])` es una
    consulta que siempre devuelve nada.

    `organization_id` acota explicitamente. Los ids salen de filas que ya estan
    acotadas, asi que en una peticion real el ambito llega por ahi; el filtro
    explicito es defensa en profundidad y no depende del filtro global de tenant,
    que es una capa de respaldo y estuvo roto (ver `app/db/session.py`).
    """
    ids = [i for i in ids if i]
    if not ids:
        return {}
    q = db.query(User).filter(User.id.in_(ids))
    if organization_id:
        q = q.filter(User.organization_id == organization_id)
    return {u.id: u for u in q.all()}


def _nombre_de(u) -> Optional[str]:
    """El nombre que se muestra de un usuario, con el mismo orden de respaldo
    que usaba el endpoint: nombre completo, luego usuario."""
    if u is None:
        return None
    return u.full_name or u.username
