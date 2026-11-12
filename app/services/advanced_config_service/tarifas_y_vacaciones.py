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
    user_id: str, year: int, days_entitled: float, db: Session,
) -> dict:
    bal = db.query(UserVacationBalance).filter(
        UserVacationBalance.user_id == user_id,
        UserVacationBalance.year == year,
    ).first()
    if not bal:
        bal = UserVacationBalance(
            user_id=user_id, year=year, days_entitled=days_entitled,
        )
        db.add(bal)
    else:
        bal.days_entitled = days_entitled
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
                    "currency": getattr(e, "currency", settings.DEFAULT_CURRENCY),
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
    o = Office(**data)
    db.add(o)
    db.commit()
    db.refresh(o)
    return {"id": o.id, "name": o.name}


def update_office(office_id: str, data: dict, db: Session) -> dict:
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o:
        raise NotFoundError("No encontrado")
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
