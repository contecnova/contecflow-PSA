"""Service Desk — Asset Management REST API.

Hardware lifecycle, software licenses, and asset audit endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse
from app.services.service_desk.asset_service import (
    asset_stats_payload,
    assign_asset_record,
    calculate_depreciation,
    create_asset_record,
    get_asset_detail_payload,
    get_expiring_soon,
    get_lifecycle_dashboard,
    list_assets_payload,
    list_assets_by_ci_payload,
    retire_asset_record,
    update_asset_record,
    create_refresh_ticket,
    asset_out,
    get_asset_or_404,
)

router = APIRouter(prefix="/assets", tags=["Asset Management"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class AssetCreateIn(BaseModel):
    name: str
    asset_type: str
    status: Optional[str] = "in_stock"
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    license_key: Optional[str] = None
    license_seats: Optional[int] = None
    license_used: Optional[int] = 0
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    eol_date: Optional[str] = None
    lease_expiry: Optional[str] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    currency: Optional[str] = "EUR"
    po_number: Optional[str] = None
    vendor: Optional[str] = None
    vendor_contract: Optional[str] = None
    location: Optional[str] = None
    assigned_user_id: Optional[str] = None
    department: Optional[str] = None
    ci_id: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    managed_by_user_id: Optional[str] = None
    depreciation_type: Optional[str] = None
    depreciation_rate: Optional[float] = None
    next_maintenance_date: Optional[str] = None
    maintenance_contract: Optional[str] = None


class AssetUpdateIn(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    license_key: Optional[str] = None
    license_seats: Optional[int] = None
    license_used: Optional[int] = None
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    eol_date: Optional[str] = None
    lease_expiry: Optional[str] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    currency: Optional[str] = None
    po_number: Optional[str] = None
    vendor: Optional[str] = None
    vendor_contract: Optional[str] = None
    location: Optional[str] = None
    assigned_user_id: Optional[str] = None
    department: Optional[str] = None
    ci_id: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    managed_by_user_id: Optional[str] = None
    depreciation_type: Optional[str] = None
    depreciation_rate: Optional[float] = None
    next_maintenance_date: Optional[str] = None
    maintenance_contract: Optional[str] = None


class AssetAssignIn(BaseModel):
    user_id: str
    notes: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", summary="Listar activos con filtros y paginación")
def list_assets(
    asset_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assigned_user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=list_assets_payload(db, asset_type, status, assigned_user_id, search, page, page_size))


@router.get("/by-ci/{ci_id}", summary="Listar activos vinculados a un CI")
def list_assets_by_ci(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return APIResponse.ok(data=list_assets_by_ci_payload(db, ci_id))


@router.post("", summary="Crear nuevo activo")
def create_asset(
    payload: AssetCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = create_asset_record(db, payload)
    db.commit()
    db.refresh(asset)
    return APIResponse.ok(data=asset_out(asset))


@router.get("/stats", summary="Estadísticas de activos por tipo y estado")
def get_asset_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=asset_stats_payload(db))


@router.get("/lifecycle", summary="Dashboard de ciclo de vida: expiración, depreciación, licencias")
def get_lifecycle(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_lifecycle_dashboard(db))


@router.get("/expiring", summary="Activos con warranty/EOL/lease próximo a vencer")
def get_expiring(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data={"items": get_expiring_soon(db, days=days), "days_window": days})


@router.get("/license-audit", summary="Auditoría de licencias: seats vs uso")
def get_license_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Asset, AssetType
    assets = (
        db.query(Asset)
        .filter(
            Asset.asset_type.in_([AssetType.software, AssetType.license]),
            Asset.license_seats.isnot(None),
            Asset.license_seats > 0,
        )
        .all()
    )
    items = []
    for a in assets:
        seats = a.license_seats or 0
        used = a.license_used or 0
        utilization = round(used / seats * 100, 1) if seats > 0 else 0
        items.append({
            "asset_id": a.id,
            "code": a.code,
            "name": a.name,
            "vendor": a.vendor,
            "license_seats": seats,
            "license_used": used,
            "utilization_pct": utilization,
            "status": "over_licensed" if utilization < 40 else ("under_licensed" if used > seats else "ok"),
            "license_key": a.license_key,
            "warranty_expiry": a.warranty_expiry,
        })
    items.sort(key=lambda x: x["utilization_pct"])
    total_seats = sum(i["license_seats"] for i in items)
    total_used = sum(i["license_used"] for i in items)
    return APIResponse.ok(data={
        "items": items,
        "summary": {
            "total_licenses": len(items),
            "total_seats": total_seats,
            "total_used": total_used,
            "overall_utilization_pct": round(total_used / total_seats * 100, 1) if total_seats else 0,
            "over_licensed_count": sum(1 for i in items if i["status"] == "over_licensed"),
            "under_licensed_count": sum(1 for i in items if i["status"] == "under_licensed"),
        },
    })


@router.get("/software-audit", summary="Auditoría de software instalado vs licenciado")
def get_software_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a software compliance summary comparing deployed software against licenses."""
    from app.models.service_desk import Asset, AssetType, AssetStatus
    all_assets = db.query(Asset).all()

    # Group software/license assets
    licensed = {
        a.name.lower(): a
        for a in all_assets
        if a.asset_type in (AssetType.software, AssetType.license)
    }
    # Count deployed hardware assets per software group
    deployed_sw = {}
    for a in all_assets:
        if a.asset_type == AssetType.hardware and a.status == AssetStatus.deployed:
            # Tags may contain installed software hints
            if a.tags:
                for tag in a.tags.split(","):
                    key = tag.strip().lower()
                    if key:
                        deployed_sw[key] = deployed_sw.get(key, 0) + 1

    rows = []
    for name, asset in licensed.items():
        seats = asset.license_seats or 0
        rows.append({
            "software": asset.name,
            "vendor": asset.vendor,
            "license_seats": seats,
            "deployed_count": deployed_sw.get(name, asset.license_used or 0),
            "license_key_present": bool(asset.license_key),
            "warranty_expiry": asset.warranty_expiry,
            "asset_id": asset.id,
        })

    return APIResponse.ok(data={"audit_rows": rows, "total": len(rows)})


@router.get("/{asset_id}", summary="Detalle de un activo con historial")
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_asset_detail_payload(db, asset_id))


@router.put("/{asset_id}", summary="Actualizar activo con historial de cambios")
def update_asset(
    asset_id: str,
    payload: AssetUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = update_asset_record(db, asset_id, payload, changed_by=current_user.id)
    db.commit()
    db.refresh(asset)
    return APIResponse.ok(data=asset_out(asset))


@router.delete("/{asset_id}", summary="Retirar activo (marca como retired)")
def retire_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "sd_asset", asset_id, action="delete")
    asset = retire_asset_record(db, asset_id, changed_by=current_user.id)
    db.commit()
    return APIResponse.ok(data={"status": "retired", "asset_id": asset_id, "code": asset.code})


@router.post("/{asset_id}/assign", summary="Asignar activo a un usuario")
def assign_asset(
    asset_id: str,
    payload: AssetAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_name = assign_asset_record(
        db, asset_id, payload.user_id, changed_by=current_user.id, notes=payload.notes
    )
    db.commit()
    return APIResponse.ok(data={"status": "assigned", "asset_id": asset_id, "assigned_to": user_name})


@router.get("/{asset_id}/depreciation", summary="Calcular depreciación actual del activo")
def get_depreciation(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = get_asset_or_404(db, asset_id)
    estimated_value = calculate_depreciation(asset)
    return APIResponse.ok(data={
        "asset_id": asset_id,
        "code": asset.code,
        "purchase_price": asset.purchase_price,
        "purchase_date": asset.purchase_date,
        "depreciation_type": asset.depreciation_type,
        "depreciation_rate": asset.depreciation_rate,
        "estimated_current_value": estimated_value,
    })


@router.post("/{asset_id}/refresh-ticket", summary="Crear ticket de renovación/reemplazo del activo")
def create_asset_refresh_ticket(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = create_refresh_ticket(db, asset_id, acting_user_id=current_user.id)
    db.commit()
    return APIResponse.ok(data=result)
