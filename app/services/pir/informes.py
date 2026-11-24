"""PIR: informes (tasa de éxito, cumplimiento) y la vista del CAB.

Docs: docs/PIR.md §«Informes» y §«CAB».

- `tasa_de_exito`: de las PIR aprobadas o cerradas del periodo (por fecha real),
  cuántas fueron éxito, éxito parcial o fallo, por ámbito y por tipo (tipo de
  cambio o de proyecto). Tasa = éxitos / revisadas; la parcial se informa aparte.
- `cumplimiento`: obligatorias del periodo (por fecha prevista): hechas a
  tiempo, hechas tarde, pendientes en plazo y vencidas, con la lista de vencidas.
- `vista_del_cab`: los cambios cerrados del periodo y cuántos están «cerrados
  del todo» (sin PIR obligatoria pendiente), más las PIR de cambios pendientes.
  Un cambio con PIR obligatoria sin aprobar NO cuenta como cerrado del todo.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.pir import PirRevision
from app.services.pir import servicio


def _periodo(desde: Optional[date], hasta: Optional[date]) -> tuple[date, date]:
    hasta = hasta or timeutil.today()
    return desde or (hasta - timedelta(days=90)), hasta


def _tasa(a: int, b: int) -> Optional[float]:
    return round(100.0 * a / b, 1) if b else None


def tasa_de_exito(db: Session, usuario, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    desde, hasta = _periodo(desde, hasta)
    filas = servicio._de_la_empresa(db, usuario).filter(
        PirRevision.estado.in_(servicio.HECHOS), PirRevision.fecha_real >= desde, PirRevision.fecha_real <= hasta).all()
    grupos: dict = {}
    for p in filas:
        for clave in ((p.origen_tipo, None), (p.origen_tipo, p.tipo or "—")):
            g = grupos.setdefault(clave, {"ambito": clave[0], "tipo": clave[1], "revisadas": 0, "exito": 0,
                                          "exito_parcial": 0, "fallo": 0, "marcha_atras": 0})
            g["revisadas"] += 1
            if p.resultado in ("exito", "exito_parcial", "fallo"):
                g[p.resultado] += 1
            if p.hubo_marcha_atras:
                g["marcha_atras"] += 1
    salida = []
    for g in grupos.values():
        g["tasa_exito"] = _tasa(g["exito"], g["revisadas"])
        g["tasa_fallo"] = _tasa(g["fallo"], g["revisadas"])
        salida.append(g)
    salida.sort(key=lambda g: (g["ambito"], g["tipo"] is not None, g["tipo"] or ""))
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "grupos": salida}


def cumplimiento(db: Session, usuario, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    desde, hasta = _periodo(desde, hasta)
    hoy = timeutil.today()
    filas = servicio._de_la_empresa(db, usuario).filter(
        PirRevision.obligatorio.is_(True), PirRevision.estado != "descartado",
        PirRevision.fecha_prevista >= desde, PirRevision.fecha_prevista <= hasta).all()
    a_tiempo = tarde = en_plazo = 0
    vencidas = []
    for p in filas:
        hecha = p.estado in servicio.HECHOS or p.estado == "enviado"
        if hecha:
            if p.fecha_real and p.fecha_prevista and p.fecha_real > p.fecha_prevista:
                tarde += 1
            else:
                a_tiempo += 1
        elif servicio.vencida(p, hoy):
            vencidas.append(p)
        else:
            en_plazo += 1
    # Las vencidas de antes del periodo también se arrastran: siguen sin hacer.
    antiguas = servicio._de_la_empresa(db, usuario).filter(
        PirRevision.obligatorio.is_(True), PirRevision.estado.in_(servicio.ABIERTOS),
        PirRevision.fecha_prevista < desde).all()
    vencidas += antiguas
    total = len(filas)
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "obligatorias": total, "a_tiempo": a_tiempo,
            "tarde": tarde, "en_plazo": en_plazo, "vencidas": len(vencidas),
            "tasa_cumplimiento": _tasa(a_tiempo, total),
            "lista_vencidas": [servicio.serializar(db, p) for p in sorted(vencidas, key=lambda x: x.fecha_prevista)]}


def vista_del_cab(db: Session, usuario, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    from datetime import datetime, time, timezone

    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import scope_change_query
    desde, hasta = _periodo(desde, hasta)
    q = scope_change_query(db.query(ITSMChangeRequest), db, usuario)
    if not getattr(usuario, "is_superadmin", False):
        q = q.filter(ITSMChangeRequest.organization_id == servicio.org_de(usuario))
    # `updated_at` no tiene valor al dar de alta (solo `onupdate`): un cambio que nace
    # cerrado (importado) no contaba nunca. Sin actualización, vale su alta.
    from sqlalchemy import func
    momento = func.coalesce(ITSMChangeRequest.updated_at, ITSMChangeRequest.created_at)
    cerrados = q.filter(ITSMChangeRequest.status.in_(("closed_success", "closed_failed")),
                        momento >= datetime.combine(desde, time.min, tzinfo=timezone.utc)).all()
    ids = [c.id for c in cerrados]
    pendientes_por_cambio: dict = {}
    if ids:
        for p in db.query(PirRevision).filter(PirRevision.change_id.in_(ids), PirRevision.obligatorio.is_(True),
                                              PirRevision.estado.in_(servicio.PENDIENTES)).all():
            pendientes_por_cambio.setdefault(p.change_id, []).append(p)
    del_todo = [c for c in cerrados if c.id not in pendientes_por_cambio]
    pendientes = servicio._de_la_empresa(db, usuario).filter(
        PirRevision.origen_tipo == "change", PirRevision.estado.in_(servicio.PENDIENTES)) \
        .order_by(PirRevision.fecha_prevista.asc().nullslast()).limit(200).all()
    hoy = timeutil.today()
    return {
        "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "cambios_cerrados": len(cerrados), "cerrados_del_todo": len(del_todo),
        "cerrados_con_pir_pendiente": len(pendientes_por_cambio),
        "pir_pendientes": len(pendientes), "pir_vencidas": sum(1 for p in pendientes if servicio.vencida(p, hoy)),
        "pir_por_aprobar": sum(1 for p in pendientes if p.estado == "enviado"),
        "pendientes": [servicio.serializar(db, p) for p in pendientes],
    }


def cerrado_del_todo(db: Session, change) -> bool:
    """Cerrado y sin PIR obligatoria pendiente (para los indicadores del CAB y la ficha del cambio)."""
    if getattr(change.status, "value", change.status) not in ("closed_success", "closed_failed"):
        return False
    return db.query(PirRevision.id).filter(PirRevision.change_id == change.id, PirRevision.obligatorio.is_(True),
                                           PirRevision.estado.in_(servicio.PENDIENTES)).first() is None
