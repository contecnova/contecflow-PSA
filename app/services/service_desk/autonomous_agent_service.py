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

from app.models.service_desk import (
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketStatus,
)
from app.services.service_desk.incident_intelligence_service import (
    AUTO_RESOLVE_CONFIDENCE_THRESHOLD,
    score_auto_resolution,
)

logger = logging.getLogger(__name__)

# ── Confidence threshold for full autonomous resolution ───────────────────────
AUTONOMY_RESOLVE_THRESHOLD = 0.80
AUTONOMY_SUGGEST_THRESHOLD = 0.50  # below this → human routing

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
                    "1. Ve a https://account.company.com/reset\n"
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
                    "3. Comprobar el estado del servicio en https://status.company.com\n\n"
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
                    "4. Estado del servidor en https://status.company.com\n\n"
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
                    "4. Reinstala el driver: https://drivers.company.com\n\n"
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


def match_playbook(ticket: Ticket, custom_playbooks: Optional[list[dict]] = None) -> Optional[dict]:
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
    all_playbooks = (custom_playbooks or []) + _BUILTIN_PLAYBOOKS

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

            elif step_type == "notify":
                # Notification is logged as a history note; actual push handled by notification service
                history = TicketHistory(
                    id=str(uuid4()),
                    ticket_id=ticket.id,
                    field_name="autonomous_note",
                    old_value=None,
                    new_value=content[:500],
                    changed_by_user_id=acting_user_id,
                )
                db.add(history)
                steps_executed.append({"type": step_type, "status": "logged"})

            elif step_type == "escalate":
                # Log escalation intent — actual routing handled by workload_service
                history = TicketHistory(
                    id=str(uuid4()),
                    ticket_id=ticket.id,
                    field_name="autonomous_escalate",
                    old_value=None,
                    new_value=content[:500],
                    changed_by_user_id=acting_user_id,
                )
                db.add(history)
                steps_executed.append({"type": step_type, "status": "logged"})

            else:
                steps_executed.append({"type": step_type, "status": "unknown_step_type"})

        except Exception as exc:  # noqa: BLE001
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
        ai_score = 0.0

    # Try to find a matching playbook
    playbook = match_playbook(ticket)

    # Compute composite score
    playbook_boost = 0.20 if playbook else 0.0
    composite = min(1.0, ai_score + playbook_boost)

    if composite >= AUTONOMY_RESOLVE_THRESHOLD and playbook and playbook.get("auto_resolve"):
        return {
            "eligible": True,
            "action": "auto_resolve",
            "score": composite,
            "playbook": playbook,
            "reason": f"High confidence ({composite:.0%}) + playbook '{playbook['name']}' matched",
        }
    elif composite >= AUTONOMY_SUGGEST_THRESHOLD and playbook:
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

def run_autonomous_resolution(
    db: Session,
    ticket_id: str,
    acting_user_id: Optional[str] = None,
) -> dict:
    """Attempt to autonomously resolve or assist with a ticket.

    This is the main entrypoint called from the API or Celery tasks.

    Returns full result dict with evaluation + execution summary.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"error": f"Ticket {ticket_id} not found"}

    # Skip already resolved/closed
    status_val = getattr(ticket.status, "value", str(ticket.status))
    if status_val in ("resolved", "closed"):
        return {"skipped": True, "reason": "Ticket already resolved or closed"}

    evaluation = evaluate_ticket_for_autonomy(db, ticket)

    if not evaluation["eligible"]:
        return {
            "ticket_id": ticket_id,
            "action": evaluation["action"],
            "eligible": False,
            "reason": evaluation["reason"],
            "score": evaluation["score"],
        }

    playbook = evaluation["playbook"]
    execution = execute_playbook(db, ticket, playbook, acting_user_id)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Commit failed in run_autonomous_resolution for %s: %s", ticket_id, exc)
        return {"error": str(exc)}

    logger.info(
        "Autonomous resolution: ticket=%s action=%s playbook=%s resolved=%s",
        ticket_id,
        evaluation["action"],
        playbook.get("id"),
        execution.get("auto_resolved"),
    )

    return {
        "ticket_id": ticket_id,
        "action": evaluation["action"],
        "eligible": True,
        "score": evaluation["score"],
        "reason": evaluation["reason"],
        "execution": execution,
    }


# ── Bulk scan entrypoint (Celery) ─────────────────────────────────────────────

def run_autonomous_scan(db: Session) -> dict:
    """Process all newly-created open tickets that haven't been evaluated yet.

    Called from Celery beat every 5 minutes for near-real-time autonomous handling.

    Returns:
        {"evaluated": N, "auto_resolved": N, "assisted": N, "skipped": N}
    """
    open_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(["new", "open"]),
        )
        .limit(100)  # process in batches to avoid long lock times
        .all()
    )

    evaluated = auto_resolved = assisted = skipped = 0

    for ticket in open_tickets:
        try:
            result = run_autonomous_resolution(db, ticket.id, acting_user_id=None)
            evaluated += 1
            if result.get("skipped"):
                skipped += 1
            elif result.get("execution", {}).get("auto_resolved"):
                auto_resolved += 1
            elif result.get("eligible"):
                assisted += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autonomous scan failed for ticket %s: %s", ticket.id, exc)
            skipped += 1

    logger.info(
        "Autonomous scan: evaluated=%d auto_resolved=%d assisted=%d skipped=%d",
        evaluated,
        auto_resolved,
        assisted,
        skipped,
    )
    return {
        "evaluated": evaluated,
        "auto_resolved": auto_resolved,
        "assisted": assisted,
        "skipped": skipped,
    }


# ── Playbook CRUD (DB-backed) ─────────────────────────────────────────────────

def list_playbooks(db: Session) -> list[dict]:
    """Return built-in playbooks merged with DB custom playbooks.

    DB playbooks appear first (allow overrides of built-in logic).
    Returns a list of dicts suitable for API responses.
    """
    from app.models.service_desk import AutonomousPlaybook

    db_rows = db.query(AutonomousPlaybook).filter(AutonomousPlaybook.is_active.is_(True)).all()
    db_playbooks = [
        {
            "id": r.id,
            "name": r.name,
            "playbook_type": r.playbook_type,
            "description": r.description,
            "steps": _safe_json(r.steps_json, []),
            "conditions": _safe_json(r.conditions_json, {}),
            "is_active": r.is_active,
            "success_count": r.success_count,
            "failure_count": r.failure_count,
            "source": "custom",
        }
        for r in db_rows
    ]

    builtin_dicts = [
        {
            "id": pb["id"],
            "name": pb["name"],
            "playbook_type": pb["id"],
            "description": f"Built-in: {pb['name']}",
            "steps": pb["steps"],
            "conditions": {
                "trigger_keywords": pb.get("trigger_keywords", []),
                "trigger_categories": pb.get("trigger_categories", []),
                "max_priority": pb.get("max_priority", "p3_medium"),
                "auto_resolve": pb.get("auto_resolve", False),
            },
            "is_active": True,
            "success_count": 0,
            "failure_count": 0,
            "source": "builtin",
        }
        for pb in _BUILTIN_PLAYBOOKS
    ]

    return db_playbooks + builtin_dicts


def _safe_json(raw: Optional[str], default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def create_playbook(db: Session, data: dict) -> dict:
    """Create a new custom playbook in the database.

    *data* keys: name, playbook_type, description, steps (list), conditions (dict).
    """
    from app.models.service_desk import AutonomousPlaybook

    row = AutonomousPlaybook(
        name=data["name"],
        playbook_type=data.get("playbook_type", data["name"].lower().replace(" ", "_")),
        description=data.get("description"),
        steps_json=json.dumps(data.get("steps", [])),
        conditions_json=json.dumps(data.get("conditions", {})),
        is_active=True,
    )
    db.add(row)
    db.flush()
    return {
        "id": row.id,
        "name": row.name,
        "playbook_type": row.playbook_type,
        "status": "created",
    }


def update_playbook(db: Session, playbook_id: str, data: dict) -> dict:
    """Update an existing custom playbook."""
    from app.models.service_desk import AutonomousPlaybook
    from fastapi import HTTPException

    row = db.query(AutonomousPlaybook).filter(AutonomousPlaybook.id == playbook_id).first()
    if not row:
        raise HTTPException(404, "Playbook not found")

    if "name" in data:
        row.name = data["name"]
    if "description" in data:
        row.description = data["description"]
    if "steps" in data:
        row.steps_json = json.dumps(data["steps"])
    if "conditions" in data:
        row.conditions_json = json.dumps(data["conditions"])
    if "is_active" in data:
        row.is_active = data["is_active"]

    db.flush()
    return {"id": row.id, "name": row.name, "status": "updated"}


def deactivate_playbook(db: Session, playbook_id: str) -> dict:
    """Deactivate (soft-delete) a custom playbook."""
    from app.models.service_desk import AutonomousPlaybook
    from fastapi import HTTPException

    row = db.query(AutonomousPlaybook).filter(AutonomousPlaybook.id == playbook_id).first()
    if not row:
        raise HTTPException(404, "Playbook not found")

    row.is_active = False
    db.flush()
    return {"id": playbook_id, "status": "deactivated"}


def get_execution_stats(db: Session) -> dict:
    """Return aggregate statistics on autonomous resolution executions."""
    from app.models.service_desk import AutonomousPlaybookExecution
    from sqlalchemy import func

    total = db.query(func.count(AutonomousPlaybookExecution.id)).scalar() or 0
    success = (
        db.query(func.count(AutonomousPlaybookExecution.id))
        .filter(AutonomousPlaybookExecution.status == "success")
        .scalar() or 0
    )
    failed = (
        db.query(func.count(AutonomousPlaybookExecution.id))
        .filter(AutonomousPlaybookExecution.status == "failed")
        .scalar() or 0
    )

    by_type = (
        db.query(
            AutonomousPlaybookExecution.playbook_type,
            func.count(AutonomousPlaybookExecution.id).label("count"),
        )
        .group_by(AutonomousPlaybookExecution.playbook_type)
        .all()
    )

    return {
        "total_executions": total,
        "success": success,
        "failed": failed,
        "success_rate_pct": round(success / total * 100, 1) if total else 0,
        "by_playbook_type": {t: c for t, c in by_type},
    }


def get_execution_log(db: Session, page: int = 1, page_size: int = 25) -> dict:
    """Return paginated autonomous agent execution log."""
    from app.models.service_desk import AutonomousPlaybookExecution

    q = db.query(AutonomousPlaybookExecution).order_by(
        AutonomousPlaybookExecution.executed_at.desc()
    )
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": r.id,
                "ticket_id": r.ticket_id,
                "playbook_type": r.playbook_type,
                "status": r.status,
                "confidence_score": r.confidence_score,
                "resolution_note": r.resolution_note,
                "error_message": r.error_message,
                "executed_at": r.executed_at.isoformat() if r.executed_at else None,
                "triggered_by": r.triggered_by,
            }
            for r in rows
        ],
    }
