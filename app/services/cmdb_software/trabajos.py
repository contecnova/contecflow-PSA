"""Trabajo diario por empresa (`cmdb_software_diario`, 04:20; `app/worker.py`).

1. Si `auto_sync`: sincroniza las fuentes activas (las caídas se registran y
   no paran las demás).
2. Reevalúa: hallazgos nuevos, resueltos (verificados) y reabiertos; prioridad
   y SLA.
3. Caduca las excepciones vencidas (el hallazgo vuelve a abierto).
4. Ticket automático para los hallazgos nuevos desde la severidad configurada.

Se ejecuta con `en_cada_organizacion` (`trabajos_de_fondo`), que pone la
empresa en la sesión y confirma por empresa.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def diario(db: Session, org) -> dict:
    from app.services.cmdb_software import ajustes, correlacion, fuentes, gestion
    from app.models.cmdb_software import SoftwareProduct
    if not db.query(SoftwareProduct.id).filter(SoftwareProduct.organization_id == org).first():
        return {"skipped": "sin catálogo"}
    conf = ajustes.leer(db, org)
    resumen: dict = {}
    if conf.get("auto_sync"):
        resumen["sync"] = fuentes.sincronizar(db, org, None, None, disparo="scheduler", estricto=False)
    res = correlacion.reevaluar_y_registrar(db, org, None, disparo="scheduler")
    resumen.update({k: v for k, v in res.items() if k != "new_ids"})
    resumen["exceptions_expired"] = gestion.caducar_excepciones(db, org)
    resumen["auto_tickets"] = gestion.tickets_automaticos(db, org, res.get("new_ids") or [])
    db.commit()
    return resumen
