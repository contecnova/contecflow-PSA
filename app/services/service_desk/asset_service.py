import re
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Asset, AssetHistory, AssetStatus, AssetType, ConfigurationItem
from app.models.user import User
import logging
from app.core import timeutil

logger = logging.getLogger(__name__)


def next_asset_code(db: Session) -> str:
    max_code = db.query(func.max(Asset.code)).scalar()
    if max_code:
        match = re.search(r"(\d+)$", max_code)
        num = (int(match.group(1)) + 1) if match else 1
    else:
        num = 1
    return f"ASSET-{num:04d}"


def asset_out(asset: Asset) -> dict:
    ci = getattr(asset, "ci", None)
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
        "ci_code": ci.code if ci else None,
        "ci_name": ci.name if ci else None,
        "ci_status": str(ci.status.value if hasattr(ci.status, "value") else ci.status) if ci else None,
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
    q = db.query(Asset).options(joinedload(Asset.assigned_user), joinedload(Asset.ci))
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
        Asset.warranty_expiry <= (timeutil.today() + timedelta(days=90)).isoformat(),
        Asset.warranty_expiry >= timeutil.today().isoformat(),
    ).scalar() or 0

    eol_soon = db.query(func.count(Asset.id)).filter(
        Asset.eol_date.isnot(None),
        Asset.eol_date <= (timeutil.today() + timedelta(days=180)).isoformat(),
        Asset.eol_date >= timeutil.today().isoformat(),
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
        joinedload(Asset.ci),
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


def _ensure_ci_exists_or_404(db: Session, ci_id: Optional[str]) -> None:
    if not ci_id:
        return
    exists = db.query(ConfigurationItem.id).filter(ConfigurationItem.id == ci_id).first()
    if not exists:
        raise HTTPException(404, "Linked CI not found")


def create_asset_record(db: Session, payload) -> Asset:
    validate_asset_type(payload.asset_type)
    _ensure_ci_exists_or_404(db, getattr(payload, "ci_id", None))
    asset = build_asset(payload, code=next_asset_code(db))
    db.add(asset)
    return asset


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
    if "ci_id" in update_data:
        _ensure_ci_exists_or_404(db, update_data.get("ci_id"))
    apply_asset_update_with_history(db, asset, update_data, changed_by)
    return asset


def list_assets_by_ci_payload(db: Session, ci_id: str) -> dict:
    _ensure_ci_exists_or_404(db, ci_id)
    assets = (
        db.query(Asset)
        .options(joinedload(Asset.assigned_user), joinedload(Asset.ci))
        .filter(Asset.ci_id == ci_id)
        .order_by(Asset.code)
        .all()
    )
    return {
        "ci_id": ci_id,
        "count": len(assets),
        "assets": [asset_out(a) for a in assets],
    }


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


# ── Phase 2 — Asset Lifecycle ─────────────────────────────────────────────────



def _days_until(date_str: Optional[str]) -> Optional[int]:
    """Return days until *date_str* (YYYY-MM-DD) or None if blank/invalid."""
    if not date_str:
        return None
    try:
        target = date.fromisoformat(date_str)
        delta = (target - timeutil.today()).days
        return delta
    except ValueError:
        return None


def get_expiring_soon(db: Session, days: int = 30) -> list[dict]:
    """Return assets whose warranty, EOL or lease expires within *days* days.

    Checks three date fields independently and returns one entry per expiry
    type per asset.

    Each entry:
        {asset_id, code, name, expiry_type, expiry_date, days_remaining}
    """
    assets = (
        db.query(Asset)
        .filter(Asset.status != AssetStatus.retired)
        .all()
    )
    results: list[dict] = []

    for asset in assets:
        for expiry_type, date_attr in (
            ("warranty_expiry", asset.warranty_expiry),
            ("eol_date", asset.eol_date),
            ("lease_expiry", asset.lease_expiry),
        ):
            remaining = _days_until(date_attr)
            if remaining is not None and 0 <= remaining <= days:
                results.append(
                    {
                        "asset_id": asset.id,
                        "code": asset.code,
                        "name": asset.name,
                        "asset_type": str(asset.asset_type),
                        "expiry_type": expiry_type,
                        "expiry_date": date_attr,
                        "days_remaining": remaining,
                    }
                )

    results.sort(key=lambda x: x["days_remaining"])
    return results


# ── Las dos auditorias de activos ───────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). Estaban en el endpoint, y las dos consultaban
# `Asset` **sin filtro de organizacion**. Hay que decir con precision lo que eso
# significaba y lo que no:
#
#   · En produccion NO era una fuga. `SessionLocal` usa `TenantSession`, que
#     sobrescribe `query()` y anade el filtro por `organization_id` —`Asset`
#     tiene la columna—, asi que el filtro estaba, solo que implicito.
#   · Pero era la UNICA capa. Y este modulo entero no menciona
#     `organization_id` ni una vez en sus dieciocho funciones, asi que no habia
#     nada detras si esa capa falla. Ya fallo una vez (§3.bis del traspaso: el
#     criterio rancio dejaba a cero a toda organizacion menos la primera).
#
# Lo que **si** era un defecto sin mitigar es la carga: `/software-audit` hacia
# `db.query(Asset).all()` —**todos** los activos, como objetos del ORM, sin
# tope— para acabar contando etiquetas. Ahora son dos consultas acotadas, y la
# de las etiquetas trae solo esa columna.

#: Por debajo de que porcentaje de uso una licencia se considera sobrada.
#: Estaba en duro en el cuerpo del endpoint.
UMBRAL_DE_LICENCIA_SOBRADA = 40


def _activos_de_la_organizacion(db: Session, current_user):
    """La consulta base de activos, acotada de forma EXPLICITA.

    Un superadmin no filtra, que es la excepcion declarada de toda la politica
    de aislamiento. Un sujeto sin organizacion ve las filas sin organizacion,
    no las de todos: el filtro no es condicional.
    """
    q = db.query(Asset)
    if getattr(current_user, "is_superadmin", False):
        return q
    return q.filter(
        Asset.organization_id == getattr(current_user, "organization_id", None))


def auditoria_de_licencias(db: Session, current_user) -> dict:
    """Butacas contratadas contra butacas usadas, licencia a licencia.

    Devuelve `license_key`, asi que el ambito importa: es una credencial.
    """
    from app.models.service_desk import AssetType

    activos = (
        _activos_de_la_organizacion(db, current_user)
        .filter(
            Asset.asset_type.in_([AssetType.software, AssetType.license]),
            Asset.license_seats.isnot(None),
            Asset.license_seats > 0,
        )
        .all()
    )

    items = []
    for a in activos:
        butacas = a.license_seats or 0
        usadas = a.license_used or 0
        uso = round(usadas / butacas * 100, 1) if butacas > 0 else 0
        if uso < UMBRAL_DE_LICENCIA_SOBRADA:
            estado = "over_licensed"
        elif usadas > butacas:
            estado = "under_licensed"
        else:
            estado = "ok"
        items.append({
            "asset_id": a.id,
            "code": a.code,
            "name": a.name,
            "vendor": a.vendor,
            "license_seats": butacas,
            "license_used": usadas,
            "utilization_pct": uso,
            "status": estado,
            "license_key": a.license_key,
            "warranty_expiry": a.warranty_expiry,
        })
    items.sort(key=lambda x: x["utilization_pct"])

    total_butacas = sum(i["license_seats"] for i in items)
    total_usadas = sum(i["license_used"] for i in items)
    return {
        "items": items,
        "summary": {
            "total_licenses": len(items),
            "total_seats": total_butacas,
            "total_used": total_usadas,
            "overall_utilization_pct": (
                round(total_usadas / total_butacas * 100, 1)
                if total_butacas else 0
            ),
            "over_licensed_count": sum(
                1 for i in items if i["status"] == "over_licensed"),
            "under_licensed_count": sum(
                1 for i in items if i["status"] == "under_licensed"),
        },
    }


def auditoria_de_software(db: Session, current_user) -> dict:
    """Software licenciado contra software desplegado, segun las etiquetas.

    Dos consultas acotadas en vez de `db.query(Asset).all()`. La de hardware
    trae **solo la columna `tags`**, que es lo unico que se usa: cargar el
    activo entero para leer una cadena era el coste de verdad de esto.
    """
    from app.models.service_desk import AssetStatus, AssetType

    licenciados = (
        _activos_de_la_organizacion(db, current_user)
        .filter(Asset.asset_type.in_([AssetType.software, AssetType.license]))
        .all()
    )
    por_nombre = {a.name.lower(): a for a in licenciados if a.name}

    etiquetas = (
        _activos_de_la_organizacion(db, current_user)
        .with_entities(Asset.tags)
        .filter(
            Asset.asset_type == AssetType.hardware,
            Asset.status == AssetStatus.deployed,
            Asset.tags.isnot(None),
        )
        .all()
    )
    desplegados: dict[str, int] = {}
    for (crudas,) in etiquetas:
        for etiqueta in (crudas or "").split(","):
            clave = etiqueta.strip().lower()
            if clave:
                desplegados[clave] = desplegados.get(clave, 0) + 1

    filas = [
        {
            "software": activo.name,
            "vendor": activo.vendor,
            "license_seats": activo.license_seats or 0,
            "deployed_count": desplegados.get(
                nombre, activo.license_used or 0),
            "license_key_present": bool(activo.license_key),
            "warranty_expiry": activo.warranty_expiry,
            "asset_id": activo.id,
        }
        for nombre, activo in por_nombre.items()
    ]
    return {"audit_rows": filas, "total": len(filas)}


def calculate_depreciation(asset: Asset) -> Optional[float]:
    """Estimate current value via straight-line or declining-balance depreciation.

    Uses ``asset.depreciation_type`` (linear|declining|none) and
    ``asset.purchase_price`` + ``asset.purchase_date`` if available.

    Returns estimated current value or None if insufficient data.
    """
    price = asset.purchase_price
    if not price or price <= 0:
        return None

    purchase_date_str = asset.purchase_date
    if not purchase_date_str:
        return None

    try:
        pd = date.fromisoformat(purchase_date_str)
    except ValueError:
        return None

    years_elapsed = (timeutil.today() - pd).days / 365.25
    dep_type = getattr(asset, "depreciation_type", None) or "linear"
    dep_rate = getattr(asset, "depreciation_rate", None)

    if dep_type == "none":
        return float(price)

    if dep_type == "declining":
        rate = (dep_rate or 0.20)  # default 20% declining balance
        value = float(price) * ((1 - rate) ** years_elapsed)
    else:  # linear (default)
        useful_life = 5.0
        rate_annual = 1.0 / useful_life
        value = float(price) * max(0, 1 - rate_annual * years_elapsed)

    return round(max(0.0, value), 2)


def get_lifecycle_dashboard(db: Session) -> dict:
    """Return a comprehensive lifecycle health dashboard.

    Includes:
        - Total assets by status
        - Expiring in 30/60/90 days
        - License utilization (used / total seats)
        - Average depreciation coverage
    """
    all_assets = db.query(Asset).all()

    status_counts: dict[str, int] = {}
    for asset in all_assets:
        s = str(asset.status)
        status_counts[s] = status_counts.get(s, 0) + 1

    expiring_30 = get_expiring_soon(db, days=30)
    expiring_60 = get_expiring_soon(db, days=60)
    expiring_90 = get_expiring_soon(db, days=90)

    # License utilization
    license_assets = [a for a in all_assets if a.license_seats and a.license_seats > 0]
    total_seats = sum(a.license_seats for a in license_assets)
    used_seats = sum(a.license_used or 0 for a in license_assets)
    license_utilization_pct = round((used_seats / total_seats * 100) if total_seats else 0, 1)

    # Depreciation: how many assets have significant residual value
    depreciated = [a for a in all_assets if calculate_depreciation(a) is not None]

    return {
        "total_assets": len(all_assets),
        "by_status": status_counts,
        "expiring_in_30_days": len(expiring_30),
        "expiring_in_60_days": len(expiring_60),
        "expiring_in_90_days": len(expiring_90),
        "top_expiring": expiring_30[:10],
        "license_utilization": {
            "total_seats": total_seats,
            "used_seats": used_seats,
            "utilization_pct": license_utilization_pct,
        },
        "assets_with_depreciation_data": len(depreciated),
    }


def create_refresh_ticket(
    db: Session,
    asset_id: str,
    acting_user_id: str,
) -> dict:
    """Create a Service Request ticket to schedule an asset refresh/renewal.

    Returns the newly created ticket as a dict summary.
    Does NOT commit — caller must commit.
    """
    from app.models.service_desk import (
        Ticket,
        TicketStatus,
        TicketPriority,
    )

    asset = get_asset_or_404(db, asset_id)

    # Find the soonest upcoming expiry
    soonest_expiry: Optional[str] = None
    soonest_days: Optional[int] = None
    for date_attr in (asset.warranty_expiry, asset.eol_date, asset.lease_expiry):
        remaining = _days_until(date_attr)
        if remaining is not None and (soonest_days is None or remaining < soonest_days):
            soonest_days = remaining
            soonest_expiry = date_attr

    title = f"[Refresh] Asset {asset.code} — {asset.name}"
    description = (
        f"Renovación/reemplazo planificado para el activo {asset.code} ({asset.name}).\n\n"
        f"Tipo: {asset.asset_type}\n"
        f"Número de serie: {asset.serial_number or 'N/A'}\n"
        f"Fecha expiración más próxima: {soonest_expiry or 'N/A'} "
        f"({soonest_days} días)\n\n"
        "Por favor, contactar con el proveedor o iniciar proceso de reemplazo."
    )

    from uuid import uuid4
    ticket_id = str(uuid4())
    # Auditoria 2026-08: este `Ticket` se construia **sin `number`**, y la
    # columna es NOT NULL, asi que despues del `AttributeError` de
    # `TicketStatus.open` venia un `IntegrityError`. Dos defectos encadenados en
    # la misma funcion, y ninguno de los dos se veia porque no habia un solo
    # test que llamara aqui.
    #
    # El numero se genera con el mismo prefijo-mas-hexadecimal que usan las
    # otras vias que no pasan por el contador de tickets (`EML-`, `SMS-`).
    ticket = Ticket(
        id=ticket_id,
        number=f"REF-{uuid4().hex[:8].upper()}",
        title=title,
        description=description,
        ticket_type="service_request",
        # Ver la nota de `inbound_email_service`: `open` no existe.
        status=TicketStatus.new,
        priority=TicketPriority.p3_medium,
        requester_user_id=acting_user_id,
        ci_id=asset.ci_id,
    )
    db.add(ticket)
    db.flush()

    return {
        "ticket_id": ticket_id,
        "title": title,
        "asset_id": asset_id,
        "asset_code": asset.code,
        "soonest_expiry": soonest_expiry,
        "days_remaining": soonest_days,
    }
