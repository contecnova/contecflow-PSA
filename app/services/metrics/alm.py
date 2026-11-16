"""ALM metrics: license_cost_by_vendor, license_utilization, license_expiry_timeline,
assets_by_type.

Fase 1 de licencias y hardware (16-11-2026): las cuatro filtraban solo por
estado y contaban licencias y activos borrados (``is_active = False``); ahora
no. Los asientos usados son la cantidad de las asignaciones de primer nivel
(una bolsa ocupa sus asientos; sus hijas no suman otra vez). En «activos por
tipo» el tipo era ``phone`` (no existe: es ``mobile``) y faltaban cuatro
tipos; cada fila lleva ahora su ``code`` para que la interfaz lo traduzca.
"""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from ._registro import register_metric
from app.core import timeutil


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
        from app.models.alm import ALMLicense, ALMVendor

        q = db.query(
            ALMVendor.name.label("vendor_name"),
            func.sum(func.coalesce(ALMLicense.annual_cost, 0)).label("cost"),
            func.count(ALMLicense.id).label("count")
        ).outerjoin(
            ALMVendor,
            ALMLicense.vendor_id == ALMVendor.id
        ).filter(
            ALMLicense.status != "cancelled",
            ALMLicense.is_active.is_(True),
        ).group_by(
            ALMVendor.name
        ).order_by(
            func.sum(func.coalesce(ALMLicense.annual_cost, 0)).desc()
        ).limit(top_n)

        rows = [
            {
                "label": r.vendor_name or "Desconocido",
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
        from app.models.alm import ALMLicense, ALMVendor, ALMAsignacion

        q = db.query(
            ALMLicense.name.label("license_name"),
            ALMVendor.name.label("vendor_name"),
            ALMLicense.total_seats.label("total_seats"),
            func.coalesce(func.sum(ALMAsignacion.quantity), 0).label("assigned")
        ).outerjoin(
            ALMVendor,
            ALMLicense.vendor_id == ALMVendor.id
        ).outerjoin(
            ALMAsignacion,
            (ALMAsignacion.license_id == ALMLicense.id) &
            (ALMAsignacion.parent_id.is_(None)) &
            (ALMAsignacion.status.in_(("active", "pending")))
        ).filter(
            ALMLicense.status != "cancelled",
            ALMLicense.is_active.is_(True),
        ).group_by(
            ALMLicense.id,
            ALMLicense.name,
            ALMVendor.name,
            ALMLicense.total_seats
        ).limit(top_n)

        rows = []
        for r in q.all():
            total = r.total_seats or 0
            assigned = r.assigned or 0
            pct = round(assigned / total * 100, 1) if total else 0
            rows.append({
                "label": f"{r.vendor_name or 'Desconocido'}/{r.license_name}",
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

        today = timeutil.today()
        end = today.replace(month=12, day=31) if today.month <= 6 else today.replace(year=today.year + 1, month=6, day=30)

        lics = db.query(ALMLicense).filter(
            ALMLicense.expiry_date.isnot(None),
            ALMLicense.expiry_date >= today,
            ALMLicense.expiry_date <= end,
            ALMLicense.status != "cancelled",
            ALMLicense.is_active.is_(True),
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

        # Etiqueta por defecto del informe; la interfaz traduce `code` (`alm.asset_type_<code>`).
        ASSET_TYPE_LABELS = {
            "laptop": "Portátil",
            "desktop": "Sobremesa",
            "server": "Servidor",
            "mobile": "Móvil",
            "tablet": "Tablet",
            "network": "Red",
            "printer": "Impresora",
            "monitor": "Monitor",
            "peripheral": "Periférico",
            "vm": "Máquina virtual",
            "other": "Otro",
        }

        rows_raw = db.query(
            ALMAsset.type,
            func.count(ALMAsset.id).label("n")
        ).filter(
            ALMAsset.status.notin_(("retired", "disposed")),
            ALMAsset.is_active.is_(True),
        ).group_by(ALMAsset.type).all()

        rows = []
        for r in rows_raw:
            code = getattr(r.type, "value", str(r.type))
            rows.append({"label": ASSET_TYPE_LABELS.get(code, code), "code": code, "value": r.n})
    except ImportError:
        rows = []

    return rows, {}
