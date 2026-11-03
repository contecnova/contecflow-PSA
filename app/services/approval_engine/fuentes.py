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

Tipos (los del disenador): `expense`, `timesheet` y `leave`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TIPOS = ("expense", "timesheet", "leave")


def abrir(db: Session, tipo: str, entidad_id: str, resumen: str, solicitante_id: str,
          contexto: Optional[dict] = None) -> None:
    """Abre la solicitud si hay flujo por defecto para el tipo; si no, nada."""
    from app.models.user import User
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine._base import find_default_workflow
    from app.services.approval_engine.requests import create_approval_request

    if not find_default_workflow(tipo, db):
        return
    solicitante = db.query(User).filter(User.id == solicitante_id).first()
    if not solicitante:
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
    except HTTPException as exc:
        # Ya no estaba pendiente (revisada, retirada o cancelada en su pantalla).
        logger.info("aprobacion %s: %s %s no aplicada: %s", req.id, req.entity_type, req.entity_id, exc.detail)


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
