"""Lo que el índice de riesgo añade al trabajo diario (`cmdb_software_diario`).

Tras reevaluar: caduca controles compensatorios (y reevalúa si hubo alguno),
recalcula el índice de todos los ámbitos y guarda la foto del día, manda los
avisos que tocan y borra el histórico más antiguo que `history_days`
(respetando el bloqueo legal: `app/db/bloqueo_legal.py`, tipo `sw_risk_snapshots`).
"""
from __future__ import annotations

from datetime import timedelta
from app.core import timeutil

from sqlalchemy.orm import Session


def diario(db: Session, org) -> dict:
    from app.services.cmdb_software.correlacion import reevaluar
    from app.services.cmdb_software.riesgo import ajustes as aj
    from app.services.cmdb_software.riesgo import alertas, calculo, controles
    resumen: dict = {"controls_expired": controles.caducar(db, org)}
    if resumen["controls_expired"]:
        reevaluar(db, org, None)
    resumen["risk"] = calculo.recalcular(db, org, None, disparo="scheduler")
    resumen["alerts"] = alertas.revisar(db, org)
    resumen["history_pruned"] = podar_historico(db, org, int(aj.leer(db, org)["history_days"]))
    return resumen


def podar_historico(db: Session, org, dias: int) -> int:
    from app.models.cmdb_riesgo import RiskSnapshot
    limite = timeutil.today() - timedelta(days=max(30, dias))
    q = db.query(RiskSnapshot).filter(RiskSnapshot.day < limite)
    if org:
        q = q.filter(RiskSnapshot.organization_id == org)
    # El borrado masivo no pasa por el `before_flush` del bloqueo legal: se excluye aquí lo bloqueado.
    from app.db.bloqueo_legal import _condicion_bloqueada, bloqueos_activos
    bloqueos = bloqueos_activos(db, org)
    if bloqueos:
        q = q.filter(~_condicion_bloqueada("sw_risk_snapshots", RiskSnapshot, bloqueos))
    n = q.delete(synchronize_session=False)
    db.flush()
    return n
