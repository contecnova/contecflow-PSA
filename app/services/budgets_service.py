"""Presupuestos por departamento y ejercicio.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.mfa import (
    Budget, BudgetEntry,
)
from app.services.audit import audit_log
from sqlalchemy.orm import joinedload as jl


def budget_by_dept(budgets) -> list:
    dept_map = {}
    for b in budgets:
        dept = b.department or "Sin departamento"
        if dept not in dept_map:
            dept_map[dept] = {"department": dept, "planned": 0, "actual": 0}
        for e in b.entries:
            dept_map[dept]["planned"] += e.planned
            dept_map[dept]["actual"] += e.actual
    for d in dept_map.values():
        d["deviation_pct"] = round((d["actual"] - d["planned"]) / max(d["planned"], 1) * 100, 1)
    return list(dept_map.values())


def list_budgets(year: Optional[int], department: Optional[str], db: Session) -> list:
    q = db.query(Budget).options(jl(Budget.entries))
    if year:
        q = q.filter(Budget.year == year)
    if department:
        q = q.filter(Budget.department == department)
    budgets = q.order_by(Budget.year.desc(), Budget.name).limit(200).all()
    return [{
        "id": b.id, "name": b.name, "year": b.year,
        "department": b.department,
        "total_amount": b.total_amount, "currency": b.currency,
        "is_approved": b.is_approved,
        "planned_total": sum(e.planned for e in b.entries),
        "actual_total": sum(e.actual for e in b.entries),
        "deviation": sum(e.actual for e in b.entries) - sum(e.planned for e in b.entries),
        "deviation_pct": round((sum(e.actual for e in b.entries) - sum(e.planned for e in b.entries)) / max(b.total_amount, 1) * 100, 1),
        "entries": [{
            "month": e.month, "planned": e.planned,
            "actual": e.actual, "committed": e.committed,
            "is_locked": e.is_locked,
        } for e in sorted(b.entries, key=lambda x: x.month)],
    } for b in budgets]


def create_budget(payload_dict: dict, created_by: str, db: Session) -> dict:
    b = Budget(
        name=payload_dict["name"], year=payload_dict["year"],
        department=payload_dict.get("department"), project_id=payload_dict.get("project_id"),
        total_amount=payload_dict.get("total_amount", 0),
        currency=payload_dict.get("currency", settings.DEFAULT_CURRENCY),
        notes=payload_dict.get("notes"), created_by=created_by,
    )
    db.add(b); db.flush()
    monthly = payload_dict.get("monthly_planned") or []
    if not monthly:
        monthly = [round(b.total_amount / 12, 2)] * 12
    for month in range(1, 13):
        planned = monthly[month - 1] if month <= len(monthly) else 0
        db.add(BudgetEntry(budget_id=b.id, month=month, planned=planned))
    db.commit()
    return {"ok": True, "id": b.id}


def update_budget_entry(budget_id: str, payload: dict, db: Session) -> dict:
    month = payload.get("month")
    entry = db.query(BudgetEntry).filter(
        BudgetEntry.budget_id == budget_id,
        BudgetEntry.month == month,
    ).first()
    if not entry:
        raise ValueError("not_found")
    if entry.is_locked:
        raise ValueError("Mes cerrado contablemente")
    for field in ["planned", "actual", "committed", "notes"]:
        if field in payload:
            setattr(entry, field, payload[field])
    db.commit()
    return {"ok": True}


def approve_budget(budget_id: str, current_user: User, db: Session) -> dict:
    b = db.query(Budget).filter(Budget.id == budget_id).first()
    if not b:
        raise ValueError("not_found")
    b.is_approved = True
    b.approved_by = current_user.id
    b.approved_at = datetime.now(timezone.utc)
    audit_log(db, current_user, "BUDGET_APPROVED", "budgets", b.id, b.name)
    db.commit()
    return {"ok": True}


def get_budget_summary(year: Optional[int], db: Session) -> dict:
    yr = year or datetime.now().year
    budgets = db.query(Budget).options(jl(Budget.entries)).filter(Budget.year == yr).all()
    total_planned = sum(e.planned for b in budgets for e in b.entries)
    total_actual = sum(e.actual for b in budgets for e in b.entries)
    by_month: dict = {}
    for b in budgets:
        for e in b.entries:
            if e.month not in by_month:
                by_month[e.month] = {"month": e.month, "planned": 0, "actual": 0}
            by_month[e.month]["planned"] += e.planned
            by_month[e.month]["actual"] += e.actual
    return {
        "year": yr,
        "total_planned": round(total_planned, 2),
        "total_actual": round(total_actual, 2),
        "deviation": round(total_actual - total_planned, 2),
        "deviation_pct": round((total_actual - total_planned) / max(total_planned, 1) * 100, 1),
        "budgets_count": len(budgets),
        "approved_count": sum(1 for b in budgets if b.is_approved),
        "by_month": [by_month[m] for m in sorted(by_month.keys())],
        "by_department": budget_by_dept(budgets),
    }
