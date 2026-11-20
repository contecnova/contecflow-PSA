"""Ficha del proveedor: clasificacion, alta de freelance, ciclo de vida y cuadros."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores.tipos import KINDS, MODES, NO_ACTIVOS, modos


def exigir(db: Session, sub_id: str):
    from app.models.enterprise import Subcontractor
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if sub is None:
        raise error(404, "no_encontrado", detail="Proveedor no encontrado", que="proveedor")
    return sub


def exigir_activo(sub) -> None:
    if (sub.lifecycle_status or "active") in NO_ACTIVOS or sub.is_active is False:
        raise error(409, "proveedor_no_activo", proveedor=sub.name)


def serializar(db: Session, sub) -> dict:
    from app.services.enterprise_service.subcontratas import serialize_subcontractor
    return serialize_subcontractor(sub)


def asignar_a(sub) -> str:
    """A quien se asigna el trabajo de este proveedor."""
    m = modos(sub)
    if (sub.kind or "company") == "freelance":
        return "person"
    persona = "staff_augmentation" in m
    unidad = "outsourcing" in m
    if persona and unidad:
        return "person_and_supplier"
    if persona:
        return "person"
    if unidad:
        return "supplier"
    return "none"


def _personas_activas(db: Session, sub_id: str) -> list:
    from app.models.enterprise import SubcontractorWorker
    return db.query(SubcontractorWorker).filter(SubcontractorWorker.subcontractor_id == sub_id,
                                                SubcontractorWorker.is_active == True).all()  # noqa: E712


def _validar_modos(lista) -> list:
    salida = []
    for m in lista or []:
        if m not in MODES:
            raise error(422, "proveedor_modo_no_valido", modo=m)
        if m not in salida:
            salida.append(m)
    return salida


def clasificar(db: Session, sub, datos: dict, actor) -> dict:
    antes = {"kind": sub.kind, "engagement_modes": sub.engagement_modes}
    if "kind" in datos and datos["kind"] is not None:
        if datos["kind"] not in KINDS:
            raise error(422, "proveedor_tipo_no_valido", tipo=datos["kind"])
        if datos["kind"] == "freelance":
            personas = _personas_activas(db, sub.id)
            if len(personas) > 1:
                raise error(422, "proveedor_freelance_una_persona", n=len(personas))
            sub.freelancer_worker_id = personas[0].id if personas else None
        else:
            sub.freelancer_worker_id = None
        sub.kind = datos["kind"]
    if "engagement_modes" in datos and datos["engagement_modes"] is not None:
        sub.engagement_modes = _validar_modos(datos["engagement_modes"])
    if sub.kind == "freelance" and not modos(sub):
        sub.engagement_modes = ["staff_augmentation"]
    if datos.get("internal_owner_id"):
        from app.services.externos.ciclo import exigir_responsable
        exigir_responsable(db, datos["internal_owner_id"])
    for campo in ("training_enabled", "alm_vendor_id", "internal_owner_id", "legal_name", "website", "address",
                  "data_access", "data_categories", "systems_access"):
        if campo in datos:
            setattr(sub, campo, datos[campo])
    audit_log(db, actor, "UPDATE", "subcontractors", sub.id, sub.name, old_values=antes,
              new_values={k: (v if not hasattr(v, "isoformat") else str(v)) for k, v in datos.items()})
    db.commit()
    db.refresh(sub)
    return serializar(db, sub)


def alta_freelance(db: Session, payload, actor) -> dict:
    """Alta en un paso: proveedor `freelance` + su persona + su usuario (el recurso)
    + su perfil de tarifa y un contrato en borrador con la linea por hora."""
    from app.models.enterprise import Subcontractor, SubcontractorRate
    from app.models.proveedores import SupplierContract, SupplierPricingLine
    from app.schemas.enterprise import WorkerCreate
    from app.services.enterprise_service.subcontratas import create_worker_with_user, next_sub_code
    from app.services.externos.ciclo import exigir_responsable
    from app.services.settings_service.por_empresa import moneda_de_empresa
    datos = payload.model_dump()
    exigir_responsable(db, datos["internal_owner_id"])
    moneda = datos.get("currency") or moneda_de_empresa(db)
    sub = Subcontractor(
        code=next_sub_code(db), name=datos["name"], email=datos.get("email"), phone=datos.get("phone"),
        country=datos.get("country"), vat_number=datos.get("vat_number"), currency=moneda,
        notes=datos.get("notes"), kind="freelance", lifecycle_status="active",
        engagement_modes=_validar_modos(datos.get("engagement_modes")) or ["staff_augmentation"],
        internal_owner_id=datos["internal_owner_id"], training_enabled=bool(datos.get("training_enabled")),
        organization_id=actor.organization_id,
    )
    db.add(sub)
    db.flush()
    worker_in = WorkerCreate(
        name=datos["name"], role=datos.get("role"), email=datos.get("email"), phone=datos.get("phone"),
        cost_rate=datos.get("cost_rate"), sell_rate=datos.get("sell_rate"), currency=moneda,
        available_from=datos.get("available_from"), available_until=datos.get("available_until"),
        weekly_capacity_hours=datos.get("weekly_capacity_hours"), notes=datos.get("notes"),
        internal_owner_id=datos["internal_owner_id"], has_access=datos.get("has_access", True),
        access_until=datos.get("access_until"),
    )
    worker = create_worker_with_user(sub, worker_in, actor, db)   # confirma
    sub.freelancer_worker_id = worker["id"]
    if datos.get("cost_rate"):
        rate = SubcontractorRate(subcontractor_id=sub.id, description=datos.get("role") or datos["name"],
                                 cost_rate=datos["cost_rate"], sell_rate=datos.get("sell_rate"), currency=moneda,
                                 valid_from=datos.get("available_from"), valid_until=datos.get("available_until"),
                                 organization_id=actor.organization_id)
        db.add(rate)
        db.flush()
        contrato = SupplierContract(subcontractor_id=sub.id, title=f"Contrato freelance · {sub.name}",
                                    contract_type="freelance", modes=list(sub.engagement_modes), status="draft",
                                    start_date=datos.get("available_from"), end_date=datos.get("available_until"),
                                    currency=moneda, internal_owner_id=datos["internal_owner_id"],
                                    created_by=actor.id, organization_id=actor.organization_id)
        db.add(contrato)
        db.flush()
        db.add(SupplierPricingLine(contract_id=contrato.id, model="per_resource", unit="hour", rate_id=rate.id,
                                   unit_price=datos["cost_rate"], description=rate.description,
                                   organization_id=actor.organization_id))
    audit_log(db, actor, "CREATE", "subcontractors", sub.id, sub.name,
              new_values={"kind": "freelance", "worker_id": worker["id"], "user_id": worker.get("user_id")})
    db.commit()
    db.refresh(sub)
    salida = {"supplier": serializar(db, sub), "worker": worker, "login_username": worker.get("login_username")}
    if worker.get("temp_password"):
        salida["temp_password"] = worker["temp_password"]
    return salida


def perfil(db: Session, sub) -> dict:
    from app.models.proveedores import SupplierContract, SupplierService, SupplierStatement, SupplierWorkPackage
    from app.services.enterprise_service.subcontratas import serialize_worker
    from app.services.proveedores import grc, rendimiento
    d = serializar(db, sub)
    d["workers"] = [serialize_worker(w) for w in _personas_activas(db, sub.id)]
    d["counts"] = {
        "contracts_active": db.query(SupplierContract).filter(SupplierContract.subcontractor_id == sub.id,
                                                              SupplierContract.status == "active").count(),
        "services_active": db.query(SupplierService).filter(SupplierService.subcontractor_id == sub.id,
                                                            SupplierService.status == "active").count(),
        "work_packages_open": db.query(SupplierWorkPackage).filter(
            SupplierWorkPackage.subcontractor_id == sub.id,
            SupplierWorkPackage.status.in_(("planned", "in_progress", "delivered", "rejected"))).count(),
        "statements_pending": db.query(SupplierStatement).filter(
            SupplierStatement.subcontractor_id == sub.id,
            SupplierStatement.status.in_(("closed", "reconciled", "disputed"))).count(),
    }
    c = grc.cumplimiento(db, sub)
    d["compliance"] = {"status": c["status"], "missing": c["missing"], "expiring": c["expiring"]}
    s = rendimiento.cuadro(db, sub)
    d["scorecard"] = {"score": s["score"], "tone": s["tone"]}
    d["assign_to"] = asignar_a(sub)
    return d


def suspender(db: Session, sub, motivo: Optional[str], actor) -> dict:
    from app.services.externos.ciclo import revocar_sesiones
    if sub.lifecycle_status == "offboarded":
        raise error(409, "proveedor_no_activo", proveedor=sub.name)
    sub.lifecycle_status = "suspended"
    sub.suspended_at = timeutil.today()
    for w in _personas_activas(db, sub.id):
        if w.has_access:
            w.has_access = False
            if w.user_id:
                revocar_sesiones(db, w.user_id)
    audit_log(db, actor, "UPDATE", "subcontractors", sub.id, f"{sub.name}: suspendido",
              new_values={"lifecycle_status": "suspended", "reason": motivo})
    db.commit()
    db.refresh(sub)
    return serializar(db, sub)


def reactivar(db: Session, sub, actor) -> dict:
    if sub.lifecycle_status not in ("suspended", "onboarding"):
        raise error(409, "proveedor_no_suspendido", proveedor=sub.name)
    sub.lifecycle_status = "active"
    sub.suspended_at = None
    audit_log(db, actor, "UPDATE", "subcontractors", sub.id, f"{sub.name}: reactivado",
              new_values={"lifecycle_status": "active"})
    db.commit()
    db.refresh(sub)
    return serializar(db, sub)


def dar_de_baja(db: Session, sub, motivo: Optional[str], actor) -> dict:
    """Offboarding: contratos terminados, servicios acabados, paquetes abiertos
    cancelados, accesos revocados y sus personas de baja (ALM, sesiones, miembros)."""
    from app.models.proveedores import SupplierAccessGrant, SupplierContract, SupplierService, SupplierWorkPackage
    from app.services.externos.ciclo import dar_de_baja as baja_de_persona
    hoy = timeutil.today()
    if sub.lifecycle_status == "offboarded":
        raise error(409, "proveedor_ya_de_baja", proveedor=sub.name)
    resumen = {"contracts": 0, "services": 0, "work_packages": 0, "access_grants": 0, "workers": 0}
    for c in db.query(SupplierContract).filter(SupplierContract.subcontractor_id == sub.id,
                                               SupplierContract.status.in_(("draft", "active", "suspended"))).all():
        c.status = "terminated"
        c.terminated_at = hoy
        resumen["contracts"] += 1
    for s in db.query(SupplierService).filter(SupplierService.subcontractor_id == sub.id,
                                              SupplierService.status != "ended").all():
        s.status = "ended"
        s.end_date = s.end_date if s.end_date and s.end_date < hoy else hoy
        resumen["services"] += 1
    for w in db.query(SupplierWorkPackage).filter(SupplierWorkPackage.subcontractor_id == sub.id,
                                                  SupplierWorkPackage.status.in_(("planned", "in_progress",
                                                                                  "delivered", "rejected"))).all():
        w.status = "cancelled"
        resumen["work_packages"] += 1
    for g in db.query(SupplierAccessGrant).filter(SupplierAccessGrant.subcontractor_id == sub.id,
                                                  SupplierAccessGrant.revoked_at.is_(None)).all():
        g.revoked_at = hoy
        g.revoked_by = actor.id if actor else None
        g.revoke_reason = "offboarding"
        resumen["access_grants"] += 1
    for w in _personas_activas(db, sub.id):
        baja_de_persona(db, w, actor, motivo="baja_proveedor")
        resumen["workers"] += 1
    sub.lifecycle_status = "offboarded"
    sub.offboarded_at = hoy
    sub.offboarding_reason = (motivo or "")[:255] or None
    audit_log(db, actor, "DEACTIVATE", "subcontractors", sub.id, f"{sub.name}: baja", new_values=resumen)
    db.commit()
    db.refresh(sub)
    return {**serializar(db, sub), "offboarding": resumen}


def resumen_global(db: Session) -> dict:
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierStatement
    from app.services.proveedores import facturacion, grc
    from app.services.settings_service.por_empresa import moneda_de_empresa
    subs = db.query(Subcontractor).all()
    por_tipo = {k: 0 for k in KINDS}
    por_modo = {m: 0 for m in MODES}
    por_ciclo = {k: 0 for k in ("onboarding", "active", "suspended", "offboarded")}
    for s in subs:
        if s.is_active is False and (s.lifecycle_status or "active") == "active":
            continue  # borrado logico de antes
        por_tipo[s.kind or "company"] = por_tipo.get(s.kind or "company", 0) + 1
        for m in modos(s):
            por_modo[m] = por_modo.get(m, 0) + 1
        por_ciclo[s.lifecycle_status or "active"] = por_ciclo.get(s.lifecycle_status or "active", 0) + 1
    g = grc.resumen(db)
    return {
        "by_kind": por_tipo, "by_mode": por_modo, "by_lifecycle": por_ciclo,
        "documents_expiring": g["expiring"], "documents_expired": g["expired"],
        "reviews_overdue": g["reviews_overdue"],
        "statements_disputed": db.query(SupplierStatement).filter(SupplierStatement.status == "disputed").count(),
        "statements_pending_approval": db.query(SupplierStatement).filter(
            SupplierStatement.status.in_(("closed", "reconciled"))).count(),
        "forecast_month": facturacion.prevision_del_mes(db), "currency": moneda_de_empresa(db),
    }


def asignables(db: Session, project_id: Optional[str]) -> list:
    """Empresas de outsourcing activas (para «Externalizar a») con sus paquetes abiertos."""
    from app.models.enterprise import Subcontractor
    from app.models.proveedores import SupplierWorkPackage
    salida = []
    for s in db.query(Subcontractor).filter(Subcontractor.is_active == True).order_by(Subcontractor.name).all():  # noqa: E712
        if (s.kind or "company") != "company" or "outsourcing" not in modos(s) \
                or (s.lifecycle_status or "active") in NO_ACTIVOS:
            continue
        q = db.query(SupplierWorkPackage).filter(SupplierWorkPackage.subcontractor_id == s.id,
                                                 SupplierWorkPackage.status.in_(("planned", "in_progress",
                                                                                 "delivered", "rejected")))
        if project_id:
            q = q.filter(SupplierWorkPackage.project_id == project_id)
        salida.append({"id": s.id, "code": s.code, "name": s.name, "kind": s.kind or "company",
                       "work_packages": [{"id": w.id, "title": w.title, "project_id": w.project_id,
                                          "status": w.status} for w in q.all()]})
    return salida
