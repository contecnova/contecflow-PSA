"""Estado de los conectores: qué ha pasado en las últimas horas (revisión 2026-11).

Sale de `conector_llamadas`, que se escribe en cada llamada real; no es una
sonda aparte. Las latencias son percentiles de las llamadas que acabaron (con
éxito o no), contadas por operación.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.services.conectores.anfitrion import PRODUCTOS, _ajuste, configurado


def _percentil(valores: list[int], p: float) -> Optional[int]:
    if not valores:
        return None
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(round(p * (len(orden) - 1))))]


def estado(db: Session, org_id: Optional[str]) -> dict:
    from app.models.conectores import ConectorLlamada
    horas = int(_ajuste(db, "CONECTOR_STATUS_WINDOW_HOURS", org_id, "int"))
    desde = datetime.now(timezone.utc) - timedelta(hours=horas)
    salida = {"ventana_horas": horas, "productos": []}
    for clave, producto in PRODUCTOS.items():
        filas = (db.query(ConectorLlamada)
                 .filter(ConectorLlamada.producto == clave, ConectorLlamada.created_at >= desde)
                 .order_by(ConectorLlamada.created_at.desc()).all())
        ops: dict[str, dict] = {}
        for f in filas:
            o = ops.setdefault(f.operacion, {"operacion": f.operacion, "llamadas": 0, "fallos": 0, "_ms": []})
            o["llamadas"] += 1
            o["fallos"] += 0 if f.ok else 1
            o["_ms"].append(f.ms)
        operaciones = []
        for o in sorted(ops.values(), key=lambda x: -x["llamadas"]):
            ms = o.pop("_ms")
            operaciones.append({**o, "p50_ms": _percentil(ms, 0.5), "p95_ms": _percentil(ms, 0.95)})
        ultimo_error = next((f for f in filas if not f.ok), None)
        salida["productos"].append({
            "producto": clave,
            "configurado": configurado(db, producto, org_id),
            "llamadas": len(filas),
            "fallos": sum(1 for f in filas if not f.ok),
            "p50_ms": _percentil([f.ms for f in filas], 0.5),
            "p95_ms": _percentil([f.ms for f in filas], 0.95),
            "ultima_llamada": filas[0].created_at.isoformat() if filas else None,
            "ultimo_error": ({"cuando": ultimo_error.created_at.isoformat(), "operacion": ultimo_error.operacion,
                              "estado_http": ultimo_error.estado_http, "error": ultimo_error.error}
                             if ultimo_error else None),
            "operaciones": operaciones,
        })
    return salida


def purgar(db: Session) -> int:
    """Borra el registro más antiguo que `CONECTOR_LOG_RETENTION_DAYS` (por empresa). Devuelve cuántas filas."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.conectores import ConectorLlamada
    total = 0
    with sin_filtro_de_tenant(db):
        orgs = [o for (o,) in db.query(ConectorLlamada.organization_id).distinct().all()]
        for org in orgs:
            dias = int(_ajuste(db, "CONECTOR_LOG_RETENTION_DAYS", org, "int"))
            limite = datetime.now(timezone.utc) - timedelta(days=dias)
            q = db.query(ConectorLlamada).filter(ConectorLlamada.created_at < limite)
            q = q.filter(ConectorLlamada.organization_id.is_(None) if org is None
                         else ConectorLlamada.organization_id == org)
            total += q.delete(synchronize_session=False)
    db.commit()
    return total
