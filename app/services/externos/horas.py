"""Horas y coste de las asignaciones de externos: una sola fuente.

El externo con acceso imputa como todos (`imputations`): esas horas y su coste
(tarifa del proveedor, ver `tarifas`) son las de su asignacion. El parte manual
(`subcontractor_timelogs`) es solo para externos SIN acceso (lo registra el PM
o se importa) y, por diseno, un parte nunca cuenta si esa persona ya tiene una
imputacion en ese proyecto y dia (`partes_sin_duplicar`): ni en
`hours_logged`, ni en el coste del proyecto (`costes_de_proyecto`).

`hours_logged` ya no se suma a mano: se recalcula (`recalcular`) cada vez que
cambian imputaciones o partes de una persona externa, desde los ganchos de
sesion de este modulo, registrados al importarse desde `app/main.py` y
`app/worker.py` (cubre alta, cronometro, edicion, borrado,
importacion, voz, bots...). Al cruzar el umbral de consumo
(`EXTERNOS_UMBRAL_CONSUMO_PCT`, en caliente) y al llegar al 100 % de horas
contratadas o del importe del pedido se avisa al responsable interno y al PM.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def partes_sin_duplicar(db: Session, q):
    """Filtra una consulta de `SubcontractorTimeLog` quitando los partes de una
    persona que ya imputo en ese proyecto y dia (la imputacion manda)."""
    from app.models.enterprise import SubcontractorTimeLog as TL, SubcontractorWorker as W
    from app.models.imputation import Imputation as I
    duplicado = exists().where(and_(
        W.id == TL.worker_id, W.user_id.isnot(None), I.user_id == W.user_id,
        I.project_id == TL.project_id, I.date == TL.log_date))
    return q.filter(~duplicado)


def _imputaciones_de(db: Session, a):
    from app.models.imputation import Imputation as I
    w = a.worker
    if w is None or not w.user_id:
        return None
    q = db.query(I).filter(I.user_id == w.user_id, I.project_id == a.project_id)
    if a.start_date:
        q = q.filter(I.date >= a.start_date)
    if a.end_date:
        q = q.filter(I.date <= a.end_date)
    return q


def consumo(db: Session, a) -> dict:
    """Horas y coste de una asignacion (imputado + parte manual sin duplicar)."""
    from sqlalchemy import func
    from app.models.enterprise import SubcontractorTimeLog as TL
    from app.models.imputation import Imputation as I
    h_imp = c_imp = 0.0
    q = _imputaciones_de(db, a)
    if q is not None:
        h_imp, c_imp = q.with_entities(func.coalesce(func.sum(I.hours), 0.0),
                                       func.coalesce(func.sum(I.cost_amount), 0.0)).one()
    tq = partes_sin_duplicar(db, db.query(TL).filter(TL.assignment_id == a.id, TL.is_active.isnot(False)))
    h_man, c_man = tq.with_entities(func.coalesce(func.sum(TL.hours), 0.0),
                                    func.coalesce(func.sum(TL.cost_amount), 0.0)).one()
    horas = float(h_imp or 0) + float(h_man or 0)
    coste = float(c_imp or 0) + float(c_man or 0)
    pct_h = (horas / a.hours_contracted * 100) if a.hours_contracted else None
    pct_c = (coste / a.po_amount * 100) if a.po_amount else None
    pcts = [p for p in (pct_h, pct_c) if p is not None]
    return {"hours_imputed": round(float(h_imp or 0), 2), "hours_manual": round(float(h_man or 0), 2),
            "hours_logged": round(horas, 2), "cost_amount": round(coste, 2),
            "hours_pct": round(pct_h, 1) if pct_h is not None else None,
            "po_consumed_pct": round(pct_c, 1) if pct_c is not None else None,
            "consumption_pct": round(max(pcts), 1) if pcts else None}


def umbral(db: Session, org_id: Optional[str]) -> float:
    from app.services.settings_service import get_runtime_float
    return float(get_runtime_float(db, "EXTERNOS_UMBRAL_CONSUMO_PCT", org_id) or 80.0)


def _avisar(db: Session, a, pct: float, nivel: float) -> None:
    from app.models.project import Project
    from app.services.notifications import notify_user
    project = db.get(Project, a.project_id)
    w = a.worker
    quien = w.name if w else (a.subcontractor.name if a.subcontractor else "")
    destinatarios = {x for x in ((w.internal_owner_id if w else None), project.pm_id if project else None) if x}
    titulo = (f"Externo {quien}: asignación consumida al {round(pct)} %" if nivel < 100
              else f"Externo {quien}: horas contratadas o pedido agotados ({round(pct)} %)")
    cuerpo = f"Proyecto {project.name if project else a.project_id}. Pedido {a.po_number or '—'}."
    for uid in destinatarios:
        notify_user(db, uid, "budget_warning", titulo, cuerpo,
                    resource="subcontractor_assignments", resource_id=a.id, action_url="/subcontractors")


def recalcular(db: Session, asignaciones: Iterable) -> None:
    """Recalcula `hours_logged` y avisa al cruzar el umbral (una vez por nivel)."""
    for a in asignaciones:
        c = consumo(db, a)
        a.hours_logged = c["hours_logged"]
        pct = c["consumption_pct"]
        if pct is None:
            continue
        u = umbral(db, a.organization_id)
        nivel = 100.0 if pct >= 100 else (u if pct >= u else None)
        if nivel is None:
            if a.consumption_alert_pct and pct < a.consumption_alert_pct:
                a.consumption_alert_pct = None  # bajo el umbral otra vez (correcciones)
            continue
        if (a.consumption_alert_pct or 0) < nivel:
            a.consumption_alert_pct = nivel
            _avisar(db, a, pct, nivel)


def asignaciones_afectadas(db: Session, pares: set, ids_asignacion: set) -> list:
    """Asignaciones de externos tocadas por cambios de imputaciones (`pares` de
    (user_id, project_id)) o de partes (`ids_asignacion`)."""
    from app.models.enterprise import SubcontractorAssignment as A, SubcontractorWorker as W
    conds = []
    if pares:
        usuarios = {u for u, _ in pares if u}
        proyectos = {p for _, p in pares if p}
        if usuarios and proyectos:
            conds.append(and_(W.user_id.in_(usuarios), A.project_id.in_(proyectos)))
    if ids_asignacion:
        conds.append(A.id.in_(ids_asignacion))
    if not conds:
        return []
    filas = db.query(A).outerjoin(W, W.id == A.worker_id).filter(or_(*conds)).all()
    return [a for a in filas if a.id in ids_asignacion or (a.worker and (a.worker.user_id, a.project_id) in pares)]


# ── Ganchos de sesion (se registran al final del modulo) ────────────────────

_CLAVE = "externos_horas_pendientes"


def anotar_cambios(session) -> None:
    """before_flush: apunta que imputaciones/partes cambian (sin consultar)."""
    from app.models.enterprise import SubcontractorTimeLog
    from app.models.imputation import Imputation
    pend = session.info.setdefault(_CLAVE, (set(), set()))
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, Imputation):
            pend[0].add((obj.user_id, obj.project_id))
            # Si cambia de proyecto, el de antes tambien se recalcula.
            from sqlalchemy import inspect as _inspect
            for antes in _inspect(obj).attrs.project_id.history.deleted or ():
                pend[0].add((obj.user_id, antes))
        elif isinstance(obj, SubcontractorTimeLog) and obj.assignment_id:
            pend[1].add(obj.assignment_id)
    if not pend[0] and not pend[1]:
        session.info.pop(_CLAVE, None)


def aplicar_pendientes(session) -> None:
    """before_commit: recalcula las asignaciones afectadas (entra en el commit)."""
    if session.info.get("_externos_en_curso"):
        return
    # Lo que aun no se ha volcado (un `add` seguido de `commit`) tambien cuenta.
    anotar_cambios(session)
    pend = session.info.pop(_CLAVE, None)
    if not pend:
        return
    session.info["_externos_en_curso"] = True
    try:
        session.flush()
        session.info.pop(_CLAVE, None)
        afectadas = asignaciones_afectadas(session, pend[0], pend[1])
        if not afectadas:
            return
        # En un punto de guardado: un fallo del aviso no tumba la imputacion.
        punto = session.begin_nested()
        try:
            recalcular(session, afectadas)
            punto.commit()
        except Exception:
            punto.rollback()
            logger.exception("externos: no se pudo recalcular el consumo de asignaciones")
    finally:
        session.info.pop("_externos_en_curso", None)


# Registro de los ganchos en la sesion base (antes en `app/models/enterprise.py`;
# un modelo no importa servicios). Lo importan `app/main.py` y `app/worker.py`.
from sqlalchemy import event as _sa_event  # noqa: E402


@_sa_event.listens_for(Session, "before_flush")
def _externos_anotar_horas(session, flush_context, instances) -> None:
    anotar_cambios(session)


@_sa_event.listens_for(Session, "before_commit")
def _externos_recalcular_horas(session) -> None:
    aplicar_pendientes(session)
