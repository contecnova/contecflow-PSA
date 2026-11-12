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
al enviar; la decision los aprueba o los rechaza).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

TIPOS = ("expense", "timesheet", "leave", "change_request", "invoice", "budget", "budget_transfer")


def abrir(db: Session, tipo: str, entidad_id: str, resumen: str, solicitante_id: str,
          contexto: Optional[dict] = None) -> None:
    """Abre la solicitud si hay flujo por defecto para el tipo; si no, nada."""
    from app.models.user import User
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine._base import elegir_flujo
    from app.services.approval_engine.requests import create_approval_request

    solicitante = db.query(User).filter(User.id == solicitante_id).first()
    if not solicitante:
        return
    if not elegir_flujo(db, tipo, {**(contexto or {}), "department": solicitante.department}):
        return
    try:
        create_approval_request(
            ApprovalRequestIn(entity_type=tipo, entity_id=entidad_id, entity_summary=resumen[:500],
                              context=contexto or {}),
            db, solicitante)
    except Exception:
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
        elif req.entity_type == "invoice":
            from app.models.billing_reports import Invoice, InvoiceStatus
            inv = db.query(Invoice).filter(Invoice.id == req.entity_id).first()
            if aprobado and inv and getattr(inv.status, "value", inv.status) == "draft":
                inv.status = InvoiceStatus.sent
                db.commit()
    except (HTTPException, ErrorDeDominio) as exc:
        # Ya no estaba pendiente (revisada, retirada o cancelada en su pantalla).
        logger.info("aprobacion %s: %s %s no aplicada: %s", req.id, req.entity_type, req.entity_id, exc.detail)


def comprobar_antes(req, decision: str, db: Session) -> None:
    """Antes de anotar una aprobación en la bandeja: lo que la impediría en su pantalla.

    El control presupuestario de un gasto con `BUDGET_CONTROL_POLICY = bloquear`
    responde 409 aquí, y no después de dar la solicitud por aprobada.
    """
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
