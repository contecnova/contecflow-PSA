"""Datos reales para los selectores de la ficha del proveedor (migracion 191).

`GET /suppliers/references` devuelve, en una llamada y acotado a la empresa
(TenantSession), lo que la ficha deja elegir y la API ya aceptaba:

- contratos: presupuestos (`budgets`, vigentes: no rechazados ni sustituidos) y
  centros de coste (`alm_cost_centers` activos);
- servicios: contratos ALM (`alm_contracts` activos; primero los del mismo
  proveedor en ALM si la ficha lo enlaza), elementos del catalogo del service
  desk (`sd_service_items`), y para la fuente de medicion de la CMDB: tipos de
  elemento, clases propias y productos de software (`sw_products`, solo lectura);
- paquetes: sesiones UAT del proyecto (`uat_sessions`, si se pasa `project_id`).

Solo id + etiqueta (y el dato minimo para ordenar o agrupar): sin importes de
presupuestos ni datos personales.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session


def _valor(v):
    return getattr(v, "value", v)


def referencias(db: Session, sub=None, project_id: Optional[str] = None) -> dict:
    from app.models.alm import ALMContract, ALMCostCenter
    from app.models.mfa import Budget
    from app.models.service_desk._enums import CIType
    from app.models.service_desk.catalog import ServiceItem

    presupuestos = [
        {"id": b.id, "label": f"{b.name} · {b.year}" + (f" · v{b.version}" if (b.version or 1) > 1 else ""),
         "project_id": b.project_id, "year": b.year, "status": b.estado}
        for b in db.query(Budget).filter(~Budget.estado.in_(("rechazado", "sustituido")))
        .order_by(Budget.year.desc(), Budget.name).limit(500).all()
    ]
    centros = [{"id": c.id, "label": f"{c.code} — {c.name}"}
               for c in db.query(ALMCostCenter).filter(ALMCostCenter.is_active.isnot(False))
               .order_by(ALMCostCenter.code).all()]
    vendor = getattr(sub, "alm_vendor_id", None)
    contratos_alm = []
    for c in db.query(ALMContract).filter(ALMContract.is_active.isnot(False)).order_by(ALMContract.title).limit(500).all():
        contratos_alm.append({"id": c.id, "label": c.title + (f" ({c.reference})" if c.reference else ""),
                              "same_vendor": bool(vendor and c.vendor_id == vendor), "status": _valor(c.status)})
    contratos_alm.sort(key=lambda x: (not x["same_vendor"], x["label"].lower()))
    q_items = db.query(ServiceItem)
    if hasattr(ServiceItem, "is_active"):
        q_items = q_items.filter(ServiceItem.is_active.isnot(False))
    elementos = [{"id": i.id, "label": i.name, "category_id": i.category_id}
                 for i in q_items.order_by(ServiceItem.name).limit(1000).all()]
    uat = []
    if project_id:
        from app.models.client_portal import UATSession
        uat = [{"id": u.id, "label": f"{u.code} — {u.title}", "status": _valor(u.status),
                "deliverable_id": u.deliverable_id}
               for u in db.query(UATSession).filter(UATSession.project_id == project_id)
               .order_by(UATSession.code).all()]
    return {
        "budgets": presupuestos, "cost_centers": centros, "alm_contracts": contratos_alm,
        "service_items": elementos, "uat_sessions": uat,
        "ci_types": [t.value for t in CIType], "ci_classes": _clases(db), "software_products": _productos(db),
    }


def _clases(db: Session) -> list[dict]:
    try:
        from app.models.service_desk.mercado import CIClass
    except ImportError:  # pragma: no cover - modelo opcional
        return []
    filas = db.query(CIClass).filter(CIClass.is_active.isnot(False)).order_by(CIClass.sort_order, CIClass.key).all()
    return [{"id": c.key, "label": c.label or c.key, "base": c.base_type} for c in filas]


def _productos(db: Session) -> list[dict]:
    """Productos de software de la CMDB (solo lectura de `app/models/cmdb_software.py`)."""
    try:
        from app.models.cmdb_software import SoftwareProduct
    except ImportError:  # pragma: no cover
        return []
    return [{"id": p.id, "label": p.name + (f" · {p.vendor_name}" if p.vendor_name else "")}
            for p in db.query(SoftwareProduct).filter(SoftwareProduct.is_active.isnot(False))
            .order_by(SoftwareProduct.name).limit(1000).all()]
