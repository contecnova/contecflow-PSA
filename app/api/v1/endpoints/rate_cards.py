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
from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse
from app.models.user import User
import app.services.rate_card_service as _svc

router = APIRouter(tags=["rate-cards"])


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



# ── Helpers (delegated to service) ────────────────────────────────────────────
_entry_out = _svc.serialize_rate_entry
_override_out = _svc.serialize_rate_override
_table_out = _svc.serialize_rate_table


# ── CRUD Tablas ────────────────────────────────────────────────────────────────
@router.get("", response_model=APIListResponse[dict], summary="Listar tablas de tarifas")
def list_rate_tables(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tables = _svc.list_rate_tables(db, current_user.organization_id, current_user.is_superadmin)
    items = [_table_out(t) for t in tables]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("", summary="Crear tabla de tarifas")
def create_rate_table(
    payload: RateTableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    t = _svc.create_rate_table(db, payload.model_dump(), current_user.organization_id, current_user.is_superadmin)
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
    return _svc.get_effective_rate(
        db, role_label, client_id, project_id, as_of,
        current_user.organization_id, current_user.is_superadmin,
    )


@router.get("/{table_id}", summary="Detalle de tabla con entradas")
def get_rate_table(
    table_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = _svc.get_rate_table_or_404(db, table_id, current_user.organization_id, current_user.is_superadmin)
    return _table_out(t, include_entries=True)


@router.patch("/{table_id}", summary="Actualizar tabla")
def update_rate_table(
    table_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    t = _svc.update_rate_table(db, table_id, payload, current_user.organization_id, current_user.is_superadmin)
    return _table_out(t, include_entries=True)


@router.delete("/{table_id}", summary="Eliminar tabla")
def delete_rate_table(
    table_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "rate_table", table_id, action="delete")
    _svc.delete_rate_table(db, table_id, current_user.organization_id, current_user.is_superadmin)
    return {"ok": True, "message": "Tabla eliminada correctamente"}


@router.post("/{table_id}/duplicate", summary="Duplicar tabla con escalado anual opcional")
def duplicate_rate_table(
    table_id: str,
    escalation_pct: float = Body(0.0, embed=True),
    new_name: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    new_table = _svc.duplicate_rate_table(
        db, table_id, escalation_pct, new_name,
        current_user.organization_id, current_user.is_superadmin,
    )
    return _table_out(new_table, include_entries=True)


# ── CRUD Entradas ──────────────────────────────────────────────────────────────
@router.post("/{table_id}/entries", summary="Añadir entrada de tarifa")
def add_entry(
    table_id: str,
    payload: RateEntryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    e = _svc.add_entry(db, table_id, payload.model_dump(), current_user.organization_id, current_user.is_superadmin)
    return _entry_out(e)


@router.patch("/{table_id}/entries/{entry_id}", summary="Actualizar entrada")
def update_entry(
    table_id: str, entry_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    e = _svc.update_entry(db, table_id, entry_id, payload, current_user.organization_id, current_user.is_superadmin)
    return _entry_out(e)


@router.delete("/{table_id}/entries/{entry_id}", summary="Eliminar entrada")
def delete_entry(
    table_id: str, entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "rate_entry", entry_id, action="delete")
    _svc.delete_entry(db, table_id, entry_id, current_user.organization_id, current_user.is_superadmin)
    return {"ok": True, "message": "Entrada eliminada correctamente"}


# ── Overrides ──────────────────────────────────────────────────────────────────
@router.post("/{table_id}/overrides", summary="Añadir override de tarifa para cliente/proyecto")
def add_override(
    table_id: str,
    payload: RateOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    o = _svc.add_override(db, table_id, payload.model_dump(), current_user.organization_id, current_user.is_superadmin)
    return _override_out(o)


@router.delete("/{table_id}/overrides/{override_id}", summary="Eliminar override")
def delete_override(
    table_id: str, override_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "rate_override", override_id, action="delete")
    _svc.delete_override(db, table_id, override_id, current_user.organization_id, current_user.is_superadmin)
    return {"ok": True, "message": "Override eliminado correctamente"}
