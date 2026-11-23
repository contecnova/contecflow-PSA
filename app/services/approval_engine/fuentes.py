"""Gastos, partes de horas y ausencias en la bandeja de aprobaciones.

Auditoria 2026-11: el disenador de flujos ofrecia estos tipos, pero nada abria
solicitudes para ellos; cada uno se revisaba solo en su pantalla y la bandeja
nunca los veia. Ahora:

- al enviar (gasto, parte de horas) o pedir (ausencia), si la organizacion
  tiene un flujo por defecto activo para ese tipo, se abre una solicitud;
  sin flujo, todo sigue como antes;
- la decision final de la bandeja aplica la revision de siempre
  (`review_expense`, `review_timesheet_flow`, `review_absence`);
- si se revisa desde la pantalla de origen, la solicitud pendiente se cierra
  con esa decision, para que no se quede en la bandeja.

Tipos (los del disenador): `expense`, `timesheet`, `leave`, `change_request`
(Cambios: al enviar), `invoice` (facturas: al pasar de borrador a enviada; la
aprobacion la envia, el rechazo la deja en borrador) y `budget` (presupuestos:
al enviar; la decision los aprueba o los rechaza) y `alm_assignment`
(licencias y hardware: al asignar; la aprobacion la activa, el rechazo la
cierra como rechazada).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

TIPOS = ("expense", "timesheet", "leave", "change_request", "invoice", "budget", "budget_transfer",
         "alm_assignment", "license_reclaim", "portfolio_gate",
         # Service desk, mejoras de mercado 16-11-2026: peticiones del catalogo
         # con aprobacion multinivel (`catalog_approval_service`, modo `engine`).
         "catalog_request",
         # Horas extra (rev. 184, 18-11-2026): `app/services/horas_extra/solicitudes.py`.
         "overtime",
         # CMDB de software (19-11-2026): excepción de vulnerabilidad con caducidad
         # (`app/services/cmdb_software/gestion.py`).
         "vuln_exception",
         # Proveedores (migración 191): estado de cuenta / factura del proveedor
         # por importe (`app/services/proveedores/facturacion.py`).
         "supplier_statement",
         # Flujo de demanda (migración 195): un paso delegado en un flujo del motor
         # (`app/services/demanda/motor.py`, entity_id = demand_step_states.id).
         "demand_step",
         # Clientes internos (rev. 193): cargo interno que excede el presupuesto
         # de la unidad (`app/services/clientes_internos/cargos.py`).
         "internal_charge")


def abrir(db: Session, tipo: str, entidad_id: str, resumen: str, solicitante_id: str,
          contexto: Optional[dict] = None, evaluacion: Optional[dict] = None,
          workflow_id: Optional[str] = None, propagar: bool = False) -> None:
    """Abre la solicitud si hay flujo por defecto para el tipo; si no, nada.

    `workflow_id` (tarea #25): el flujo concreto que pide la entidad (el flujo
    por defecto de un tipo de ausencia); si está activo, manda sobre el
    elegido por condiciones.

    `evaluacion` (motor de políticas, #26): lo que devolvió
    `politicas.evaluar`. Su contexto se guarda en la solicitud (para las ramas
    del diseñador) junto a su resumen (`_politica`, el indicador de la bandeja),
    y su resultado añade niveles, pasos y avisos, o la aprueba sola
    (`create_approval_request(politicas=…)`).

    Rev. 166 (#27): si no hay flujo pero las políticas piden niveles o pasos,
    la solicitud se abre igualmente SOLO con esos pasos (sin flujo): una
    política que pide «+2 niveles» no se pierde porque la empresa no haya
    diseñado un flujo.
    """
    if evaluacion:
        from app.services.politicas.catalogo import dominio_de_aprobacion
        from app.services.politicas.motor import resumen as resumen_de_politica
        dom = dominio_de_aprobacion(tipo)
        contexto = {**(evaluacion.get("contexto") or {}), **(contexto or {}),
                    "_politica": {**resumen_de_politica(evaluacion), "dominio": dom.clave if dom else None}}
    from app.models.user import User
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine._base import elegir_flujo
    from app.services.approval_engine.requests import create_approval_request

    solicitante = db.query(User).filter(User.id == solicitante_id).first()
    if not solicitante:
        return
    resultado = (evaluacion or {}).get("resultado") or {}
    solo_politicas = bool(resultado.get("niveles") or resultado.get("pasos"))
    if workflow_id:
        from app.models.billing_reports import ApprovalWorkflow
        if db.query(ApprovalWorkflow.id).filter(ApprovalWorkflow.id == workflow_id,
                                                ApprovalWorkflow.is_active.is_(True)).first() is None:
            workflow_id = None
    if not workflow_id and not elegir_flujo(db, tipo, {**(contexto or {}), "department": solicitante.department})             and not solo_politicas:
        return
    try:
        create_approval_request(
            ApprovalRequestIn(entity_type=tipo, entity_id=entidad_id, entity_summary=resumen[:500],
                              context=contexto or {}, workflow_id=workflow_id),
            db, solicitante, politicas=(evaluacion or {}).get("resultado"), de_confianza=True)
    except Exception:
        # M106 (auditoría 22-11-2026): con `propagar`, el fallo sube y quien llama
        # deshace TODO el envío (misma transacción): no queda una entidad
        # «enviada» sin solicitud de aprobación.
        if propagar:
            raise
        # El envio ya esta guardado; su pantalla de revision sigue valiendo.
        db.rollback()
        logger.exception("no se pudo abrir la aprobacion de %s %s", tipo, entidad_id)


def aplicar(req, decision: str, actor, db: Session) -> None:
    """Decision final de la bandeja sobre la entidad de origen."""
    aprobado = decision == "approved"
    nota = req.final_note
    try:
        if req.entity_type == "expense":
            from app.services.expense_service import review_expense
            review_expense(req.entity_id, aprobado, None if aprobado else nota, actor, db)
        elif req.entity_type == "timesheet":
            from app.services.psa_flows import review_timesheet_flow
            review_timesheet_flow(db, req.entity_id, actor, aprobado, nota)
        elif req.entity_type == "leave":
            from app.models.resources import AbsenceStatus
            from app.services import absence_service
            ausencia = absence_service.get_absence_by_id(db, req.entity_id)
            if ausencia and ausencia.status == AbsenceStatus.pending:
                absence_service.review_absence(db, ausencia, approved=aprobado, approver_id=actor.id,
                                               rejection_reason=None if aprobado else nota)
        elif req.entity_type == "change_request":
            from app.services import change_service
            cr = change_service.get_by_id(db, req.entity_id)
            if cr and getattr(cr.status, "value", cr.status) in ("submitted", "under_review"):
                change_service.review_change_request(db, cr, approved=aprobado, reviewer_id=actor.id,
                                                     resolution_notes=nota)
        elif req.entity_type == "budget":
            from app.services.budgets_service import aplicar_desde_bandeja
            from app.models.mfa import Budget
            b = db.query(Budget).filter(Budget.id == req.entity_id).first()
            if b and b.estado == "enviado":
                aplicar_desde_bandeja(db, actor, b.id, aprobado, nota)
        elif req.entity_type == "budget_transfer":
            from app.models.mfa import BudgetTransfer
            from app.services.presupuestos_seguir import aplicar_desde_bandeja as aplicar_traspaso
            t = db.query(BudgetTransfer).filter(BudgetTransfer.id == req.entity_id).first()
            if t and t.estado == "pendiente":
                aplicar_traspaso(db, actor, t.id, aprobado, nota)
        elif req.entity_type == "alm_assignment":
            # Licencias y hardware, fase 1: asignar una licencia o un equipo con aprobación.
            from app.services.alm_asignaciones import aplicar_decision
            aplicar_decision(db, req.entity_id, aprobado, actor, nota)
        elif req.entity_type == "license_reclaim":
            # Licencias y hardware, fase 2: aprobar libera la licencia sin uso; rechazar la conserva.
            from app.services.alm_uso.recuperacion import aplicar_desde_bandeja as aplicar_recuperacion
            aplicar_recuperacion(req, decision, actor, db)
        elif req.entity_type == "vuln_exception":
            # CMDB de software: aprobada, el hallazgo pasa a riesgo aceptado hasta su caducidad.
            from app.services.cmdb_software.gestion import aplicar_desde_bandeja as aplicar_excepcion
            aplicar_excepcion(db, req.entity_id, aprobado, actor, nota)
        elif req.entity_type == "portfolio_gate":
            # Cartera (rev. 173): la fase de una propuesta; aprobada, pasa a la siguiente.
            from app.services.cartera_service import aplicar_decision as aplicar_fase
            aplicar_fase(db, req.entity_id, aprobado, actor, nota)
        elif req.entity_type == "catalog_request":
            from app.services.service_desk.catalog_approval_service import aplicar_decision_del_motor
            aplicar_decision_del_motor(db, req.entity_id, "approved" if aprobado else "rejected", actor, nota)
        elif req.entity_type == "overtime":
            from app.services.horas_extra.solicitudes import aplicar_desde_bandeja as aplicar_horas_extra
            aplicar_horas_extra(req, decision, actor, db)
        elif req.entity_type == "supplier_statement":
            # Proveedores (migración 191): aprobado, el estado de cuenta y su factura quedan aprobados;
            # rechazado, en disputa con la nota de la bandeja.
            from app.services.proveedores.facturacion import aplicar_desde_bandeja as aplicar_estado_de_cuenta
            aplicar_estado_de_cuenta(db, req.entity_id, aprobado, actor, nota)
        elif req.entity_type == "demand_step":
            # Flujo de demanda: la decisión de la bandeja es la del paso, con su actor real.
            from app.services.demanda.motor import aplicar_desde_bandeja as aplicar_paso_de_demanda
            aplicar_paso_de_demanda(req, decision, actor, db)
        elif req.entity_type == "internal_charge":
            # Clientes internos (rev. 193): aprobado, el cargo se emite; rechazado, vuelve a borrador.
            from app.services.clientes_internos.cargos import aplicar_desde_bandeja as aplicar_cargo
            aplicar_cargo(db, req.entity_id, aprobado, actor, nota)
        elif req.entity_type == "invoice":
            from app.models.billing_reports import Invoice, InvoiceStatus
            inv = db.query(Invoice).filter(Invoice.id == req.entity_id).first()
            if aprobado and inv and getattr(inv.status, "value", inv.status) == "draft":
                inv.status = InvoiceStatus.sent
                db.commit()
    except ErrorDeDominio as exc:
        # Ya no estaba pendiente (revisada, retirada o cancelada en su pantalla).
        logger.info("aprobacion %s: %s %s no aplicada: %s", req.id, req.entity_type, req.entity_id, exc.detail)


def comprobar_antes(req, decision: str, db: Session, actor=None) -> None:
    """Antes de anotar una aprobación en la bandeja: lo que la impediría en su pantalla.

    El control presupuestario de un gasto con `BUDGET_CONTROL_POLICY = bloquear`
    responde 409 aquí, y no después de dar la solicitud por aprobada.

    Horas extra (18-11-2026): nadie vota sobre las suyas ni sobre las que pidió
    para otra persona (la solicitud lleva como solicitante a la persona, así que
    el control general de la bandeja no ve a quien las pidió en su nombre).
    """
    if req.entity_type == "overtime":
        from app.services.horas_extra.solicitudes import comprobar_en_bandeja
        comprobar_en_bandeja(req, actor, db)
        return
    if req.entity_type == "supplier_statement":
        # Proveedores (migración 191): no aprueba quien cerró el periodo ni quien registró la factura.
        from app.services.proveedores.facturacion import comprobar_en_bandeja as segregacion_del_estado
        segregacion_del_estado(req, actor, db, decision)
        return
    if req.entity_type == "internal_charge":
        # Clientes internos (rev. 193): no decide quien generó ni quien emitió el cargo.
        from app.services.clientes_internos.cargos import comprobar_en_bandeja as segregacion_del_cargo
        segregacion_del_cargo(req, actor, db, decision)
        return
    if decision != "approved" or req.entity_type != "expense":
        return
    from app.models.expenses import Expense, ExpenseStatus
    from app.services.presupuestos_seguir import control_de_gasto
    gasto = db.query(Expense).filter(Expense.id == req.entity_id).first()
    if gasto is not None and gasto.status == ExpenseStatus.submitted:
        control_de_gasto(db, gasto)


def cerrar(db: Session, tipo: str, entidad_id: str, estado: str, nota: str) -> None:
    """La entidad se decidio fuera de la bandeja: cierra su solicitud pendiente.

    `estado`: approved, rejected o cancelled. No hace commit; lo hace quien llama.
    """
    from app.models.billing_reports import ApprovalRequest
    for req in db.query(ApprovalRequest).filter(
        ApprovalRequest.entity_type == tipo, ApprovalRequest.entity_id == entidad_id,
        ApprovalRequest.status == "pending",
    ):
        req.status = estado
        req.final_decision = estado
        req.final_note = nota
        req.completed_at = datetime.now(timezone.utc)


def estado(db: Session, tipo: str, entidad_id: str) -> Optional[str]:
    """Estado de la ultima solicitud de esa entidad (pending, approved…), o None."""
    from app.models.billing_reports import ApprovalRequest
    req = db.query(ApprovalRequest).filter(
        ApprovalRequest.entity_type == tipo, ApprovalRequest.entity_id == entidad_id,
    ).order_by(ApprovalRequest.created_at.desc()).first()
    return req.status if req else None


# ── Contexto de confianza (auditoría 22-11-2026, C1) ─────────────────────────
#
# `POST /approvals/requests` aceptaba `context` del cliente y con él decidía la
# auto-aprobación, el flujo y las condiciones de los pasos: `{"amount": 1}` en
# un gasto de 50.000 lo dejaba aprobado. Ahora el contexto que deciden las
# reglas sale de la ENTIDAD REAL (por entity_type/entity_id, de la empresa de
# quien pide); lo que manda el cliente se guarda aparte (`_cliente`), solo
# como dato informativo para quien aprueba.

def _num(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _val(v):
    return getattr(v, "value", v)


def _cargar(db: Session, modulo: str, clase: str, entidad_id: str, org_id: Optional[str]):
    import importlib
    modelo = getattr(importlib.import_module(modulo), clase)
    q = db.query(modelo).filter(modelo.id == entidad_id)
    if org_id and hasattr(modelo, "organization_id"):
        q = q.filter(modelo.organization_id == org_id)
    return q.first()


#: entity_type -> (módulo, clase, cómo sacar el contexto de la fila). Las claves
#: son las MISMAS que ponen los dominios al abrir su solicitud (`abrir(...)`),
#: para que una regla o una condición de paso signifique lo mismo venga de
#: donde venga la solicitud.
_ENTIDADES = {
    "expense": ("app.models.expenses", "Expense",
                lambda e: {"amount": _num(e.amount), "currency": e.currency,
                           "category": str(_val(e.category)) if e.category is not None else None,
                           "project_id": e.project_id, "_solicitante": e.user_id}),
    "invoice": ("app.models.billing_reports", "Invoice",
                lambda i: {"amount": _num(i.total), "currency": i.currency, "project_id": i.project_id}),
    "budget": ("app.models.mfa", "Budget",
               lambda b: {"amount": _num(b.total_amount), "currency": b.currency, "category": b.ambito,
                          "project_id": b.project_id, "_solicitante": b.created_by}),
    "budget_transfer": ("app.models.mfa", "BudgetTransfer",
                        lambda t: {"amount": _num(t.importe)}),
    "change_request": ("app.models.resources", "ChangeRequest",
                       lambda c: {"cost_impact": _num(c.cost_impact) or 0.0,
                                  "schedule_impact_days": getattr(c, "schedule_impact_days", None) or 0,
                                  "impact": _val(getattr(c, "impact", None)), "project_id": c.project_id,
                                  "_solicitante": c.requested_by}),
    "timesheet": ("app.models.financial", "Timesheet",
                  lambda t: {"hours": _num(t.total_hours), "billable_hours": _num(t.billable_hours),
                             "_solicitante": t.user_id}),
    "leave": ("app.models.resources", "Absence",
              lambda a: {"days": _num(getattr(a, "working_days", None)), "type": _val(getattr(a, "type", None)),
                         "_solicitante": a.user_id}),
    "overtime": ("app.models.horas_extra", "PeticionDeHorasExtra",
                 lambda p: {"type": p.tipo, "amount": _num(p.horas), "hours": _num(p.horas),
                            "origin": getattr(p, "origen", None), "_solicitante": p.user_id}),
    "internal_charge": ("app.models.clientes_internos", "InternalCharge",
                        lambda c: {"amount": _num(c.total), "currency": c.currency, "category": "internal_charge",
                                   "_solicitante": c.created_by}),
    "supplier_statement": ("app.models.proveedores", "SupplierStatement",
                           lambda s: {"amount": _num(s.invoice_amount if s.invoice_amount is not None
                                                     else s.expected_amount), "currency": s.currency}),
}


def contexto_de_entidad(db: Session, entity_type: str, entity_id: str, org_id: Optional[str]) -> Optional[dict]:
    """El contexto de reglas de una entidad, leído de la base de datos.

    - dict con los datos de la fila (importe, moneda, categoría…) si el tipo
      es conocido y la entidad existe en la empresa `org_id`;
    - `{}` si el tipo no tiene entidad conocida aquí (las reglas con importe o
      categoría no se cumplen: lo dudoso pide firma humana);
    - None si el tipo es conocido y la entidad no existe o es de otra empresa.
    """
    spec = _ENTIDADES.get(entity_type)
    if spec is None:
        return {}
    modulo, clase, extraer = spec
    fila = _cargar(db, modulo, clase, entity_id, org_id)
    if fila is None:
        return None
    ctx = {k: v for k, v in extraer(fila).items() if v is not None}
    solicitante = ctx.pop("_solicitante", None)
    if solicitante:
        from app.models.user import User
        dep = db.query(User.department).filter(User.id == solicitante).scalar()
        if dep:
            ctx["department"] = dep
    return ctx
