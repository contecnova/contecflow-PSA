"""Coste por hora de un externo: la tarifa del proveedor vigente en la fecha.

Orden (la primera que aplique):

1. La tarifa (`SubcontractorRate`) de su asignacion activa al proyecto en esa
   fecha, si esta vigente (`valid_from`/`valid_until`).
2. El `cost_rate` del trabajador (lo que se le paga por hora).
3. Nada: `cost_service` sigue con la ficha de coste / `hourly_rate` del usuario.

La moneda es la de la tarifa (o la del trabajador / proveedor); `cost_service`
la convierte a la de la empresa con el tipo de la fecha. Asi la imputacion de
un externo lleva su coste real en `imputations.cost_amount` y la rentabilidad
lo cuenta como el de cualquiera (una sola fuente de horas y coste).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session


def _vigente(rate, dia: date) -> bool:
    return bool(rate and rate.is_active is not False
                and (rate.valid_from is None or rate.valid_from <= dia)
                and (rate.valid_until is None or rate.valid_until >= dia))


def asignacion_en_fecha(db: Session, user_id: str, project_id: Optional[str], dia: date):
    """La asignacion activa del externo al proyecto que cubre `dia` (o None)."""
    from app.models.enterprise import SubcontractorAssignment, SubcontractorWorker
    if not project_id:
        return None
    return (db.query(SubcontractorAssignment)
            .join(SubcontractorWorker, SubcontractorWorker.id == SubcontractorAssignment.worker_id)
            .filter(SubcontractorWorker.user_id == user_id,
                    SubcontractorAssignment.project_id == project_id,
                    or_(SubcontractorAssignment.start_date.is_(None), SubcontractorAssignment.start_date <= dia),
                    or_(SubcontractorAssignment.end_date.is_(None), SubcontractorAssignment.end_date >= dia))
            .order_by(SubcontractorAssignment.start_date.desc().nulls_last())   # M18: en PostgreSQL NULL iba primero
            .first())


def tarifa_de_asignacion(db: Session, asignacion, dia: date) -> Optional[tuple[float, Optional[str]]]:
    """(coste/h, moneda) de una asignacion en `dia`: su tarifa vigente o la del trabajador."""
    from app.models.enterprise import Subcontractor
    if asignacion is None:
        return None
    rate = asignacion.rate
    if _vigente(rate, dia) and rate.cost_rate:
        return float(rate.cost_rate), rate.currency
    w = asignacion.worker
    if w is not None and w.cost_rate:
        moneda = w.currency
        if not moneda:
            sub = db.get(Subcontractor, w.subcontractor_id)
            moneda = sub.currency if sub else None
        return float(w.cost_rate), moneda
    return None


def tarifa_vigente(db: Session, user, project_id: Optional[str], dia: date) -> Optional[tuple[float, Optional[str]]]:
    """(coste/h, moneda) del externo `user` en el proyecto y fecha; None si es interno
    o no hay tarifa de proveedor (entonces manda la ficha de coste del usuario)."""
    from app.models.enterprise import SubcontractorWorker
    from app.models.user import UserRole
    if user is None or getattr(user, "role", None) not in (UserRole.subcontractor, UserRole.subcontractor.value):
        return None
    t = tarifa_de_asignacion(db, asignacion_en_fecha(db, user.id, project_id, dia), dia)
    if t:
        return t
    w = db.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user.id).first()
    if w is not None and w.cost_rate:
        return float(w.cost_rate), w.currency
    return None
