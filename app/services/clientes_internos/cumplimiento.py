"""Controles de clientes internos en el informe de cumplimiento (docs/CLIENTES_INTERNOS.md §7).

Mismo patrón que `cmdb_software/cumplimiento.py`: `controles(db, org, _control)`.

- ``internal_units_owner``: unidades internas sin responsable de negocio.
- ``internal_units_budget``: unidades con chargeback/intercompañía sin
  presupuesto aprobado del año.
- ``internal_charges_sod``: cargos aprobados por quien los generó o emitió
  (debe ser 0; se mide en el registro de auditoría).
- ``internal_charges_pending``: cargos por aprobar (exceso de presupuesto) de
  hace más de 30 días.
- ``internal_chargeback_erp``: unidades con chargeback sin cuenta ERP.

Sin unidades internas, todos son `info` (no hay nada que medir todavía).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MARCOS = ("ISO27001 A.5.2", "SOC2 CC1.3")
MARCOS_SOD = ("ISO27001 A.5.3", "SOC2 CC5.1")


def controles(db, org, _control) -> list[dict]:
    from app.core import timeutil
    from app.models.clientes_internos import InternalCharge
    from app.models.clients import Client
    from app.models.enterprise import AuditLog
    from app.models.mfa import Budget

    unidades = db.query(Client).filter(Client.organization_id == org, Client.kind == "interno",
                                       Client.is_active.is_(True)).all()
    hay = bool(unidades)
    salida = []

    sin_resp = [u.name for u in unidades if not u.business_owner_id]
    salida.append(_control("internal_units_owner", "info" if not hay else ("attention" if sin_resp else "pass"),
                           {"internal_units": len(unidades), "without_owner": len(sin_resp),
                            "names": sin_resp[:20]},
                           "clients (kind=interno).business_owner_id", MARCOS))

    year = timeutil.today().year
    con_cargo = [u for u in unidades if u.finance_mode in ("chargeback", "intercompania")]
    con_presupuesto = {b for (b,) in db.query(Budget.cliente_id).filter(
        Budget.cliente_id.in_([u.id for u in con_cargo] or [""]), Budget.year == year, Budget.estado == "aprobado")}
    sin_pres = [u.name for u in con_cargo if u.id not in con_presupuesto]
    salida.append(_control("internal_units_budget", "info" if not con_cargo else ("attention" if sin_pres else "pass"),
                           {"year": year, "charged_units": len(con_cargo), "without_budget": len(sin_pres),
                            "names": sin_pres[:20]},
                           "budgets aprobados con cliente_id de unidades con chargeback o intercompañía",
                           ("ISO27001 A.5.2",)))

    cargos = {c.id: c for c in db.query(InternalCharge).filter(InternalCharge.organization_id == org)}
    infracciones = 0
    if cargos:
        for a in db.query(AuditLog).filter(AuditLog.resource == "internal_charge", AuditLog.action == "APPROVE",
                                           AuditLog.resource_id.in_(list(cargos))):
            c = cargos.get(a.resource_id)
            if c is not None and a.user_id and a.user_id == c.created_by:
                infracciones += 1
    salida.append(_control("internal_charges_sod", "info" if not cargos else ("attention" if infracciones else "pass"),
                           {"charges": len(cargos), "approved_by_creator": infracciones},
                           "audit_logs APPROVE de internal_charge frente a internal_charges.created_by", MARCOS_SOD))

    limite = datetime.now(timezone.utc) - timedelta(days=30)
    viejos = sum(1 for c in cargos.values() if c.status == "por_aprobar" and c.created_at is not None
                 and (c.created_at if c.created_at.tzinfo else c.created_at.replace(tzinfo=timezone.utc)) < limite)
    salida.append(_control("internal_charges_pending", "info" if not cargos else ("attention" if viejos else "pass"),
                           {"pending_over_budget": sum(1 for c in cargos.values() if c.status == "por_aprobar"),
                            "older_than_30_days": viejos},
                           "internal_charges en por_aprobar", ("SOC2 CC5.1",)))

    sin_cuenta = [u.name for u in unidades if u.finance_mode == "chargeback" and not (u.erp_account or "").strip()]
    salida.append(_control("internal_chargeback_erp",
                           "info" if not hay else ("attention" if sin_cuenta else "pass"),
                           {"without_erp_account": len(sin_cuenta), "names": sin_cuenta[:20]},
                           "clients (kind=interno, finance_mode=chargeback).erp_account", ("SOC2 CC3.2",)))
    return salida
