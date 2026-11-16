"""
Autonomous Agent Service — Fase 2 ITSM Intelligence
====================================================
Sprint 11-12: Agente autónomo para resolución de tickets de baja complejidad.

Arquitectura:
  1. evaluate_ticket_for_autonomy() — decide si el ticket puede ser resuelto
     automáticamente o requiere agente humano.
  2. match_playbook() — busca el playbook estándar más adecuado.
  3. execute_playbook() — ejecuta los pasos del playbook (webhooks, notifs, KB).
  4. run_autonomous_resolution() — orquestador principal.

Playbooks incluidos (basados en los top-10 ticket types más frecuentes):
  - password_reset     → instrucciones self-service + KB
  - account_unlock     → instrucciones IT + notificación
  - vpn_issue          → KB article + escalada a IT
  - software_provision → aprobación automática si política permite + ticket activo
  - email_issue        → checks básicos + KB
  - access_request     → auto-aprobación si dentro de política
  - printer_issue      → KB + escalada a l2
  - slow_pc            → KB checklist + escalada si recurrente

Todos los playbooks son configurables como JSON en la tabla
`sd_autonomous_playbooks`.  Esta implementación tiene playbooks por defecto
embebidos para funcionar sin configuración inicial.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.models.service_desk import (
    Ticket,
    TicketHistory,
    TicketStatus,
)
from app.services.service_desk.incident_intelligence_service import (
    score_auto_resolution,
)
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

# ── Confidence threshold for full autonomous resolution ───────────────────────
# Auditoria 2026-11: los umbrales eran constantes y el agente no tenia
# interruptor. Ahora son ajustes por organizacion (Admin > Service Desk):
# SD_AUTONOMOUS_AGENT_ENABLED (apagado por defecto),
# SD_AUTONOMY_RESOLVE_THRESHOLD y SD_AUTONOMY_SUGGEST_THRESHOLD.


#: Tipo de cada ajuste del agente (mejoras de mercado 16-11-2026: modo y
#: playbooks de serie apagados por empresa).
_TIPOS_DE_AJUSTE = {
    "SD_AUTONOMOUS_AGENT_ENABLED": "bool",
    "SD_AUTONOMY_RESOLVE_THRESHOLD": "float",
    "SD_AUTONOMY_SUGGEST_THRESHOLD": "float",
    "SD_AUTONOMOUS_AGENT_MODE": "str",
    "SD_AUTONOMOUS_DISABLED_PLAYBOOKS": "str",
}

#: Modos del agente. `suggest`: deja la propuesta en el registro y un agente
#: humano la aplica o la descarta. `execute`: la ejecuta (comenta, avisa y, si
#: el playbook lo permite, resuelve).
MODOS_DEL_AGENTE = ("suggest", "execute")


def _ajuste(db: Session, clave: str, org_id):
    from app.services import settings_service
    lectores = {"bool": settings_service.get_runtime_bool, "float": settings_service.get_runtime_float,
                "str": settings_service.get_runtime_str}
    return lectores[_TIPOS_DE_AJUSTE.get(clave, "float")](db, clave, org_id)


def modo_del_agente(db: Session, org_id) -> str:
    """`suggest` o `execute`; un valor desconocido cuenta como `suggest` (lo prudente)."""
    modo = (_ajuste(db, "SD_AUTONOMOUS_AGENT_MODE", org_id) or "").strip().lower()
    return modo if modo in MODOS_DEL_AGENTE else "suggest"


def playbooks_de_serie_apagados(db: Session, org_id) -> set[str]:
    crudo = _ajuste(db, "SD_AUTONOMOUS_DISABLED_PLAYBOOKS", org_id) or ""
    return {p.strip() for p in crudo.split(",") if p.strip()}


def _de_serie_activos(db: Session, org_id) -> list[dict]:
    apagados = playbooks_de_serie_apagados(db, org_id)
    return [pb for pb in _BUILTIN_PLAYBOOKS if pb["id"] not in apagados]


def _playbooks_de_la_organizacion(db: Session, org_id) -> list[dict]:
    """Los playbooks creados en la API, en el formato de `match_playbook`.

    Auditoria 2026-11: se guardaban y nunca se usaban; solo valian los de serie.
    """
    from app.models.service_desk import AutonomousPlaybook
    filas = db.query(AutonomousPlaybook).filter(
        AutonomousPlaybook.is_active.is_(True), AutonomousPlaybook.organization_id == org_id).all()
    salida = []
    for r in filas:
        cond = _safe_json(r.conditions_json, {}) or {}
        salida.append({
            "id": r.id, "name": r.name, "steps": _safe_json(r.steps_json, []) or [],
            "trigger_keywords": cond.get("trigger_keywords", []),
            "trigger_categories": cond.get("trigger_categories", []),
            "max_priority": cond.get("max_priority", "p3_medium"),
            "auto_resolve": bool(cond.get("auto_resolve", False)),
        })
    return salida

# ── Built-in playbooks ────────────────────────────────────────────────────────
# Each playbook has:
#   id, name, trigger_keywords, trigger_categories, min_priority, max_priority
#   steps: list of {type, content}  (type: notify | kb | comment | resolve | escalate)
#   auto_resolve: bool — whether the playbook can close the ticket on its own

_BUILTIN_PLAYBOOKS = [
    {
        "id": "pw-reset",
        "name": "Password Reset Self-Service",
        "trigger_keywords": ["password", "contraseña", "reset", "locked out", "bloqueado"],
        "trigger_categories": ["access", "acceso", "security", "seguridad"],
        "max_priority": "p3_medium",
        "auto_resolve": True,
        "steps": [
            {
                "type": "comment",
                "content": (
                    "Hola,\n\nPara restablecer tu contraseña, sigue estos pasos:\n"
                    "1. Abre el portal de restablecimiento de contraseña de tu organización\n"
                    "2. Introduce tu correo corporativo\n"
                    "3. Sigue el enlace recibido en tu correo\n\n"
                    "Si el problema persiste en 15 minutos, este ticket será asignado a un agente."
                ),
            },
            {"type": "notify", "content": "Se ha enviado respuesta automática al solicitante."},
            {"type": "resolve", "content": "Resuelto automáticamente: instrucciones password reset enviadas."},
        ],
    },
    {
        "id": "vpn-issue",
        "name": "VPN Connectivity Issue",
        "trigger_keywords": ["vpn", "remote", "remoto", "connect", "conexión"],
        "trigger_categories": ["network", "red", "connectivity"],
        "max_priority": "p2_high",
        "auto_resolve": False,
        "steps": [
            {
                "type": "comment",
                "content": (
                    "Hola,\n\nPara problemas de VPN, por favor intenta:\n"
                    "1. Desconectar y reconectar el cliente VPN\n"
                    "2. Reiniciar el adaptador de red\n"
                    "3. Comprobar el estado del servicio en la página de estado\n\n"
                    "Tu ticket ha sido asignado con alta prioridad para revisión por el equipo de red."
                ),
            },
            {"type": "notify", "content": "Ticket de VPN: respuesta automática enviada y escalado a Red."},
        ],
    },
    {
        "id": "email-issue",
        "name": "Email / Outlook Issue",
        "trigger_keywords": ["email", "correo", "outlook", "mail", "smtp"],
        "trigger_categories": ["email", "correo", "collaboration"],
        "max_priority": "p3_medium",
        "auto_resolve": True,
        "steps": [
            {
                "type": "comment",
                "content": (
                    "Hola,\n\nPara problemas con el correo, comprueba:\n"
                    "1. Conexión a internet activa\n"
                    "2. Outlook: Archivo → Info → Configuración de cuenta → Probar conexión\n"
                    "3. Caché de Outlook: cierra Outlook, borra el perfil OST y reabre\n"
                    "4. Comprueba el estado del servidor en la página de estado\n\n"
                    "Si el problema persiste tras estos pasos, responde a este ticket."
                ),
            },
            {"type": "resolve", "content": "Resuelto automáticamente: guía de troubleshooting enviada."},
        ],
    },
    {
        "id": "printer-issue",
        "name": "Printer / Print Queue Issue",
        "trigger_keywords": ["printer", "impresora", "print", "imprimir", "cola"],
        "trigger_categories": ["hardware", "periférico", "print"],
        "max_priority": "p3_medium",
        "auto_resolve": True,
        "steps": [
            {
                "type": "comment",
                "content": (
                    "Hola,\n\nPara problemas con impresoras:\n"
                    "1. Comprueba que la impresora está encendida y conectada\n"
                    "2. Cancela todos los trabajos de impresión en cola\n"
                    "3. Windows: Servicios → Print Spooler → Reiniciar\n"
                    "4. Reinstala el driver desde la web del fabricante\n\n"
                    "Si el problema persiste, un técnico se pondrá en contacto contigo."
                ),
            },
            {"type": "resolve", "content": "Resuelto automáticamente: guía de impresora enviada."},
        ],
    },
    {
        "id": "slow-pc",
        "name": "Slow PC / Performance Issue",
        "trigger_keywords": ["slow", "lento", "performance", "cuelga", "freeze", "tarda"],
        "trigger_categories": ["hardware", "performance", "rendimiento"],
        "max_priority": "p3_medium",
        "auto_resolve": False,
        "steps": [
            {
                "type": "comment",
                "content": (
                    "Hola,\n\nPara mejorar el rendimiento de tu equipo:\n"
                    "1. Reinicia el equipo completamente (no suspender)\n"
                    "2. Cierra las aplicaciones que no uses\n"
                    "3. Ejecuta Liberador de espacio en disco\n"
                    "4. Comprueba actualizaciones de Windows pendientes\n\n"
                    "Si el problema continúa, un técnico revisará tu equipo remotamente."
                ),
            },
            {"type": "notify", "content": "Ticket de rendimiento: respuesta enviada, pendiente revisión técnica."},
        ],
    },
]


# ── Playbook matching ─────────────────────────────────────────────────────────

def _text_matches_keywords(text: str, keywords: list[str]) -> int:
    """Return number of keyword matches in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def match_playbook(ticket: Ticket, custom_playbooks: Optional[list[dict]] = None,
                   de_serie: Optional[list[dict]] = None) -> Optional[dict]:
    """Find the best matching playbook for *ticket*.

    Searches custom_playbooks first (from DB), then falls back to built-ins.
    Returns None when no playbook matches with score > 0.

    Priority constraint: playbooks with max_priority prevent high-priority
    tickets from being auto-handled (safety guard).
    """
    priority_order = {
        "p1_critical": 1,
        "p2_high": 2,
        "p3_medium": 3,
        "p4_low": 4,
    }
    ticket_priority_rank = priority_order.get(
        getattr(ticket.priority, "value", str(ticket.priority)), 3
    )

    search_text = f"{ticket.title or ''} {ticket.description or ''}"
    # `de_serie`: los de serie que la empresa no ha apagado; sin él, todos.
    all_playbooks = (custom_playbooks or []) + (_BUILTIN_PLAYBOOKS if de_serie is None else de_serie)

    best_match: Optional[dict] = None
    best_score = 0

    for pb in all_playbooks:
        # Priority guard: never auto-handle tickets above max_priority
        max_prio = pb.get("max_priority", "p3_medium")
        max_prio_rank = priority_order.get(max_prio, 3)
        if ticket_priority_rank < max_prio_rank:
            continue  # ticket is too critical for this playbook

        # Keyword matching
        keyword_hits = _text_matches_keywords(search_text, pb.get("trigger_keywords", []))
        category_hits = _text_matches_keywords(
            search_text, pb.get("trigger_categories", [])
        )
        score = keyword_hits * 2 + category_hits

        if score > best_score:
            best_score = score
            best_match = pb

    return best_match if best_score > 0 else None


# ── Playbook execution ────────────────────────────────────────────────────────

def _destinatarios_del_paso(db, ticket) -> list:
    """El agente del ticket y los responsables de su cola."""
    from app.models.service_desk import AgentGroupMember
    ids = [ticket.assigned_to_user_id] if ticket.assigned_to_user_id else []
    if ticket.assigned_group_id:
        ids += [r[0] for r in db.query(AgentGroupMember.user_id).filter(
            AgentGroupMember.group_id == ticket.assigned_group_id,
            AgentGroupMember.is_lead == True,  # noqa: E712
        ).all()]
    return list(dict.fromkeys(ids))


def _add_ticket_comment(db: Session, ticket: Ticket, content: str, acting_user_id: Optional[str]) -> None:
    """Add a public comment to the ticket."""
    try:
        from app.models.service_desk import TicketComment
        comment = TicketComment(
            id=str(uuid4()),
            ticket_id=ticket.id,
            body=content,
            is_public=True,
            is_solution=False,
            author_user_id=acting_user_id,
            author_name="Autonomous Agent",
        )
        db.add(comment)
    except Exception as exc:
        logger.warning("Could not add comment to ticket %s: %s", ticket.id, exc)


def _resolve_ticket(db: Session, ticket: Ticket, resolution: str, acting_user_id: Optional[str]) -> None:
    """Mark ticket as resolved by the autonomous agent."""
    old_status = str(ticket.status)
    ticket.status = TicketStatus.resolved
    ticket.resolution = resolution
    ticket.resolved_at = datetime.now(tz=timezone.utc)

    history = TicketHistory(
        id=str(uuid4()),
        ticket_id=ticket.id,
        field_name="status",
        old_value=old_status,
        new_value=TicketStatus.resolved.value,
        changed_by_user_id=acting_user_id,
    )
    db.add(history)


def execute_playbook(
    db: Session,
    ticket: Ticket,
    playbook: dict,
    acting_user_id: Optional[str] = None,
) -> dict:
    """Execute all steps of *playbook* for *ticket*.

    Returns execution summary dict.
    """
    steps_executed = []

    for step in playbook.get("steps", []):
        step_type = step.get("type")
        content = step.get("content", "")

        try:
            if step_type == "comment":
                _add_ticket_comment(db, ticket, content, acting_user_id)
                steps_executed.append({"type": step_type, "status": "ok"})

            elif step_type == "resolve":
                if playbook.get("auto_resolve"):
                    _resolve_ticket(db, ticket, content, acting_user_id)
                    steps_executed.append({"type": step_type, "status": "ok"})
                else:
                    steps_executed.append({"type": step_type, "status": "skipped_no_auto_resolve"})

            elif step_type in ("notify", "escalate"):
                # Auditoria 2026-11: «avisar» y «escalar» solo dejaban una nota
                # en el historial; nadie se enteraba. Ahora pasan por la bandeja
                # de eventos como un escalado: avisa al agente y a los
                # responsables de la cola (campana, correo y guardia).
                from app.services.service_desk.ticket_events import registrar
                destinatarios = _destinatarios_del_paso(db, ticket)
                registrar(db, ticket, "escalated",
                          {"rule": playbook.get("name") or "Agente autónomo", "action": content[:500],
                           "recipients": destinatarios},
                          actor_user_id=acting_user_id)
                db.add(TicketHistory(
                    id=str(uuid4()), ticket_id=ticket.id,
                    field_name="autonomous_note" if step_type == "notify" else "autonomous_escalate",
                    old_value=None, new_value=content[:500], changed_by_user_id=acting_user_id,
                ))
                steps_executed.append({"type": step_type, "status": "ok", "notified": len(destinatarios)})

            else:
                steps_executed.append({"type": step_type, "status": "unknown_step_type"})

        except Exception as exc:
            logger.warning("Playbook step %s failed for ticket %s: %s", step_type, ticket.id, exc)
            steps_executed.append({"type": step_type, "status": "error", "error": str(exc)})

    db.flush()
    return {
        "playbook_id": playbook.get("id"),
        "playbook_name": playbook.get("name"),
        "steps_executed": steps_executed,
        "auto_resolved": playbook.get("auto_resolve", False),
    }


# ── Autonomous resolution evaluation ─────────────────────────────────────────

def evaluate_ticket_for_autonomy(db: Session, ticket: Ticket) -> dict:
    """Determine whether a ticket can be handled autonomously.

    Returns:
        {
          "eligible": bool,
          "action": str,   # "auto_resolve" | "playbook_assist" | "human_required"
          "score": float,  # composite confidence 0-1
          "playbook": dict | None,
          "reason": str,
        }
    """
    # Safety: never autonomously handle critical tickets without KB match
    priority_val = getattr(ticket.priority, "value", str(ticket.priority))
    if priority_val == "p1_critical":
        return {
            "eligible": False,
            "action": "human_required",
            "score": 0.0,
            "playbook": None,
            "reason": "P1 tickets always require human review",
        }

    # Check auto-resolution scoring from incident_intelligence
    try:
        aii = score_auto_resolution(db, ticket)
        ai_score = aii.get("score", 0.0)
    except Exception:
        logger.warning("evaluate_ticket_for_autonomy: excepcion ignorada", exc_info=True)
        ai_score = 0.0

    # Try to find a matching playbook (los de la organizacion primero)
    playbook = match_playbook(ticket, _playbooks_de_la_organizacion(db, ticket.organization_id),
                              _de_serie_activos(db, ticket.organization_id))
    umbral_resolver = _ajuste(db, "SD_AUTONOMY_RESOLVE_THRESHOLD", ticket.organization_id)
    umbral_sugerir = _ajuste(db, "SD_AUTONOMY_SUGGEST_THRESHOLD", ticket.organization_id)

    # Compute composite score
    playbook_boost = 0.20 if playbook else 0.0
    composite = min(1.0, ai_score + playbook_boost)

    if composite >= umbral_resolver and playbook and playbook.get("auto_resolve"):
        return {
            "eligible": True,
            "action": "auto_resolve",
            "score": composite,
            "playbook": playbook,
            "reason": f"High confidence ({composite:.0%}) + playbook '{playbook['name']}' matched",
        }
    elif composite >= umbral_sugerir and playbook:
        return {
            "eligible": True,
            "action": "playbook_assist",
            "score": composite,
            "playbook": playbook,
            "reason": f"Medium confidence ({composite:.0%}) — playbook assist without auto-close",
        }
    else:
        return {
            "eligible": False,
            "action": "human_required",
            "score": composite,
            "playbook": playbook,
            "reason": f"Confidence too low ({composite:.0%}) or no matching playbook",
        }


# ── Main orchestrator ─────────────────────────────────────────────────────────

def _anotar(db: Session, ticket: Ticket, evaluation: dict, estado: str, origen: str,
            modo: Optional[str] = None, acciones: Optional[list] = None):
    """Fila del registro de ejecuciones: lo que leen las estadisticas, lo que
    impide que el barrido evalue dos veces el mismo ticket y, en modo
    `suggest`, la propuesta que un agente aplica o descarta."""
    from app.models.service_desk import AutonomousPlaybookExecution
    pb = evaluation.get("playbook") or {}
    fila = AutonomousPlaybookExecution(
        organization_id=ticket.organization_id, ticket_id=ticket.id,
        playbook_type=str(pb.get("id") or evaluation.get("action") or "none")[:50],
        status=estado, confidence_score=evaluation.get("score"),
        resolution_note=(evaluation.get("reason") or "")[:2000], triggered_by=origen,
        mode=modo, playbook_id=str(pb.get("id"))[:64] if pb.get("id") else None,
        action=str(evaluation.get("action") or "")[:30] or None,
        actions_json=json.dumps(acciones, default=str) if acciones is not None else None,
    )
    db.add(fila)
    db.flush()
    return fila


def _pasos_previstos(playbook: dict) -> list[dict]:
    """Lo que haria el playbook, paso a paso, sin hacerlo (modo sugerir)."""
    salida = []
    for paso in playbook.get("steps", []):
        tipo = paso.get("type")
        if tipo == "resolve" and not playbook.get("auto_resolve"):
            continue
        salida.append({"type": tipo, "content": (paso.get("content") or "")[:2000], "status": "planned"})
    return salida


def _ticket_de_la_organizacion(db: Session, ticket_id: str, org_id) -> Optional[Ticket]:
    q = db.query(Ticket).filter(Ticket.id == ticket_id)
    if org_id is not None:
        q = q.filter(Ticket.organization_id == org_id)
    return q.first()


def run_autonomous_resolution(
    db: Session,
    ticket_id: str,
    acting_user_id: Optional[str] = None,
    origen: str = "api",
    org_id=None,
    modo: Optional[str] = None,
) -> dict:
    """Evalua el ticket y, segun el modo de la empresa, propone o ejecuta.

    `org_id` acota el ticket a la empresa de quien llama (la API lo pasa
    siempre; el barrido, el de cada ticket). `modo` fuerza el modo; sin el,
    el ajuste `SD_AUTONOMOUS_AGENT_MODE` de la empresa del ticket.
    """
    ticket = _ticket_de_la_organizacion(db, ticket_id, org_id)
    if not ticket:
        raise ErrorDeDominio(404, "Ticket no encontrado")

    status_val = getattr(ticket.status, "value", str(ticket.status))
    if status_val in ESTADOS_DE_TICKET_RESUELTOS:
        return {"ticket_id": ticket_id, "skipped": True, "reason": "ticket_already_resolved"}

    modo = modo if modo in MODOS_DEL_AGENTE else modo_del_agente(db, ticket.organization_id)
    evaluation = evaluate_ticket_for_autonomy(db, ticket)

    if not evaluation["eligible"]:
        _anotar(db, ticket, evaluation, "skipped", origen, modo=modo, acciones=[])
        db.commit()
        return {"ticket_id": ticket_id, "action": evaluation["action"], "eligible": False,
                "reason": evaluation["reason"], "score": evaluation["score"], "mode": modo}

    playbook = evaluation["playbook"]
    if modo == "suggest":
        fila = _anotar(db, ticket, evaluation, "suggested", origen, modo=modo,
                       acciones=_pasos_previstos(playbook))
        db.commit()
        return {"ticket_id": ticket_id, "action": evaluation["action"], "eligible": True,
                "score": evaluation["score"], "reason": evaluation["reason"], "mode": modo,
                "execution_id": fila.id, "suggested": True}

    execution = execute_playbook(db, ticket, playbook, acting_user_id)
    _anotar(db, ticket, evaluation, "success", origen, modo=modo, acciones=execution["steps_executed"])

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Commit failed in run_autonomous_resolution for %s: %s", ticket_id, exc)
        raise

    logger.info("Autonomous resolution: ticket=%s action=%s playbook=%s resolved=%s",
                ticket_id, evaluation["action"], playbook.get("id"), execution.get("auto_resolved"))
    return {"ticket_id": ticket_id, "action": evaluation["action"], "eligible": True,
            "score": evaluation["score"], "reason": evaluation["reason"], "mode": modo,
            "execution": execution}


def _playbook_por_id(db: Session, org_id, playbook_id: Optional[str]) -> Optional[dict]:
    for pb in _playbooks_de_la_organizacion(db, org_id) + list(_BUILTIN_PLAYBOOKS):
        if str(pb.get("id")) == str(playbook_id):
            return pb
    return None


def decidir_sugerencia(db: Session, execution_id: str, user, aplicar: bool) -> dict:
    """Un agente aplica o descarta la propuesta que el agente dejo en modo sugerir.

    Solo una propuesta pendiente (`suggested`) de la empresa de quien decide, y
    sobre un ticket que siga abierto. Aplicar ejecuta el playbook en nombre de
    quien la aplica (sus comentarios y avisos llevan su usuario).
    """
    from app.models.service_desk import AutonomousPlaybookExecution
    fila = db.query(AutonomousPlaybookExecution).filter(
        AutonomousPlaybookExecution.id == execution_id,
        AutonomousPlaybookExecution.organization_id == getattr(user, "organization_id", None),
    ).first()
    if not fila:
        raise ErrorDeDominio(404, "Ejecución no encontrada")
    if fila.status != "suggested":
        raise ErrorDeDominio(409, "La propuesta ya está decidida")
    fila.decided_by_user_id = user.id
    fila.decided_at = datetime.now(timezone.utc)
    if not aplicar:
        fila.status = "discarded"
        db.commit()
        return {"id": fila.id, "status": fila.status}
    ticket = _ticket_de_la_organizacion(db, fila.ticket_id, fila.organization_id)
    if not ticket or getattr(ticket.status, "value", str(ticket.status)) in ESTADOS_DE_TICKET_RESUELTOS:
        raise ErrorDeDominio(409, "El ticket ya no está abierto")
    playbook = _playbook_por_id(db, fila.organization_id, fila.playbook_id or fila.playbook_type)
    if not playbook:
        raise ErrorDeDominio(409, "El playbook ya no existe")
    resultado = execute_playbook(db, ticket, playbook, user.id)
    fila.status = "applied"
    fila.actions_json = json.dumps(resultado["steps_executed"], default=str)
    db.commit()
    return {"id": fila.id, "status": fila.status, "execution": resultado}


# ── Bulk scan entrypoint (Celery) ─────────────────────────────────────────────

#: Tickets por pasada y empresa: acota el tiempo con bloqueos de una pasada.
TICKETS_POR_PASADA = 100


def run_autonomous_scan(db: Session, org_id=None) -> dict:
    """Evalua los tickets nuevos no evaluados de las empresas con el agente encendido.

    Llamado por Celery beat cada 5 minutos, empresa a empresa (`org_id`); sin
    `org_id`, todas. Cada ticket se evalua una sola vez.
    """
    from app.models.service_desk import AutonomousPlaybookExecution
    ya_evaluados = db.query(AutonomousPlaybookExecution.ticket_id)
    q = db.query(Ticket).filter(
        Ticket.status.in_(["new", "assigned"]),
        # Una vez por ticket: antes, un «assist» dejaba el ticket en `new` y
        # cada 5 minutos se repetia el mismo comentario publico.
        ~Ticket.id.in_(ya_evaluados),
    )
    if org_id is not None:
        q = q.filter(Ticket.organization_id == org_id)
    open_tickets = q.limit(TICKETS_POR_PASADA).all()

    evaluated = auto_resolved = assisted = suggested = skipped = 0
    encendido: dict = {}

    for ticket in open_tickets:
        org = ticket.organization_id
        if org not in encendido:
            encendido[org] = bool(_ajuste(db, "SD_AUTONOMOUS_AGENT_ENABLED", org))
        if not encendido[org]:
            continue
        try:
            result = run_autonomous_resolution(db, ticket.id, acting_user_id=None, origen="celery", org_id=org)
            evaluated += 1
            if result.get("skipped"):
                skipped += 1
            elif result.get("suggested"):
                suggested += 1
            elif result.get("execution", {}).get("auto_resolved"):
                auto_resolved += 1
            elif result.get("eligible"):
                assisted += 1
            else:
                skipped += 1
        except Exception as exc:
            db.rollback()
            logger.warning("Autonomous scan failed for ticket %s: %s", ticket.id, exc)
            skipped += 1

    logger.info("Autonomous scan: evaluated=%d auto_resolved=%d assisted=%d suggested=%d skipped=%d",
                evaluated, auto_resolved, assisted, suggested, skipped)
    return {"evaluated": evaluated, "auto_resolved": auto_resolved, "assisted": assisted,
            "suggested": suggested, "skipped": skipped}


# ── Playbook CRUD (DB-backed) ─────────────────────────────────────────────────

def list_playbooks(db: Session, org_id=None) -> list[dict]:
    """Los playbooks de la empresa y los de serie, con si estan encendidos en ella."""
    from app.models.service_desk import AutonomousPlaybook

    q = db.query(AutonomousPlaybook).filter(AutonomousPlaybook.is_active.is_(True))
    q = q.filter(AutonomousPlaybook.organization_id == org_id)
    db_playbooks = [
        {
            "id": r.id, "name": r.name, "playbook_type": r.playbook_type, "description": r.description,
            "steps": _safe_json(r.steps_json, []), "conditions": _safe_json(r.conditions_json, {}),
            "is_active": r.is_active, "enabled": True,
            "success_count": r.success_count, "failure_count": r.failure_count, "source": "custom",
        }
        for r in q.order_by(AutonomousPlaybook.name).all()
    ]
    apagados = playbooks_de_serie_apagados(db, org_id)
    builtin_dicts = [
        {
            "id": pb["id"], "name": pb["name"], "playbook_type": pb["id"], "description": None,
            "steps": pb["steps"],
            "conditions": {
                "trigger_keywords": pb.get("trigger_keywords", []),
                "trigger_categories": pb.get("trigger_categories", []),
                "max_priority": pb.get("max_priority", "p3_medium"),
                "auto_resolve": pb.get("auto_resolve", False),
            },
            "is_active": True, "enabled": pb["id"] not in apagados,
            "success_count": 0, "failure_count": 0, "source": "builtin",
        }
        for pb in _BUILTIN_PLAYBOOKS
    ]
    return db_playbooks + builtin_dicts


def ids_de_serie() -> list[str]:
    return [pb["id"] for pb in _BUILTIN_PLAYBOOKS]


def _safe_json(raw: Optional[str], default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        logger.debug("_safe_json: excepcion ignorada", exc_info=True)
        return default


_TIPOS_DE_PASO = ("comment", "notify", "escalate", "resolve")


def _validar_pasos(pasos: list) -> list[dict]:
    salida = []
    for p in pasos or []:
        tipo = (p or {}).get("type")
        if tipo not in _TIPOS_DE_PASO:
            raise ErrorDeDominio(422, f"Tipo de paso no válido: {tipo}")
        salida.append({"type": tipo, "content": str(p.get("content") or "")[:4000]})
    return salida


def create_playbook(db: Session, data: dict, org_id=None) -> dict:
    """Playbook propio de la empresa."""
    from app.models.service_desk import AutonomousPlaybook

    row = AutonomousPlaybook(
        organization_id=org_id,
        name=data["name"],
        playbook_type=(data.get("playbook_type") or data["name"].lower().replace(" ", "_"))[:50],
        description=data.get("description"),
        steps_json=json.dumps(_validar_pasos(data.get("steps", []))),
        conditions_json=json.dumps(data.get("conditions", {})),
        is_active=True,
    )
    db.add(row)
    db.flush()
    resultado = {"id": row.id, "name": row.name, "playbook_type": row.playbook_type, "status": "created"}
    db.commit()
    return resultado


def _playbook_propio(db: Session, playbook_id: str, org_id):
    from app.models.service_desk import AutonomousPlaybook
    row = db.query(AutonomousPlaybook).filter(
        AutonomousPlaybook.id == playbook_id, AutonomousPlaybook.organization_id == org_id).first()
    if not row:
        raise ErrorDeDominio(404, "Playbook not found")
    return row


def update_playbook(db: Session, playbook_id: str, data: dict, org_id=None) -> dict:
    """Cambia un playbook propio de la empresa."""
    row = _playbook_propio(db, playbook_id, org_id)
    if "name" in data:
        row.name = data["name"]
    if "description" in data:
        row.description = data["description"]
    if "steps" in data:
        row.steps_json = json.dumps(_validar_pasos(data["steps"]))
    if "conditions" in data:
        row.conditions_json = json.dumps(data["conditions"])
    if "is_active" in data:
        row.is_active = data["is_active"]
    db.flush()
    resultado = {"id": row.id, "name": row.name, "status": "updated"}
    db.commit()
    return resultado


def deactivate_playbook(db: Session, playbook_id: str, org_id=None) -> dict:
    """Desactiva (borrado logico) un playbook propio de la empresa."""
    row = _playbook_propio(db, playbook_id, org_id)
    row.is_active = False
    db.flush()
    db.commit()
    return {"id": playbook_id, "status": "deactivated"}


def get_execution_stats(db: Session, org_id=None) -> dict:
    """Totales del registro de la empresa: por estado y por playbook."""
    from app.models.service_desk import AutonomousPlaybookExecution
    from sqlalchemy import func

    base = db.query(AutonomousPlaybookExecution).filter(AutonomousPlaybookExecution.organization_id == org_id)
    por_estado = dict(
        base.with_entities(AutonomousPlaybookExecution.status, func.count(AutonomousPlaybookExecution.id))
        .group_by(AutonomousPlaybookExecution.status).all())
    by_type = (
        base.with_entities(AutonomousPlaybookExecution.playbook_type, func.count(AutonomousPlaybookExecution.id))
        .group_by(AutonomousPlaybookExecution.playbook_type).all())
    total = sum(por_estado.values())
    hechas = por_estado.get("success", 0) + por_estado.get("applied", 0)
    return {
        "total_executions": total,
        "success": por_estado.get("success", 0),
        "applied": por_estado.get("applied", 0),
        "suggested": por_estado.get("suggested", 0),
        "discarded": por_estado.get("discarded", 0),
        "skipped": por_estado.get("skipped", 0),
        "failed": por_estado.get("failed", 0),
        "success_rate_pct": round(hechas / total * 100, 1) if total else 0,
        "by_playbook_type": {t: c for t, c in by_type},
    }


def get_execution_log(db: Session, page: int = 1, page_size: int = 25, org_id=None,
                      estado: Optional[str] = None, ticket_id: Optional[str] = None) -> dict:
    """Registro de la empresa, lo mas reciente primero, con lo que hizo o propuso."""
    from app.models.service_desk import AutonomousPlaybookExecution

    q = db.query(AutonomousPlaybookExecution).filter(AutonomousPlaybookExecution.organization_id == org_id)
    if estado:
        q = q.filter(AutonomousPlaybookExecution.status == estado)
    if ticket_id:
        q = q.filter(AutonomousPlaybookExecution.ticket_id == ticket_id)
    q = q.order_by(AutonomousPlaybookExecution.executed_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    numeros = dict(db.query(Ticket.id, Ticket.number).filter(
        Ticket.id.in_({r.ticket_id for r in rows})).all()) if rows else {}

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": r.id, "ticket_id": r.ticket_id, "ticket_number": numeros.get(r.ticket_id),
                "playbook_type": r.playbook_type, "playbook_id": r.playbook_id, "action": r.action,
                "status": r.status, "mode": r.mode, "confidence_score": r.confidence_score,
                "resolution_note": r.resolution_note, "error_message": r.error_message,
                "actions": _safe_json(r.actions_json, []),
                "executed_at": r.executed_at.isoformat() if r.executed_at else None,
                "decided_by_user_id": r.decided_by_user_id,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "triggered_by": r.triggered_by,
            }
            for r in rows
        ],
    }


def configuracion_del_agente(db: Session, org_id) -> dict:
    return {
        "enabled": bool(_ajuste(db, "SD_AUTONOMOUS_AGENT_ENABLED", org_id)),
        "mode": modo_del_agente(db, org_id),
        "resolve_threshold": _ajuste(db, "SD_AUTONOMY_RESOLVE_THRESHOLD", org_id),
        "suggest_threshold": _ajuste(db, "SD_AUTONOMY_SUGGEST_THRESHOLD", org_id),
        "disabled_playbooks": sorted(playbooks_de_serie_apagados(db, org_id)),
        "builtin_playbooks": ids_de_serie(),
        "modes": list(MODOS_DEL_AGENTE),
    }


def guardar_configuracion_del_agente(db: Session, org_id, datos: dict) -> dict:
    """Escribe los ajustes del agente en la fila de la empresa (ajustes en caliente)."""
    from app.services.settings_service import update_setting
    if "mode" in datos and datos["mode"] is not None:
        if datos["mode"] not in MODOS_DEL_AGENTE:
            raise ErrorDeDominio(422, "Modo no válido")
        update_setting("SD_AUTONOMOUS_AGENT_MODE", datos["mode"], org_id, db)
    if datos.get("enabled") is not None:
        update_setting("SD_AUTONOMOUS_AGENT_ENABLED", "true" if datos["enabled"] else "false", org_id, db)
    for clave, campo in (("SD_AUTONOMY_RESOLVE_THRESHOLD", "resolve_threshold"),
                         ("SD_AUTONOMY_SUGGEST_THRESHOLD", "suggest_threshold")):
        if datos.get(campo) is not None:
            valor = float(datos[campo])
            if not 0 <= valor <= 1:
                raise ErrorDeDominio(422, "El umbral va de 0 a 1")
            update_setting(clave, str(valor), org_id, db)
    if datos.get("disabled_playbooks") is not None:
        validos = set(ids_de_serie())
        elegidos = [p for p in datos["disabled_playbooks"] if p in validos]
        update_setting("SD_AUTONOMOUS_DISABLED_PLAYBOOKS", ",".join(sorted(set(elegidos))), org_id, db)
    return configuracion_del_agente(db, org_id)
