"""
rate_card_service.py — Service layer for Rate Cards (RateTable / RateEntry / RateOverride).
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.advanced_config import RateTable
from app.models.advanced_config import RateTable, RateEntry
from app.models.advanced_config import RateEntry
from app.models.advanced_config import RateOverride
from app.models.advanced_config import RateTable, RateOverride


# ── helpers ────────────────────────────────────────────────────────────────────

def _org_filter(q, model, org_id, is_superadmin):
    if not is_superadmin and org_id:
        q = q.filter(model.organization_id == org_id)
    return q


def _date_valid(valid_from, valid_to, today: str) -> bool:
    if valid_from and today < valid_from:
        return False
    if valid_to and today > valid_to:
        return False
    return True


# ── RateTable ──────────────────────────────────────────────────────────────────

def list_rate_tables(db: Session, org_id, is_superadmin: bool):
    q = db.query(RateTable)
    q = _org_filter(q, RateTable, org_id, is_superadmin)
    return q.order_by(RateTable.is_default.desc(), RateTable.name).all()


def create_rate_table(db: Session, payload_dict: dict, org_id, is_superadmin: bool):
    if payload_dict.get("is_default"):
        q = db.query(RateTable)
        q = _org_filter(q, RateTable, org_id, is_superadmin)
        q.update({"is_default": False})
    t = RateTable(id=str(uuid.uuid4()), organization_id=org_id, **payload_dict)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def get_rate_table_or_404(db: Session, table_id: str, org_id, is_superadmin: bool):
    q = db.query(RateTable).filter(RateTable.id == table_id)
    q = _org_filter(q, RateTable, org_id, is_superadmin)
    t = q.first()
    if not t:
        raise HTTPException(404)
    return t


def update_rate_table(db: Session, table_id: str, payload: dict, org_id, is_superadmin: bool):
    t = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    allowed = ["name", "description", "applies_to", "is_default", "is_active"]
    if payload.get("is_default"):
        q2 = db.query(RateTable).filter(RateTable.id != table_id)
        q2 = _org_filter(q2, RateTable, org_id, is_superadmin)
        q2.update({"is_default": False})
    for k, v in payload.items():
        if k in allowed:
            setattr(t, k, v)
    db.commit()
    return t


def delete_rate_table(db: Session, table_id: str, org_id, is_superadmin: bool):
    t = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    db.delete(t)
    db.commit()


def duplicate_rate_table(
    db: Session,
    table_id: str,
    escalation_pct: float,
    new_name: Optional[str],
    org_id,
    is_superadmin: bool,
):
    src = get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    new_table = RateTable(
        id=str(uuid.uuid4()),
        organization_id=src.organization_id,
        name=new_name or f"{src.name} +{escalation_pct}%",
        description=src.description,
        applies_to=src.applies_to,
        is_default=False,
        is_active=True,
    )
    db.add(new_table)
    db.flush()
    for e in (src.entries or []):
        new_rate = round((e.billing_rate or 0) * (1 + escalation_pct / 100), 2) if escalation_pct else e.billing_rate
        new_cost = round((e.cost_rate or 0) * (1 + escalation_pct / 100), 2) if escalation_pct else e.cost_rate
        db.add(RateEntry(
            id=str(uuid.uuid4()),
            table_id=new_table.id,
            label=e.label,
            billing_rate=new_rate,
            cost_rate=new_cost,
            escalation_pct=escalation_pct,
            valid_from=str(date.today()),
        ))
    db.commit()
    db.refresh(new_table)
    return new_table


# ── RateEntry ──────────────────────────────────────────────────────────────────

def add_entry(db: Session, table_id: str, payload_dict: dict, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = RateEntry(id=str(uuid.uuid4()), table_id=table_id, **payload_dict)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def update_entry(
    db: Session,
    table_id: str,
    entry_id: str,
    payload: dict,
    org_id,
    is_superadmin: bool,
):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id, RateEntry.table_id == table_id
    ).first()
    if not e:
        raise HTTPException(404)
    allowed = ["label", "cost_rate", "billing_rate", "escalation_pct", "valid_from", "valid_to", "notes"]
    for k, v in payload.items():
        if k in allowed:
            setattr(e, k, v)
    db.commit()
    return e


def delete_entry(db: Session, table_id: str, entry_id: str, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id, RateEntry.table_id == table_id
    ).first()
    if not e:
        raise HTTPException(404)
    db.delete(e)
    db.commit()


# ── RateOverride ───────────────────────────────────────────────────────────────

def add_override(db: Session, table_id: str, payload_dict: dict, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    if not payload_dict.get("client_id") and not payload_dict.get("project_id"):
        raise HTTPException(400, "Debe especificar client_id o project_id")
    o = RateOverride(id=str(uuid.uuid4()), table_id=table_id, **payload_dict)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def delete_override(db: Session, table_id: str, override_id: str, org_id, is_superadmin: bool):
    get_rate_table_or_404(db, table_id, org_id, is_superadmin)
    o = db.query(RateOverride).filter(
        RateOverride.id == override_id, RateOverride.table_id == table_id
    ).first()
    if not o:
        raise HTTPException(404)
    db.delete(o)
    db.commit()


# ── Effective rate ─────────────────────────────────────────────────────────────

def get_effective_rate(
    db: Session,
    role_label: str,
    client_id: Optional[str],
    project_id: Optional[str],
    as_of: Optional[str],
    org_id,
    is_superadmin: bool,
) -> dict:

    today = as_of or str(date.today())

    # 1 & 2: Overrides
    for scope_id, scope_col in [(project_id, "project_id"), (client_id, "client_id")]:
        if not scope_id:
            continue
        overrides = db.query(RateOverride).filter(
            getattr(RateOverride, scope_col) == scope_id,
            RateOverride.role_label == role_label,
        ).all()
        for o in overrides:
            if _date_valid(o.valid_from, o.valid_to, today):
                return {
                    "billing_rate": o.billing_rate,
                    "source": f"override_{scope_col}",
                    "role_label": role_label,
                    "override_id": o.id,
                }

    # 3 & 4 & 5: Tables
    q = db.query(RateTable).filter(RateTable.is_active == True)
    q = _org_filter(q, RateTable, org_id, is_superadmin)
    tables = q.all()

    tables_sorted = sorted(tables, key=lambda t: (
        0 if (project_id and t.applies_to == "client") else
        1 if (client_id and t.applies_to == "client") else
        2 if t.is_default else 3
    ))

    for table in tables_sorted:
        for entry in (table.entries or []):
            if entry.label.lower() == role_label.lower():
                if _date_valid(entry.valid_from, entry.valid_to, today):
                    rate = entry.billing_rate or 0
                    if entry.escalation_pct and entry.valid_from:
                        years = date.today().year - int(entry.valid_from[:4])
                        rate = rate * ((1 + entry.escalation_pct / 100) ** max(0, years))
                        rate = round(rate, 2)
                    return {
                        "billing_rate": rate,
                        "cost_rate": entry.cost_rate,
                        "source": f"table:{table.name}",
                        "role_label": role_label,
                        "table_id": table.id,
                        "entry_id": entry.id,
                        "escalation_applied": entry.escalation_pct > 0,
                    }

    return {"billing_rate": None, "source": "not_found", "role_label": role_label}


# ── Serialization helpers ─────────────────────────────────────────────────────────

def serialize_rate_entry(e) -> dict:
    return {
        "id": e.id, "label": e.label,
        "cost_rate": e.cost_rate, "billing_rate": e.billing_rate,
        "escalation_pct": e.escalation_pct or 0.0,
        "valid_from": e.valid_from, "valid_to": e.valid_to,
        "notes": e.notes,
    }


def serialize_rate_override(o) -> dict:
    return {
        "id": o.id, "client_id": o.client_id, "project_id": o.project_id,
        "role_label": o.role_label, "billing_rate": o.billing_rate,
        "valid_from": o.valid_from, "valid_to": o.valid_to, "notes": o.notes,
    }


def serialize_rate_table(t, include_entries: bool = False) -> dict:
    d = {
        "id": t.id, "name": t.name, "description": t.description,
        "applies_to": t.applies_to, "is_default": t.is_default,
        "is_active": t.is_active,
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    }
    if include_entries:
        d["entries"]   = [serialize_rate_entry(e) for e in (t.entries or [])]
        d["overrides"] = [serialize_rate_override(o) for o in getattr(t, "overrides", [])]
    else:
        d["entry_count"] = len(t.entries or [])
    return d
