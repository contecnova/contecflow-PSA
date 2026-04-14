"""ALM metrics: license_cost_by_vendor, license_utilization, license_expiry_timeline,
assets_by_type."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import register_metric


@register_metric("license_cost_by_vendor")
def metric_license_cost_by_vendor(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Coste anual de licencias por proveedor."""
    try:
        from app.models.alm import ALMLicense

        q = db.query(
            ALMLicense.vendor,
            func.sum(ALMLicense.annual_cost).label("cost"),
            func.count(ALMLicense.id).label("count")
        ).filter(
            ALMLicense.status != "cancelled"
        ).group_by(
            ALMLicense.vendor
        ).order_by(
            func.sum(ALMLicense.annual_cost).desc()
        ).limit(top_n)

        rows = [
            {
                "label": r.vendor or "Desconocido",
                "value": round(r.cost or 0, 0),
                "count": r.count
            }
            for r in q.all()
        ]
    except ImportError:
        rows = []

    return rows, {}


@register_metric("license_utilization")
def metric_license_utilization(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Utilización de licencias: usuarios activos vs licencias totales."""
    try:
        from app.models.alm import ALMLicense

        q = db.query(
            ALMLicense.name,
            ALMLicense.vendor,
            ALMLicense.quantity,
            func.count(ALMLicense.id).label("assigned")
        ).filter(
            ALMLicense.status != "cancelled"
        ).group_by(
            ALMLicense.name,
            ALMLicense.vendor,
            ALMLicense.quantity
        ).limit(top_n)

        rows = []
        for r in q.all():
            total = r.quantity or 1
            assigned = r.assigned or 0
            pct = round(assigned / total * 100, 1) if total > 0 else 0
            rows.append({
                "label": f"{r.vendor}/{r.name}",
                "value": pct,
                "assigned": assigned,
                "total": total
            })
    except ImportError:
        rows = []

    return rows, {}


@register_metric("license_expiry_timeline")
def metric_license_expiry_timeline(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Vencimientos de licencias próximos (próximos 6-12 meses)."""
    try:
        from app.models.alm import ALMLicense

        today = date.today()
        end = today.replace(month=12, day=31) if today.month <= 6 else today.replace(year=today.year + 1, month=6, day=30)

        lics = db.query(ALMLicense).filter(
            ALMLicense.expiry_date.isnot(None),
            ALMLicense.expiry_date >= today,
            ALMLicense.expiry_date <= end,
            ALMLicense.status != "cancelled"
        ).all()

        monthly = {}
        for lic in lics:
            k = str(lic.expiry_date)[:7]
            if k not in monthly:
                monthly[k] = 0
            monthly[k] += 1

        rows = [
            {"label": k, "value": v}
            for k, v in sorted(monthly.items())
        ]
    except ImportError:
        rows = []

    return rows, {}


@register_metric("assets_by_type")
def metric_assets_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Inventario de activos por tipo."""
    try:
        from app.models.alm import ALMAsset

        ASSET_TYPE_LABELS = {
            "laptop": "Portátil",
            "desktop": "Sobremesa",
            "server": "Servidor",
            "phone": "Teléfono",
            "tablet": "Tablet",
            "monitor": "Monitor",
            "printer": "Impresora",
            "other": "Otro"
        }

        rows_raw = db.query(
            ALMAsset.type,
            func.count(ALMAsset.id).label("n")
        ).filter(
            ALMAsset.status != "retired"
        ).group_by(ALMAsset.type).all()

        rows = [
            {
                "label": ASSET_TYPE_LABELS.get(str(r.type).replace("AssetType.", ""), str(r.type)),
                "value": r.n
            }
            for r in rows_raw
        ]
    except ImportError:
        rows = []

    return rows, {}
