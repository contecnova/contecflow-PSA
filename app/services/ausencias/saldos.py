"""Saldos: de qué descuenta cada tipo y cuánto queda.

- Saldo `vacaciones`: los días que tiene la persona (`user_vacation_balances`
  o `DEFAULT_VACATION_DAYS_PER_YEAR` de su empresa, más lo arrastrado). Lo
  comparten todos los tipos con `saldo = vacaciones` y se cuenta en días
  (`working_days`: un medio día es 0,5).
- Saldo `propio`: el `cupo_anual` del tipo, en la unidad del tipo (días,
  medios días u horas: `amount`).

Cuenta lo aprobado («usado») y lo pendiente o en lista de espera («pedido»).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.ausencias import TipoDeAusencia
from app.models.resources import Absence, AbsenceStatus

PEDIDAS = (AbsenceStatus.pending, AbsenceStatus.waitlisted)


def _suma(db: Session, user_id: str, year: int, filtro, columna, estados, excluir: Optional[str]) -> float:
    q = db.query(func.sum(columna)).outerjoin(TipoDeAusencia, TipoDeAusencia.id == Absence.absence_type_id).filter(
        Absence.user_id == user_id, Absence.is_active.is_(True), Absence.status.in_(estados),
        Absence.start_date >= date(year, 1, 1), Absence.start_date < date(year + 1, 1, 1), filtro)
    if excluir:
        q = q.filter(Absence.id != excluir)
    return float(q.scalar() or 0)


def _de_vacaciones():
    # Las ausencias de antes de la 167 sin tipo enlazado cuentan por su clave.
    return or_(TipoDeAusencia.saldo == "vacaciones",
               and_(Absence.absence_type_id.is_(None), Absence.type == "vacation"))


def derecho_de_vacaciones(db: Session, user_id: str, year: int) -> tuple[float, float]:
    """(días que le corresponden, arrastrados del año anterior)."""
    from app.models.advanced_config import UserVacationBalance
    from app.models.user import User
    from app.services.settings_service import get_runtime_int
    bal = db.query(UserVacationBalance).filter(UserVacationBalance.user_id == user_id,
                                               UserVacationBalance.year == year).first()
    if bal is not None:
        return float(bal.days_entitled or 0), float(bal.days_carried_over or 0)
    org = db.query(User.organization_id).filter(User.id == user_id).scalar()
    return float(get_runtime_int(db, "DEFAULT_VACATION_DAYS_PER_YEAR", org)), 0.0


def vacaciones(db: Session, user_id: str, year: int, excluir: Optional[str] = None) -> dict:
    derecho, arrastre = derecho_de_vacaciones(db, user_id, year)
    usado = _suma(db, user_id, year, _de_vacaciones(), Absence.working_days, (AbsenceStatus.approved,), excluir)
    pedido = _suma(db, user_id, year, _de_vacaciones(), Absence.working_days, PEDIDAS, excluir)
    return {"saldo": "vacaciones", "unidad": "dias", "year": year, "disponible": derecho + arrastre,
            "derecho": derecho, "arrastre": arrastre, "usado": round(usado, 2), "pedido": round(pedido, 2),
            "restante": round(derecho + arrastre - usado - pedido, 2)}


def propio(db: Session, user_id: str, year: int, tipo: TipoDeAusencia, excluir: Optional[str] = None) -> dict:
    filtro = Absence.absence_type_id == tipo.id
    usado = _suma(db, user_id, year, filtro, Absence.amount, (AbsenceStatus.approved,), excluir)
    pedido = _suma(db, user_id, year, filtro, Absence.amount, PEDIDAS, excluir)
    total = float(tipo.cupo_anual or 0)
    return {"saldo": "propio", "tipo_id": tipo.id, "unidad": tipo.unidad, "year": year, "disponible": total,
            "derecho": total, "arrastre": 0.0, "usado": round(usado, 2), "pedido": round(pedido, 2),
            "restante": round(total - usado - pedido, 2)}


def de_tipo(db: Session, user_id: str, year: int, tipo: TipoDeAusencia, excluir: Optional[str] = None) -> Optional[dict]:
    if not tipo.descuenta_saldo:
        return None
    return vacaciones(db, user_id, year, excluir) if tipo.saldo == "vacaciones" else propio(db, user_id, year, tipo, excluir)


def todos(db: Session, user_id: str, year: int) -> list[dict]:
    """Todos los saldos de una persona: el de vacaciones y uno por tipo con cupo propio."""
    from app.services.ausencias import catalogo
    tipos = catalogo.tipos(db)
    salida = []
    if any(t.descuenta_saldo and t.saldo == "vacaciones" for t in tipos):
        v = vacaciones(db, user_id, year)
        v["tipos"] = [t.id for t in tipos if t.descuenta_saldo and t.saldo == "vacaciones"]
        salida.append(v)
    for t in tipos:
        if t.descuenta_saldo and t.saldo == "propio":
            p = propio(db, user_id, year, t)
            p["tipos"] = [t.id]
            salida.append(p)
    return salida
