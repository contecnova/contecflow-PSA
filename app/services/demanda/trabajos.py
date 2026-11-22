"""Trabajo diario del flujo de demanda (por organización): avisos de plazo y vencimientos.

Lo lanza `app.worker.demanda_plazos` cada hora con `en_cada_organizacion`.
"""
from __future__ import annotations


def plazos(db, org_id) -> dict:
    from app.services.demanda.motor import revisar_plazos
    return revisar_plazos(db, org_id)
