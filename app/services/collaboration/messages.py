"""
Message service: send, edit, delete, history, threads, reactions, mentions, reads, pins, saves, drafts.
Emits realtime events on the bus and writes audit entries.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.models.collaboration import (
    CollaborationAttachment,
    CollaborationChannel, CollaborationConversation,
    CollaborationDirectConversation,
    CollaborationDraft, CollaborationGroupConversation,
    CollaborationMention,
    CollaborationMessage, CollaborationMessageVersion, CollaborationConversationMember,
    CollaborationNotification, CollaborationPinnedMessage, CollaborationRead,
    CollaborationReaction, CollaborationSavedMessage, CollaborationThread,
)
from app.models.user import User
from app.services.collaboration import audit_log, bus
from app.services.collaboration._bus import (
    conv_channel, user_channel, client_user_channel,
)
from app.services.collaboration._permissions import (
    _org, assert_conversation_access,
)
from app.services.collaboration._search import search_engine
from app.services.collaboration._storage import scan_dlp
import logging
from app.core.background import spawn
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


MENTION_RE = re.compile(r"@([a-zA-Z0-9_.\-]+)")


def _aware(dt: datetime) -> datetime:
    """Devuelve un datetime tz-aware (UTC) para comparaciones consistentes."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _resolve_conversation(db: Session, *, conversation_id: Optional[str], channel_id: Optional[str], direct_id: Optional[str], group_id: Optional[str]) -> CollaborationConversation:
    if conversation_id:
        c = db.query(CollaborationConversation).filter(CollaborationConversation.id == conversation_id).first()
        if not c:
            raise ErrorDeDominio(404, "Conversación no encontrada")
        return c
    if channel_id:
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.id == channel_id).first()
        if not ch:
            raise ErrorDeDominio(404, "Canal no encontrado")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == ch.conversation_id).first()
    if direct_id:
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.id == direct_id).first()
        if not d:
            raise ErrorDeDominio(404, "Direct no encontrada")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == d.conversation_id).first()
    if group_id:
        g = db.query(CollaborationGroupConversation).filter(CollaborationGroupConversation.id == group_id).first()
        if not g:
            raise ErrorDeDominio(404, "Grupo no encontrado")
        return db.query(CollaborationConversation).filter(CollaborationConversation.id == g.conversation_id).first()
    raise ErrorDeDominio(400, "Indica conversation_id / channel_id / direct_id / group_id")


# ── Notifications fan-out ────────────────────────────────────────────────────
# ── A quién se avisa de un mensaje nuevo ─────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_notify_recipients` era complejidad 22 en dos
# fases mezcladas: reunir los destinatarios segun el tipo de conversacion, y
# decidir a quien de ellos se le avisa. Ahora son dos fases con nombre.
#
# Lo que se ve al separarlas y no se veia antes: **«una mencion rompe todo
# silencio» es UNA regla escrita CINCO veces**. El bucle original repetia
# `and not is_mention` en las cinco comprobaciones de silencio —regla por
# conversacion a 'none', a 'mentions', miembro silenciado, nivel 'none' y nivel
# 'mentions'—. Escrita cinco veces, basta olvidarla en una para que un @mencion
# deje de llegar por un camino y siga llegando por los otros cuatro, sin que nada
# falle. Ahora se calcula el silencio y la excepcion se aplica una sola vez.


# Los valores de `notify_level` y de `notify_messages` que silencian. Cualquier
# otro valor NO silencia: un nivel desconocido avisa, que es el lado seguro para
# una notificacion (mejor un aviso de mas que perderse una mencion). Era el
# comportamiento del original y se conserva.
_NIVELES_QUE_SILENCIAN = frozenset({"none", "mentions"})


@dataclass(frozen=True, slots=True)
class _Destinatario:
    """Un candidato a recibir el aviso.

    `user_id` y `client_user_id` son excluyentes: los internos llevan el primero
    y los del portal de cliente el segundo.
    """

    user_id: str | None
    client_user_id: str | None
    notify_level: str
    is_muted: bool


def _destinatarios_de_canal(db: Session, conv: CollaborationConversation) -> list[_Destinatario]:
    """Los de un canal.

    Publico, de anuncios y de proyecto se resuelven por el EQUIPO: todo el equipo
    los ve, con nivel 'all' y sin silenciar. Los demas por la pertenencia
    explicita al canal, que si trae nivel y silencio por miembro.
    """
    ch = (db.query(CollaborationChannel)
            .filter(CollaborationChannel.conversation_id == conv.id)
            .first())
    if not ch:
        return []

    if ch.channel_type in {"public", "announcement", "project"}:
        from app.models.collaboration import CollaborationTeamMember
        return [
            _Destinatario(tm.user_id, None, "all", False)
            for tm in db.query(CollaborationTeamMember)
                        .filter(CollaborationTeamMember.team_id == ch.team_id)
                        .all()
        ]

    from app.models.collaboration import CollaborationChannelMember
    return [
        _Destinatario(cm.user_id, None, cm.notify_level or "all", bool(cm.is_muted))
        for cm in db.query(CollaborationChannelMember)
                    .filter(CollaborationChannelMember.channel_id == ch.id)
                    .all()
    ]


def _destinatarios_de_directo(db: Session, conv: CollaborationConversation) -> list[_Destinatario]:
    """Los dos lados de una conversacion directa, internos o del portal.

    Los internos se recogen en un conjunto para que una conversacion de alguien
    consigo mismo no genere dos avisos.
    """
    d = (db.query(CollaborationDirectConversation)
           .filter(CollaborationDirectConversation.conversation_id == conv.id)
           .first())
    if not d:
        return []
    salida = [
        _Destinatario(uid, None, "all", False)
        for uid in {d.user_a_id, d.user_b_id} if uid
    ]
    salida += [
        _Destinatario(None, cid, "all", False)
        for cid in (d.client_user_a_id, d.client_user_b_id) if cid
    ]
    return salida


def _destinatarios_de_grupo(db: Session, conv: CollaborationConversation) -> list[_Destinatario]:
    return [
        _Destinatario(m.user_id, m.client_user_id, "all",
                      bool(getattr(m, "is_muted", False)))
        for m in db.query(CollaborationConversationMember)
                   .filter(CollaborationConversationMember.conversation_id == conv.id)
                   .all()
    ]


_DESTINATARIOS_POR_TIPO = {
    "channel": _destinatarios_de_canal,
    "direct": _destinatarios_de_directo,
    "group": _destinatarios_de_grupo,
}


def _reglas_por_conversacion(db: Session, organization_id: str, conv_id: str) -> dict:
    """`{user_id: notify_messages}` de las reglas con alcance de conversacion."""
    from app.models.collaboration import CollaborationNotificationRule

    filas = db.query(CollaborationNotificationRule).filter(
        CollaborationNotificationRule.organization_id == organization_id,
        CollaborationNotificationRule.scope == "conversation",
        CollaborationNotificationRule.target_id == conv_id,
    ).all()
    return {r.user_id: r.notify_messages for r in filas if r.user_id}


def _es_el_autor(d: _Destinatario, message: CollaborationMessage) -> bool:
    """Nadie recibe aviso de su propio mensaje."""
    if message.user_id and d.user_id == message.user_id:
        return True
    return bool(message.client_user_id and d.client_user_id == message.client_user_id)


def _le_mencionan(d: _Destinatario, mencionados_usuarios: set,
                  mencionados_clientes: set, es_para_todos: bool) -> bool:
    if es_para_todos:
        return True
    if d.user_id and d.user_id in mencionados_usuarios:
        return True
    return bool(d.client_user_id and d.client_user_id in mencionados_clientes)


def _esta_silenciado(d: _Destinatario, regla_de_conversacion: str | None) -> bool:
    """Si este destinatario tiene silenciada la conversacion.

    Tres fuentes de silencio, y la regla por conversacion manda sobre la
    pertenencia porque es la que la persona ha puesto para ESTA conversacion.
    Ninguna de las tres sobrevive a una mencion — eso lo decide quien llama.
    """
    return (
        regla_de_conversacion in _NIVELES_QUE_SILENCIAN
        or d.is_muted
        or d.notify_level in _NIVELES_QUE_SILENCIAN
    )


def _notify_recipients(db: Session, *, organization_id: str, conv: CollaborationConversation, message: CollaborationMessage, mentions: list[CollaborationMention]) -> None:
    """Crea CollaborationNotification para los participantes, respetando:
        • Channel/Group membership: `notify_level` ('all' | 'mentions' | 'none')
          y `is_muted` por miembro.
        • Reglas globales (`CollaborationNotificationRule`) con scope='conversation'
          y target_id = conv.id por usuario; si `notify_messages='none'` se silencia
          ese usuario para esa conversación.

    Una mención rompe cualquier silencio. Es la regla que el bucle original
    repetía cinco veces y que ahora se aplica en un solo sitio.
    """
    reunir = _DESTINATARIOS_POR_TIPO.get(conv.kind)
    if reunir is None:
        return
    destinatarios = reunir(db, conv)
    if not destinatarios:
        return

    mencionados_usuarios = {m.mentioned_user_id for m in mentions if m.mentioned_user_id}
    mencionados_clientes = {m.mentioned_client_user_id for m in mentions if m.mentioned_client_user_id}
    es_para_todos = any(m.is_everyone for m in mentions)
    reglas = _reglas_por_conversacion(db, organization_id, conv.id)

    for d in destinatarios:
        if _es_el_autor(d, message):
            continue
        mencionado = _le_mencionan(
            d, mencionados_usuarios, mencionados_clientes, es_para_todos
        )
        if not mencionado and _esta_silenciado(d, reglas.get(d.user_id) if d.user_id else None):
            continue
        db.add(CollaborationNotification(
            organization_id=organization_id,
            user_id=d.user_id, client_user_id=d.client_user_id,
            kind="mention" if mencionado else "message",
            conversation_id=conv.id, message_id=message.id,
            title=("Mención en chat" if mencionado else "Nuevo mensaje"),
            body=(message.body or "")[:200],
            payload={"conversation_id": conv.id, "message_id": message.id},
        ))


def _publish_async(channel: str, event: dict) -> None:
    """Fire-and-forget publish."""
    try:
        loop = asyncio.get_event_loop()
        # auditoría 2026-08, P2-15: referencia fuerte para el publish.
        spawn(bus.publish(channel, event), name="collab-publish", loop=loop)
    except RuntimeError:
        # No loop (test mode) — best-effort
        asyncio.run(bus.publish(channel, event))


# ── Send / edit / delete ─────────────────────────────────────────────────────
def _autorizar_envio(db: Session, user, conv, *, client_user_id, bot_id) -> None:
    """Quién puede escribir en esta conversación, según quién escribe.

    La comprobación cambia con el tipo de remitente, y por eso vive aquí y no en
    quien llama: **un cliente del portal no pasa por ABAC**, porque las
    políticas están escritas sobre usuarios internos. Pasa por la comprobación
    de participante-cliente, que es su equivalente.

    Un bot no pasa por ninguna de las dos: lo que autoriza a un bot es haberlo
    dado de alta, y eso ocurre antes de llegar aquí.
    """
    if client_user_id:
        from app.services.collaboration._permissions import (
            is_client_conversation_participant,
        )
        if not is_client_conversation_participant(db, user, conv.id):
            raise ErrorDeDominio(403, "No tienes acceso a esta conversación")
        return
    if bot_id:
        return
    assert_conversation_access(db, user, conv.id)
    enforce_abac(db, user, "collaboration_message", resource_id=conv.id, action="send")


def _enganchar_al_hilo(db: Session, org, conv, msg, parent_message_id) -> None:
    """Mete el mensaje en el hilo de su padre, creando el hilo si es el primero.

    El hilo se identifica por su mensaje raíz, no por un id propio: eso permite
    que el primer «responder» a un mensaje cualquiera cree el hilo sin que nadie
    lo haya declarado antes, que es como funciona en un chat.
    """
    if not parent_message_id:
        return
    hilo = db.query(CollaborationThread).filter(
        CollaborationThread.root_message_id == parent_message_id,
    ).first()
    if not hilo:
        hilo = CollaborationThread(
            organization_id=org, conversation_id=conv.id,
            root_message_id=parent_message_id,
        )
        db.add(hilo)
        db.flush()
    msg.thread_id = hilo.id
    hilo.reply_count = (hilo.reply_count or 0) + 1
    hilo.last_reply_at = datetime.now(timezone.utc)


def _crear_menciones(
    db: Session, org, msg, *, mention_user_ids, mention_client_ids, is_everyone
) -> list:
    """Las menciones del mensaje: a usuarios, a clientes del portal y a todos.

    Se devuelven además de guardarse porque el reparto de notificaciones las
    necesita, y volver a consultarlas sería una consulta de más por mensaje.
    """
    menciones = []
    for uid in (mention_user_ids or []):
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, mentioned_user_id=uid)
        db.add(m)
        menciones.append(m)
    for cid in (mention_client_ids or []):
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, mentioned_client_user_id=cid)
        db.add(m)
        menciones.append(m)
    if is_everyone:
        m = CollaborationMention(
            organization_id=org, message_id=msg.id, is_everyone=True)
        db.add(m)
        menciones.append(m)
    return menciones


def _exigir_enlaces_de_la_org(db: Session, org, tarea, ticket, entregable, riesgo) -> None:
    """Auditoria 2026-11: un mensaje solo enlaza tareas, tickets, entregables y
    riesgos de su organizacion (antes los ids se guardaban sin comprobar)."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.pipeline import Risk
    from app.models.resources import Deliverable
    from app.models.service_desk.tickets import Ticket
    from app.models.task import Task
    for modelo, valor, nombre in ((Task, tarea, "tarea"), (Ticket, ticket, "ticket"),
                                  (Deliverable, entregable, "entregable"), (Risk, riesgo, "riesgo")):
        if not valor:
            continue
        with sin_filtro_de_tenant(db):
            fila = db.query(modelo.organization_id).filter(modelo.id == valor).first()
        if fila is None or (fila[0] and fila[0] != org):
            raise ErrorDeDominio(422, f"El {nombre} enlazado no existe en tu organizacion")


def send_message(
    db: Session, user, *,
    body: str,
    conversation_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    direct_id: Optional[str] = None,
    group_id: Optional[str] = None,
    parent_message_id: Optional[str] = None,
    type: str = "text",
    metadata_json: Optional[dict] = None,
    mention_user_ids: Optional[list[str]] = None,
    mention_client_ids: Optional[list[str]] = None,
    is_everyone: bool = False,
    scheduled_for: Optional[datetime] = None,
    linked_task_id: Optional[str] = None,
    linked_ticket_id: Optional[str] = None,
    linked_deliverable_id: Optional[str] = None,
    linked_risk_id: Optional[str] = None,
    bot_id: Optional[str] = None,
    client_user_id: Optional[str] = None,
) -> CollaborationMessage:
    """Crea y reparte un mensaje. Es la UNICA via de envio.

    `client_user_id` marca que quien escribe es un usuario del portal, y entonces
    `user` es ese `ClientUser`. Auditoria 2026-08: el portal tenia su propia
    implementacion de envio en `endpoints/collaboration_portal.py`, y le faltaba
    casi todo lo que hace esta —el escaneo DLP, el indexado para busqueda, el
    reparto completo de notificaciones y los hilos—. El efecto visible: un
    cliente **no encontraba sus propios mensajes** en la busqueda que el propio
    portal le ofrece, porque nadie los indexaba. Es la misma forma que las dos
    puertas de subida de adjuntos: mismo destino, una con controles y otra sin
    ellos.

    La comprobacion de acceso cambia con el tipo de remitente, y por eso se
    ramifica aqui y no en quien llama: un cliente no pasa por ABAC —las
    politicas estan escritas sobre usuarios internos— sino por la comprobacion
    de participante-cliente.
    """
    org = _org(user)
    conv = _resolve_conversation(db, conversation_id=conversation_id, channel_id=channel_id, direct_id=direct_id, group_id=group_id)

    _autorizar_envio(db, user, conv, client_user_id=client_user_id, bot_id=bot_id)
    _exigir_enlaces_de_la_org(db, org, linked_task_id, linked_ticket_id, linked_deliverable_id, linked_risk_id)

    # DLP scan on body
    dlp_status, dlp_findings = scan_dlp(body)
    is_redacted = dlp_status == "blocked"

    msg = CollaborationMessage(
        organization_id=org,
        conversation_id=conv.id,
        thread_id=None,
        parent_message_id=parent_message_id,
        user_id=None if (bot_id or client_user_id) else user.id,
        client_user_id=client_user_id,
        bot_id=bot_id,
        type=type,
        status="visible",
        body="[REDACTED — DLP]" if is_redacted else body,
        body_html=None,
        metadata_json=metadata_json or {},
        is_redacted=is_redacted,
        scheduled_for=scheduled_for,
        sent_at=scheduled_for or datetime.now(timezone.utc),
        linked_task_id=linked_task_id,
        linked_ticket_id=linked_ticket_id,
        linked_deliverable_id=linked_deliverable_id,
        linked_risk_id=linked_risk_id,
    )
    db.add(msg)
    db.flush()

    _enganchar_al_hilo(db, org, conv, msg, parent_message_id)

    mentions = _crear_menciones(
        db, org, msg,
        mention_user_ids=mention_user_ids,
        mention_client_ids=mention_client_ids,
        is_everyone=is_everyone,
    )

    # Update conv last activity
    conv.last_activity_at = datetime.now(timezone.utc)
    conv.last_message_id = msg.id

    # Notifications fan-out — sólo si NO es programado al futuro
    _is_future = bool(scheduled_for) and _aware(scheduled_for) > datetime.now(timezone.utc)
    if not _is_future:
        _notify_recipients(db, organization_id=org, conv=conv, message=msg, mentions=mentions)

    # Audit + index
    audit_log.write(
        db, organization_id=org,
        actor_user_id=None if client_user_id else user.id,
        actor_client_id=client_user_id,
        action="message.sent", entity_type="message", entity_id=msg.id,
        payload={"conversation_id": conv.id, "type": type, "dlp": dlp_status,
                 "redacted": is_redacted,
                 "kind": "client" if client_user_id else "user"},
    )
    db.commit()
    search_engine.index(db, msg.id)

    # Si está programado para el futuro: NO hacemos fan-out ni publish ahora.
    # El scheduler (_scheduler.py) entregará cuando llegue scheduled_for.
    if _is_future:
        return msg

    # Realtime publish
    event = {
        "type": "message.created",
        "conversation_id": conv.id,
        "message_id": msg.id,
        "payload": _serialize_message(db, msg),
    }
    _publish_async(conv_channel(conv.id), event)
    # User channels for unread badges + Web Push
    from app.services.collaboration import _push as push_svc
    for n in db.query(CollaborationNotification).filter(CollaborationNotification.message_id == msg.id).all():
        if n.user_id:
            _publish_async(user_channel(n.user_id), {"type": "notification.new", "payload": {"id": n.id}})
            try:
                delivered = push_svc.push_to_user(db, n.user_id, {
                    "title": n.title or "Contecflow Chat",
                    "body": (n.body or "")[:200],
                    "url": f"/chat?conversation={n.conversation_id or ''}",
                    "tag": n.conversation_id or "",
                    "notification_id": n.id,
                })
                if delivered:
                    n.delivered_push = True
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:
                logger.debug("send_message: fallo best-effort ignorado", exc_info=True)
        if n.client_user_id:
            _publish_async(client_user_channel(n.client_user_id), {"type": "notification.new", "payload": {"id": n.id}})
    db.commit()
    return msg


def edit_message(db: Session, user, message_id: str, body: str, metadata_json: Optional[dict] = None) -> CollaborationMessage:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    if msg.user_id != user.id:
        raise ErrorDeDominio(403, "Solo puedes editar tus propios mensajes")
    if msg.status == "deleted":
        raise ErrorDeDominio(409, "Mensaje borrado")
    # Save version
    db.add(CollaborationMessageVersion(
        organization_id=org, message_id=msg.id, body=msg.body, body_html=msg.body_html,
        metadata_json=msg.metadata_json or {}, edited_by_user_id=user.id,
    ))
    msg.body = body
    if metadata_json is not None:
        msg.metadata_json = metadata_json
    msg.edited_at = datetime.now(timezone.utc)
    msg.status = "edited"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.edited", entity_type="message", entity_id=msg.id, payload={},
    )
    db.commit()
    search_engine.index(db, msg.id)
    _publish_async(conv_channel(msg.conversation_id), {
        "type": "message.updated", "conversation_id": msg.conversation_id,
        "message_id": msg.id, "payload": _serialize_message(db, msg),
    })
    return msg


def delete_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    if msg.user_id != user.id and not getattr(user, "is_superadmin", False):
        # team_lead and admin can delete others' messages — relax later via policy
        if getattr(user, "role", None) not in ("admin",):
            raise ErrorDeDominio(403, "No puedes borrar mensajes de otros")
    msg.status = "deleted"
    msg.deleted_at = datetime.now(timezone.utc)
    msg.body = "[mensaje eliminado]"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.deleted", entity_type="message", entity_id=msg.id, payload={},
    )
    db.commit()
    search_engine.remove(db, msg.id)
    _publish_async(conv_channel(msg.conversation_id), {
        "type": "message.deleted", "conversation_id": msg.conversation_id,
        "message_id": msg.id, "payload": {"id": msg.id},
    })


def list_messages(db: Session, user, conversation_id: str, *, before: Optional[str] = None, limit: int = 50, thread_root: Optional[str] = None) -> list[CollaborationMessage]:
    assert_conversation_access(db, user, conversation_id)
    enforce_abac(db, user, "collaboration_message", resource_id=conversation_id, action="read")
    org = _org(user)
    q = db.query(CollaborationMessage).filter(
        CollaborationMessage.organization_id == org,
        CollaborationMessage.conversation_id == conversation_id,
    )
    if thread_root:
        q = q.filter(or_(CollaborationMessage.parent_message_id == thread_root, CollaborationMessage.id == thread_root))
    else:
        q = q.filter(CollaborationMessage.parent_message_id == None)
    if before:
        anchor = db.query(CollaborationMessage).filter(CollaborationMessage.id == before).first()
        if anchor:
            q = q.filter(CollaborationMessage.sent_at < anchor.sent_at)
    rows = q.order_by(CollaborationMessage.sent_at.desc()).limit(min(limit, 200)).all()
    rows.reverse()
    return rows


def get_message_versions(db: Session, user, message_id: str) -> list[CollaborationMessageVersion]:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    return db.query(CollaborationMessageVersion).filter(CollaborationMessageVersion.message_id == message_id).order_by(CollaborationMessageVersion.edited_at.asc()).all()


# ── Reactions ────────────────────────────────────────────────────────────────
def toggle_reaction(db: Session, user, message_id: str, emoji: str) -> dict:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    existing = db.query(CollaborationReaction).filter(
        CollaborationReaction.message_id == message_id,
        CollaborationReaction.user_id == user.id,
        CollaborationReaction.emoji == emoji,
    ).first()
    if existing:
        db.delete(existing)
        action = "reaction.removed"
    else:
        db.add(CollaborationReaction(
            organization_id=org, message_id=message_id, user_id=user.id, emoji=emoji,
        ))
        action = "reaction.added"
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action=action, entity_type="message", entity_id=message_id, payload={"emoji": emoji},
    )
    db.commit()
    _publish_async(conv_channel(msg.conversation_id), {
        "type": action, "conversation_id": msg.conversation_id, "message_id": message_id,
        "payload": {"emoji": emoji, "user_id": user.id, "added": existing is None},
    })
    return {"toggled": True, "added": existing is None}


# ── Read markers ─────────────────────────────────────────────────────────────
def mark_read(db: Session, user, conversation_id: str, last_message_id: str) -> None:
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    row = db.query(CollaborationRead).filter(
        CollaborationRead.conversation_id == conversation_id,
        CollaborationRead.user_id == user.id,
    ).first()
    if row:
        row.last_message_id = last_message_id
        row.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(CollaborationRead(
            organization_id=org, conversation_id=conversation_id,
            user_id=user.id, last_message_id=last_message_id,
        ))

    # Keep notification-based unread counters in sync with read markers.
    # As soon as a user reads a conversation, unread notifications for that
    # conversation should disappear immediately.
    db.query(CollaborationNotification).filter(
        CollaborationNotification.user_id == user.id,
        CollaborationNotification.conversation_id == conversation_id,
        CollaborationNotification.is_read == False,
    ).update({
        "is_read": True,
        "read_at": datetime.now(timezone.utc),
    }, synchronize_session=False)

    db.commit()
    _publish_async(conv_channel(conversation_id), {
        "type": "read.updated", "conversation_id": conversation_id,
        "payload": {"user_id": user.id, "last_message_id": last_message_id},
    })


# ── Pin ──────────────────────────────────────────────────────────────────────
def pin_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    if not db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == msg.conversation_id,
        CollaborationPinnedMessage.message_id == message_id,
    ).first():
        db.add(CollaborationPinnedMessage(
            organization_id=org, conversation_id=msg.conversation_id,
            message_id=message_id, pinned_by=user.id,
        ))
        msg.is_pinned = True
        audit_log.write(
            db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
            action="message.pinned", entity_type="message", entity_id=message_id, payload={},
        )
        db.commit()
        _publish_async(conv_channel(msg.conversation_id), {
            "type": "message.pinned", "conversation_id": msg.conversation_id, "message_id": message_id,
            "payload": {"is_pinned": True},
        })


def unpin_message(db: Session, user, message_id: str) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    row = db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == msg.conversation_id,
        CollaborationPinnedMessage.message_id == message_id,
    ).first()
    if row:
        db.delete(row)
        msg.is_pinned = False
        audit_log.write(
            db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
            action="message.unpinned", entity_type="message", entity_id=message_id, payload={},
        )
        db.commit()
        _publish_async(conv_channel(msg.conversation_id), {
            "type": "message.unpinned", "conversation_id": msg.conversation_id, "message_id": message_id,
            "payload": {"is_pinned": False},
        })


def list_pins(db: Session, user, conversation_id: str) -> list[dict]:
    assert_conversation_access(db, user, conversation_id)
    rows = db.query(CollaborationPinnedMessage).filter(
        CollaborationPinnedMessage.conversation_id == conversation_id,
    ).order_by(CollaborationPinnedMessage.pinned_at.desc()).all()
    out = []
    for r in rows:
        msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == r.message_id).first()
        if msg and msg.status != "deleted":
            out.append({
                "id": r.id, "message_id": r.message_id, "pinned_at": r.pinned_at,
                "preview": (msg.body or "")[:200], "user_id": msg.user_id,
            })
    return out


# ── Saved (per-user bookmark) ────────────────────────────────────────────────
def save_message(db: Session, user, message_id: str, note: Optional[str] = None) -> None:
    org = _org(user)
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org).first()
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    if not db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
        CollaborationSavedMessage.message_id == message_id,
    ).first():
        db.add(CollaborationSavedMessage(
            organization_id=org, user_id=user.id, message_id=message_id, note=note,
        ))
        db.commit()


def unsave_message(db: Session, user, message_id: str) -> None:
    row = db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
        CollaborationSavedMessage.message_id == message_id,
    ).first()
    if row:
        db.delete(row)
        db.commit()


def list_saved(db: Session, user) -> list[CollaborationSavedMessage]:
    return db.query(CollaborationSavedMessage).filter(
        CollaborationSavedMessage.user_id == user.id,
    ).order_by(CollaborationSavedMessage.saved_at.desc()).limit(200).all()


# ── Drafts ──────────────────────────────────────────────────────────────────
def upsert_draft(db: Session, user, conversation_id: str, body: str, metadata_json: Optional[dict] = None, parent_message_id: Optional[str] = None) -> None:
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    row = db.query(CollaborationDraft).filter(
        CollaborationDraft.user_id == user.id,
        CollaborationDraft.conversation_id == conversation_id,
        CollaborationDraft.parent_message_id == parent_message_id,
    ).first()
    if row:
        row.body = body
        row.metadata_json = metadata_json or {}
    else:
        db.add(CollaborationDraft(
            organization_id=org, user_id=user.id, conversation_id=conversation_id,
            body=body, metadata_json=metadata_json or {}, parent_message_id=parent_message_id,
        ))
    db.commit()


def get_draft(db: Session, user, conversation_id: str, parent_message_id: Optional[str] = None) -> Optional[CollaborationDraft]:
    return db.query(CollaborationDraft).filter(
        CollaborationDraft.user_id == user.id,
        CollaborationDraft.conversation_id == conversation_id,
        CollaborationDraft.parent_message_id == parent_message_id,
    ).first()


# ── Serialize ────────────────────────────────────────────────────────────────
def _serialize_message(db: Session, msg: CollaborationMessage) -> dict:
    author_name = None
    author_avatar = None
    if msg.user_id:
        u = db.query(User).filter(User.id == msg.user_id).first()
        if u:
            author_name = u.full_name or u.username or u.email
            author_avatar = getattr(u, "avatar_url", None)
    elif msg.bot_id:
        from app.models.collaboration import CollaborationBotApp
        b = db.query(CollaborationBotApp).filter(CollaborationBotApp.id == msg.bot_id).first()
        if b:
            author_name = b.display_name
            author_avatar = b.avatar_url
    elif msg.client_user_id:
        from app.models.client_portal import ClientUser
        c = db.query(ClientUser).filter(ClientUser.id == msg.client_user_id).first()
        if c:
            author_name = c.full_name or c.email
    reactions = [
        {"emoji": r.emoji, "user_id": r.user_id, "client_user_id": r.client_user_id}
        for r in db.query(CollaborationReaction).filter(CollaborationReaction.message_id == msg.id).all()
    ]
    attachments = [
        {
            "id": a.id, "name": a.name, "mime_type": a.mime_type,
            "size_bytes": a.size_bytes, "av_status": a.av_status,
            "dlp_status": a.dlp_status, "is_quarantined": a.is_quarantined,
        }
        for a in db.query(CollaborationAttachment).filter(CollaborationAttachment.message_id == msg.id).all()
    ]
    return {
        "id": msg.id, "conversation_id": msg.conversation_id,
        "thread_id": msg.thread_id, "parent_message_id": msg.parent_message_id,
        "user_id": msg.user_id, "client_user_id": msg.client_user_id, "bot_id": msg.bot_id,
        "author_name": author_name, "author_avatar": author_avatar,
        "type": msg.type, "status": msg.status,
        "body": msg.body, "body_html": msg.body_html,
        "metadata_json": msg.metadata_json or {},
        "has_attachments": bool(attachments), "attachments": attachments,
        "reactions": reactions,
        "is_pinned": msg.is_pinned, "is_redacted": msg.is_redacted,
        "linked_task_id": msg.linked_task_id, "linked_ticket_id": msg.linked_ticket_id,
        # Auditoria 2026-11: las columnas existian y el chat pinta sus chips, pero no se mandaban.
        "linked_deliverable_id": msg.linked_deliverable_id, "linked_risk_id": msg.linked_risk_id,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
    }


# ── Lo que antes hacia el endpoint ───────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). Cuatro operaciones vivian en
# `endpoints/collaboration/messages.py` con acceso directo a base, y dos de
# ellas con un N+1 escondido dentro del bucle que construia la respuesta:
# `/saved` pedia un mensaje POR CADA guardado y `/mentions` uno POR CADA
# mencion. Con cien menciones eran 101 consultas.
#
# Y dos defensas muertas retiradas: `hasattr(Task, "organization_id")` y
# `hasattr(Ticket, "organization_id")`. Las dos son columnas declaradas del
# modelo, asi que la comprobacion siempre era verdadera — solo escondia el dia
# en que dejara de serlo.

#: Caracteres de mensaje que se devuelven como vista previa en las listas de
#: guardados y menciones. Es una lista para saltar a la conversacion, no para
#: leer el mensaje entero.
CARACTERES_DE_VISTA_PREVIA = 200

#: Tope de menciones recientes que se devuelven.
MAX_MENCIONES = 100

#: Las entidades PSA a las que se puede anclar un mensaje. La lista es cerrada a
#: proposito: cada valor se convierte en el nombre de una columna
#: `linked_<kind>_id` del modelo, asi que aceptar cualquier cadena permitiria
#: escribir en un atributo arbitrario.
ENTIDADES_ANCLABLES = ("task", "ticket", "deliverable", "risk")


def _vista_previa(cuerpo: Optional[str]) -> str:
    return (cuerpo or "")[:CARACTERES_DE_VISTA_PREVIA]


def _mensajes_por_id(db: Session, ids) -> dict:
    """Los mensajes de esos ids en una sola consulta."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    filas = (
        db.query(CollaborationMessage)
        .filter(CollaborationMessage.id.in_(ids))
        .all()
    )
    return {m.id: m for m in filas}


def list_saved_con_vista_previa(db: Session, user) -> list[dict]:
    """Los mensajes guardados con su vista previa.

    Los mensajes se cargan en una consulta: el endpoint pedia uno por guardado.
    Un guardado cuyo mensaje ya no existe se omite, que es lo que hacia antes.
    """
    guardados = list_saved(db, user)
    mensajes = _mensajes_por_id(db, (g.message_id for g in guardados))
    salida = []
    for g in guardados:
        m = mensajes.get(g.message_id)
        if not m:
            continue
        salida.append({
            "id": g.id, "message_id": g.message_id, "note": g.note,
            "saved_at": g.saved_at, "preview": _vista_previa(m.body),
            "conversation_id": m.conversation_id,
        })
    return salida


def list_my_mentions(db: Session, user) -> list[dict]:
    """Las menciones recientes de quien pregunta.

    Se omiten las de mensajes borrados: una mencion a un mensaje que ya no
    existe no lleva a ninguna parte. Los mensajes se cargan en una consulta.
    """
    filas = (
        db.query(CollaborationMention)
        .filter(CollaborationMention.mentioned_user_id == user.id)
        .order_by(CollaborationMention.created_at.desc())
        .limit(MAX_MENCIONES)
        .all()
    )
    mensajes = _mensajes_por_id(db, (r.message_id for r in filas))
    salida = []
    for r in filas:
        m = mensajes.get(r.message_id)
        if not m or m.status == "deleted":
            continue
        salida.append({
            "id": r.id, "message_id": r.message_id,
            "preview": _vista_previa(m.body),
            "conversation_id": m.conversation_id,
            "created_at": r.created_at,
        })
    return salida


def _mensaje_accesible(db: Session, user, message_id: str) -> CollaborationMessage:
    org = _org(user)
    msg = (
        db.query(CollaborationMessage)
        .filter(
            CollaborationMessage.id == message_id,
            CollaborationMessage.organization_id == org,
        )
        .first()
    )
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    assert_conversation_access(db, user, msg.conversation_id)
    return msg


def link_message(db: Session, user, message_id: str, *, kind: str, linked_id) -> dict:
    """Ancla un mensaje a una entidad PSA.

    `kind` se valida contra una lista cerrada **antes** de usarlo para construir
    el nombre de la columna: sin esa validacion, un `kind` arbitrario escribiria
    en cualquier atributo del modelo.
    """
    from app.services.collaboration import audit_log

    org = _org(user)
    msg = _mensaje_accesible(db, user, message_id)
    kind = (kind or "").lower()
    if kind not in ENTIDADES_ANCLABLES:
        raise ErrorDeDominio(400, "kind debe ser task|ticket|deliverable|risk")
    setattr(msg, f"linked_{kind}_id", linked_id)
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="message.linked", entity_type="message", entity_id=message_id,
        payload={"kind": kind, "linked_id": linked_id},
    )
    db.commit()
    return {"ok": True, "kind": kind, "linked_id": linked_id}


def link_candidates(db: Session, user, message_id: str, *, kind: str, q: str,
                    limit: int) -> list[dict]:
    """Candidatos a los que anclar un mensaje.

    Para tareas se acota al proyecto del canal si lo tiene: en un canal de
    proyecto, ofrecer tareas de otro no ayuda. Para tickets no hay ese acote
    porque un ticket no cuelga de un proyecto del canal.

    Un `kind` que no se sabe buscar devuelve lista vacia en vez de error: es un
    autocompletado, y fallar mientras alguien escribe no aporta nada.
    """
    org = _org(user)
    msg = _mensaje_accesible(db, user, message_id)

    if kind == "task":
        from app.models.collaboration import CollaborationChannel
        from app.models.task import Task

        canal = (
            db.query(CollaborationChannel)
            .filter(CollaborationChannel.conversation_id == msg.conversation_id)
            .first()
        )
        consulta = db.query(Task).filter(Task.organization_id == org)
        if canal and canal.project_id:
            consulta = consulta.filter(Task.project_id == canal.project_id)
        if q:
            consulta = consulta.filter(Task.title.ilike(f"%{q}%"))
        filas = consulta.order_by(Task.created_at.desc()).limit(limit).all()
        return [{"id": t.id, "label": f"{t.code or '?'} · {t.title}"} for t in filas]

    if kind == "ticket":
        from app.models.service_desk import Ticket

        consulta = db.query(Ticket).filter(Ticket.organization_id == org)
        if q:
            consulta = consulta.filter(Ticket.title.ilike(f"%{q}%"))
        filas = consulta.order_by(Ticket.created_at.desc()).limit(limit).all()
        return [{"id": t.id, "label": f"{t.number} · {t.title}"} for t in filas]

    return []
