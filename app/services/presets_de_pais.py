"""Escrituras de los presets de coste por pais que pide la API.

Auditoria 2026-11 (#21): la edicion de un preset se hacia —y se confirmaba— en
el endpoint. Vive aqui y no en `cost_service` para no mezclarla con el calculo
de costes; la busqueda acotada (`preset_propio_o_global`) sigue siendo la de alli.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def actualizar_preset_de_pais(db: Session, actor, preset_id: str, cambios: dict):
    """Aplica `cambios` al preset (propio o global; 404 si es de otro) y confirma."""
    from app.services.cost_service import preset_propio_o_global

    row = preset_propio_o_global(db, actor, preset_id)
    for k, v in cambios.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row
