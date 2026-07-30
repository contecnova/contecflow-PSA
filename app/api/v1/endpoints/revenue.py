"""
revenue.py — ASC 606 / IFRS 15 Revenue Recognition endpoints.

Prefix: /revenue-recognition  (set in delivery.py)

Routes:
  Contracts:
    GET    /contracts
    POST   /contracts
    GET    /contracts/{id}
    PATCH  /contracts/{id}
    DELETE /contracts/{id}

  Obligations (per contract):
    GET    /contracts/{id}/obligations
    POST   /contracts/{id}/obligations
    PATCH  /obligations/{id}
    DELETE /obligations/{id}

  Entries:
    GET    /entries
    POST   /entries/{id}/reverse

  Period Close:
    GET    /period-closes
    POST   /period-closes
    DELETE /period-closes/{year}/{month}

  Recognition:
    POST   /run-monthly          — manual trigger (normally run by Celery)

  Dashboard:
    GET    /dashboard
"""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.services import revenue_service as svc

router = APIRouter(tags=["Revenue Recognition"])


# ── Contracts ──────────────────────────────────────────────────────────────────

@router.get("/contracts", summary="Listar contratos ASC 606")
def list_contracts(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contracts = svc.list_contracts(db, project_id=project_id)
    return APIListResponse.ok(items=[svc._serialize_contract(c) for c in contracts])


@router.post("/contracts", summary="Crear contrato ASC 606")
def create_contract(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = svc.create_contract(db, organization_id=current_user.organization_id, data=payload)
    return APIResponse.ok(data=svc._serialize_contract(c))


@router.get("/contracts/{contract_id}", summary="Detalle de contrato ASC 606")
def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = svc.get_contract(db, contract_id)
    return APIResponse.ok(data=svc._serialize_contract(c))


@router.patch("/contracts/{contract_id}", summary="Actualizar contrato ASC 606")
def update_contract(
    contract_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = svc.update_contract(db, contract_id, payload)
    return APIResponse.ok(data=svc._serialize_contract(c))


@router.delete("/contracts/{contract_id}", summary="Eliminar contrato ASC 606")
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "revenue_contract", contract_id, action="delete")
    svc.delete_contract(db, contract_id)
    return APIResponse.ok(data={"ok": True})


# ── Obligations ────────────────────────────────────────────────────────────────

@router.get("/contracts/{contract_id}/obligations", summary="Listar obligaciones de desempeño")
def list_obligations(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obs = svc.list_obligations(db, contract_id)
    return APIListResponse.ok(items=[svc._serialize_obligation(ob) for ob in obs])


@router.post("/contracts/{contract_id}/obligations", summary="Crear obligación de desempeño")
def create_obligation(
    contract_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ob = svc.create_obligation(db, contract_id, payload)
    return APIResponse.ok(data=svc._serialize_obligation(ob))


@router.patch("/obligations/{obligation_id}", summary="Actualizar obligación de desempeño")
def update_obligation(
    obligation_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ob = svc.update_obligation(db, obligation_id, payload)
    return APIResponse.ok(data=svc._serialize_obligation(ob))


@router.delete("/obligations/{obligation_id}", summary="Eliminar obligación de desempeño")
def delete_obligation(
    obligation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "revenue_obligation", obligation_id, action="delete")
    svc.delete_obligation(db, obligation_id)
    return APIResponse.ok(data={"ok": True})


# ── Entries ────────────────────────────────────────────────────────────────────

@router.get("/entries", summary="Listar entradas contables de reconocimiento")
def list_entries(
    contract_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entries = svc.list_entries(db, contract_id=contract_id, year=year, month=month)
    return APIListResponse.ok(items=[svc._serialize_entry(e) for e in entries])


@router.post("/entries/{entry_id}/reverse", summary="Revertir entrada contable")
def reverse_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rev = svc.reverse_entry(db, entry_id, current_user.id)
    return APIResponse.ok(data=svc._serialize_entry(rev))


# ── Period Close ───────────────────────────────────────────────────────────────

@router.get("/period-closes", summary="Listar cierres contables")
def list_period_closes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    closes = svc.list_period_closes(db)
    return APIListResponse.ok(items=[svc._serialize_period_close(pc) for pc in closes])


@router.post("/period-closes", summary="Cerrar período contable")
def close_period(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    year = payload.get("year")
    month = payload.get("month")
    notes = payload.get("notes")
    if not year or not month:
        from fastapi import HTTPException
        raise HTTPException(400, "Se requieren year y month")
    pc = svc.close_period(db, current_user.organization_id, int(year), int(month), current_user.id, notes)
    return APIResponse.ok(data=svc._serialize_period_close(pc))


@router.delete("/period-closes/{year}/{month}", summary="Reabrir período contable")
def reopen_period(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "revenue_period_close", f"{year}-{month}", action="delete")
    svc.reopen_period(db, current_user.organization_id, year, month)
    return APIResponse.ok(data={"ok": True})


# ── Manual recognition trigger ─────────────────────────────────────────────────

@router.post("/run-monthly", summary="Ejecutar reconocimiento mensual manualmente")
def run_monthly(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from datetime import date
    today = date.today()
    year  = int(payload.get("year",  today.year))
    month = int(payload.get("month", today.month))
    result = svc.run_monthly_recognition(db, year, month, user_id=current_user.id)
    return APIResponse.ok(data=result)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", summary="Dashboard ASC 606 — reconocido y diferido por mes")
def asc606_dashboard(
    year: Optional[int] = None,
    months: int = 12,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import date
    y = year or date.today().year
    return APIResponse.ok(data=svc.get_asc606_dashboard(db, y, months))
