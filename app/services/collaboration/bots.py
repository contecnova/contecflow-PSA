"""
Collaboration bots — slash command handlers + auto-generation of bot replies.

Bots:
  nexus      — IA: pregunta libre, busca KB, escala a ticket si no resuelve
  oracle     — PSA insights (proyectos, recursos, riesgos)
  pulse      — standups, recordatorios, post-call summaries
  watcher    — alertas de SLA / hitos / riesgos
  bridge     — Jira / GitHub / GitLab / SD / M365 / Google calendar
  compliance — retención / legal hold / audit / eDiscovery commands

All output goes into the conversation as messages of type=bot, user_id=null,
bot_id=<bot.id>, metadata_json containing card data.

Slash commands (handled inline if message body starts with /):
  /ask /task /ticket /imputar /risk /decision /poll /standup
  /findfile /onboard /meet /recap /escalate
"""
from __future__ import annotations

import logging
import re
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy.orm import Session

from app.models.collaboration import (
    CollaborationBotApp, CollaborationBotExecution,
    CollaborationCall, CollaborationConversation, CollaborationMessage,
    CollaborationSlashCommandLog, CollaborationTranscript,
)
from app.services.collaboration._permissions import _org

logger = logging.getLogger(__name__)


SLASH_RE = re.compile(r"^/([a-zA-Z]+)\b\s*(.*)$", re.DOTALL)


def _bot_for(db: Session, organization_id: str, handle: str) -> Optional[CollaborationBotApp]:
    return db.query(CollaborationBotApp).filter(
        CollaborationBotApp.organization_id == organization_id,
        CollaborationBotApp.handle == handle,
        CollaborationBotApp.is_enabled == True,
    ).first()


def _post_bot_message(
    db: Session, *,
    organization_id: str,
    bot: CollaborationBotApp,
    conversation_id: str,
    body: str,
    metadata: Optional[dict] = None,
) -> CollaborationMessage:
    from app.services.collaboration.messages import _serialize_message  # noqa: F401
    from app.services.collaboration._bus import bus, conv_channel
    import asyncio

    msg = CollaborationMessage(
        organization_id=organization_id,
        conversation_id=conversation_id,
        bot_id=bot.id,
        type="bot",
        status="visible",
        body=body,
        metadata_json=metadata or {},
        sent_at=utcnow(),
    )
    db.add(msg)
    db.flush()

    # Update conv last activity
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
    if conv:
        conv.last_activity_at = utcnow()
        conv.last_message_id = msg.id
    db.commit()

    # publish realtime
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(bus.publish(conv_channel(conversation_id), {
            "type": "message.created",
            "conversation_id": conversation_id,
            "message_id": msg.id,
            "payload": {
                "id": msg.id, "conversation_id": conversation_id, "bot_id": bot.id,
                "author_name": bot.display_name, "type": "bot", "status": "visible",
                "body": body, "metadata_json": msg.metadata_json or {},
                "sent_at": msg.sent_at.isoformat(),
                "reactions": [], "attachments": [], "is_pinned": False, "is_redacted": False,
            },
        }))
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except RuntimeError:
        pass
    return msg


def _log_exec(db: Session, *, bot: CollaborationBotApp, conversation_id: Optional[str], user, command: Optional[str], status: str, output: dict, error: Optional[str] = None) -> None:
    db.add(CollaborationBotExecution(
        organization_id=bot.organization_id,
        bot_id=bot.id,
        conversation_id=conversation_id,
        triggered_by_user_id=user.id if user else None,
        command=command,
        input_payload={},
        output_payload=output,
        status=status,
        duration_ms=0,
        error_message=error,
    ))
    db.commit()


# ── Inline command dispatcher ────────────────────────────────────────────────
def maybe_handle_inline_command(db: Session, user, message: CollaborationMessage) -> None:
    """If message body starts with '/', dispatch a slash command."""
    if not message.body:
        return
    m = SLASH_RE.match(message.body.strip())
    if not m:
        return
    command, args = m.group(1).lower(), m.group(2).strip()
    handle_slash(db, user, conversation_id=message.conversation_id, command=command, args=args)


def handle_slash(db: Session, user, *, conversation_id: str, command: str, args: str) -> dict:
    org = _org(user)
    handler = SLASH_HANDLERS.get(command)
    success, output = True, {}
    try:
        if not handler:
            output = {"error": f"Comando desconocido: /{command}"}
            success = False
        else:
            output = handler(db, user, conversation_id, args) or {}
    except Exception as e:
        success = False
        output = {"error": str(e)}
        logger.exception("slash %s failed", command)
    db.add(CollaborationSlashCommandLog(
        organization_id=org, user_id=user.id, conversation_id=conversation_id,
        command=command, args=args, success=success, response=output,
    ))
    db.commit()
    return {"command": command, "success": success, "response": output}


# ── Handlers ─────────────────────────────────────────────────────────────────
def _slash_ask(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "nexus")
    if not bot:
        return {"error": "Bot Nexus no disponible"}
    answer, source = _nexus_answer(db, user, args)
    found = bool(answer)
    if not found:
        # Escalate to ticket — use Service Desk integration
        ticket_info = _escalate_to_ticket(db, user, conversation_id, args)
        body = (
            f"No he encontrado información en la base de conocimiento.\n"
            f"He abierto un ticket de soporte: **{ticket_info.get('number', '?')}**.\n"
            f"Auto-asignado a: **{ticket_info.get('assignee', 'soporte')}**."
        )
        meta = {"card": "escalation", "ticket": ticket_info, "source": "nexus"}
    else:
        body = f"**Respuesta:**\n{answer}\n\n_Fuente: {source}_"
        meta = {"card": "answer", "source": source}
    _post_bot_message(db, organization_id=org, bot=bot, conversation_id=conversation_id, body=body, metadata=meta)
    _log_exec(db, bot=bot, conversation_id=conversation_id, user=user, command="ask", status="ok" if found else "partial", output={"found": found})
    return {"found": found}


def _slash_task(db: Session, user, conversation_id: str, args: str) -> dict:
    """Crea una Tarea del PSA vinculada al canal/proyecto."""
    from app.models.task import Task
    from app.models.project import Project
    from app.models.collaboration import CollaborationChannel
    import uuid as _uuid
    org = _org(user)
    title = args.strip() or "Tarea desde chat"
    project_id = None
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
    if ch:
        project_id = ch.project_id
    if not project_id:
        # Pick the first active project of the org so the task can be created.
        proj_q = db.query(Project)
        if hasattr(Project, "organization_id"):
            proj_q = proj_q.filter(Project.organization_id == org)
        if hasattr(Project, "status"):
            proj_q = proj_q.filter(Project.status == "active")
        any_proj = proj_q.first()
        if not any_proj:
            return {"error": "No hay proyectos activos a los que asignar la tarea. Vincula este canal a un proyecto antes."}
        project_id = any_proj.id
    code = f"CHAT-{_uuid.uuid4().hex[:6].upper()}"
    task = Task(
        title=title, project_id=project_id, status="todo",
        priority="medium", created_by=user.id, code=code,
    )
    if hasattr(task, "organization_id"):
        task.organization_id = org
    db.add(task)
    db.commit()
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"✅ Tarea creada: **{title}**" + (f" (proyecto vinculado: {project_id})" if project_id else ""),
            metadata={"card": "task", "task_id": task.id, "project_id": project_id},
        )
    return {"task_id": task.id, "project_id": project_id}


def _slash_ticket(db: Session, user, conversation_id: str, args: str) -> dict:
    info = _escalate_to_ticket(db, user, conversation_id, args, force=True)
    org = _org(user)
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"🎫 Ticket abierto: **{info.get('number', '?')}** asignado a {info.get('assignee', 'soporte')}.",
            metadata={"card": "ticket", "ticket": info},
        )
    return info


def _slash_imputar(db: Session, user, conversation_id: str, args: str) -> dict:
    """Formato: /imputar 30m sobre tarea T-123  ó  /imputar 1h proyecto X"""
    from app.models.imputation import Imputation
    from app.models.collaboration import CollaborationChannel
    org = _org(user)
    # naive parse
    duration = 0.0
    m_h = re.search(r"(\d+(?:\.\d+)?)\s*h", args)
    m_m = re.search(r"(\d+)\s*m", args)
    if m_h:
        duration += float(m_h.group(1))
    if m_m:
        duration += float(m_m.group(1)) / 60
    if duration <= 0:
        return {"error": "indica duración (ej: 30m o 1h30m)"}
    project_id = None
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
    if ch:
        project_id = ch.project_id
    if not project_id:
        return {"error": "El canal no está vinculado a un proyecto"}
    imp = Imputation(user_id=user.id, project_id=project_id, hours=duration, description=args, date=utcnow().date())
    if hasattr(imp, "organization_id"):
        imp.organization_id = org
    db.add(imp)
    db.commit()
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"⏱️ {duration:.2f}h imputadas al proyecto.",
            metadata={"card": "imputation", "imputation_id": imp.id, "hours": duration, "project_id": project_id},
        )
    return {"imputation_id": imp.id, "hours": duration}


def _slash_risk(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "watcher")
    if not bot:
        return {"error": "Bot Watcher no disponible"}
    _post_bot_message(
        db, organization_id=org, bot=bot, conversation_id=conversation_id,
        body=f"⚠️ Riesgo registrado: {args}",
        metadata={"card": "risk", "title": args},
    )
    return {"ok": True}


def _slash_decision(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "compliance")
    if not bot:
        return {"error": "Bot Compliance no disponible"}
    _post_bot_message(
        db, organization_id=org, bot=bot, conversation_id=conversation_id,
        body=f"📜 Decisión registrada (auditada):\n{args}",
        metadata={"card": "decision", "text": args, "actor": user.id, "ts": utcnow().isoformat()},
    )
    from app.services.collaboration import audit_log
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="decision.recorded", entity_type="conversation", entity_id=conversation_id,
        payload={"text": args},
    )
    db.commit()
    return {"ok": True}


def _slash_poll(db: Session, user, conversation_id: str, args: str) -> dict:
    """Formato: /poll Pregunta? | opción 1 | opción 2 | opción 3"""
    org = _org(user)
    bot = _bot_for(db, org, "pulse")
    parts = [p.strip() for p in args.split("|") if p.strip()]
    if len(parts) < 2:
        return {"error": "Formato: /poll Pregunta | opción A | opción B | ..."}
    question, options = parts[0], parts[1:]
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"📊 **{question}**",
            metadata={"card": "poll", "question": question, "options": [{"label": o, "votes": 0} for o in options]},
        )
    return {"options": options}


def _slash_standup(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "pulse")
    if not bot:
        return {"error": "Bot Pulse no disponible"}
    questions = [
        "¿Qué hiciste ayer?",
        "¿Qué harás hoy?",
        "¿Hay algún bloqueo?",
    ]
    body = "🌅 **Standup diario**\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    _post_bot_message(
        db, organization_id=org, bot=bot, conversation_id=conversation_id, body=body,
        metadata={"card": "standup", "questions": questions},
    )
    return {"ok": True}


def _slash_findfile(db: Session, user, conversation_id: str, args: str) -> dict:
    """Busca documentos del proyecto."""
    from app.models.collaboration import CollaborationAttachment, CollaborationChannel
    org = _org(user)
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
    project_id = ch.project_id if ch else None
    q = db.query(CollaborationAttachment).filter(CollaborationAttachment.organization_id == org)
    if args:
        q = q.filter(CollaborationAttachment.name.ilike(f"%{args}%"))
    rows = q.order_by(CollaborationAttachment.created_at.desc()).limit(8).all()
    bot = _bot_for(db, org, "bridge")
    items = [{"id": a.id, "name": a.name, "conversation_id": a.conversation_id} for a in rows]
    if bot:
        body = "🔍 Resultados:\n" + "\n".join(f"- {a['name']}" for a in items) if items else "Sin resultados."
        _post_bot_message(db, organization_id=org, bot=bot, conversation_id=conversation_id, body=body,
                          metadata={"card": "findfile", "items": items, "project_id": project_id})
    return {"results": items}


def _slash_onboard(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "pulse")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body="👋 ¡Bienvenido al equipo! Tienes 3 pasos para empezar:\n1. Únete al canal #general\n2. Configura tu presencia\n3. Conecta tu calendario",
            metadata={"card": "onboard"},
        )
    return {"ok": True}


def _slash_meet(db: Session, user, conversation_id: str, args: str) -> dict:
    """Inicia llamada inmediata."""

    # Pequeño helper que vivía en endpoints/collaboration/calls.py — inlined
    # aquí para romper la dependencia services → endpoints.
    def _room_name(call_id: str) -> str:
        return f"contec-{call_id}"

    org = _org(user)
    call = CollaborationCall(
        organization_id=org, conversation_id=conversation_id, initiated_by=user.id,
        kind="video", status="active", livekit_room="placeholder", started_at=utcnow(),
    )
    db.add(call); db.flush()
    call.livekit_room = f"contec-{call.id}"
    db.commit()
    bot = _bot_for(db, org, "pulse")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body="📞 Llamada iniciada — únete con un click",
            metadata={"card": "call", "call_id": call.id, "room": call.livekit_room},
        )
    return {"call_id": call.id}


def _slash_recap(db: Session, user, conversation_id: str, args: str) -> dict:
    """Resumen IA de los últimos N mensajes."""
    org = _org(user)
    rows = db.query(CollaborationMessage).filter(
        CollaborationMessage.conversation_id == conversation_id,
        CollaborationMessage.status != "deleted",
    ).order_by(CollaborationMessage.sent_at.desc()).limit(40).all()
    rows.reverse()
    text = "\n".join((m.body or "")[:500] for m in rows if m.body)
    summary = _ai_summarize(text) or "Sin contenido suficiente para resumir."
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"📝 **Resumen ({len(rows)} mensajes recientes)**\n{summary}",
            metadata={"card": "recap", "count": len(rows)},
        )
    return {"summarized": True}


def _slash_escalate(db: Session, user, conversation_id: str, args: str) -> dict:
    info = _escalate_to_ticket(db, user, conversation_id, args, force=True, priority="high")
    org = _org(user)
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=f"🚨 Escalado a soporte: {info.get('number', '?')}",
            metadata={"card": "escalation", "ticket": info},
        )
    return info


SLASH_HANDLERS = {
    "ask": _slash_ask,
    "task": _slash_task,
    "ticket": _slash_ticket,
    "imputar": _slash_imputar,
    "risk": _slash_risk,
    "decision": _slash_decision,
    "poll": _slash_poll,
    "standup": _slash_standup,
    "findfile": _slash_findfile,
    "onboard": _slash_onboard,
    "meet": _slash_meet,
    "recap": _slash_recap,
    "escalate": _slash_escalate,
}


# ── Nexus IA backend ─────────────────────────────────────────────────────────
def _nexus_answer(db: Session, user, query: str) -> tuple[Optional[str], Optional[str]]:
    """Tries to answer using Service Desk KB first; returns (answer, source) or (None, None)."""
    if not query:
        return None, None
    try:
        from app.models.service_desk import KBArticle
        rows = db.query(KBArticle).filter(
            KBArticle.organization_id == _org(user),
            KBArticle.title.ilike(f"%{query.split()[0]}%") | KBArticle.summary.ilike(f"%{query}%"),
        ).limit(3).all()
        if rows:
            top = rows[0]
            return (top.summary or top.title, f"KB: {top.title}")
    except Exception:
        logger.debug("_nexus_answer: fallo best-effort ignorado", exc_info=True)
    # Try AI provider next (best-effort)
    try:
        from app.services.ai_chat_service import quick_answer  # may not exist
        ans = quick_answer(query)
        if ans:
            return ans, "Nexus IA"
    except Exception:
        logger.debug("_nexus_answer: fallo best-effort ignorado", exc_info=True)
    return None, None


def _ai_summarize(text: str) -> Optional[str]:
    """Naive summarizer used as fallback when no AI provider is wired in."""
    if not text:
        return None
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", text) if s.strip()]
    if not sentences:
        return text[:280]
    pick = sentences[: min(5, len(sentences))]
    return "• " + "\n• ".join(pick)


# ── Service Desk auto-ticket escalation ──────────────────────────────────────
def _escalate_to_ticket(db: Session, user, conversation_id: str, query: str, *, force: bool = False, priority: str = "p3_medium") -> dict:
    from app.models.service_desk import Ticket, TicketStatus, TicketType, TicketPriority
    _org(user)  # authz guard: lanza 403 si el usuario no tiene organización
    title = (query or "Solicitud desde chat").strip()[:120]
    description = query or "Generado desde chat"
    # FIX: el modelo Ticket usa ``requester_user_id`` (no ``reporter_user_id``)
    # → pasar la clave incorrecta lanzaba TypeError en runtime al crear ticket
    # desde el bot de chat. Verificado con `Ticket(reporter_user_id=...)`.
    ticket = Ticket(
        title=title, description=description,
        ticket_type=TicketType.question if not force else TicketType.incident,
        priority=TicketPriority.p3_medium if priority == "p3_medium" else TicketPriority.p2_high,
        status=TicketStatus.new,
        requester_user_id=user.id,
    )
    # NOTA: Ticket no tiene columna organization_id; el scope multi-tenant
    # viene vía project_id → Project.organization_id. El bot crea tickets
    # ad-hoc sin project, así que la org se deriva del requester user.
    if hasattr(ticket, "number"):
        ticket.number = f"SD-{int(utcnow().timestamp()) % 1_000_000:06d}"
    db.add(ticket)
    db.commit()
    return {"id": ticket.id, "number": getattr(ticket, "number", None), "assignee": "soporte"}


# ── Post-call summary (called from queue when a call ends) ───────────────────
def summarize_call(call_id: str, organization_id: str) -> None:
    """Generate transcript summary + actions and post into the call conversation.

    Si hay un transcript ya creado por subtítulos en vivo, usa ese texto.
    Si no, se queda con un placeholder. Si OPENAI_API_KEY está configurada
    se usa GPT para resumen de calidad; si no, fallback heurístico.
    """
    from app.db.session import SessionLocal
    from app.services.collaboration._transcription import summarize_text
    db = SessionLocal()
    try:
        call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id).first()
        if not call:
            return
        existing = db.query(CollaborationTranscript).filter(CollaborationTranscript.call_id == call.id).first()
        text = existing.text if existing and existing.text else f"Reunión iniciada {call.started_at}, finalizada {call.ended_at}."
        summary, actions = summarize_text(text)
        if existing:
            existing.summary = summary
            existing.actions_json = actions
        else:
            db.add(CollaborationTranscript(
                organization_id=organization_id, call_id=call.id,
                language="es", text=text, segments_json=[],
                summary=summary, actions_json=actions,
            ))
        call.has_summary = True
        call.has_transcript = True
        db.commit()
        bot = db.query(CollaborationBotApp).filter(
            CollaborationBotApp.organization_id == organization_id,
            CollaborationBotApp.handle == "pulse",
        ).first()
        if bot and call.conversation_id:
            _post_bot_message(
                db, organization_id=organization_id, bot=bot,
                conversation_id=call.conversation_id,
                body=f"📋 Resumen reunión:\n{summary}",
                metadata={"card": "call_summary", "call_id": call.id, "actions": actions},
            )
    finally:
        db.close()
