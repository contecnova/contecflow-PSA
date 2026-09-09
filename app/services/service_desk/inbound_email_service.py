import hmac
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.service_desk import (
    SupportLevel,
    Ticket,
    TicketImpact,
    TicketPriority,
    TicketStatus,
    TicketType,
    TicketUrgency,
)
from app.models.user import User, UserRole
import logging

logger = logging.getLogger(__name__)


def parse_email_address(raw: Optional[str]) -> Tuple[str, str]:
    if not raw:
        return "", ""
    raw = raw.strip()
    if "<" in raw and ">" in raw:
        name = raw[: raw.index("<")].strip().strip('"')
        email = raw[raw.index("<") + 1 : raw.index(">")].strip()
    else:
        name, email = "", raw
    return name, email


def _validate_inbound_secret(configured_secret: str, provided_secret: Optional[str]) -> None:
    if not configured_secret:
        raise HTTPException(403, "Email inbound deshabilitado: configura INBOUND_EMAIL_SECRET")
    if not hmac.compare_digest(provided_secret or "", configured_secret):
        raise HTTPException(403, "Firma inválida")


def build_inbound_ticket(db: Session, payload: dict, configured_secret: str, provided_secret: Optional[str]):
    _validate_inbound_secret(configured_secret, provided_secret)

    raw_from = payload.get("from") or payload.get("From") or payload.get("sender") or ""
    req_name, req_email = parse_email_address(raw_from)

    description = (
        payload.get("stripped-text")
        or payload.get("body-plain")
        or payload.get("text")
        or payload.get("html")
        or "(Sin cuerpo)"
    )[:4000]

    subject = (payload.get("subject") or "(Sin asunto)").strip()[:255]

    # ── Smart routing si está disponible ──────────────────────────────────
    # Antes este parser asignaba siempre al primer admin/pm activo, ignorando
    # el motor ML routing (ml_routing_service) y el semantic engine. Ahora
    # intenta usarlos como mejora best-effort y, si falla, cae al
    # comportamiento legacy.
    agents = db.query(User).filter(
        User.role.in_([UserRole.admin, UserRole.pm]),
        User.is_active.is_(True),
    ).order_by(User.created_at).all()
    assigned_to = agents[0].id if agents else None

    # Auditoria 2026-08. Aqui habia dos defectos mas, encadenados detras del
    # `TicketStatus.open` de abajo:
    #
    #   · `SLAPolicy.response_hours` **no existe**. Las columnas son
    #     `p1_response_hours` ... `p4_response_hours`, una por prioridad. Asi
    #     que tanto el `order_by` como los dos calculos de vencimiento
    #     reventaban con `AttributeError`.
    #   · Y el vencimiento se calculaba a mano, `now + timedelta(hours=...)`,
    #     ignorando el horario laboral y los festivos que `SLAPolicy` declara.
    #
    # Las dos cosas ya estaban resueltas en el repositorio y sin usar aqui:
    # `resolve_sla_policy_for_ticket` elige la politica por contrato, cliente y
    # defecto, y `calculate_sla_due` calcula los dos vencimientos con aritmetica
    # de horas laborables. Se usan las dos.
    from app.services.service_desk.scoping import resolve_sla_policy_for_ticket
    from app.services.sla_service import calculate_sla_due

    sla = resolve_sla_policy_for_ticket(db)
    now = datetime.now(timezone.utc)
    prioridad = TicketPriority.p3_medium
    respuesta_due, resolucion_due = calculate_sla_due(
        prioridad.value, policy=sla, db=db)
    ticket = Ticket(
        id=str(uuid.uuid4()),
        number=f"EML-{uuid.uuid4().hex[:8].upper()}",
        ticket_type=TicketType.service_request,
        title=subject,
        description=description,
        # `TicketStatus` no tiene `open`: el estado inicial es `new`, que es
        # ademas el `default` de la columna y lo que usan las otras tres
        # vias de creacion de tickets. Auditoria 2026-08: esto reventaba con
        # `AttributeError` en cada correo entrante.
        status=TicketStatus.new,
        priority=prioridad,
        urgency=TicketUrgency.medium,
        impact=TicketImpact.user,
        support_level=SupportLevel.l1,
        source="email",
        requester_name=req_name or req_email or "Email",
        requester_email=req_email or None,
        assigned_to_user_id=assigned_to,
        sla_policy_id=sla.id if sla else None,
        sla_response_due=respuesta_due,
        sla_resolution_due=resolucion_due,
        created_at=now,
    )

    db.add(ticket)
    db.flush()  # asegurar ID para el smart-assign

    # ── Mejora: usar semantic engine para reasignar si hay perfiles ──────
    try:
        from app.services.semantic_classifier import SemanticAssigner
        asg = SemanticAssigner(db)
        suggestion = asg.suggest_for_ticket(
            ticket_title=ticket.title or "",
            ticket_desc=ticket.description or "",
            priority=str(ticket.priority).split(".")[-1] if ticket.priority else "medium",
        )
        if suggestion and suggestion.get("suggested_user_id") and not suggestion.get("needs_review"):
            ticket.assigned_to_user_id = suggestion["suggested_user_id"]
    except Exception:
        # Best-effort: si el motor semántico falla, mantenemos el assignment legacy.
        logger.debug(
            "process_inbound_email: auto-asignación semántica fallida, se usa la legacy",
            exc_info=True,
        )

    return ticket, req_email


def process_inbound_email(db: Session, payload: dict, provided_secret: Optional[str]):
    configured_secret = settings.INBOUND_EMAIL_SECRET if hasattr(settings, "INBOUND_EMAIL_SECRET") else ""
    return build_inbound_ticket(db, payload, configured_secret, provided_secret)
