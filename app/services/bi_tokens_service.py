"""Tokens de acceso para BI externo y los datos que exponen.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from app.core import timeutil
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.project import Project
from app.models.imputation import Imputation
from app.models.mfa import (
    BIToken,
)
from sqlalchemy.orm import joinedload as jl


def verify_bi_token(token: str, db: Session) -> Optional[BIToken]:
    if not token or not token.startswith("bi_"):
        return None
    import bcrypt
    prefix = token[:10]
    candidates = db.query(BIToken).filter(
        BIToken.token_prefix == prefix,
        BIToken.is_active == True,
    ).all()
    for bt in candidates:
        if bcrypt.checkpw(token.encode(), bt.token_hash.encode()):
            bt_exp = bt.expires_at.replace(tzinfo=timezone.utc) if bt.expires_at and not bt.expires_at.tzinfo else bt.expires_at
            if bt_exp and bt_exp < datetime.now(timezone.utc):
                return None
            bt.last_used_at = datetime.now(timezone.utc)
            bt.requests_today = (bt.requests_today or 0) + 1
            return bt
    return None


def list_bi_tokens(db: Session) -> list:
    tokens = db.query(BIToken).options(jl(BIToken.creator)).all()
    return [{
        "id": t.id, "name": t.name, "tool": t.tool,
        "token_prefix": t.token_prefix,
        "scopes": json.loads(t.scopes or '["read"]'),
        "is_active": t.is_active,
        "expires_at": str(t.expires_at)[:10] if t.expires_at else None,
        "last_used_at": str(t.last_used_at)[:16] if t.last_used_at else None,
        "requests_today": t.requests_today or 0,
        "created_by": t.creator.full_name if t.creator else None,
    } for t in tokens]


def create_bi_token(payload_dict: dict, created_by: str, db: Session) -> dict:
    import bcrypt
    raw_token = "bi_" + secrets.token_hex(24)
    prefix = raw_token[:10]
    hashed = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    expires_at = None
    if payload_dict.get("expires_days"):
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload_dict["expires_days"])
    t = BIToken(
        name=payload_dict["name"], tool=payload_dict.get("tool", "powerbi"),
        token_hash=hashed, token_prefix=prefix,
        scopes=json.dumps(payload_dict.get("scopes") or ["read"]),
        expires_at=expires_at, created_by=created_by,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "token": raw_token,
            "warning": "Guarda este token. No se mostrará de nuevo."}


def revoke_bi_token(token_id: str, db: Session) -> dict:
    t = db.query(BIToken).filter(BIToken.id == token_id).first()
    if not t:
        raise ValueError("not_found")
    t.is_active = False
    db.commit()
    return {"ok": True}


def _check_bi_token_auth(raw_token: Optional[str], db: Session) -> None:
    """Verify BI token auth; raises ValueError('unauthorized') if invalid."""
    if not raw_token:
        raise ValueError("unauthorized")
    bt = verify_bi_token(raw_token, db)
    if not bt:
        raise ValueError("unauthorized")
    db.commit()


def bi_data_projects(raw_token: Optional[str], db: Session) -> list:
    _check_bi_token_auth(raw_token, db)
    projects = db.query(Project).filter(Project.status != "archived").all()
    return [{
        "id": p.id, "code": p.code, "name": p.name,
        "client_name": p.client_name, "status": p.status,
        "start_date": str(p.start_date) if p.start_date else None,
        "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
        "budget_amount": p.budget_amount, "billing_rate": p.billing_rate,
        "total_hours_logged": db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == p.id).scalar() or 0,
    } for p in projects]


def bi_data_timesheets(
    raw_token: Optional[str],
    date_from: Optional[str], date_to: Optional[str],
    page: int, page_size: int,
    db: Session,
) -> list:
    _check_bi_token_auth(raw_token, db)
    q = db.query(Imputation).options(jl(Imputation.user), jl(Imputation.project))
    if date_from:
        q = q.filter(Imputation.date >= date.fromisoformat(date_from))
    if date_to:
        q = q.filter(Imputation.date <= date.fromisoformat(date_to))
    imputations = (
        q.order_by(Imputation.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [{
        "date": str(i.date),
        "user_name": i.user.full_name if i.user else "—",
        "user_role": i.user.role if i.user else "—",
        "project_code": i.project.code if i.project else "—",
        "project_name": i.project.name if i.project else "—",
        "hours": i.hours,
        "is_billable": i.is_billable,
        "description": i.description,
    } for i in imputations]


def bi_data_kpis(raw_token: Optional[str], db: Session) -> dict:
    _check_bi_token_auth(raw_token, db)
    active_projects = db.query(func.count(Project.id)).filter(Project.status == "active").scalar()
    total_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    this_week_start = timeutil.today() - timedelta(days=timeutil.today().weekday())
    hours_this_week = db.query(func.sum(Imputation.hours)).filter(
        Imputation.date >= this_week_start
    ).scalar() or 0
    total_budget = db.query(func.sum(Project.budget_amount)).filter(
        Project.status.in_(["active", "planning"])
    ).scalar() or 0
    return {
        "active_projects": active_projects,
        "total_users": total_users,
        "hours_this_week": round(hours_this_week, 1),
        "total_budget_active": round(total_budget, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
