import logging
from typing import Optional
import json

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.service_desk import Ticket, TicketComment, TicketTimeLog
from app.services.sla_service import log_history as _log_history
from app.core.errores import ErrorDeDominio


# La guarda vive en `scoping.py`, junto a `scope_ticket_query`, de la que
# depende. Se reexporta con el mismo nombre para que ningun sitio de llamada
# cambie: estaba copiada literalmente en este modulo y en dos mas.
from app.services.service_desk.scoping import (  # noqa: E402,F401
    get_scoped_ticket_or_404,
)


def _to_minutes(value: int, unit: str, horas_por_dia: float = 8.0) -> int:
    unit_l = (unit or "minutes").strip().lower()
    if unit_l in {"minute", "minutes", "min", "m"}:
        return max(0, int(value))
    if unit_l in {"hour", "hours", "h"}:
        return max(0, int(value) * 60)
    if unit_l in {"day", "days", "d"}:
        # La jornada es un ajuste (DEFAULT_WORKING_HOURS_PER_DAY), no 8 fijas.
        return max(0, int(round(value * 60 * horas_por_dia)))
    return max(0, int(value))


def add_ticket_time(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    user,
    minutes: int,
    description: Optional[str] = None,
    unit: str = "minutes",
    billable: bool = False,
) -> dict:
    """Registra tiempo en el ticket y, si tiene proyecto, en los partes del agente.

    Auditoria 2026-11: `billable` venia en el formulario y no se pasaba (todo
    quedaba no facturable), y el tiempo de ticket no llegaba ni a partes ni a
    factura: el PSA no sabia del Service Desk.
    """
    from app.services import settings_service as _ss

    horas_dia = _ss.get_runtime_float(db, "DEFAULT_WORKING_HOURS_PER_DAY", ticket.organization_id) or 8.0
    minutes_norm = _to_minutes(minutes, unit, horas_dia)
    time_log = TicketTimeLog(ticket_id=ticket_id, user_id=user.id, minutes=minutes_norm,
                             description=description, billable=billable)
    db.add(time_log)
    ticket.time_spent_minutes = (ticket.time_spent_minutes or 0) + minutes_norm
    db.flush()
    partes = _a_partes(db, ticket, user, minutes_norm, description, billable)
    if partes.get("imputation_id"):
        time_log.imputation_id = partes["imputation_id"]
    return {"ok": True, "total_minutes": ticket.time_spent_minutes, "logged_minutes": minutes_norm, **partes}


def _a_partes(db: Session, ticket: Ticket, user, minutos: int, descripcion: Optional[str],
              facturable: bool) -> dict:
    """Lleva el tiempo a los partes del agente si el ticket tiene proyecto.

    Por `validate_and_create_imputation`, con todas sus reglas (pertenecer al
    proyecto, fechas bloqueadas, topes, redondeo a medias horas). Si una lo
    impide, el tiempo se queda en el ticket y se dice por que.
    """
    from app.core import timeutil
    from app.schemas.imputations import ImputationCreate
    from app.services import settings_service as _ss
    from app.services.imputation_service import validate_and_create_imputation

    if not _ss.get_runtime_bool(db, "SD_TIME_TO_TIMESHEET", ticket.organization_id):
        return {"timesheet": "off"}
    if not ticket.project_id:
        return {"timesheet": "skipped", "reason": "El ticket no tiene proyecto: el tiempo queda en el ticket"}
    entrada = ImputationCreate(project_id=ticket.project_id, date=timeutil.today(), hours=minutos / 60,
                               description=f"{ticket.number} · {descripcion or ticket.title}"[:2000],
                               is_billable=facturable)
    if entrada.hours <= 0:
        return {"timesheet": "skipped", "reason": "Menos de un cuarto de hora: no llega al mínimo de los partes"}
    try:
        imputacion = validate_and_create_imputation(entrada, user, db)
    except ErrorDeDominio as exc:
        return {"timesheet": "skipped", "reason": str(exc.detail)}
    return {"timesheet": "created", "imputation_id": imputacion.id, "hours": imputacion.hours}


def _pending_snapshot_key(ticket_id: str) -> str:
    return f"sd.ticket.pending_snapshot.{ticket_id}"


def save_pending_snapshot(db: Session, ticket: Ticket) -> None:
    snapshot = {
        "status": str(ticket.status.value) if hasattr(ticket.status, "value") else str(ticket.status),
        "assigned_to_user_id": ticket.assigned_to_user_id,
        "assigned_group_id": ticket.assigned_group_id,
        "support_level": str(ticket.support_level.value) if hasattr(ticket.support_level, "value") else str(ticket.support_level),
        "priority": str(ticket.priority.value) if hasattr(ticket.priority, "value") else str(ticket.priority),
    }
    serialized = json.dumps(snapshot, ensure_ascii=False)
    key = _pending_snapshot_key(ticket.id)
    # Revision multitenant 2026-11: con la organizacion del ticket (antes
    # global, y salia en los ajustes generales de todas las empresas).
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == ticket.organization_id).first()
    if row:
        row.value = serialized
        row.description = "Ticket pending snapshot"
    else:
        db.add(AppSetting(key=key, organization_id=ticket.organization_id, value=serialized,
                          description="Ticket pending snapshot"))


def restore_pending_snapshot(db: Session, ticket: Ticket, current_user_id: str) -> dict:
    key = _pending_snapshot_key(ticket.id)
    row = db.query(AppSetting).filter(AppSetting.key == key, AppSetting.organization_id == ticket.organization_id).first()
    if not row or not row.value:
        return {"ok": False, "restored": False, "detail": "No pending snapshot"}

    try:
        snap = json.loads(row.value)
    except Exception:
        logging.getLogger(__name__).debug("restore_pending_snapshot: excepcion ignorada", exc_info=True)
        snap = {}

    old_status = str(ticket.status.value) if hasattr(ticket.status, "value") else str(ticket.status)
    ticket.status = snap.get("status") or "in_progress"
    ticket.assigned_to_user_id = snap.get("assigned_to_user_id")
    ticket.assigned_group_id = snap.get("assigned_group_id")
    ticket.support_level = snap.get("support_level") or ticket.support_level
    # Auditoria 2026-11: antes se ponia `sla_paused_at = None` sin sumar los
    # minutos en pausa, y ese tiempo contaba contra el SLA. Y si la prioridad
    # vuelve a otra, sus vencimientos tambien.
    from datetime import datetime, timezone
    from app.services.service_desk.sla_del_ticket import _reanudar_sla_pausado, cambiar_prioridad
    _reanudar_sla_pausado(ticket, datetime.now(timezone.utc))
    cambiar_prioridad(db, ticket, snap.get("priority") or ticket.priority)
    _log_history(db, ticket.id, "status", old_status, str(ticket.status), current_user_id)

    db.delete(row)
    return {"ok": True, "restored": True, "status": str(ticket.status)}


def escalate_ticket_level(
    db: Session,
    ticket: Ticket,
    ticket_id: str,
    to_level: str,
    reason: Optional[str],
    current_user_id: str,
) -> dict:
    old_level = ticket.support_level
    ticket.support_level = to_level
    _log_history(db, ticket_id, "support_level", old_level, to_level, current_user_id)
    if reason:
        db.add(
            TicketComment(
                ticket_id=ticket_id,
                body=f"🔺 Escalado a {to_level}: {reason}",
                is_public=False,
                author_user_id=current_user_id,
            )
        )
    return {"ok": True, "from": old_level, "to": to_level}


# ── Transaction helper ─────────────────────────────────────────────────────────

def commit_or_rollback(db, detail: str = "Error de transacción") -> None:
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    try:
        db.commit()
    except Exception:
        db.rollback()
        _logger.exception("Database transaction failed in service_desk")
        raise ErrorDeDominio(500, detail)
