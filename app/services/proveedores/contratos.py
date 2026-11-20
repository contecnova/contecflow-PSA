"""Contratos de proveedor, plantillas y lineas de precio (modelos de cobro)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import CONTRACT_TYPES, MODES, PRICING_MODELS, modos


def _q(db: Session):
    from app.models.proveedores import SupplierContract
    return db.query(SupplierContract).options(joinedload(SupplierContract.lines))


def exigir(db: Session, contrato_id: str, plantilla: Optional[bool] = False):
    """`plantilla`: False contrato, True plantilla, None cualquiera (lineas de precio)."""
    from app.models.proveedores import SupplierContract
    q = _q(db).filter(SupplierContract.id == contrato_id)
    if plantilla is not None:
        q = q.filter(SupplierContract.is_template == plantilla)
    c = q.first()
    if c is None:
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    return c


def _validar(db: Session, c, sub=None) -> None:
    if c.contract_type not in CONTRACT_TYPES:
        raise error(422, "proveedor_tipo_de_contrato_no_valido", tipo=c.contract_type)
    for m in c.modes or []:
        if m not in MODES:
            raise error(422, "proveedor_modo_no_valido", modo=m)
        if sub is not None and modos(sub) and m not in modos(sub):
            raise error(422, "proveedor_modo_no_contratado", modo=m, proveedor=sub.name)
    if c.start_date and c.end_date and c.end_date < c.start_date:
        raise error(422, "proveedor_fechas_no_validas")
    # Migracion 191: presupuesto y centro de coste elegibles en la ficha (de la empresa).
    from app.models.alm import ALMCostCenter
    from app.models.mfa import Budget
    from app.models.project import Project
    if c.budget_id and not db.query(Budget.id).filter(Budget.id == c.budget_id).first():
        raise error(404, "no_encontrado", detail="Presupuesto no encontrado", que="presupuesto")
    if c.cost_center_id and not db.query(ALMCostCenter.id).filter(ALMCostCenter.id == c.cost_center_id).first():
        raise error(404, "no_encontrado", detail="Centro de coste no encontrado", que="centro_de_coste")
    if c.project_id and not db.query(Project.id).filter(Project.id == c.project_id).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")


def listar(db: Session, sub_id: str) -> list:
    from app.models.proveedores import SupplierContract
    filas = _q(db).filter(SupplierContract.subcontractor_id == sub_id, SupplierContract.is_template == False)  # noqa: E712
    return [ser.contrato(c) for c in filas.order_by(SupplierContract.created_at.desc()).all()]


def crear(db: Session, sub, datos: dict, actor, plantilla: bool = False) -> dict:
    from app.models.proveedores import SupplierContract
    datos = {k: v for k, v in datos.items() if v is not None}
    if not datos.get("title"):
        raise error(422, "campo_obligatorio", campo="title")
    c = SupplierContract(subcontractor_id=sub.id if sub else None, is_template=plantilla, status="draft",
                         created_by=actor.id, **datos)
    c.contract_type = c.contract_type or ("freelance" if sub is not None and sub.kind == "freelance" else "framework")
    if sub is not None:
        c.currency = c.currency or sub.currency
        c.modes = c.modes or list(sub.engagement_modes or [])
    _validar(db, c, sub)
    db.add(c)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_contracts", c.id, c.title,
              new_values={"subcontractor_id": c.subcontractor_id, "is_template": plantilla, "type": c.contract_type})
    db.commit()
    return ser.contrato(exigir(db, c.id, plantilla))


def actualizar(db: Session, c, datos: dict, actor) -> dict:
    from app.models.enterprise import Subcontractor
    if c.status in ("terminated", "expired"):
        raise error(409, "proveedor_contrato_cerrado")
    antes = ser.contrato(c, lineas=False)
    for k, v in datos.items():
        setattr(c, k, v)
    _validar(db, c, db.get(Subcontractor, c.subcontractor_id) if c.subcontractor_id else None)
    audit_log(db, actor, "UPDATE", "supplier_contracts", c.id, c.title,
              old_values={k: antes.get(k) for k in datos},
              new_values={k: (str(v) if hasattr(v, "isoformat") else v) for k, v in datos.items()})
    db.commit()
    return ser.contrato(exigir(db, c.id, bool(c.is_template)))


def activar(db: Session, c, actor) -> dict:
    """Activar exige el proveedor activo y sus requisitos de GRC (DPA, NDA, certificaciones, seguro)."""
    from app.models.enterprise import Subcontractor
    from app.services.proveedores import ficha, grc
    sub = db.get(Subcontractor, c.subcontractor_id)
    ficha.exigir_activo(sub)
    faltan = grc.cumplimiento(db, sub)["missing"]
    if faltan:
        raise error(409, "proveedor_requisitos_grc_pendientes", faltan=", ".join(faltan))
    if c.status not in ("draft", "suspended"):
        raise error(409, "proveedor_contrato_cerrado")
    c.status = "active"
    if sub.lifecycle_status == "onboarding":
        sub.lifecycle_status = "active"
    audit_log(db, actor, "APPROVE", "supplier_contracts", c.id, c.title, new_values={"status": "active"})
    db.commit()
    return ser.contrato(exigir(db, c.id))


def terminar(db: Session, c, actor) -> dict:
    from app.core import timeutil
    if c.status in ("terminated", "expired"):
        raise error(409, "proveedor_contrato_cerrado")
    c.status = "terminated"
    c.terminated_at = timeutil.today()
    audit_log(db, actor, "UPDATE", "supplier_contracts", c.id, c.title, new_values={"status": "terminated"})
    db.commit()
    return ser.contrato(exigir(db, c.id))


def listar_plantillas(db: Session) -> list:
    from app.models.proveedores import SupplierContract
    return [ser.contrato(c) for c in _q(db).filter(SupplierContract.is_template == True)  # noqa: E712
            .order_by(SupplierContract.title).all()]


def borrar_plantilla(db: Session, c, actor) -> dict:
    audit_log(db, actor, "DELETE", "supplier_contracts", c.id, c.title, old_values={"is_template": True})
    db.delete(c)
    db.commit()
    return {"ok": True}


def desde_plantilla(db: Session, sub, plantilla, actor) -> dict:
    """Copia la plantilla (con sus lineas) como contrato en borrador del proveedor."""
    from app.models.proveedores import SupplierContract, SupplierPricingLine
    campos = ("title", "contract_type", "modes", "notice_days", "currency", "committed_minimum", "minimum_period",
              "total_cap", "payment_terms_days", "expenses_rebillable", "expenses_cap", "notes", "auto_renew")
    c = SupplierContract(subcontractor_id=sub.id, is_template=False, status="draft", created_by=actor.id,
                         **{k: getattr(plantilla, k) for k in campos})
    c.title = f"{plantilla.title} · {sub.name}"[:255]
    c.currency = c.currency or sub.currency
    c.modes = [m for m in (c.modes or []) if not modos(sub) or m in modos(sub)] or list(sub.engagement_modes or [])
    _validar(db, c, sub)
    db.add(c)
    db.flush()
    for x in plantilla.lines or []:
        if x.is_active is False:
            continue
        db.add(SupplierPricingLine(
            contract_id=c.id, model=x.model, unit=x.unit, description=x.description, unit_price=x.unit_price,
            period=x.period, included_units=x.included_units, overage_price=x.overage_price, tiers=x.tiers,
            min_amount=x.min_amount, max_amount=x.max_amount))
    audit_log(db, actor, "CREATE", "supplier_contracts", c.id, c.title, new_values={"from_template": plantilla.id})
    db.commit()
    return ser.contrato(exigir(db, c.id))


# ── Lineas de precio ─────────────────────────────────────────────────────────

def _tramos(tiers) -> list:
    salida = []
    for t in tiers or []:
        d = t if isinstance(t, dict) else t.model_dump(by_alias=True)
        desde = float(d.get("from", d.get("desde", 0)) or 0)
        hasta = d.get("to", d.get("hasta"))
        if hasta is not None and float(hasta) <= desde:
            raise error(422, "proveedor_tramos_no_validos")
        salida.append({"from": desde, "to": float(hasta) if hasta is not None else None, "price": float(d["price"])})
    salida.sort(key=lambda t: t["from"])
    for a, b in zip(salida, salida[1:]):
        if a["to"] is None or a["to"] > b["from"]:
            raise error(422, "proveedor_tramos_no_validos")
    return salida


def _validar_linea(db: Session, x, c) -> None:
    from app.models.enterprise import SubcontractorRate
    from app.models.proveedores import SupplierService, SupplierWorkPackage
    if x.model not in PRICING_MODELS:
        raise error(422, "proveedor_modelo_no_valido", modelo=x.model)
    if x.min_amount is not None and x.max_amount is not None and x.max_amount < x.min_amount:
        raise error(422, "proveedor_minimo_mayor_que_tope")
    if x.model == "per_resource" and not x.unit:
        x.unit = "hour"
    if x.model in ("per_resource", "per_unit") and x.unit_price is None and not x.tiers:
        raise error(422, "proveedor_linea_sin_precio")
    if x.model == "subscription" and x.unit_price is None:
        raise error(422, "proveedor_linea_sin_precio")
    if x.rate_id and c.subcontractor_id and not db.query(SubcontractorRate.id).filter(
            SubcontractorRate.id == x.rate_id, SubcontractorRate.subcontractor_id == c.subcontractor_id).first():
        raise error(422, "externo_tarifa_no_valida")
    if x.service_id and not db.query(SupplierService.id).filter(
            SupplierService.id == x.service_id, SupplierService.subcontractor_id == c.subcontractor_id).first():
        raise error(404, "no_encontrado", detail="Servicio no encontrado", que="servicio")
    if x.work_package_id and not db.query(SupplierWorkPackage.id).filter(
            SupplierWorkPackage.id == x.work_package_id,
            SupplierWorkPackage.subcontractor_id == c.subcontractor_id).first():
        raise error(404, "no_encontrado", detail="Paquete no encontrado", que="paquete_de_trabajo")


def crear_linea(db: Session, c, datos: dict, actor) -> dict:
    from app.models.proveedores import SupplierPricingLine
    datos = {k: v for k, v in datos.items() if v is not None}
    if not datos.get("model"):
        raise error(422, "campo_obligatorio", campo="model")
    if "tiers" in datos:
        datos["tiers"] = _tramos(datos["tiers"])
    x = SupplierPricingLine(contract_id=c.id, **datos)
    _validar_linea(db, x, c)
    db.add(x)
    db.flush()
    audit_log(db, actor, "CREATE", "supplier_pricing_lines", x.id, c.title,
              new_values={"model": x.model, "unit": x.unit, "unit_price": x.unit_price})
    db.commit()
    db.refresh(x)
    return ser.linea(x)


def exigir_linea(db: Session, linea_id: str):
    from app.models.proveedores import SupplierPricingLine
    x = db.query(SupplierPricingLine).filter(SupplierPricingLine.id == linea_id).first()
    if x is None:
        raise error(404, "no_encontrado", detail="Línea de precio no encontrada", que="linea_de_precio")
    return x


def actualizar_linea(db: Session, x, datos: dict, actor) -> dict:
    if "tiers" in datos:
        datos["tiers"] = _tramos(datos["tiers"])
    antes = ser.linea(x)
    for k, v in datos.items():
        setattr(x, k, v)
    _validar_linea(db, x, x.contract)
    audit_log(db, actor, "UPDATE", "supplier_pricing_lines", x.id, x.contract.title,
              old_values={k: antes.get(k) for k in datos},
              new_values={k: (str(v) if hasattr(v, "isoformat") else v) for k, v in datos.items()})
    db.commit()
    db.refresh(x)
    return ser.linea(x)


def borrar_linea(db: Session, x, actor) -> dict:
    x.is_active = False
    audit_log(db, actor, "DELETE", "supplier_pricing_lines", x.id, x.contract.title)
    db.commit()
    return {"ok": True}
