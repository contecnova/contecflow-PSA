"""
ALM service — business logic extracted from alm.py endpoint.
Covers: input data cleaning, serialisers for Vendor / Contract / License / Asset,
        linked-client query helpers, and all CRUD record operations.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session


# ── Input cleaner ─────────────────────────────────────────────────────────────

def clean_input(data: dict, model_cls, date_fields=None, int_fields=None, float_fields=None) -> dict:
    """Limpia el dict del frontend: '' → None, tipos correctos, ignora campos sin columna."""
    from datetime import date as _date

    date_fields  = date_fields  or []
    int_fields   = int_fields   or []
    float_fields = float_fields or []
    out = {}
    for k, v in data.items():
        if not hasattr(model_cls, k):
            continue
        if v == "" or v is None:
            out[k] = None
            continue
        if k in date_fields:
            try:
                parts = str(v).split("-")
                out[k] = _date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception:
                out[k] = None
        elif k in int_fields:
            try:
                out[k] = int(v)
            except Exception:
                out[k] = None
        elif k in float_fields:
            try:
                out[k] = float(v)
            except Exception:
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
        return []


# ── Serialisers ───────────────────────────────────────────────────────────────

def serialize_vendor(v) -> dict:
    return {
        "id": v.id, "name": v.name, "category": v.category,
        "website": v.website, "support_email": v.support_email,
        "support_phone": v.support_phone, "account_manager": v.account_manager,
        "account_number": v.account_number, "country": v.country,
        "is_active": v.is_active, "notes": v.notes,
        "contracts_count": len(v.contracts) if v.contracts else 0,
    }


def serialize_contract(c, db: Optional[Session] = None) -> dict:
    today = date.today()
    days_to_renewal = None
    if c.renewal_date:
        days_to_renewal = (c.renewal_date - today).days
    return {
        "id": c.id, "title": c.title, "reference": c.reference,
        "type": c.type, "status": c.status,
        "vendor_id": c.vendor_id,
        "vendor_name": c.vendor.name if c.vendor else None,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "renewal_date": str(c.renewal_date) if c.renewal_date else None,
        "auto_renew": c.auto_renew, "notice_days": c.notice_days,
        "days_to_renewal": days_to_renewal,
        "renewal_urgent": days_to_renewal is not None and 0 <= days_to_renewal <= 60,
        "total_value": c.total_value, "annual_value": c.annual_value,
        "billing_cycle": c.billing_cycle, "currency": c.currency,
        "payment_method": c.payment_method, "po_number": c.po_number,
        "cost_center_id": c.cost_center_id,
        "owner_id": c.owner_id,
        "owner_name": c.owner.full_name if c.owner else None,
        "project_id": c.project_id,
        "document_url": c.document_url,
        "notes": c.notes, "tags": c.tags,
        "licenses_count": len(c.licenses) if c.licenses else 0,
        "linked_clients": get_linked_clients_for_contract(c.id, db) if db else [],
    }


def serialize_license(lic, db: Session) -> dict:
    used  = sum(1 for a in lic.assignments if a.is_active)
    avail = (lic.total_seats - used) if lic.total_seats else None
    status = lic.status
    if lic.expiry_date and lic.expiry_date < date.today():
        status = "expired"
    elif lic.total_seats and used > lic.total_seats:
        status = "overallocated"
    elif used == 0 and lic.total_seats and lic.total_seats > 0:
        status = "unassigned"
    return {
        "id": lic.id, "name": lic.name, "product_name": lic.product_name,
        "version": lic.version, "edition": lic.edition,
        "type": lic.type, "platform": lic.platform, "status": status,
        "vendor_id": lic.vendor_id,
        "vendor_name": lic.vendor.name if lic.vendor else None,
        "contract_id": lic.contract_id,
        "total_seats": lic.total_seats, "used_seats": used, "available_seats": avail,
        "expiry_date": str(lic.expiry_date) if lic.expiry_date else None,
        "purchase_date": str(lic.purchase_date) if lic.purchase_date else None,
        "purchase_price": lic.purchase_price, "annual_cost": lic.annual_cost,
        "cost_center_id": lic.cost_center_id, "project_id": lic.project_id,
        "environment": lic.environment, "is_compliance_req": lic.is_compliance_req,
        "notes": lic.notes,
        "assignments_count": used,
        "days_to_expiry": (lic.expiry_date - date.today()).days if lic.expiry_date else None,
        "linked_clients": get_linked_clients_for_license(lic.id, db),
    }


def serialize_asset(a) -> dict:
    age_years  = None
    book_value = None
    if a.purchase_date:
        age_years = (date.today() - a.purchase_date).days / 365
        if a.purchase_price and a.depreciation_years:
            depreciated = a.purchase_price * (age_years / a.depreciation_years)
            book_value  = max(0, a.purchase_price - depreciated)
    return {
        "id": a.id, "name": a.name, "type": a.type,
        "brand": a.brand, "model": a.model,
        "serial_number": a.serial_number, "asset_tag": a.asset_tag,
        "status": a.status, "condition": a.condition,
        "assigned_to_id": a.assigned_to_id,
        "assigned_to_name": a.assigned_to.full_name if a.assigned_to else None,
        "location": a.location, "department_id": a.department_id,
        "project_id": a.project_id,
        "vendor_id": a.vendor_id,
        "vendor_name": a.vendor.name if a.vendor else None,
        "purchase_date": str(a.purchase_date) if a.purchase_date else None,
        "purchase_price": a.purchase_price, "currency": a.currency,
        "warranty_expiry": str(a.warranty_expiry) if a.warranty_expiry else None,
        "warranty_expired": a.warranty_expiry < date.today() if a.warranty_expiry else False,
        "age_years": round(age_years, 1) if age_years else None,
        "book_value": round(book_value, 2) if book_value is not None else None,
        "depreciation_years": a.depreciation_years,
        "ip_address": a.ip_address, "hostname": a.hostname, "os": a.os,
        "cpu": a.cpu, "ram_gb": a.ram_gb, "storage_gb": a.storage_gb,
        "notes": a.notes,
        "installed_licenses": len(a.installs) if a.installs else 0,
    }


# ── Dashboard / KPIs ─────────────────────────────────────────────────────────

def get_alm_dashboard(db: Session) -> dict:
    from app.models.alm import ALMContract, ALMLicense, ALMAsset, ALMVendor

    today = date.today()
    in_60 = today + timedelta(days=60)
    in_90 = today + timedelta(days=90)

    total_contracts   = db.query(ALMContract).filter(ALMContract.status == "active").count()
    expiring_soon     = db.query(ALMContract).filter(
        ALMContract.status == "active",
        ALMContract.renewal_date.isnot(None),
        ALMContract.renewal_date <= in_60,
    ).count()
    total_licenses    = db.query(ALMLicense).filter(ALMLicense.status != "cancelled").count()
    expired_licenses  = db.query(ALMLicense).filter(
        ALMLicense.expiry_date < today,
        ALMLicense.status != "cancelled",
    ).count()
    total_assets      = db.query(ALMAsset).filter(ALMAsset.status != "retired").count()
    assets_in_use     = db.query(ALMAsset).filter(ALMAsset.status == "in_use").count()
    warranty_expiring = db.query(ALMAsset).filter(
        ALMAsset.warranty_expiry.isnot(None),
        ALMAsset.warranty_expiry <= in_90,
        ALMAsset.warranty_expiry >= today,
    ).count()
    total_vendors     = db.query(ALMVendor).filter(ALMVendor.is_active == True).count()

    annual_cost    = db.query(func.sum(ALMLicense.annual_cost)).scalar() or 0
    contract_cost  = db.query(func.sum(ALMContract.annual_value)).filter(
        ALMContract.status == "active"
    ).scalar() or 0

    upcoming = db.query(ALMContract).filter(
        ALMContract.status == "active",
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
    from app.models.alm import ALMVendor

    query = db.query(ALMVendor)
    if q:
        query = query.filter(ALMVendor.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(ALMVendor.category == category)
    return [serialize_vendor(v) for v in query.order_by(ALMVendor.name).all()]


def create_vendor_record(data: dict, db: Session) -> dict:
    from app.models.alm import ALMVendor

    clean = clean_input(data, ALMVendor)
    v = ALMVendor(**clean)
    db.add(v)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def get_vendor_record(vid: str, db: Session) -> dict:
    from app.models.alm import ALMVendor

    v = db.query(ALMVendor).filter(ALMVendor.id == vid).first()
    if not v:
        raise HTTPException(404, "Proveedor no encontrado")
    return serialize_vendor(v)


def update_vendor_record(vid: str, data: dict, db: Session) -> dict:
    from app.models.alm import ALMVendor

    v = db.query(ALMVendor).filter(ALMVendor.id == vid).first()
    if not v:
        raise HTTPException(404)
    clean = clean_input(data, ALMVendor)
    for k, val in clean.items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return serialize_vendor(v)


def delete_vendor_record(vid: str, db: Session) -> dict:
    from app.models.alm import ALMVendor

    v = db.query(ALMVendor).filter(ALMVendor.id == vid).first()
    if not v:
        raise HTTPException(404)
    db.delete(v)
    db.commit()
    return {"ok": True}


# ── Contract record operations ────────────────────────────────────────────────

def list_contracts_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    db: Session,
) -> list:
    from app.models.alm import ALMContract

    query = db.query(ALMContract)
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
    from app.models.alm import ALMContract

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
    from app.models.alm import ALMContract

    c = db.query(ALMContract).filter(ALMContract.id == cid).first()
    if not c:
        raise HTTPException(404)
    return serialize_contract(c, db)


def update_contract_record(cid: str, data: dict, db: Session) -> dict:
    from app.models.alm import ALMContract
    from datetime import date as d_

    c = db.query(ALMContract).filter(ALMContract.id == cid).first()
    if not c:
        raise HTTPException(404)
    for k, v in data.items():
        if hasattr(c, k):
            if k in ["start_date", "end_date", "renewal_date"] and isinstance(v, str) and v:
                try:
                    parts = v.split("-")
                    v = d_(int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    v = None
            setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return serialize_contract(c, db)


def delete_contract_record(cid: str, db: Session) -> dict:
    from app.models.alm import ALMContract

    c = db.query(ALMContract).filter(ALMContract.id == cid).first()
    if not c:
        raise HTTPException(404)
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── License record operations ─────────────────────────────────────────────────

def list_licenses_records(
    vendor_id: Optional[str],
    status: Optional[str],
    expiring_days: Optional[int],
    compliance_only: bool,
    db: Session,
) -> list:
    from app.models.alm import ALMLicense

    query = db.query(ALMLicense)
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
    from app.models.alm import ALMLicense

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
    from app.models.alm import ALMLicense

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid).first()
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
    from app.models.alm import ALMLicense

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid).first()
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
    from app.models.alm import ALMLicense

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid).first()
    if not lic:
        raise HTTPException(404)
    db.delete(lic)
    db.commit()
    return {"ok": True}


def assign_license_record(lid: str, data: dict, assigned_by_id: str, db: Session) -> dict:
    from app.models.alm import ALMLicense, ALMLicenseAssignment

    lic = db.query(ALMLicense).filter(ALMLicense.id == lid).first()
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
    from app.models.alm import ALMLicenseAssignment

    a = db.query(ALMLicenseAssignment).filter(
        ALMLicenseAssignment.id == aid,
        ALMLicenseAssignment.license_id == lid,
    ).first()
    if not a:
        raise HTTPException(404)
    a.is_active = False
    db.commit()
    return {"ok": True}


# ── Asset record operations ───────────────────────────────────────────────────

def list_assets_records(
    type: Optional[str],
    status: Optional[str],
    assigned_to: Optional[str],
    q: Optional[str],
    db: Session,
) -> list:
    from app.models.alm import ALMAsset

    query = db.query(ALMAsset)
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
    from app.models.alm import ALMAsset

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
    from app.models.alm import ALMAsset

    a = db.query(ALMAsset).filter(ALMAsset.id == aid).first()
    if not a:
        raise HTTPException(404)
    out = serialize_asset(a)
    out["licenses"] = [
        {"id": i.license_id, "name": i.license.name if i.license else "—", "version": i.version}
        for i in a.installs
    ]
    return out


def update_asset_record(aid: str, data: dict, db: Session) -> dict:
    from app.models.alm import ALMAsset

    a = db.query(ALMAsset).filter(ALMAsset.id == aid).first()
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
    from app.models.alm import ALMAsset

    a = db.query(ALMAsset).filter(ALMAsset.id == aid).first()
    if not a:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


def assign_asset_record(aid: str, data: dict, db: Session) -> dict:
    from app.models.alm import ALMAsset

    a = db.query(ALMAsset).filter(ALMAsset.id == aid).first()
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
    from app.models.alm import ALMCostCenter

    return [
        {
            "id": c.id, "code": c.code, "name": c.name,
            "budget_annual": c.budget_annual, "currency": c.currency,
            "is_active": c.is_active, "description": c.description,
        }
        for c in db.query(ALMCostCenter).order_by(ALMCostCenter.code).all()
    ]


def create_cost_center_record(data: dict, db: Session) -> dict:
    from app.models.alm import ALMCostCenter

    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    c = ALMCostCenter(**clean)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "code": c.code, "name": c.name}


def update_cost_center_record(cid: str, data: dict, db: Session) -> dict:
    from app.models.alm import ALMCostCenter

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid).first()
    if not c:
        raise HTTPException(404)
    clean = clean_input(data, ALMCostCenter, float_fields=["budget_annual"])
    for k, v in clean.items():
        setattr(c, k, v)
    db.commit()
    return {"id": c.id, "code": c.code, "name": c.name}


def delete_cost_center_record(cid: str, db: Session) -> dict:
    from app.models.alm import ALMCostCenter

    c = db.query(ALMCostCenter).filter(ALMCostCenter.id == cid).first()
    if not c:
        raise HTTPException(404)
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── Software install record operations ────────────────────────────────────────

def add_install_record(aid: str, data: dict, installed_by_id: str, db: Session) -> dict:
    from app.models.alm import ALMSoftwareInstall

    license_id = data.get("license_id")
    if not license_id:
        raise HTTPException(400, "license_id es obligatorio")
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
    from app.models.alm import ALMSoftwareInstall

    inst = db.query(ALMSoftwareInstall).filter(
        ALMSoftwareInstall.id == iid,
        ALMSoftwareInstall.asset_id == aid,
    ).first()
    if not inst:
        raise HTTPException(404)
    db.delete(inst)
    db.commit()
    return {"ok": True}


# ── Compliance report ─────────────────────────────────────────────────────────

def get_compliance_report(db: Session) -> dict:
    from app.models.alm import ALMLicense

    today = date.today()
    issues = []
    for lic in db.query(ALMLicense).filter(ALMLicense.is_compliance_req == True).all():
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

