"""
ALM — Asset & License Management endpoints
Enterprise-grade gestión de proveedores, contratos, licencias y activos.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.alm import ALMAsset
from app.services.alm_ciclo_de_vida import (
    abrir_ticket_de_renovacion, activos_del_ci, historial, proximos_vencimientos,
)
from app.services.alm_service import (
    get_alm_dashboard,
    list_vendors_records, create_vendor_record, get_vendor_record,
    update_vendor_record, delete_vendor_record,
    list_contracts_records, create_contract_record, get_contract_record,
    update_contract_record, delete_contract_record,
    list_licenses_records, create_license_record, get_license_record,
    update_license_record, delete_license_record,
    assign_license_record, revoke_assignment_record,
    list_assets_records, create_asset_record, get_asset_record, serialize_asset,
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
    return APIResponse.ok(data=get_alm_dashboard(db))


# ── Vendors ───────────────────────────────────────────────────────────────────
@router.get("/vendors")
def list_vendors(q: Optional[str] = None, category: Optional[str] = None,
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=list_vendors_records(q, category, db))

@router.post("/vendors")
def create_vendor(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_vendor_record(data, db))

@router.get("/vendors/{vid}")
def get_vendor(vid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=get_vendor_record(vid, db))

@router.patch("/vendors/{vid}")
def update_vendor(vid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_vendor_record(vid, data, db))

@router.delete("/vendors/{vid}")
def delete_vendor(vid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_vendor", vid, action="delete")
    return APIResponse.ok(data=delete_vendor_record(vid, db))


# ── Contracts ─────────────────────────────────────────────────────────────────
@router.get("/contracts")
def list_contracts(vendor_id: Optional[str] = None, status: Optional[str] = None,
                   expiring_days: Optional[int] = None,
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=list_contracts_records(vendor_id, status, expiring_days, db))

@router.post("/contracts")
def create_contract(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=create_contract_record(data, cu.id, db))

@router.get("/contracts/{cid}")
def get_contract(cid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=get_contract_record(cid, db))

@router.patch("/contracts/{cid}")
def update_contract(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_contract_record(cid, data, db))

@router.delete("/contracts/{cid}")
def delete_contract(cid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_contract", cid, action="delete")
    return APIResponse.ok(data=delete_contract_record(cid, db))


# ── Licenses ──────────────────────────────────────────────────────────────────
@router.get("/licenses")
def list_licenses(vendor_id: Optional[str] = None, status: Optional[str] = None,
                  expiring_days: Optional[int] = None, compliance_only: bool = False,
                  db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=list_licenses_records(vendor_id, status, expiring_days, compliance_only, db))

@router.post("/licenses")
def create_license(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_license_record(data, db))

@router.get("/licenses/{lid}")
def get_license(lid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=get_license_record(lid, db))

@router.patch("/licenses/{lid}")
def update_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_license_record(lid, data, db))

@router.delete("/licenses/{lid}")
def delete_license(lid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_license", lid, action="delete")
    return APIResponse.ok(data=delete_license_record(lid, db))


# ── License Assignments ───────────────────────────────────────────────────────
@router.post("/licenses/{lid}/assign")
def assign_license(lid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(get_current_user),
    _rol = Depends(require_any_manager),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=assign_license_record(lid, data, cu.id, db))

@router.delete("/licenses/{lid}/assignments/{aid}")
def revoke_assignment(
    lid: str,
    aid: str,
    db: Session = Depends(get_db),
    cu=Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada. Crear la licencia (`POST /alm/licenses`)
    # ya exige gestor, asi que revocar una asignacion con el mismo
    # rol no atrapa a nadie: nadie por debajo pudo crearla.
    _=Depends(require_any_manager),
):
    enforce_abac(db, cu, "alm_license_assignment", aid, action="delete")
    return APIResponse.ok(data=revoke_assignment_record(lid, aid, db))


# ── Assets ────────────────────────────────────────────────────────────────────
# Las rutas fijas van antes de `/assets/{aid}` para que no las capture.

@router.get("/assets/expiring", summary="Fechas de activos que vencen en los próximos días")
def list_expiring_assets(days: int = Query(90, ge=0, le=730), db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    return APIListResponse.ok(items=proximos_vencimientos(db, days))

@router.get("/assets/by-ci/{ci_id}", summary="Activos enlazados a un CI")
def list_assets_by_ci(ci_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=[serialize_asset(a) for a in activos_del_ci(db, ci_id)])

@router.get("/assets")
def list_assets(type: Optional[str] = None, status: Optional[str] = None,
                assigned_to: Optional[str] = None, q: Optional[str] = None,
                db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=list_assets_records(type, status, assigned_to, q, db))

@router.post("/assets")
def create_asset(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=create_asset_record(data, db, cu))

@router.get("/assets/{aid}")
def get_asset(aid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=get_asset_record(aid, db))

@router.patch("/assets/{aid}")
def update_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=update_asset_record(aid, data, db, cu))

@router.delete("/assets/{aid}")
def delete_asset(aid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_asset", aid, action="delete")
    return APIResponse.ok(data=delete_asset_record(aid, db, cu))

@router.post("/assets/{aid}/assign")
def assign_asset(aid: str, data: dict = Body(...), db: Session = Depends(get_db),
    cu = Depends(require_any_manager),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    return APIResponse.ok(data=assign_asset_record(aid, data, db, cu))

@router.get("/assets/{aid}/history", summary="Historial de cambios del activo")
def get_asset_history(aid: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _activo_o_404(db, aid)
    return APIListResponse.ok(items=historial(db, aid))

@router.post("/assets/{aid}/refresh-ticket", summary="Abrir (o recuperar) el ticket de renovación del activo")
def open_refresh_ticket(aid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    datos = abrir_ticket_de_renovacion(db, _activo_o_404(db, aid), cu.id)
    db.commit()
    return APIResponse.ok(data=datos)


def _activo_o_404(db: Session, aid: str) -> ALMAsset:
    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active.is_(True)).first()
    if a is None:
        raise HTTPException(404, "Activo no encontrado")
    return a


# ── Cost Centers ──────────────────────────────────────────────────────────────
@router.get("/cost-centers")
def list_cost_centers(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIListResponse.ok(items=list_cost_centers_records(db))

@router.post("/cost-centers")
def create_cost_center(data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=create_cost_center_record(data, db))

@router.patch("/cost-centers/{cid}")
def update_cost_center(cid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(require_any_manager)):
    return APIResponse.ok(data=update_cost_center_record(cid, data, db))

@router.delete("/cost-centers/{cid}")
def delete_cost_center(cid: str, db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    enforce_abac(db, cu, "alm_cost_center", cid, action="delete")
    return APIResponse.ok(data=delete_cost_center_record(cid, db))


# ── Software Installs ─────────────────────────────────────────────────────────
@router.post("/assets/{aid}/installs")
def add_install(aid: str, data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(require_any_manager)):
    return APIResponse.ok(data=add_install_record(aid, data, cu.id, db))

@router.delete("/assets/{aid}/installs/{iid}")
def remove_install(
    aid: str,
    iid: str,
    db: Session = Depends(get_db),
    cu=Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada. `POST /alm/assets/{aid}/installs` ya exige
    # gestor; borrar la instalacion no puede pedir menos que crearla.
    _=Depends(require_any_manager),
):
    enforce_abac(db, cu, "alm_software_install", iid, action="delete")
    return APIResponse.ok(data=remove_install_record(aid, iid, db))


# ── Compliance report ─────────────────────────────────────────────────────────
@router.get("/compliance")
def compliance_report(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return APIResponse.ok(data=get_compliance_report(db))
