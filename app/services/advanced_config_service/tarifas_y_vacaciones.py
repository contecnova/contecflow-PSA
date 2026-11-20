"""Tablas de tarifas, politicas y saldos de vacaciones, y oficinas.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.services.settings_service import por_empresa as _pe
from app.core.config import settings
from app.models.advanced_config import UserVacationBalance
from app.models.advanced_config import RateTable
from app.models.advanced_config import RateEntry
from app.models.advanced_config import VacationPolicy
from app.models.advanced_config import Office
from app.models.resources import Absence, AbsenceStatus, AbsenceType
from app.models.user import User as UserModel

from app.services.advanced_config_service._comun import NotFoundError


# ── Vacation balances ─────────────────────────────────────────────────────────

def get_vacation_balances(year: Optional[int], db: Session) -> list:

    if not year:
        year = datetime.now().year
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)

    users = db.query(UserModel).filter(UserModel.is_active == True).all()
    results = []
    for u in users:
        bal = db.query(UserVacationBalance).filter(
            UserVacationBalance.user_id == u.id,
            UserVacationBalance.year == year,
        ).first()
        taken = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id,
            Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.approved,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        pending = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id,
            Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.pending,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        entitled = bal.days_entitled if bal else settings.DEFAULT_VACATION_DAYS_PER_YEAR
        results.append({
            "user_id": u.id, "user_name": u.full_name, "department": u.department,
            "year": year, "days_entitled": entitled,
            "days_taken": round(taken, 1),
            "days_pending": round(pending, 1),
            "days_remaining": round(entitled - taken - pending, 1),
            "days_carried_over": bal.days_carried_over if bal else 0,
        })
    return results


def update_vacation_balance(
    user_id: str, year: int, days_entitled: float, db: Session, actor=None,
) -> dict:
    """Cambia el derecho de vacaciones de `user_id` en `year`.

    19-11-2026 (GRC): queda en la auditoría (`audit_logs`, recurso
    `vacation_balance`): quién (`actor`), de quién y qué año, el antes y el
    después de `days_entitled`, en la misma transacción que el cambio.
    """
    # 19-11-2026: el máximo era sólo el `max="60"` de la pantalla; ahora es el
    # ajuste de la empresa de la persona (`VACATION_MAX_DAYS_ENTITLED`) y lo
    # comprueba el servidor.
    from app.core.codigos_de_error import error
    from app.services.settings_service.valores_de_negocio import maximo_de_dias_de_vacaciones
    persona = db.get(UserModel, user_id)
    maximo = maximo_de_dias_de_vacaciones(db, registro=persona)
    if not (0 <= float(days_entitled) <= maximo):
        raise error(422, "ajuste_valor_no_valido", detail=f"days_entitled must be between 0 and {maximo}",
                    clave="days_entitled", esperado=f"0..{maximo}")
    bal = db.query(UserVacationBalance).filter(
        UserVacationBalance.user_id == user_id,
        UserVacationBalance.year == year,
    ).first()
    # Sin fila, el derecho efectivo era el de por defecto (lo que se enseñaba).
    antes = bal.days_entitled if bal else settings.DEFAULT_VACATION_DAYS_PER_YEAR
    fila_nueva = bal is None
    if not bal:
        bal = UserVacationBalance(
            user_id=user_id, year=year, days_entitled=days_entitled,
        )
        db.add(bal)
        db.flush()
    else:
        bal.days_entitled = days_entitled
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE", "vacation_balance", bal.id,
              getattr(persona, "full_name", None) or user_id,
              old_values={"days_entitled": antes, "year": year},
              new_values={"days_entitled": float(days_entitled), "year": year},
              metadata={"user_id": user_id, "fila_nueva": fila_nueva})
    db.commit()
    return {"ok": True}


# ── Rate tables ───────────────────────────────────────────────────────────────

def list_rate_tables(db: Session) -> list:
    tables = (
        db.query(RateTable)
        .options(joinedload(RateTable.entries))
        .filter(RateTable.is_active == True)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "is_default": t.is_default, "is_active": t.is_active, "applies_to": t.applies_to,
            "entries": [
                {
                    "id": e.id, "label": e.label, "cost_rate": e.cost_rate,
                    "billing_rate": e.billing_rate,
                    "currency": getattr(e, "currency", None) or _pe.moneda_de_empresa(db, registro=t),  # 18-11-2026
                }
                for e in (t.entries or []) if getattr(e, "is_active", True)
            ],
        }
        for t in tables
    ]


def create_rate_table(data: dict, db: Session) -> dict:
    if data.get("is_default"):
        db.query(RateTable).filter(RateTable.is_default == True).update({"is_default": False})
    t = RateTable(**data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name}


def add_rate_entry(table_id: str, data: dict, db: Session) -> dict:
    # 18-11-2026: sin moneda, la de la empresa (antes el esquema ponía la global).
    data = {**data, "currency": data.get("currency") or _pe.moneda_de_empresa(db)}
    e = RateEntry(table_id=table_id, **data)
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


def update_rate_entry(table_id: str, entry_id: str, data: dict, db: Session) -> dict:
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise NotFoundError("No encontrado")
    if not data.get("currency"):
        data = {**data, "currency": e.currency or _pe.moneda_de_empresa(db, registro=e)}
    for k, v in data.items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


def delete_rate_entry(table_id: str, entry_id: str, db: Session) -> dict:
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise NotFoundError("No encontrado")
    e.is_active = False
    db.commit()
    return {"ok": True, "message": "Tarifa eliminada"}


def delete_rate_table(table_id: str, db: Session) -> dict:
    t = db.query(RateTable).filter(RateTable.id == table_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ── Vacation policies ─────────────────────────────────────────────────────────

def list_vacation_policies(db: Session) -> list:
    policies = db.query(VacationPolicy).filter(VacationPolicy.is_active == True).all()
    return [
        {
            "id": p.id, "name": p.name, "description": p.description,
            "days_per_year": p.days_per_year, "carries_over": p.carries_over,
            "max_carryover_days": p.max_carryover_days,
            "carryover_expiry_months": p.carryover_expiry_months,
            "applies_to_roles": p.applies_to_roles, "is_default": p.is_default,
            "is_active": p.is_active,
        }
        for p in policies
    ]


def create_vacation_policy(data: dict, db: Session) -> dict:
    if data.get("is_default"):
        db.query(VacationPolicy).filter(VacationPolicy.is_default == True).update({"is_default": False})
    p = VacationPolicy(**{**data, "applies_to_roles": json.dumps(data.get("applies_to_roles") or [])})
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name}


def update_vacation_policy(policy_id: str, data: dict, db: Session) -> dict:
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(p, k, json.dumps(v) if k == "applies_to_roles" else v)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


def delete_vacation_policy(policy_id: str, db: Session) -> dict:
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p:
        raise NotFoundError("No encontrado")
    p.is_active = False
    db.commit()
    return {"ok": True}


# ── Offices ───────────────────────────────────────────────────────────────────

def list_offices(db: Session) -> list:
    offices = db.query(Office).filter(Office.is_active == True).order_by(Office.name).all()
    return [
        {"id": o.id, "name": o.name, "country": o.country, "city": o.city,
         "timezone": o.timezone, "is_active": o.is_active}
        for o in offices
    ]


def create_office(data: dict, db: Session) -> dict:
    # 18-11-2026: sin zona, la de la empresa (antes el esquema ponía la global).
    data = {**data, "timezone": data.get("timezone") or _pe.zona_de_empresa(db)}
    o = Office(**data)
    db.add(o)
    db.commit()
    db.refresh(o)
    return {"id": o.id, "name": o.name}


def update_office(office_id: str, data: dict, db: Session) -> dict:
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o:
        raise NotFoundError("No encontrado")
    if not data.get("timezone"):
        data = {**data, "timezone": o.timezone or _pe.zona_de_empresa(db, registro=o)}
    for k, v in data.items():
        setattr(o, k, v)
    db.commit()
    db.refresh(o)
    return {"id": o.id}


def delete_office(office_id: str, db: Session) -> dict:
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o:
        raise NotFoundError("No encontrado")
    o.is_active = False
    db.commit()
    return {"ok": True}
