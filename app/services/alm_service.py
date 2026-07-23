"""
ALM service — business logic extracted from alm.py endpoint.
Covers: input data cleaning, serialisers for Vendor / Contract / License / Asset,
        linked-client query helpers, and all CRUD record operations.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.models.alm import (
    ALMVendor, ALMContract, ALMLicense, ALMLicenseAssignment,
    ALMAsset, ALMCostCenter, ALMSoftwareInstall,
)

logger = logging.getLogger(__name__)


# ── Input cleaner ─────────────────────────────────────────────────────────────

# Fields that must NEVER be set from client-supplied payloads (mass-assignment
# guard). Tenant isolation (organization_id), identity (id), audit timestamps and
# the soft-delete flag are owned by the server, not the caller.
PROTECTED_FIELDS = frozenset({
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "created_by",
    "is_active",
})


def clean_input(data: dict, model_cls, date_fields=None, int_fields=None, float_fields=None) -> dict:
    """Limpia el dict del frontend: '' → None, tipos correctos, ignora campos sin columna.

    Aplica además una deny-list (PROTECTED_FIELDS) para impedir mass-assignment
    de campos de tenant/identidad/auditoría desde el payload del cliente.
    """

    date_fields  = date_fields  or []
    int_fields   = int_fields   or []
    float_fields = float_fields or []
    out = {}
    for k, v in data.items():
        if k in PROTECTED_FIELDS:
            continue
        if not hasattr(model_cls, k):
            continue
        if v == "" or v is None:
            out[k] = None
            continue
        if k in date_fields:
            try:
                parts = str(v).split("-")
                out[k] = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception:
                logger.debug("ALM clean_input: invalid date field %s=%r → None", k, v, exc_info=True)
                out[k] = None
        elif k in int_fields:
            try:
                out[k] = int(v)
            except Exception:
                logger.debug("ALM clean_input: invalid int field %s=%r → None", k, v, exc_info=True)
                out[k] = None
        elif k in float_fields:
            try:
                out[k] = float(v)
            except Exception:
                logger.debug("ALM clean_input: invalid float field %s=%r → None", k, v, exc_info=True)
                out[k] = None
        else:
            out[k] = v
    return out


# ── Linked-client query helpers ───────────────────────────────────────────────

def get_linked_clients_for_license(license_id, db: Session) -> list:
    """Devuelve los clientes vinculados a una licencia via client_license_links."""
    try:
        from app.models.clients import ClientLicenseLink, Client

        links = db.query(ClientLicenseLink).filter(ClientLicenseLink.license_id == license_id).all()
        result = []
        for ll in links:
            cl = db.query(Client).filter(Client.id == ll.client_id).first()
            if cl:
                result.append({"id": cl.id, "name": cl.name})
        return result
    except Exception:
        logger.warning("Failed to load linked clients for license=%s", license_id, exc_info=True)
        return []


def get_linked_clients_for_contract(contract_id, db: Session) -> list:
    """Devuelve los clientes vinculados a un contrato pipeline via client_contract_links."""
    try:
        from app.models.clients import ClientContractLink, Client

        links = db.query(ClientContractLink).filter(ClientContractLink.contract_id == contract_id).all()
        result = []
        for cl_link in links:
            cl = db.query(Client).filter(Client.id == cl_link.client_id).first()
            if cl:
                result.append({"id": cl.id, "name": cl.name})
        return result
    except Exception:
        logger.warning("Failed to load linked clients for contract=%s", contract_id, exc_info=True)
        return []


# ── Serialisers (Refactored with ModelSerializer base class) ─────────────────

from app.core.serializers import VendorSerializer, ContractSerializer, LicenseSerializer, AssetSerializer


def serialize_vendor(v: ALMVendor) -> dict[str, Any]:
    """Serialize Vendor using base class."""
    return VendorSerializer(v).to_dict()


def serialize_contract(c: ALMContract, db: Optional[Session] = None) -> dict[str, Any]:
    """Serialize Contract using base class. Note: linked_clients not included by base class."""
    result = ContractSerializer(c).to_dict()
    if db:
        result["linked_clients"] = get_linked_clients_for_contract(c.id, db)
    else:
        result["linked_clients"] = []
    return result


def serialize_license(lic: ALMLicense, db: Session) -> dict[str, Any]:
    """Serialize License using base class. Note: linked_clients not included by base class."""
    result = LicenseSerializer(lic).to_dict()
    result["linked_clients"] = get_linked_clients_for_license(lic.id, db)
    return result


def serialize_asset(a: ALMAsset) -> dict[str, Any]:
    """Serialize Asset using base class."""
    return AssetSerializer(a).to_dict()


# ── Dashboard / KPIs ─────────────────────────────────────────────────────────

def get_alm_dashboard(db: Session) -> dict:

    today = date.today()
    in_60 = today + timedelta(days=60)
    in_90 = today + timedelta(days=90)

    total_contracts   = db.query(ALMContract).filter(ALMContract.status == "active", ALMContract.is_active == True).count()
    expiring_soon     = db.query(ALMContract).filter(
        ALMContract.status == "active",
        ALMContract.is_active == True,
        ALMContract.renewal_date.isnot(None),
        ALMContract.renewal_date <= in_60,
    ).count()
    total_licenses    = db.query(ALMLicense).filter(ALMLicense.status != "cancelled", ALMLicense.is_active == True).count()
    expired_licenses  = db.query(ALMLicense).filter(
        ALMLicense.expiry_date < today,
        ALMLicense.status != "cancelled",
        ALMLicense.is_active == True,
    ).count()
    total_assets      = db.query(ALMAsset).filter(ALMAsset.status != "retired", ALMAsset.is_active == True).count()
    assets_in_use     = db.query(ALMAsset).filter(ALMAsset.status == "in_use", ALMAsset.is_active == True).count()
    warranty_expiring = db.query(ALMAsset).filter(
        ALMAsset.warranty_expiry.isnot(None),
        ALMAsset.warranty_expiry <= in_90,
        ALMAsset.warranty_expiry >= today,
        ALMAsset.is_active == True,
    ).count()
    total_vendors     = db.query(ALMVendor).filter(ALMVendor.is_active == True).count()

    annual_cost    = db.query(func.sum(ALMLicense.annual_cost)).scalar() or 0
    contract_cost  = db.query(func.sum(ALMContract.annual_value)).filter(
        ALMContract.status == "active"
        , ALMContract.is_active == True
    ).scalar() or 0

    upcoming = db.query(ALMContract).filter(
        ALMContract.status == "active",
        ALMContract.is_active == True,
        ALMContract.renewal_date.isnot(None),
        ALMContract.renewal_date >= today,
        ALMContract.renewal_date <= in_60,
    ).order_by(ALMContract.renewal_date).limit(5).all()

    return {
        "kpis": {
            "total_contracts": total_contracts,
            "expiring_soon": expiring_soon,
            "total_licenses": total_licenses,
            "expired_licenses": expired_licenses,
            "total_assets": total_assets,
            "assets_in_use": assets_in_use,
            "warranty_expiring_90d": warranty_expiring,
            "total_vendors": total_vendors,
            "annual_license_cost": round(annual_cost, 2),
            "annual_contract_cost": round(contract_cost, 2),
            "total_annual_cost": round(annual_cost + contract_cost, 2),
        },
        "upcoming_renewals": [serialize_contract(c, db) for c in upcoming],
    }


# ── Vendor record operations ──────────────────────────────────────────────────

def list_vendors_records(q: Optional[str], category: Optional[str], db: Session) -> list:

    query = db.query(ALMVendor).filter(ALMVendor.is_active == True)
    if q:
        query = query.filter(ALMVendor.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(ALMVendor.category == category)
    return [serialize_vendor(v) for v in query.order_by(ALMVendor.name).all()]


def create_vendor_record(data: dict, db: Session) -> dict:

    clean = clean_input(data, ALMVendor)
    v = ALMVendor(**clean)
    db.add(v)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def get_vendor_record(vid: str, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise HTTPException(404, "Proveedor no encontrado")
    return serialize_vendor(v)


def update_vendor_record(vid: str, data: dict, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise HTTPException(404)
    clean = clean_input(data, ALMVendor)
    for k, val in clean.items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def delete_vendor_record(vid: str, db: Session) -> dict:

    v = db.query(ALMVendor).filter(ALMVendor.id == vid, ALMVendor.is_active == True).first()
    if not v:
        raise HTTPException(404)
    active_contracts = db.query(func.count(ALMContract.id)).filter(
        ALMContract.vendor_id == vid,
        ALMContract.is_active == True,
    ).scalar() or 0
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.vendor_id == vid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    active_assets = db.query(func.count(ALMAsset.id)).filter(
        ALMAsset.vendor_id == vid,
        ALMAsset.is_active == True,
    ).scalar() or 0
    if active_contracts or active_licenses or active_assets:
        raise HTTPException(
            400,
            f"No se puede eliminar: contratos={active_contracts}, licencias={active_licenses}, activos={active_assets}",
        )
    v.is_active = False
    db.commit()
    return {"ok": True, "message": "Proveedor eliminado correctamente"}


# ── Contract record operations ────────────────────────────────────────────────

def list_contracts_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    db: Session,
) -> list:

    query = db.query(ALMContract).filter(ALMContract.is_active == True)
    if vendor_id:
        query = query.filter(ALMContract.vendor_id == vendor_id)
    if status:
        query = query.filter(ALMContract.status == status)
    if expiring_days:
        cutoff = date.today() + timedelta(days=expiring_days)
        query = query.filter(
            ALMContract.renewal_date.isnot(None),
            ALMContract.renewal_date <= cutoff,
            ALMContract.renewal_date >= date.today(),
        )
    return [serialize_contract(c, db) for c in query.order_by(ALMContract.renewal_date.nullsfirst()).all()]


def create_contract_record(data: dict, created_by_id: str, db: Session) -> dict:

    clean = clean_input(
        data, ALMContract,
        date_fields=["start_date", "end_date", "renewal_date"],
        int_fields=["notice_days"],
        float_fields=["total_value", "annual_value"],
    )
    clean["created_by"] = created_by_id
    c = ALMContract(**clean)
    db.add(c)
    db.commit()
    db.refresh(c)
    return serialize_contract(c, db)


def get_contract_record(cid: str, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise HTTPException(404)
    return serialize_contract(c, db)


def update_contract_record(cid: str, data: dict, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise HTTPException(404)
    for k, v in data.items():
        if k in PROTECTED_FIELDS:
            continue
        if hasattr(c, k):
            if k in ["start_date", "end_date", "renewal_date"] and isinstance(v, str) and v:
                try:
                    parts = v.split("-")
                    v = date(int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    logger.debug("ALM contract update: invalid date %s=%r for cid=%s → None", k, v, cid, exc_info=True)
                    v = None
            setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return serialize_contract(c, db)


def delete_contract_record(cid: str, db: Session) -> dict:

    c = db.query(ALMContract).filter(ALMContract.id == cid, ALMContract.is_active == True).first()
    if not c:
        raise HTTPException(404)
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.contract_id == cid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    if active_licenses > 0:
        raise HTTPException(400, f"No se puede eliminar: {active_licenses} licencia(s) activas asociadas")
    c.is_active = False
    c.status = "cancelled"
    db.commit()
    return {"ok": True, "message": "Contrato eliminado correctamente"}


# ── License record operations ─────────────────────────────────────────────────

def list_licenses_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    compliance_only: bool,
    db: Session,
) -> list:

    query = db.query(ALMLicense).filter(ALMLicense.is_active == True)
    if vendor_id:
        query = query.filter(ALMLicense.vendor_id == vendor_id)
    if status:
        query = query.filter(ALMLicense.status == status)
    if expiring_days:
        cutoff = date.today() + timedelta(days=expiring_days)
        query = query.filter(
            ALMLicense.expiry_date.isnot(None),
            ALMLicense.expiry_date <= cutoff,
        )
    if compliance_only:
        query = query.filter(ALMLicense.is_compliance_req == True)
    return [serialize_license(lic, db) for lic in query.order_by(ALMLicense.name).all()]


def create_license_record(data: dict, db: Session) -> dict:

    clean = clean_input(
        data, ALMLicense,
        date_fields=["purchase_date", "expiry_date"],
        int_fields=["total_seats"],
        float_fields=["purchase_price", "annual_cost"],
    )
    lic = ALMLicense(**clean)
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return serialize_license(lic, db)


def get_license_record(lid: str, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise HTTPException(404)
    out = serialize_license(lic, db)
    out["assignments"] = []
    for a in lic.assignments:
        if a.is_active:
            out["assignments"].append({
                "id": a.id,
                "user_id": a.user_id,
                "user_name": a.user.full_name if a.user else None,
                "asset_id": a.asset_id,
                "asset_name": a.asset.name if a.asset else None,
                "project_id": a.project_id,
                "assigned_at": str(a.assigned_at),
                "expires_at": str(a.expires_at) if a.expires_at else None,
                "notes": a.notes,
            })
    return out


def update_license_record(lid: str, data: dict, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise HTTPException(404)
    clean = clean_input(
        data, ALMLicense,
        date_fields=["purchase_date", "expiry_date"],
        int_fields=["total_seats"],
        float_fields=["purchase_price", "annual_cost"],
    )
    for k, v in clean.items():
        setattr(lic, k, v)
    db.commit()
    db.refresh(lic)
    return serialize_license(lic, db)


def delete_license_record(lid: str, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise HTTPException(404)
    active_assignments = db.query(func.count(ALMLicenseAssignment.id)).filter(
        ALMLicenseAssignment.license_id == lid,
        ALMLicenseAssignment.is_active == True,
    ).scalar() or 0
    active_installs = db.query(func.count(ALMSoftwareInstall.id)).filter(
        ALMSoftwareInstall.license_id == lid,
        ALMSoftwareInstall.is_active == True,
    ).scalar() or 0
    if active_assignments or active_installs:
        raise HTTPException(
            400,
            f"No se puede eliminar: asignaciones={active_assignments}, instalaciones={active_installs}",
        )
    lic.is_active = False
    lic.status = "cancelled"
    db.commit()
    return {"ok": True, "message": "Licencia eliminada correctamente"}


def assign_license_record(lid: str, data: dict, assigned_by_id: str, db: Session) -> dict:

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.is_active == True).first()
    if not lic:
        raise HTTPException(404, "Licencia no encontrada")
    used = sum(1 for a in lic.assignments if a.is_active)
    if lic.total_seats and used >= lic.total_seats:
        raise HTTPException(409, f"Sin seats disponibles ({used}/{lic.total_seats} usados)")
    expires_at = None
    if data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(data["expires_at"]).date()
        except ValueError:
            raise HTTPException(400, "Formato de expires_at inválido, se espera YYYY-MM-DD")

    def _none(v):
        return v if v else None

    assignment = ALMLicenseAssignment(
        license_id  = lid,
        user_id     = _none(data.get("user_id")),
        asset_id    = _none(data.get("asset_id")),
        project_id  = _none(data.get("project_id")),
        assigned_by = assigned_by_id,
        expires_at  = expires_at,
        notes       = _none(data.get("notes")),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id, "license_id": lid, "user_id": assignment.user_id}


def revoke_assignment_record(lid: str, aid: str, db: Session) -> dict:

    a = db.query(ALMLicenseAssignment).filter(
        ALMLicenseAssignment.id == aid,
        ALMLicenseAssignment.license_id == lid,
        ALMLicenseAssignment.is_active == True,
    ).first()
    if not a:
        raise HTTPException(404)
    a.is_active = False
    db.commit()
    return {"ok": True, "message": "Asignacion revocada correctamente"}


# ── Asset record operations ───────────────────────────────────────────────────

def list_assets_records(
    type: Optional[str],
    status: Optional[str],
    assigned_to: Optional[str],
    q: Optional[str],
    db: Session,
) -> list:

    query = db.query(ALMAsset).filter(ALMAsset.is_active == True)
    if type:
        query = query.filter(ALMAsset.type == type)
    if status:
        query = query.filter(ALMAsset.status == status)
    if assigned_to:
        query = query.filter(ALMAsset.assigned_to_id == assigned_to)
    if q:
        query = query.filter(or_(
            ALMAsset.name.ilike(f"%{q}%"),
            ALMAsset.serial_number.ilike(f"%{q}%"),
            ALMAsset.asset_tag.ilike(f"%{q}%"),
            ALMAsset.hostname.ilike(f"%{q}%"),
        ))
    return [serialize_asset(a) for a in query.order_by(ALMAsset.name).all()]


def create_asset_record(data: dict, db: Session) -> dict:

    clean = clean_input(
        data, ALMAsset,
        date_fields=["purchase_date", "warranty_expiry"],
        int_fields=["depreciation_years", "ram_gb", "storage_gb"],
        float_fields=["purchase_price"],
    )
    a = ALMAsset(**clean)
    db.add(a)
    db.commit()
    db.refresh(a)
    return serialize_asset(a)


def get_asset_record(aid: str, db: Session) -> dict:

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise HTTPException(404)
    out = serialize_asset(a)
    out["licenses"] = [
        {"id": i.license_id, "name": i.license.name if i.license else "—", "version": i.version}
        for i in a.installs if i.is_active
    ]
    return out


def update_asset_record(aid: str, data: dict, db: Session) -> dict:

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise HTTPException(404)
    clean = clean_input(
        data, ALMAsset,
        date_fields=["purchase_date", "warranty_expiry"],
        int_fields=["depreciation_years", "ram_gb", "storage_gb"],
        float_fields=["purchase_price"],
    )
    for k, v in clean.items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return serialize_asset(a)


def delete_asset_record(aid: str, db: Session) -> dict:

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise HTTPException(404)
    active_installs = db.query(func.count(ALMSoftwareInstall.id)).filter(
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.is_active == True,
    ).scalar() or 0
    active_assignments = db.query(func.count(ALMLicenseAssignment.id)).filter(
        ALMLicenseAssignment.asset_id == aid,
        ALMLicenseAssignment.is_active == True,
    ).scalar() or 0
    if active_installs or active_assignments:
        raise HTTPException(
            400,
            f"No se puede eliminar: instalaciones={active_installs}, asignaciones={active_assignments}",
        )
    a.is_active = False
    a.status = "retired"
    db.commit()
    return {"ok": True, "message": "Activo eliminado correctamente"}


def assign_asset_record(aid: str, data: dict, db: Session) -> dict:

    a = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not a:
        raise HTTPException(404)
    uid = data.get("user_id") or None
    a.assigned_to_id = uid
    a.status = "in_use" if uid else "available"
    a.location = data.get("location", a.location)
    db.commit()
    db.refresh(a)
    return serialize_asset(a)


# ── Cost center record operations ─────────────────────────────────────────────

def list_cost_centers_records(db: Session) -> list:

    return [
        {
            "id": c.id, "code": c.code, "name": c.name,
            "budget_annual": c.budget_annual, "currency": c.currency,
            "is_active": c.is_active, "description": c.description,
        }
        for c in db.query(ALMCostCenter).filter(ALMCostCenter.is_active == True).order_by(ALMCostCenter.code).all()
    ]


def create_cost_center_record(data: dict, db: Session) -> dict:

    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    c = ALMCostCenter(**clean)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "code": c.code, "name": c.name}


def update_cost_center_record(cid: str, data: dict, db: Session) -> dict:

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid, ALMCostCenter.is_active == True).first()
    if not c:
        raise HTTPException(404)
    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    for k, v in clean.items():
        setattr(c, k, v)
    db.commit()
    return {"id": c.id, "code": c.code, "name": c.name}


def delete_cost_center_record(cid: str, db: Session) -> dict:

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid, ALMCostCenter.is_active == True).first()
    if not c:
        raise HTTPException(404)
    active_contracts = db.query(func.count(ALMContract.id)).filter(
        ALMContract.cost_center_id == cid,
        ALMContract.is_active == True,
    ).scalar() or 0
    active_licenses = db.query(func.count(ALMLicense.id)).filter(
        ALMLicense.cost_center_id == cid,
        ALMLicense.is_active == True,
    ).scalar() or 0
    if active_contracts or active_licenses:
        raise HTTPException(
            400,
            f"No se puede eliminar: contratos={active_contracts}, licencias={active_licenses}",
        )
    c.is_active = False
    db.commit()
    return {"ok": True, "message": "Centro de coste eliminado correctamente"}


# ── Software install record operations ────────────────────────────────────────

def add_install_record(aid: str, data: dict, installed_by_id: str, db: Session) -> dict:

    license_id = data.get("license_id")
    if not license_id:
        raise HTTPException(400, "license_id es obligatorio")
    asset = db.query(ALMAsset).filter(ALMAsset.id == aid, ALMAsset.is_active == True).first()
    if not asset:
        raise HTTPException(404, "Activo no encontrado")
    license_obj = db.query(ALMLicense).filter(ALMLicense.id == license_id, ALMLicense.is_active == True).first()
    if not license_obj:
        raise HTTPException(404, "Licencia no encontrada")
    existing = db.query(ALMSoftwareInstall).filter(
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.license_id == license_id,
        ALMSoftwareInstall.is_active == True,
    ).first()
    if existing:
        raise HTTPException(400, "La instalacion ya existe")
    inst = ALMSoftwareInstall(
        asset_id     = aid,
        license_id   = license_id,
        installed_by = installed_by_id,
        version      = data.get("version"),
        notes        = data.get("notes"),
    )
    db.add(inst)
    db.commit()
    return {"id": inst.id, "asset_id": aid, "license_id": license_id}


def remove_install_record(aid: str, iid: str, db: Session) -> dict:

    inst = db.query(ALMSoftwareInstall).filter(
        ALMSoftwareInstall.id == iid,
        ALMSoftwareInstall.asset_id == aid,
        ALMSoftwareInstall.is_active == True,
    ).first()
    if not inst:
        raise HTTPException(404)
    inst.is_active = False
    db.commit()
    return {"ok": True, "message": "Instalacion eliminada correctamente"}


# ── Compliance report ─────────────────────────────────────────────────────────

def get_compliance_report(db: Session) -> dict:

    today = date.today()
    issues = []
    for lic in db.query(ALMLicense).filter(ALMLicense.is_compliance_req == True, ALMLicense.is_active == True).all():
        used = sum(1 for a in lic.assignments if a.is_active)
        if lic.expiry_date and lic.expiry_date < today:
            issues.append({
                "license_id": lic.id, "name": lic.name,
                "issue": "EXPIRED", "severity": "critical",
                "detail": f"Expiró el {lic.expiry_date}",
            })
        if lic.total_seats and used > lic.total_seats:
            issues.append({
                "license_id": lic.id, "name": lic.name,
                "issue": "OVERALLOCATED", "severity": "critical",
                "detail": f"{used} usadas de {lic.total_seats} permitidas",
            })
    return {
        "issues": issues,
        "total": len(issues),
        "critical": sum(1 for i in issues if i["severity"] == "critical"),
    }

