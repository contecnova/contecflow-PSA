"""Chat en vivo de Soporte completo (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §10).

El tercer chat del portal (Soporte → Chat en vivo; el operador lo atiende en la
bandeja de canales) pasa a tener lo mismo que las conversaciones del portal y
la pestaña «Chat». No reinventa nada: REUTILIZA

- los ajustes por empresa `portal_chat` (`portal_conversation_service.ajustes`):
  adjuntos, extensiones, tamaño, plazo de edición, llamadas, vídeo y tono;
- la validación de ficheros por contenido (`portal_conversation_service.adjuntos
  .validar_fichero`: plataforma + bytes mágicos que casen con la extensión), el
  antivirus/DLP (`collaboration.files.escanear`) y el almacén de objetos
  (`collaboration._storage`);
- la regla de reacciones (`portal_conversation_service.interaccion`);
- las constantes y la sala de LiveKit de las llamadas del portal
  (`portal_conversation_service.llamadas`, `collaboration.livekit`);
- el transporte en vivo de los canales (`canales_en_vivo`).

Solo para conversaciones `livechat` (WhatsApp, Slack y Teams siguen con lo suyo).

**Solo el operador llama.** `iniciar_llamada` recibe un `User` y su ruta exige
`clientes.llamar` (y aquí, además, `sd.completo`). La ruta del portal para
iniciar existe a propósito y SIEMPRE responde 403 `portal_llamada_solo_operador`
(auditado: `livechat.call_start_denied`). El cliente solo acepta (si suena o está
en curso; único modo de recibir su token), rechaza (si suena) o cuelga.
**Grabación solo con consentimiento** (24-11-2026, migración 214, §11): la
propone el operador si la empresa lo permite y se graba solo si el cliente
consiente (`portal_conversation_service.grabacion`); la ruta antigua de grabar
responde 409 `portal_grabacion_desactivada` / `portal_grabacion_sin_consentimiento`
(`grabar_denegado`). Al colgar se para.

**Aislamiento de empresa.** Todo se busca por `organization_id` de la
conversación; el cliente, además, por `client_user_id` y su empresa.

**Auditoría** (`audit_logs`, recurso `livechat`, con la empresa y, si es el
cliente, `actor_client_id`): `attachment_uploaded` / `_quarantined` /
`_downloaded` / `_deleted`, `message_edited`, `message_deleted`,
`reaction_added` / `_removed`, `call_started`, `call_accepted`, `call_declined`,
`call_missed`, `call_joined`, `call_ended`, `call_start_denied`,
`call_recording_denied`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.service_desk import ChannelConversation, ChannelMessage, Ticket, TicketComment
from app.models.service_desk.mercado import ChannelAttachment, ChannelCall, ChannelMessageVersion, ChannelReaction
from app.services.portal_conversation_service import ajustes as _ajustes

CANAL = "livechat"
#: Texto que queda en el comentario del ticket de un mensaje borrado.
MENSAJE_ELIMINADO = "[mensaje eliminado]"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Conversación y acceso ─────────────────────────────────────────────────────

def _solo_livechat(conv: ChannelConversation, codigo: str) -> None:
    if conv.channel != CANAL:
        raise error(422, codigo)


def conversacion_del_operador(db: Session, conv_id: str, usuario, codigo: str = "portal_mensaje_no_editable"):
    """Conversación de chat en vivo de la empresa del operador (404 si no es de su empresa)."""
    conv = db.query(ChannelConversation).filter(
        ChannelConversation.id == conv_id,
        ChannelConversation.organization_id == usuario.organization_id,
    ).first()
    if conv is None:
        raise error(404, "conversacion_no_encontrada")
    _solo_livechat(conv, codigo)
    return conv


def conversacion_del_cliente(db: Session, conv_id: str, cliente):
    """Conversación del cliente del portal, de SU empresa (404 si no)."""
    conv = db.query(ChannelConversation).filter(
        ChannelConversation.id == conv_id,
        ChannelConversation.client_user_id == cliente.id,
        ChannelConversation.organization_id == cliente.organization_id,
        ChannelConversation.channel == CANAL,
    ).first()
    if conv is None:
        raise error(404, "conversacion_no_encontrada")
    return conv


def _abierta(conv: ChannelConversation) -> None:
    if conv.status == "closed":
        raise error(409, "conversacion_cerrada")


def _auditar(db: Session, conv: ChannelConversation, accion: str, recurso_id: Optional[str] = None,
             nombre: Optional[str] = None, *, usuario=None, cliente=None, datos: Optional[dict] = None) -> None:
    from app.services.audit import audit_log
    meta = {"conversation_id": conv.id, "channel": conv.channel, "ticket_id": conv.ticket_id, **(datos or {})}
    if cliente is not None:
        meta["actor_client_id"] = cliente.id
    entrada = audit_log(db, usuario, f"livechat.{accion}", "livechat", recurso_id, nombre, metadata=meta)
    entrada.organization_id = conv.organization_id


def _mensaje(db: Session, conv: ChannelConversation, message_id: str) -> ChannelMessage:
    m = db.query(ChannelMessage).filter(
        ChannelMessage.id == message_id,
        ChannelMessage.conversation_id == conv.id,
        ChannelMessage.organization_id == conv.organization_id,
    ).first()
    if m is None:
        raise error(404, "mensaje_no_encontrado")
    return m


def validar_cita(db: Session, conv: ChannelConversation, reply_to: Optional[str]) -> Optional[str]:
    """El mensaje citado tiene que ser de la misma conversación (y empresa)."""
    if not reply_to:
        return None
    m = db.query(ChannelMessage.id).filter(
        ChannelMessage.id == reply_to,
        ChannelMessage.conversation_id == conv.id,
        ChannelMessage.organization_id == conv.organization_id,
    ).first()
    if m is None:
        raise error(422, "portal_mensaje_citado_no_valido")
    return reply_to


# ── Serialización (extras de los mensajes) ────────────────────────────────────

def _adjunto_salida(a: ChannelAttachment) -> dict:
    return {"id": a.id, "name": a.name, "mime_type": a.mime_type, "size_bytes": a.size_bytes or 0,
            "is_quarantined": bool(a.is_quarantined),
            "is_image": (a.mime_type or "").startswith("image/") and not a.is_quarantined}


def extras(db: Session, mensajes: Iterable[ChannelMessage]) -> dict[str, dict]:
    """Adjuntos, reacciones, cita y nombre del autor de varios mensajes, en pocas consultas."""
    from app.models.user import User
    lista = list(mensajes)
    ids = [m.id for m in lista]
    if not ids:
        return {}
    salida: dict[str, dict] = {i: {"attachments": [], "reactions": []} for i in ids}
    for a in db.query(ChannelAttachment).filter(ChannelAttachment.message_id.in_(ids),
                                                ChannelAttachment.deleted_at.is_(None)).all():
        salida[a.message_id]["attachments"].append(_adjunto_salida(a))
    for r in db.query(ChannelReaction).filter(ChannelReaction.message_id.in_(ids)).all():
        salida[r.message_id]["reactions"].append(
            {"emoji": r.emoji, "user_id": r.user_id, "client_user_id": r.client_user_id})
    citas_ids = {m.reply_to_message_id for m in lista if m.reply_to_message_id}
    citas = {c.id: c for c in db.query(ChannelMessage).filter(ChannelMessage.id.in_(citas_ids)).all()} if citas_ids else {}
    autores_ids = {m.author_user_id for m in lista if m.author_user_id} | {
        c.author_user_id for c in citas.values() if c.author_user_id}
    autores = dict(db.query(User.id, User.full_name).filter(User.id.in_(autores_ids)).all()) if autores_ids else {}
    conv_ids = {m.conversation_id for m in lista}
    visitantes = dict(db.query(ChannelConversation.id, ChannelConversation.visitor_name)
                      .filter(ChannelConversation.id.in_(conv_ids)).all())

    def _nombre(m) -> Optional[str]:
        if m.author_type == "customer":
            return visitantes.get(m.conversation_id)
        return autores.get(m.author_user_id) if m.author_user_id else None

    for m in lista:
        salida[m.id]["author_name"] = _nombre(m)
        c = citas.get(m.reply_to_message_id) if m.reply_to_message_id else None
        salida[m.id]["reply_to"] = None if c is None else {
            "id": c.id, "author_name": _nombre(c), "author_type": c.author_type,
            "body": "" if c.deleted_at else (c.body or "")[:300], "is_deleted": c.deleted_at is not None}
    return salida


# ── Adjuntos ──────────────────────────────────────────────────────────────────

def _crear_adjunto(db: Session, conv: ChannelConversation, m: ChannelMessage, nombre: str, mime: str, datos: bytes,
                   *, usuario=None, cliente=None) -> ChannelAttachment:
    from app.services.collaboration._storage import storage
    from app.services.collaboration.files import escanear, nombre_para_clave_de_objeto

    av_status, _av, dlp_status, _dlp, en_cuarentena = escanear(datos)
    seguro = nombre_para_clave_de_objeto(nombre)
    clave = f"livechat/{conv.organization_id}/{conv.id}/{_ahora().strftime('%Y%m%d%H%M%S%f')}_{seguro}"
    guardado = storage.save_bytes(clave, datos)
    a = ChannelAttachment(
        organization_id=conv.organization_id, conversation_id=conv.id, message_id=m.id,
        uploaded_by_user_id=usuario.id if usuario is not None else None,
        uploaded_by_client_id=cliente.id if cliente is not None else None,
        name=(os.path.basename((nombre or "").replace("\\", "/")) or seguro)[:255], mime_type=mime,
        size_bytes=guardado.size_bytes, storage_provider=guardado.storage_provider, storage_key=guardado.storage_key,
        sha256=guardado.sha256, av_status=av_status, dlp_status=dlp_status, is_quarantined=en_cuarentena,
    )
    db.add(a)
    db.flush()
    _auditar(db, conv, "attachment_quarantined" if en_cuarentena else "attachment_uploaded", a.id, a.name,
             usuario=usuario, cliente=cliente,
             datos={"message_id": m.id, "size": guardado.size_bytes, "mime": mime, "sha256": guardado.sha256,
                    "av": av_status, "dlp": dlp_status})
    return a


def _al_ticket(db: Session, conv: ChannelConversation, m: ChannelMessage, cuerpo: str, *, usuario=None,
              cliente=None) -> None:
    """El mensaje queda también como comentario público del ticket (si lo hay)."""
    if not conv.ticket_id:
        return
    ticket = db.get(Ticket, conv.ticket_id)
    if ticket is None:
        return
    comentario = TicketComment(ticket_id=ticket.id, body=cuerpo, is_public=True,
                               author_user_id=usuario.id if usuario is not None else None,
                               author_client_id=cliente.id if cliente is not None else None)
    db.add(comentario)
    db.flush()
    m.ticket_comment_id = comentario.id
    if cliente is not None:
        from app.services.service_desk.conversaciones import _reactivar
        _reactivar(ticket)


def subir(db: Session, conv: ChannelConversation, fichero, caption: Optional[str], reply_to: Optional[str], *,
          usuario=None, cliente=None) -> ChannelMessage:
    """Imagen o fichero en el chat en vivo (operador o cliente). Mismas reglas que el chat del portal."""
    from app.core.uploads import read_upload_within_limit_sync
    from app.services.portal_conversation_service.adjuntos import validar_fichero
    from app.services.service_desk import canales_en_vivo, conversaciones

    _abierta(conv)
    ajustes = _ajustes.leer(db, conv.organization_id)
    if not ajustes.adjuntos:
        raise error(403, "portal_adjuntos_desactivados")
    datos = read_upload_within_limit_sync(fichero, ajustes.max_mb * 1024 * 1024)
    nombre = fichero.filename or ""
    mime = validar_fichero(nombre, fichero.content_type or "", datos, ajustes)
    cita = validar_cita(db, conv, reply_to)
    cuerpo = ((caption or "").strip() or nombre)[:conversaciones.MAX_MENSAJE]
    if usuario is not None:
        if conv.status != "agent":
            conv.status, conv.assigned_user_id = "agent", usuario.id
        m = conversaciones.anotar(db, conv, "out", "agent", cuerpo, author_user_id=usuario.id)
    else:
        m = conversaciones.anotar(db, conv, "in", "customer", cuerpo)
    m.reply_to_message_id = cita
    a = _crear_adjunto(db, conv, m, nombre, mime, datos, usuario=usuario, cliente=cliente)
    # En el ticket, el texto y la nota del adjunto (el fichero se baja desde el chat).
    nota = f"[adjunto: {a.name}]"
    _al_ticket(db, conv, m, f"{m.body}\n{nota}" if (caption or "").strip() else nota,
               usuario=usuario, cliente=cliente)
    db.commit()
    canales_en_vivo.avisar_mensaje(db, conv, m)
    return m


def descargar(db: Session, conv: ChannelConversation, adjunto_id: str, *, usuario=None, cliente=None):
    """(bytes, mime, nombre). Solo por la API: el operador de la empresa o el cliente de la conversación."""
    from app.services.collaboration._storage import storage
    from app.services.portal_conversation_service.adjuntos import TIPO_POR_DEFECTO
    a = db.query(ChannelAttachment).filter(
        ChannelAttachment.id == adjunto_id,
        ChannelAttachment.conversation_id == conv.id,
        ChannelAttachment.organization_id == conv.organization_id,
    ).first()
    if a is None or a.deleted_at is not None:
        raise error(404, "portal_adjunto_no_encontrado")
    if a.is_quarantined:
        raise error(409, "portal_adjunto_en_cuarentena")
    datos = storage.read(a.storage_key)
    _auditar(db, conv, "attachment_downloaded", a.id, a.name, usuario=usuario, cliente=cliente,
             datos={"message_id": a.message_id})
    db.commit()
    return datos, a.mime_type or TIPO_POR_DEFECTO, a.name


# ── Editar, borrar y reaccionar ───────────────────────────────────────────────

def _es_propio(conv: ChannelConversation, m: ChannelMessage, *, usuario=None, cliente=None) -> bool:
    if usuario is not None:
        return m.author_type == "agent" and m.author_user_id == usuario.id
    return cliente is not None and m.author_type == "customer" and conv.client_user_id == cliente.id


def _comprobar_autoria_y_plazo(db: Session, conv, m, *, usuario=None, cliente=None) -> None:
    if not _es_propio(conv, m, usuario=usuario, cliente=cliente):
        raise error(403, "portal_mensaje_no_propio")
    if m.deleted_at is not None:
        raise error(409, "portal_mensaje_ya_borrado")
    minutos = _ajustes.leer(db, conv.organization_id).minutos_de_edicion
    if minutos and m.created_at is not None and _ahora() - _aware(m.created_at) > timedelta(minutes=minutos):
        raise error(409, "portal_mensaje_fuera_de_plazo", minutos=minutos)


def _version(db: Session, conv, m, tipo: str, *, usuario=None, cliente=None) -> None:
    db.add(ChannelMessageVersion(
        organization_id=conv.organization_id, conversation_id=conv.id, message_id=m.id, body=m.body,
        change_type=tipo, edited_by_user_id=usuario.id if usuario is not None else None,
        edited_by_client_id=cliente.id if cliente is not None else None))


def editar(db: Session, conv: ChannelConversation, message_id: str, texto: str, *, usuario=None,
           cliente=None) -> ChannelMessage:
    """Edita el propio mensaje dentro del plazo de la empresa; el texto anterior queda en el rastro."""
    from app.services.service_desk import canales_en_vivo, conversaciones
    texto = (texto or "").strip()[:conversaciones.MAX_MENSAJE]
    if not texto:
        raise error(422, "mensaje_vacio")
    _abierta(conv)
    m = _mensaje(db, conv, message_id)
    _comprobar_autoria_y_plazo(db, conv, m, usuario=usuario, cliente=cliente)
    if texto == m.body:
        return m
    _version(db, conv, m, "edit", usuario=usuario, cliente=cliente)
    m.body = texto
    m.edited_at = _ahora()
    if m.ticket_comment_id:
        comentario = db.get(TicketComment, m.ticket_comment_id)
        if comentario is not None:
            comentario.body = texto
    _auditar(db, conv, "message_edited", m.id, None, usuario=usuario, cliente=cliente)
    db.commit()
    canales_en_vivo.avisar_cambio(db, conv, m, "edited")
    return m


def borrar(db: Session, conv: ChannelConversation, message_id: str, *, usuario=None, cliente=None) -> ChannelMessage:
    """Borrado lógico del propio mensaje: «Mensaje eliminado» para todos, con rastro.
    Sus adjuntos se quitan del almacén al confirmar; bajo bloqueo legal, 409."""
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    from app.services.service_desk import canales_en_vivo

    m = _mensaje(db, conv, message_id)
    _comprobar_autoria_y_plazo(db, conv, m, usuario=usuario, cliente=cliente)
    adjuntos = db.query(ChannelAttachment).filter(ChannelAttachment.message_id == m.id,
                                                  ChannelAttachment.deleted_at.is_(None)).all()
    activos = bloqueos_activos(db, conv.organization_id)
    for a in adjuntos:
        b = _bloqueo_de("sd_channel_attachments", a, activos)
        if b is not None:
            raise error(409, "portal_mensaje_bajo_bloqueo_legal", caso=b.case_reference)
    _version(db, conv, m, "delete", usuario=usuario, cliente=cliente)
    ahora = _ahora()
    m.deleted_at = ahora
    m.deleted_by_user_id = usuario.id if usuario is not None else None
    m.deleted_by_client_id = cliente.id if cliente is not None else None
    db.query(ChannelReaction).filter(ChannelReaction.message_id == m.id).delete(synchronize_session=False)
    claves = db.info.setdefault("portal_chat_ficheros_a_borrar", [])
    for a in adjuntos:
        a.deleted_at = ahora
        claves.append(a.storage_key)
        _auditar(db, conv, "attachment_deleted", a.id, a.name, usuario=usuario, cliente=cliente,
                 datos={"message_id": m.id, "sha256": a.sha256, "size": a.size_bytes})
    if m.ticket_comment_id:
        comentario = db.get(TicketComment, m.ticket_comment_id)
        if comentario is not None:
            comentario.body = MENSAJE_ELIMINADO
    _auditar(db, conv, "message_deleted", m.id, None, usuario=usuario, cliente=cliente,
             datos={"attachments": [a.id for a in adjuntos]})
    db.commit()
    canales_en_vivo.avisar_cambio(db, conv, m, "deleted")
    return m


def reaccionar(db: Session, conv: ChannelConversation, message_id: str, emoji: str, *, usuario=None,
               cliente=None) -> dict:
    """Pone o quita una reacción (la misma regla de emoji que el chat del portal)."""
    from app.services.portal_conversation_service.interaccion import MAX_LONGITUD_DE_REACCION, _REACCION_NO_VALIDA
    from app.services.service_desk import canales_en_vivo

    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > MAX_LONGITUD_DE_REACCION or _REACCION_NO_VALIDA.search(emoji):
        raise error(422, "portal_reaccion_no_valida")
    m = _mensaje(db, conv, message_id)
    if m.deleted_at is not None:
        raise error(409, "portal_mensaje_ya_borrado")
    q = db.query(ChannelReaction).filter(ChannelReaction.organization_id == conv.organization_id,
                                         ChannelReaction.message_id == m.id, ChannelReaction.emoji == emoji)
    q = q.filter(ChannelReaction.user_id == usuario.id) if usuario is not None else q.filter(
        ChannelReaction.client_user_id == cliente.id)
    existente = q.first()
    if existente is not None:
        db.delete(existente)
    else:
        db.add(ChannelReaction(organization_id=conv.organization_id, conversation_id=conv.id, message_id=m.id,
                               emoji=emoji, user_id=usuario.id if usuario is not None else None,
                               client_user_id=cliente.id if cliente is not None else None))
    _auditar(db, conv, "reaction_removed" if existente is not None else "reaction_added", m.id, None,
             usuario=usuario, cliente=cliente, datos={"emoji": emoji})
    db.commit()
    canales_en_vivo.avisar_reaccion(conv, m.id)
    return {"message_id": m.id, "emoji": emoji, "added": existente is None}


def versiones(db: Session, conv: ChannelConversation, message_id: str) -> list[dict]:
    """El rastro de un mensaje (solo el operador): el texto que tenía antes de cada cambio."""
    m = _mensaje(db, conv, message_id)
    filas = db.query(ChannelMessageVersion).filter(
        ChannelMessageVersion.message_id == m.id,
        ChannelMessageVersion.organization_id == conv.organization_id,
    ).order_by(ChannelMessageVersion.edited_at).all()
    return [{"id": v.id, "change_type": v.change_type, "body": v.body, "raw_body": None,
             "edited_by_user_id": v.edited_by_user_id, "edited_by_client_id": v.edited_by_client_id,
             "edited_at": str(v.edited_at)[:19] if v.edited_at else None} for v in filas]


# ── Llamadas ──────────────────────────────────────────────────────────────────

def _sala(call_id: str) -> str:
    return f"contec-livechat-{call_id}"


def _llamada_salida(c: ChannelCall) -> dict:
    return {"id": c.id, "conversation_id": c.conversation_id, "kind": c.kind, "status": c.status,
            "initiated_by_user_id": c.initiated_by_user_id, "answered_by_client_id": c.answered_by_client_id,
            "created_at": str(c.created_at)[:19] if c.created_at else None,
            "answered_at": str(c.answered_at)[:19] if c.answered_at else None,
            "ended_at": str(c.ended_at)[:19] if c.ended_at else None,
            "duration_seconds": c.duration_seconds or 0, "is_recorded": _grabando(c)}


def _grabando(c: ChannelCall) -> bool:
    """Se graba ahora con el consentimiento del cliente (migración 214)."""
    from sqlalchemy.orm import object_session
    from app.services.portal_conversation_service import grabacion
    db = object_session(c)
    return bool(db is not None and c.status in ("ringing", "active")
                and grabacion.grabando(db, "en_vivo", c.id, c.organization_id))


def _con_token(c: ChannelCall, *, identidad: str, nombre: str, rol: str) -> dict:
    from app.services.collaboration.livekit import issue_access_token, url
    from app.services.portal_conversation_service.llamadas import TTL_DEL_TOKEN
    salida = _llamada_salida(c)
    salida.update({"role": rol, "livekit_url": url(), "livekit_room": c.livekit_room,
                   "livekit_token": issue_access_token(room=c.livekit_room, identity=identidad, name=nombre,
                                                       is_recorder=False, ttl_seconds=TTL_DEL_TOKEN)})
    return salida


def _caducar_si_no_contestan(db: Session, conv, c: ChannelCall) -> bool:
    if c.status != "ringing" or c.created_at is None:
        return False
    tono = _ajustes.leer(db, conv.organization_id).segundos_de_tono
    if _ahora() - _aware(c.created_at) <= timedelta(seconds=tono):
        return False
    c.status, c.ended_at = "missed", _ahora()
    _auditar(db, conv, "call_missed", c.id, None, datos={"kind": c.kind})
    return True


def _llamada(db: Session, conv, call_id: str) -> ChannelCall:
    c = db.query(ChannelCall).filter(ChannelCall.id == call_id, ChannelCall.conversation_id == conv.id,
                                     ChannelCall.organization_id == conv.organization_id).first()
    if c is None:
        raise error(404, "portal_llamada_no_encontrada")
    if _caducar_si_no_contestan(db, conv, c):
        db.commit()
    return c


def _avisar_llamada(conv, c: ChannelCall) -> None:
    from app.services.service_desk import canales_en_vivo
    canales_en_vivo.avisar_llamada(conv, {"call_id": c.id, "status": c.status, "kind": c.kind})


def iniciar_llamada(db: Session, conv: ChannelConversation, kind: str, usuario) -> dict:
    """El OPERADOR llama al cliente. Todo se comprueba antes de crear nada."""
    from app.core.capacidades import tiene
    from app.services.portal_conversation_service.llamadas import TIPOS, VIVAS
    if kind not in TIPOS:
        raise error(422, "portal_llamada_tipo_no_valido", tipo=kind)
    if not tiene(db, usuario, "sd.completo"):
        raise error(403, "portal_llamada_sin_acceso")
    ajustes = _ajustes.leer(db, conv.organization_id)
    if not ajustes.llamadas:
        raise error(403, "portal_llamadas_desactivadas")
    if kind == "video" and not ajustes.video:
        raise error(403, "portal_videollamadas_desactivadas")
    _abierta(conv)
    if not conv.client_user_id:
        raise error(422, "portal_llamada_sin_cliente")
    vivas = db.query(ChannelCall).filter(ChannelCall.conversation_id == conv.id,
                                         ChannelCall.organization_id == conv.organization_id,
                                         ChannelCall.status.in_(VIVAS)).all()
    for c in vivas:
        _caducar_si_no_contestan(db, conv, c)
    if any(c.status in VIVAS for c in vivas):
        db.commit()
        raise error(409, "portal_llamada_en_curso")
    c = ChannelCall(organization_id=conv.organization_id, conversation_id=conv.id, initiated_by_user_id=usuario.id,
                    kind=kind, status="ringing", livekit_room="pendiente")
    db.add(c)
    db.flush()
    c.livekit_room = _sala(c.id)
    _auditar(db, conv, "call_started", c.id, None, usuario=usuario, datos={"kind": kind})
    db.commit()
    _avisar_llamada(conv, c)
    return _con_token(c, identidad=f"user:{usuario.id}", nombre=usuario.full_name, rol="host")


def unirse(db: Session, conv: ChannelConversation, call_id: str, usuario) -> dict:
    from app.core.capacidades import tiene
    from app.services.portal_conversation_service.llamadas import VIVAS
    if not tiene(db, usuario, "sd.completo"):
        raise error(403, "portal_llamada_sin_acceso")
    c = _llamada(db, conv, call_id)
    if c.status not in VIVAS:
        raise error(409, "portal_llamada_terminada")
    _auditar(db, conv, "call_joined", c.id, None, usuario=usuario)
    db.commit()
    return _con_token(c, identidad=f"user:{usuario.id}", nombre=usuario.full_name, rol="participant")


def iniciar_como_cliente(db: Session, conv_id: str, cliente, kind: Optional[str] = None) -> None:
    """El cliente NUNCA inicia: 403 con código y el intento queda auditado."""
    conv = db.query(ChannelConversation).filter(
        ChannelConversation.id == conv_id, ChannelConversation.client_user_id == cliente.id,
        ChannelConversation.organization_id == cliente.organization_id).first()
    if conv is not None:
        _auditar(db, conv, "call_start_denied", None, None, cliente=cliente,
                 datos={"kind": kind, "motivo": "solo_operador"})
        db.commit()
    raise error(403, "portal_llamada_solo_operador")


def grabar_denegado(db: Session, conv: ChannelConversation, call_id: Optional[str], *, usuario=None,
                    cliente=None) -> dict:
    """Ruta antigua de «grabar» (24-11-2026, migración 214): ya no graba por sí sola.

    Se graba por la propuesta del operador y el consentimiento del cliente
    (`/portal-call-recording/...`). Aquí: si se está grabando con consentimiento,
    devuelve el estado; si no, 409 `portal_grabacion_desactivada` (la empresa no
    lo permite) o `portal_grabacion_sin_consentimiento` (auditado).
    """
    from app.services.portal_conversation_service import grabacion
    try:
        grabacion.exigir_consentimiento(db, "en_vivo", call_id or "", conv.organization_id)
    except Exception:
        _auditar(db, conv, "call_recording_denied", call_id, None, usuario=usuario, cliente=cliente)
        db.commit()
        raise
    llamada = grabacion.cargar(db, "en_vivo", call_id or "", conv.organization_id)
    return grabacion.estado(db, llamada, cliente=cliente)


def aceptar(db: Session, conv: ChannelConversation, call_id: str, cliente) -> dict:
    from app.services.portal_conversation_service.llamadas import VIVAS
    c = _llamada(db, conv, call_id)
    if c.status not in VIVAS:
        raise error(409, "portal_llamada_terminada")
    if not c.initiated_by_user_id:
        raise error(403, "portal_llamada_solo_operador")
    if c.status == "ringing":
        c.status, c.answered_at, c.answered_by_client_id = "active", _ahora(), cliente.id
    _auditar(db, conv, "call_accepted", c.id, None, cliente=cliente, datos={"kind": c.kind})
    db.commit()
    _avisar_llamada(conv, c)
    return _con_token(c, identidad=f"client:{cliente.id}", nombre=cliente.full_name, rol="participant")


def rechazar(db: Session, conv: ChannelConversation, call_id: str, cliente) -> dict:
    c = _llamada(db, conv, call_id)
    if c.status != "ringing":
        raise error(409, "portal_llamada_terminada")
    c.status, c.declined_by_client_id, c.ended_at = "declined", cliente.id, _ahora()
    _auditar(db, conv, "call_declined", c.id, None, cliente=cliente, datos={"kind": c.kind})
    db.commit()
    _avisar_llamada(conv, c)
    return _llamada_salida(c)


def colgar(db: Session, conv: ChannelConversation, call_id: str, *, usuario=None, cliente=None) -> dict:
    from app.services.portal_conversation_service.llamadas import VIVAS
    c = _llamada(db, conv, call_id)
    if c.status not in VIVAS:
        return _llamada_salida(c)
    ahora = _ahora()
    if c.status == "active" and c.answered_at is not None:
        c.duration_seconds = max(0, int((ahora - _aware(c.answered_at)).total_seconds()))
    from app.services.portal_conversation_service import grabacion
    grabacion.al_terminar_llamada(db, "en_vivo", c.id, c.organization_id)
    c.status, c.ended_at = "ended", ahora
    c.ended_by_user_id = usuario.id if usuario is not None else None
    c.ended_by_client_id = cliente.id if cliente is not None else None
    _auditar(db, conv, "call_ended", c.id, None, usuario=usuario, cliente=cliente,
             datos={"kind": c.kind, "duration_seconds": c.duration_seconds})
    db.commit()
    _avisar_llamada(conv, c)
    return _llamada_salida(c)


def listar_llamadas(db: Session, conv: ChannelConversation, limite: int = 20) -> list[dict]:
    filas = db.query(ChannelCall).filter(ChannelCall.conversation_id == conv.id,
                                         ChannelCall.organization_id == conv.organization_id
                                         ).order_by(ChannelCall.created_at.desc()).limit(limite).all()
    if any([_caducar_si_no_contestan(db, conv, c) for c in filas]):
        db.commit()
    return [_llamada_salida(c) for c in filas]


def sonando_para_cliente(db: Session, cliente) -> list[dict]:
    """Llamadas del operador que suenan ahora en los chats en vivo del cliente."""
    filas = (db.query(ChannelCall, ChannelConversation)
             .join(ChannelConversation, ChannelConversation.id == ChannelCall.conversation_id)
             .filter(ChannelCall.organization_id == cliente.organization_id,
                     ChannelConversation.organization_id == cliente.organization_id,
                     ChannelConversation.client_user_id == cliente.id,
                     ChannelCall.status == "ringing")
             .order_by(ChannelCall.created_at.desc()).limit(5).all())
    salida, cambios = [], False
    for c, conv in filas:
        if _caducar_si_no_contestan(db, conv, c):
            cambios = True
            continue
        salida.append(_llamada_salida(c))
    if cambios:
        db.commit()
    return salida


def ajustes_salida(db: Session, organization_id: Optional[str], usuario=None) -> dict:
    """Ajustes `portal_chat` para la pantalla; `can_call` solo para el operador con `clientes.llamar`."""
    datos = _ajustes.leer(db, organization_id).salida()
    if usuario is None:
        datos["can_call"] = False
    else:
        from app.core.capacidades import tiene
        datos["can_call"] = bool(datos["calls_enabled"] and tiene(db, usuario, "clientes.llamar")
                                 and tiene(db, usuario, "sd.completo"))
    return datos


# ── RGPD (lo llama `cab_service/gdpr.py`, dentro de su transacción; sin commit) ──

BORRADO_RGPD = "[ERASED]"


def _conversaciones_de(db: Session, client_ids: list[str], org: str) -> list[str]:
    return [r[0] for r in db.query(ChannelConversation.id).filter(
        ChannelConversation.organization_id == org, ChannelConversation.channel == CANAL,
        ChannelConversation.client_user_id.in_(client_ids)).all()]


def _fecha(v) -> Optional[str]:
    return str(v)[:19] if v else None


def copia_rgpd(db: Session, client_ids: Iterable[str], org: str) -> dict:
    """Acceso y portabilidad: sus mensajes del chat en vivo, el rastro de sus ediciones,
    sus adjuntos (metadatos y huella), sus reacciones y las llamadas que contestó,
    rechazó o colgó."""
    ids = list(client_ids)
    vacio = {"livechat": {"messages": [], "edits": [], "attachments": [], "reactions": [], "calls": []}}
    if not ids:
        return vacio
    convs = _conversaciones_de(db, ids, org)
    mensajes = db.query(ChannelMessage).filter(
        ChannelMessage.organization_id == org, ChannelMessage.conversation_id.in_(convs),
        ChannelMessage.author_type == "customer").order_by(ChannelMessage.created_at).all() if convs else []
    versiones_ = db.query(ChannelMessageVersion).filter(
        ChannelMessageVersion.organization_id == org,
        ChannelMessageVersion.message_id.in_([m.id for m in mensajes])).all() if mensajes else []
    adjuntos = db.query(ChannelAttachment).filter(ChannelAttachment.organization_id == org,
                                                  ChannelAttachment.uploaded_by_client_id.in_(ids)).all()
    reacciones = db.query(ChannelReaction).filter(ChannelReaction.organization_id == org,
                                                  ChannelReaction.client_user_id.in_(ids)).all()
    from sqlalchemy import or_
    llamadas = db.query(ChannelCall).filter(ChannelCall.organization_id == org, or_(
        ChannelCall.answered_by_client_id.in_(ids), ChannelCall.declined_by_client_id.in_(ids),
        ChannelCall.ended_by_client_id.in_(ids))).all()
    return {"livechat": {
        "messages": [{"conversation_id": m.conversation_id, "body": m.body, "created_at": _fecha(m.created_at),
                      "edited_at": _fecha(m.edited_at), "deleted_at": _fecha(m.deleted_at)} for m in mensajes],
        "edits": [{"message_id": v.message_id, "change_type": v.change_type, "body": v.body,
                   "at": _fecha(v.edited_at)} for v in versiones_],
        "attachments": [{"conversation_id": a.conversation_id, "name": a.name, "mime_type": a.mime_type,
                         "size_bytes": a.size_bytes, "sha256": a.sha256, "created_at": _fecha(a.created_at),
                         "deleted_at": _fecha(a.deleted_at)} for a in adjuntos],
        "reactions": [{"message_id": r.message_id, "emoji": r.emoji, "at": _fecha(r.created_at)} for r in reacciones],
        "calls": [{"conversation_id": c.conversation_id, "kind": c.kind, "status": c.status,
                   "created_at": _fecha(c.created_at), "answered_at": _fecha(c.answered_at),
                   "ended_at": _fecha(c.ended_at), "duration_seconds": c.duration_seconds} for c in llamadas],
    }}


def exigir_sin_bloqueo_legal_rgpd(db: Session, client_ids: Iterable[str], org: str) -> None:
    """Bajo bloqueo legal de un adjunto suyo, 409 ANTES de tocar nada."""
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    ids = list(client_ids)
    if not ids:
        return
    activos = bloqueos_activos(db, org)
    if not activos:
        return
    casos = set()
    for a in db.query(ChannelAttachment).filter(ChannelAttachment.organization_id == org,
                                                ChannelAttachment.uploaded_by_client_id.in_(ids)).all():
        b = _bloqueo_de("sd_channel_attachments", a, activos)
        if b is not None:
            casos.add(b.case_reference)
    if casos:
        raise error(409, "bloqueo_legal_no_suprimible", casos=", ".join(sorted(casos)))


def suprimir_rgpd(db: Session, client_ids: Iterable[str], org: str) -> dict:
    """Supresión: «[ERASED]» en sus mensajes, fuera sus versiones, adjuntos (fila y
    fichero al confirmar) y reacciones. Las llamadas quedan como metadatos de servicio."""
    ids = list(client_ids)
    if not ids:
        return {"messages": 0, "attachments": 0, "reactions": 0, "edits": 0}
    exigir_sin_bloqueo_legal_rgpd(db, ids, org)
    convs = _conversaciones_de(db, ids, org)
    mensajes = db.query(ChannelMessage).filter(
        ChannelMessage.organization_id == org, ChannelMessage.conversation_id.in_(convs),
        ChannelMessage.author_type == "customer").all() if convs else []
    n_versiones = 0
    if mensajes:
        for v in db.query(ChannelMessageVersion).filter(
                ChannelMessageVersion.message_id.in_([m.id for m in mensajes])).all():
            db.delete(v)
            n_versiones += 1
    for m in mensajes:
        m.body = BORRADO_RGPD
    if convs:
        for c in db.query(ChannelConversation).filter(ChannelConversation.id.in_(convs)).all():
            c.visitor_name = BORRADO_RGPD
    adjuntos = db.query(ChannelAttachment).filter(ChannelAttachment.organization_id == org,
                                                  ChannelAttachment.uploaded_by_client_id.in_(ids)).all()
    for a in adjuntos:
        db.delete(a)  # el fichero se borra al confirmar (app/db/portal_chat_borrado.py)
    reacciones = db.query(ChannelReaction).filter(ChannelReaction.organization_id == org,
                                                  ChannelReaction.client_user_id.in_(ids)).all()
    for r in reacciones:
        db.delete(r)
    db.flush()
    return {"messages": len(mensajes), "attachments": len(adjuntos), "reactions": len(reacciones),
            "edits": n_versiones}
