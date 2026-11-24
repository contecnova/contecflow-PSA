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
from typing import Callable, NamedTuple, Optional

from sqlalchemy.orm import Session

from app.services.textos_de_salida import texto as _texto

from app.models.collaboration import (
    CollaborationBotApp, CollaborationBotExecution,
    CollaborationCall, CollaborationConversation, CollaborationMessage,
    CollaborationSlashCommandLog, CollaborationTranscript,
)
from app.services.collaboration._permissions import _org
from app.core.background import spawn

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
        # auditoría 2026-08, P2-15: referencia fuerte para el publish. `spawn`
        # resuelve el bucle en marcha, así que ya no hace falta obtenerlo aquí.
        spawn(bus.publish(conv_channel(conversation_id), {
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
            output = {"error": _t(db, user, "comando_desconocido", comando=command)}
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
        return {"error": _t(db, user, "no_disponible", bot="Nexus")}
    answer, source = _nexus_answer(db, user, args)
    found = bool(answer)
    if not found:
        # Escalate to ticket — use Service Desk integration
        ticket_info = _escalate_to_ticket(db, user, conversation_id, args)
        body = _t(db, user, "ask_sin_respuesta", numero=ticket_info.get('number', '?'),
                  asignado=ticket_info.get('assignee') or _t(db, user, "soporte"))
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
        # Auditoría 22-11-2026 (A35): antes cogía «el primer proyecto activo» de la
        # empresa y la tarea caía en un proyecto cualquiera. Sin proyecto, no se crea.
        return {"error": _t(db, user, "canal_sin_proyecto_tareas")}
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
            body=(_t(db, user, "tarea_creada_en", titulo=title, proyecto=project_id) if project_id
                  else _t(db, user, "tarea_creada", titulo=title)),
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
            body=_t(db, user, "ticket_abierto", numero=info.get('number', '?'),
                    asignado=info.get('assignee') or _t(db, user, "soporte")),
            metadata={"card": "ticket", "ticket": info},
        )
    return info


def _slash_imputar(db: Session, user, conversation_id: str, args: str) -> dict:
    """Formato: /imputar 30m sobre tarea T-123  ó  /imputar 1h proyecto X"""
    from app.models.project import Project
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
        return {"error": _t(db, user, "indica_duracion")}
    project_id = None
    ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()
    if ch:
        project_id = ch.project_id
    if not project_id:
        return {"error": _t(db, user, "canal_sin_proyecto")}
    # Auditoría 22-11-2026 (A35): antes `Imputation(...)` a mano, sin coste (0 €),
    # sin topes ni cierre de periodo, y con la fecha en UTC. Ahora, la puerta común.
    from app.core.errores import ErrorDeDominio
    from app.core.timeutil import today_for_user
    from app.services.imputation_service.alta import crear_imputacion_validada
    proyecto = db.query(Project).filter(Project.id == project_id).first()
    try:
        imp = crear_imputacion_validada(user, db, project_id=project_id, fecha=today_for_user(user),
                                        horas=duration, description=args,
                                        is_billable=bool(getattr(proyecto, "is_billable", False)))
    except ErrorDeDominio as exc:
        db.rollback()
        return {"error": str(exc.detail), "code": getattr(exc, "code", None)}
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=_t(db, user, "horas_imputadas", horas=f"{duration:.2f}"),
            metadata={"card": "imputation", "imputation_id": imp.id, "hours": duration, "project_id": project_id},
        )
    return {"imputation_id": imp.id, "hours": duration}


def _slash_risk(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "watcher")
    if not bot:
        return {"error": _t(db, user, "no_disponible", bot="Watcher")}
    _post_bot_message(
        db, organization_id=org, bot=bot, conversation_id=conversation_id,
        body=_t(db, user, "riesgo_registrado", texto=args),
        metadata={"card": "risk", "title": args},
    )
    return {"ok": True}


def _slash_decision(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "compliance")
    if not bot:
        return {"error": _t(db, user, "no_disponible", bot="Compliance")}
    _post_bot_message(
        db, organization_id=org, bot=bot, conversation_id=conversation_id,
        body=_t(db, user, "decision_registrada", texto=args),
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
        return {"error": _t(db, user, "formato_poll")}
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
        return {"error": _t(db, user, "no_disponible", bot="Pulse")}
    questions = [_t(db, user, "standup_ayer"), _t(db, user, "standup_hoy"), _t(db, user, "standup_bloqueo")]
    body = _t(db, user, "standup_titulo") + "\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
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
        body = (_t(db, user, "resultados") + "\n" + "\n".join(f"- {a['name']}" for a in items)
                if items else _t(db, user, "sin_resultados"))
        _post_bot_message(db, organization_id=org, bot=bot, conversation_id=conversation_id, body=body,
                          metadata={"card": "findfile", "items": items, "project_id": project_id})
    return {"results": items}


def _slash_onboard(db: Session, user, conversation_id: str, args: str) -> dict:
    org = _org(user)
    bot = _bot_for(db, org, "pulse")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=_t(db, user, "bienvenida"),
            metadata={"card": "onboard"},
        )
    return {"ok": True}


def _slash_meet(db: Session, user, conversation_id: str, args: str) -> dict:
    """Inicia llamada inmediata."""

    org = _org(user)
    call = CollaborationCall(
        organization_id=org, conversation_id=conversation_id, initiated_by=user.id,
        kind="video", status="active", livekit_room="placeholder", started_at=utcnow(),
    )
    db.add(call); db.flush()
    from app.services.collaboration.calls import _prefijo_de_sala  # §5: un solo nombre de sala
    call.livekit_room = _prefijo_de_sala(call.id)
    db.commit()
    bot = _bot_for(db, org, "pulse")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=_t(db, user, "llamada_iniciada"),
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
    summary = _ai_summarize(text) or _t(db, user, "sin_contenido")
    bot = _bot_for(db, org, "nexus")
    if bot:
        _post_bot_message(
            db, organization_id=org, bot=bot, conversation_id=conversation_id,
            body=_t(db, user, "resumen_mensajes", n=len(rows), resumen=summary),
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
            body=_t(db, user, "escalado", numero=info.get('number', '?')),
            metadata={"card": "escalation", "ticket": info},
        )
    return info


def _t(db, user, clave: str, **params) -> str:
    """Texto `bot.<clave>` en el idioma de quien escribe (23-11-2026: antes castellano fijo)."""
    from app.services.texto_para_usuario import texto_para
    return texto_para(db, getattr(user, "id", None), f"bot.{clave}", org_id=getattr(user, "organization_id", None),
                      **params)


class _Comando(NamedTuple):
    """Un slash command: lo que lo ejecuta y lo que se le cuenta a la gente."""

    handler: Callable
    descripcion: str  # clave de `textos_de_salida` (`bot.ayuda.<comando>`)


# ── Los slash commands, en UNA tabla ────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). El despacho estaba aqui y el listado de ayuda
# escrito a mano en el endpoint, con las trece descripciones repetidas. Hoy
# coincidian —comprobado uno a uno— pero nada lo garantizaba: un comando nuevo
# se podia implementar sin anunciarlo, o anunciar sin implementar.
#
# Ahora el nombre, el ejecutor y la descripcion van juntos, y `/slash/help` se
# deriva de esta tabla. Hay un test que cruza las claves con las funciones
# `_slash_*` del modulo, para que implementar una y olvidarse de la tabla
# tampoco pase en silencio.
COMANDOS: dict[str, _Comando] = {
    "ask": _Comando(_slash_ask, "bot.ayuda.ask"),
    "task": _Comando(_slash_task, "bot.ayuda.task"),
    "ticket": _Comando(_slash_ticket, "bot.ayuda.ticket"),
    "imputar": _Comando(_slash_imputar, "bot.ayuda.imputar"),
    "risk": _Comando(_slash_risk, "bot.ayuda.risk"),
    "decision": _Comando(_slash_decision, "bot.ayuda.decision"),
    "poll": _Comando(_slash_poll, "bot.ayuda.poll"),
    "standup": _Comando(_slash_standup, "bot.ayuda.standup"),
    "findfile": _Comando(_slash_findfile, "bot.ayuda.findfile"),
    "onboard": _Comando(_slash_onboard, "bot.ayuda.onboard"),
    "meet": _Comando(_slash_meet, "bot.ayuda.meet"),
    "recap": _Comando(_slash_recap, "bot.ayuda.recap"),
    "escalate": _Comando(_slash_escalate, "bot.ayuda.escalate"),
}

#: La tabla de despacho, derivada. Se conserva el nombre porque es el que usa
#: `handle_slash`, pero ya no es una fuente de verdad aparte.
SLASH_HANDLERS = {nombre: c.handler for nombre, c in COMANDOS.items()}


def slash_help(idioma: Optional[str] = None) -> list[dict]:
    """El listado de ayuda, derivado de la tabla de comandos.

    El orden es el de la tabla, que es el que tenia el listado escrito a mano:
    los mas usados primero, no alfabetico.
    """
    return [
        {"name": f"/{nombre}", "desc": _texto(c.descripcion, idioma)}
        for nombre, c in COMANDOS.items()
    ]


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
    # ── La vía de IA del bot: RETIRADA (auditoría 22-11-2026, fantasma 2) ──
    #
    # Importaba `ai_chat_service.quick_answer`, que nunca ha existido: la rama
    # no respondía nunca y aparentaba un bot con IA. Se retira; Nexus responde
    # con la base de conocimiento del Service Desk y, si no encuentra nada,
    # abre ticket (ver DOCS «Colaboración → bots»). Para IA en el chat, el
    # asistente (`/ask` → ai_chat) es la vía con gobierno y guardarraíles.
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
    org_id = _org(user)  # authz guard: lanza 403 si el usuario no tiene organización
    title = (query or _t(db, user, "solicitud_desde_chat")).strip()[:120]
    description = query or _t(db, user, "generado_desde_chat")
    # FIX: el modelo Ticket usa ``requester_user_id`` (no ``reporter_user_id``)
    # → pasar la clave incorrecta lanzaba TypeError en runtime al crear ticket
    # desde el bot de chat. Verificado con `Ticket(reporter_user_id=...)`.
    ticket = Ticket(
        title=title, description=description,
        ticket_type=TicketType.question if not force else TicketType.incident,
        priority=TicketPriority.p3_medium if priority == "p3_medium" else TicketPriority.p2_high,
        status=TicketStatus.new,
        requester_user_id=user.id,
        # 24-11-2026 (migración 208): la empresa explícita, la activa de quien
        # escribe (la deducción por `requester_user_id` daría la de su ficha).
        organization_id=org_id,
    )
    if hasattr(ticket, "number"):
        # Auditoría 22-11-2026 (A35): `SD-{timestamp % 1e6}` colisionaba; la
        # numeración común de tickets (por empresa y tipo).
        from app.services.sla_service import next_ticket_number
        ticket.number = next_ticket_number(ticket.ticket_type.value, db, getattr(user, "organization_id", None))
    db.add(ticket)
    db.commit()
    return {"id": ticket.id, "number": getattr(ticket, "number", None), "assignee": None}


# ── Post-call summary (called from queue when a call ends) ───────────────────
def texto_de_sistema(clave: str, org_id=None, **params) -> str:
    """Texto sin persona delante (tarea en segundo plano): en el idioma de la empresa."""
    from app.db.session import SessionLocal
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto
    s = SessionLocal()
    from app.db.contexto_de_tenant import fijar_contexto as _fijar_contexto
    _fijar_contexto(s, org_id, "textos de sistema sin empresa")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
    try:
        return texto(clave, idioma_de_salida(s, org_id=org_id), **params)
    finally:
        s.close()


def summarize_call(call_id: str, organization_id: str) -> None:
    """Generate transcript summary + actions and post into the call conversation.

    Si hay un transcript ya creado por subtítulos en vivo, usa ese texto.
    Si no, se queda con un placeholder. Si OPENAI_API_KEY está configurada
    se usa GPT para resumen de calidad; si no, fallback heurístico.
    """
    from app.db.session import SessionLocal
    from app.services.collaboration._transcription import summarize_text
    from app.services.formato_regional import idioma
    db = SessionLocal()
    from app.db.contexto_de_tenant import fijar_contexto as _fijar_contexto
    _fijar_contexto(db, organization_id, "resumen de llamada sin empresa")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
    try:
        call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id).first()
        if not call:
            return
        existing = db.query(CollaborationTranscript).filter(CollaborationTranscript.call_id == call.id).first()
        text = existing.text if existing and existing.text else texto_de_sistema("bot.reunion_fechas", organization_id, iniciada=call.started_at, finalizada=call.ended_at)
        summary, actions = summarize_text(text, db=db, organization_id=organization_id)
        if existing:
            existing.summary = summary
            existing.actions_json = actions
        else:
            db.add(CollaborationTranscript(
                organization_id=organization_id, call_id=call.id,
                language=idioma(db, org_id=organization_id), text=text, segments_json=[],
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
                body=texto_de_sistema("bot.resumen_reunion", resumen=summary, org_id=organization_id),
                metadata={"card": "call_summary", "call_id": call.id, "actions": actions},
            )
    finally:
        db.close()
