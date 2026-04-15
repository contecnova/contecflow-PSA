"""
ALM — Asset & License Management endpoints
Enterprise-grade gestión de proveedores, contratos, licencias y activos.
"""
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.services.alm_service import (
    get_alm_dashboard,
    list_vendors_records, create_vendor_record, get_vendor_record,
    update_vendor_record, delete_vendor_record,
    list_contracts_records, create_contract_record, get_contract_record,
    update_contract_record, delete_contract_record,
    list_licenses_records, create_license_record, get_license_record,
    update_license_record, delete_license_record,
    assign_license_record, revoke_assignment_record,
    list_assets_records, create_asset_record, get_asset_record,
    update_asset_record, delete_asset_record, assign_asset_record,
    list_cost_centers_records, create_cost_center_record,
    update_cost_center_record, delete_cost_center_record,
    add_install_record, remove_install_record,
    get_compliance_report,
)

router = APIRouter()


# ── Dashboard / KPIs ──────────────────────────────────────────────────────────
@router.get("/dashboard", summary="KPIs del módulo ALM")
def alm_dashboard(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_alm_dashboard(db)


# ── Vendors ───────────────────────────────────────────────────────────────────
@router.get("/vendors")
def list_vendors(q: Optional[str] = None, category: Optional[str] = None,
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    return list_vendors_records(q, category, db)

@router.post("/vendors")
def create_vendor(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return create_vendor_record(data, db)

@router.get("/vendors/{vid}")
def get_vendor(vid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_vendor_record(vid, db)

@router.patch("/vendors/{vid}")
def update_vendor(vid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return update_vendor_record(vid, data, db)

@router.delete("/vendors/{vid}")
def delete_vendor(vid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return delete_vendor_record(vid, db)


# ── Contracts ─────────────────────────────────────────────────────────────────
@router.get("/contracts")
def list_contracts(vendor_id: Optional[str] = None, status: Optional[str] = None,
                   expiring_days: Optional[int] = None,
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    return list_contracts_records(vendor_id, status, expiring_days, db)

@router.post("/contracts")
def create_contract(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return create_contract_record(data, cu.id, db)

@router.get("/contracts/{cid}")
def get_contract(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_contract_record(cid, db)

@router.patch("/contracts/{cid}")
def update_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return update_contract_record(cid, data, db)

@router.delete("/contracts/{cid}")
def delete_contract(cid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return delete_contract_record(cid, db)


# ── Licenses ──────────────────────────────────────────────────────────────────
@router.get("/licenses")
def list_licenses(vendor_id: Optional[str] = None, status: Optional[str] = None,
                  expiring_days: Optional[int] = None, compliance_only: bool = False,
                  db: Session = Depends(get_db), _=Depends(get_current_user)):
    return list_licenses_records(vendor_id, status, expiring_days, compliance_only, db)

@router.post("/licenses")
def create_license(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return create_license_record(data, db)

@router.get("/licenses/{lid}")
def get_license(lid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_license_record(lid, db)

@router.patch("/licenses/{lid}")
def update_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return update_license_record(lid, data, db)

@router.delete("/licenses/{lid}")
def delete_license(lid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return delete_license_record(lid, db)


# ── License Assignments ───────────────────────────────────────────────────────
@router.post("/licenses/{lid}/assign")
def assign_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(get_current_user)):
    return assign_license_record(lid, data, cu.id, db)

@router.delete("/licenses/{lid}/assignments/{aid}")
def revoke_assignment(lid: str, aid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return revoke_assignment_record(lid, aid, db)


# ── Assets ────────────────────────────────────────────────────────────────────
@router.get("/assets")
def list_assets(type: Optional[str] = None, status: Optional[str] = None,
                assigned_to: Optional[str] = None, q: Optional[str] = None,
                db: Session = Depends(get_db), _=Depends(get_current_user)):
    return list_assets_records(type, status, assigned_to, q, db)

@router.post("/assets")
def create_asset(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return create_asset_record(data, db)

@router.get("/assets/{aid}")
def get_asset(aid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_asset_record(aid, db)

@router.patch("/assets/{aid}")
def update_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return update_asset_record(aid, data, db)

@router.delete("/assets/{aid}")
def delete_asset(aid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return delete_asset_record(aid, db)

@router.post("/assets/{aid}/assign")
def assign_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(get_current_user)):
    return assign_asset_record(aid, data, db)


# ── Cost Centers ──────────────────────────────────────────────────────────────
@router.get("/cost-centers")
def list_cost_centers(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return list_cost_centers_records(db)

@router.post("/cost-centers")
def create_cost_center(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return create_cost_center_record(data, db)

@router.patch("/cost-centers/{cid}")
def update_cost_center(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return update_cost_center_record(cid, data, db)

@router.delete("/cost-centers/{cid}")
def delete_cost_center(cid: str, db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return delete_cost_center_record(cid, db)


# ── Software Installs ─────────────────────────────────────────────────────────
@router.post("/assets/{aid}/installs")
def add_install(aid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return add_install_record(aid, data, cu.id, db)

@router.delete("/assets/{aid}/installs/{iid}")
def remove_install(aid: str, iid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return remove_install_record(aid, iid, db)


# ── Compliance report ─────────────────────────────────────────────────────────
@router.get("/compliance")
def compliance_report(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_compliance_report(db)
