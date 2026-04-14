"""
rate_cards.py — Rate Cards sofisticadas: tablas de tarifas con herencia cliente/proyecto.

Endpoints:
  GET    /rate-cards                       — listar tablas
  POST   /rate-cards                       — crear tabla
  GET    /rate-cards/{id}                  — detalle con entradas
  PATCH  /rate-cards/{id}                  — actualizar tabla
  DELETE /rate-cards/{id}                  — eliminar
  POST   /rate-cards/{id}/entries          — añadir entrada (rol+tarifa)
  PATCH  /rate-cards/{id}/entries/{eid}    — actualizar entrada
  DELETE /rate-cards/{id}/entries/{eid}    — eliminar entrada
  POST   /rate-cards/{id}/overrides        — añadir override cliente/proyecto
  DELETE /rate-cards/{id}/overrides/{oid}  — eliminar override
  GET    /rate-cards/effective             — tarifa efectiva para rol+cliente+fecha
  POST   /rate-cards/{id}/duplicate        — duplicar tabla con escalado anual
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User

router = APIRouter(prefix="/rate-cards", tags=["rate-cards"])


# ── Schemas ────────────────────────────────────────────────────────────────────
class RateTableIn(BaseModel):
    name:        str
    description: Optional[str] = None
    applies_to:  str = "role"     # role | department | client
    is_default:  bool = False

class RateEntryIn(BaseModel):
    label:         str
    cost_rate:     Optional[float] = None
    billing_rate:  Optional[float] = None
    escalation_pct: float = 0.0
    valid_from:    Optional[str] = None
    valid_to:      Optional[str] = None
    notes:         Optional[str] = None

class RateOverrideIn(BaseModel):
    client_id:    Optional[str] = None
    project_id:   Optional[str] = None
    role_label:   str
    billing_rate: float
    valid_from:   Optional[str] = None
    valid_to:     Optional[str] = None
    notes:        Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────
def _entry_out(e) -> dict:
    return {
        "id": e.id, "label": e.label,
        "cost_rate": e.cost_rate, "billing_rate": e.billing_rate,
        "escalation_pct": e.escalation_pct or 0.0,
        "valid_from": e.valid_from, "valid_to": e.valid_to,
        "notes": e.notes,
    }

def _override_out(o) -> dict:
    return {
        "id": o.id, "client_id": o.client_id, "project_id": o.project_id,
        "role_label": o.role_label, "billing_rate": o.billing_rate,
        "valid_from": o.valid_from, "valid_to": o.valid_to, "notes": o.notes,
    }

def _table_out(t, include_entries=False) -> dict:
    d = {
        "id": t.id, "name": t.name, "description": t.description,
        "applies_to": t.applies_to, "is_default": t.is_default,
        "is_active": t.is_active,
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    }
    if include_entries:
        d["entries"]   = [_entry_out(e) for e in (t.entries or [])]
        d["overrides"] = [_override_out(o) for o in getattr(t, "overrides", [])]
    else:
        d["entry_count"] = len(t.entries or [])
    return d


# ── CRUD Tablas ────────────────────────────────────────────────────────────────
@router.get("", summary="Listar tablas de tarifas")
def list_rate_tables(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.advanced_config import RateTable
    q = db.query(RateTable)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    tables = q.order_by(RateTable.is_default.desc(), RateTable.name).all()
    return [_table_out(t) for t in tables]


@router.post("", summary="Crear tabla de tarifas")
def create_rate_table(
    payload: RateTableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable
    import uuid
    # Si se marca como default, desmarcar las demás
    if payload.is_default:
        q = db.query(RateTable)
        if not current_user.is_superadmin and current_user.organization_id:
            q = q.filter(RateTable.organization_id == current_user.organization_id)
        q.update({"is_default": False})

    t = RateTable(id=str(uuid.uuid4()), organization_id=current_user.organization_id, **payload.model_dump())
    db.add(t); db.commit(); db.refresh(t)
    return _table_out(t, include_entries=True)


@router.get("/effective", summary="Tarifa efectiva para un rol en un cliente/proyecto y fecha")
def get_effective_rate(
    role_label:  str            = Query(...),
    client_id:   Optional[str]  = Query(None),
    project_id:  Optional[str]  = Query(None),
    as_of:       Optional[str]  = Query(None),   # YYYY-MM-DD, default hoy
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Jerarquía de tarifas:
      1. Override específico de proyecto
      2. Override específico de cliente
      3. Entrada en tabla asignada al proyecto
      4. Entrada en tabla asignada al cliente
      5. Entrada en tabla por defecto
    """
    from app.models.advanced_config import RateTable, RateOverride

    today = as_of or str(date.today())

    def _date_valid(valid_from, valid_to):
        if valid_from and today < valid_from: return False
        if valid_to   and today > valid_to:   return False
        return True

    # 1 & 2: Buscar overrides
    for scope_id, scope_col in [(project_id, "project_id"), (client_id, "client_id")]:
        if not scope_id: continue
        overrides = db.query(RateOverride).filter(
            getattr(RateOverride, scope_col) == scope_id,
            RateOverride.role_label == role_label,
        ).all()
        for o in overrides:
            if _date_valid(o.valid_from, o.valid_to):
                return {"billing_rate": o.billing_rate, "source": f"override_{scope_col}",
                        "role_label": role_label, "override_id": o.id}

    # 3 & 4 & 5: Buscar en tablas de tarifas
    # Prioridad: tabla asociada a proyecto > cliente > default
    q = db.query(RateTable).filter(RateTable.is_active == True)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    tables = q.all()

    # Ordenar: default al final
    tables_sorted = sorted(tables, key=lambda t: (
        0 if (project_id and t.applies_to == "client") else
        1 if (client_id  and t.applies_to == "client") else
        2 if t.is_default else 3
    ))

    for table in tables_sorted:
        for entry in (table.entries or []):
            if entry.label.lower() == role_label.lower():
                if _date_valid(entry.valid_from, entry.valid_to):
                    # Aplicar escalado anual si valid_from es de otro año
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


@router.get("/{table_id}", summary="Detalle de tabla con entradas")
def get_rate_table(
    table_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.advanced_config import RateTable
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    t = q.first()
    if not t: raise HTTPException(404)
    return _table_out(t, include_entries=True)


@router.patch("/{table_id}", summary="Actualizar tabla")
def update_rate_table(
    table_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    t = q.first()
    if not t: raise HTTPException(404)
    allowed = ["name", "description", "applies_to", "is_default", "is_active"]
    if payload.get("is_default"):
        q2 = db.query(RateTable).filter(RateTable.id != table_id)
        if not current_user.is_superadmin and current_user.organization_id:
            q2 = q2.filter(RateTable.organization_id == current_user.organization_id)
        q2.update({"is_default": False})
    for k, v in payload.items():
        if k in allowed: setattr(t, k, v)
    db.commit()
    return _table_out(t, include_entries=True)


@router.delete("/{table_id}", summary="Eliminar tabla")
def delete_rate_table(
    table_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    t = q.first()
    if not t: raise HTTPException(404)
    db.delete(t); db.commit()
    return {"ok": True}


@router.post("/{table_id}/duplicate", summary="Duplicar tabla con escalado anual opcional")
def duplicate_rate_table(
    table_id: str,
    escalation_pct: float = Body(0.0, embed=True),
    new_name: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable, RateEntry
    import uuid
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    src = q.first()
    if not src: raise HTTPException(404)

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
            id=str(uuid.uuid4()), table_id=new_table.id,
            label=e.label, billing_rate=new_rate, cost_rate=new_cost,
            escalation_pct=escalation_pct,
            valid_from=str(date.today()),
        ))

    db.commit(); db.refresh(new_table)
    return _table_out(new_table, include_entries=True)


# ── CRUD Entradas ──────────────────────────────────────────────────────────────
@router.post("/{table_id}/entries", summary="Añadir entrada de tarifa")
def add_entry(
    table_id: str,
    payload: RateEntryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable, RateEntry
    import uuid
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    t = q.first()
    if not t: raise HTTPException(404)
    e = RateEntry(id=str(uuid.uuid4()), table_id=table_id, **payload.model_dump())
    db.add(e); db.commit(); db.refresh(e)
    return _entry_out(e)


@router.patch("/{table_id}/entries/{entry_id}", summary="Actualizar entrada")
def update_entry(
    table_id: str, entry_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateEntry, RateTable
    tq = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        tq = tq.filter(RateTable.organization_id == current_user.organization_id)
    if not tq.first():
        raise HTTPException(404)
    e = db.query(RateEntry).filter(RateEntry.id == entry_id, RateEntry.table_id == table_id).first()
    if not e: raise HTTPException(404)
    allowed = ["label", "cost_rate", "billing_rate", "escalation_pct", "valid_from", "valid_to", "notes"]
    for k, v in payload.items():
        if k in allowed: setattr(e, k, v)
    db.commit()
    return _entry_out(e)


@router.delete("/{table_id}/entries/{entry_id}", summary="Eliminar entrada")
def delete_entry(
    table_id: str, entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateEntry, RateTable
    tq = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        tq = tq.filter(RateTable.organization_id == current_user.organization_id)
    if not tq.first():
        raise HTTPException(404)
    e = db.query(RateEntry).filter(RateEntry.id == entry_id, RateEntry.table_id == table_id).first()
    if not e: raise HTTPException(404)
    db.delete(e); db.commit()
    return {"ok": True}


# ── Overrides ──────────────────────────────────────────────────────────────────
@router.post("/{table_id}/overrides", summary="Añadir override de tarifa para cliente/proyecto")
def add_override(
    table_id: str,
    payload: RateOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateTable, RateOverride
    import uuid
    q = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = q.filter(RateTable.organization_id == current_user.organization_id)
    t = q.first()
    if not t: raise HTTPException(404)
    if not payload.client_id and not payload.project_id:
        raise HTTPException(400, "Debe especificar client_id o project_id")
    o = RateOverride(id=str(uuid.uuid4()), table_id=table_id, **payload.model_dump())
    db.add(o); db.commit(); db.refresh(o)
    return _override_out(o)


@router.delete("/{table_id}/overrides/{override_id}", summary="Eliminar override")
def delete_override(
    table_id: str, override_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.advanced_config import RateOverride, RateTable
    tq = db.query(RateTable).filter(RateTable.id == table_id)
    if not current_user.is_superadmin and current_user.organization_id:
        tq = tq.filter(RateTable.organization_id == current_user.organization_id)
    if not tq.first():
        raise HTTPException(404)
    o = db.query(RateOverride).filter(
        RateOverride.id == override_id, RateOverride.table_id == table_id
    ).first()
    if not o: raise HTTPException(404)
    db.delete(o); db.commit()
    return {"ok": True}
