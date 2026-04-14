import re
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Asset, AssetHistory, AssetStatus, AssetType
from app.models.user import User


def next_asset_code(db: Session) -> str:
    max_code = db.query(func.max(Asset.code)).scalar()
    if max_code:
        match = re.search(r"(\d+)$", max_code)
        num = (int(match.group(1)) + 1) if match else 1
    else:
        num = 1
    return f"ASSET-{num:04d}"


def asset_out(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "code": asset.code,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "status": asset.status,
        "serial_number": asset.serial_number,
        "model": asset.model,
        "manufacturer": asset.manufacturer,
        "part_number": asset.part_number,
        "license_key": asset.license_key,
        "license_seats": asset.license_seats,
        "license_used": asset.license_used,
        "purchase_date": asset.purchase_date,
        "warranty_expiry": asset.warranty_expiry,
        "eol_date": asset.eol_date,
        "lease_expiry": asset.lease_expiry,
        "purchase_price": asset.purchase_price,
        "current_value": asset.current_value,
        "currency": asset.currency,
        "po_number": asset.po_number,
        "vendor": asset.vendor,
        "vendor_contract": asset.vendor_contract,
        "location": asset.location,
        "assigned_user_id": asset.assigned_user_id,
        "assigned_user_name": asset.assigned_user.full_name if asset.assigned_user else None,
        "department": asset.department,
        "ci_id": asset.ci_id,
        "tags": asset.tags,
        "notes": asset.notes,
        "managed_by_user_id": asset.managed_by_user_id,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def list_assets_payload(
    db: Session,
    asset_type: Optional[str],
    status: Optional[str],
    assigned_user_id: Optional[str],
    search: Optional[str],
    page: int,
    page_size: int,
) -> dict:
    q = db.query(Asset).options(joinedload(Asset.assigned_user))
    if asset_type:
        q = q.filter(Asset.asset_type == asset_type)
    if status:
        q = q.filter(Asset.status == status)
    if assigned_user_id:
        q = q.filter(Asset.assigned_user_id == assigned_user_id)
    if search:
        q = q.filter(
            or_(
                Asset.name.ilike(f"%{search}%"),
                Asset.serial_number.ilike(f"%{search}%"),
                Asset.code.ilike(f"%{search}%"),
                Asset.model.ilike(f"%{search}%"),
            )
        )

    total = q.count()
    assets = q.order_by(Asset.code).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "assets": [asset_out(a) for a in assets]}


def asset_stats_payload(db: Session) -> dict:
    total = db.query(func.count(Asset.id)).scalar() or 0
    by_type = db.query(Asset.asset_type, func.count(Asset.id)).group_by(Asset.asset_type).all()
    by_status = db.query(Asset.status, func.count(Asset.id)).group_by(Asset.status).all()

    expiring_warranty = db.query(func.count(Asset.id)).filter(
        Asset.warranty_expiry.isnot(None),
        Asset.warranty_expiry <= (date.today() + timedelta(days=90)).isoformat(),
        Asset.warranty_expiry >= date.today().isoformat(),
    ).scalar() or 0

    eol_soon = db.query(func.count(Asset.id)).filter(
        Asset.eol_date.isnot(None),
        Asset.eol_date <= (date.today() + timedelta(days=180)).isoformat(),
        Asset.eol_date >= date.today().isoformat(),
    ).scalar() or 0

    return {
        "total_assets": total,
        "by_type": {t: c for t, c in by_type},
        "by_status": {s: c for s, c in by_status},
        "expiring_warranty_90d": expiring_warranty,
        "eol_within_180d": eol_soon,
    }


def get_asset_with_relations_or_404(db: Session, asset_id: str) -> Asset:
    asset = db.query(Asset).options(
        joinedload(Asset.assigned_user),
        joinedload(Asset.managed_by),
        joinedload(Asset.history),
    ).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404)
    return asset


def build_asset_detail(asset: Asset) -> dict:
    out = asset_out(asset)
    out["history"] = [
        {
            "field": h.field_name,
            "old": h.old_value,
            "new": h.new_value,
            "note": h.note,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        }
        for h in (asset.history or [])
    ]
    return out


def get_asset_detail_payload(db: Session, asset_id: str) -> dict:
    asset = get_asset_with_relations_or_404(db, asset_id)
    return build_asset_detail(asset)


def validate_asset_type(asset_type: str) -> None:
    try:
        AssetType(asset_type)
    except ValueError:
        raise HTTPException(400, f"Invalid asset_type: {asset_type}")


def build_asset(payload, code: str) -> Asset:
    return Asset(code=code, **payload.model_dump())


def create_asset_record(db: Session, payload) -> Asset:
    validate_asset_type(payload.asset_type)
    return build_asset(payload, code=next_asset_code(db))


def get_asset_for_update_or_404(db: Session, asset_id: str) -> Asset:
    asset = db.query(Asset).options(joinedload(Asset.assigned_user)).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404)
    return asset


def apply_asset_update_with_history(db: Session, asset: Asset, update_data: dict, changed_by: str) -> None:
    for key, value in update_data.items():
        old_val = str(getattr(asset, key, None))
        setattr(asset, key, value)
        if old_val != str(value):
            db.add(
                AssetHistory(
                    asset_id=asset.id,
                    field_name=key,
                    old_value=old_val,
                    new_value=str(value),
                    changed_by=changed_by,
                )
            )


def update_asset_record(db: Session, asset_id: str, payload, changed_by: str) -> Asset:
    asset = get_asset_for_update_or_404(db, asset_id)
    update_data = payload.model_dump(exclude_unset=True)
    apply_asset_update_with_history(db, asset, update_data, changed_by)
    return asset


def retire_asset_with_history(db: Session, asset: Asset, changed_by: str) -> None:
    old = asset.status
    asset.status = AssetStatus.retired
    db.add(
        AssetHistory(
            asset_id=asset.id,
            field_name="status",
            old_value=str(old),
            new_value="retired",
            changed_by=changed_by,
        )
    )


def retire_asset_record(db: Session, asset_id: str, changed_by: str) -> Asset:
    asset = get_asset_or_404(db, asset_id)
    retire_asset_with_history(db, asset, changed_by)
    return asset


def get_asset_or_404(db: Session, asset_id: str) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404)
    return asset


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def assign_asset_to_user_with_history(db: Session, asset: Asset, user_id: str, changed_by: str, notes: str = None) -> None:
    old_user = asset.assigned_user_id
    asset.assigned_user_id = user_id
    asset.status = AssetStatus.deployed
    db.add(
        AssetHistory(
            asset_id=asset.id,
            field_name="assigned_user_id",
            old_value=old_user,
            new_value=user_id,
            changed_by=changed_by,
            note=notes,
        )
    )


def assign_asset_record(db: Session, asset_id: str, user_id: str, changed_by: str, notes: str = None) -> str:
    asset = get_asset_or_404(db, asset_id)
    user = get_user_or_404(db, user_id)
    assign_asset_to_user_with_history(db, asset, user_id, changed_by, notes)
    return user.full_name
