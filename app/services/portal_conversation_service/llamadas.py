"""Llamadas y videollamadas del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

**Solo el operador llama.** Se impone en el servidor, en tres capas:

1. No existe ninguna vía de servicio por la que un cliente cree una llamada:
   `iniciar` recibe un `User` del equipo y la ruta exige `clientes.llamar`.
2. La ruta del portal `POST /portal/conversations/{id}/calls` existe a
   propósito y SIEMPRE responde 403 `portal_llamada_solo_operador` (y deja el
   intento en la auditoría): un cliente modificado no encuentra un 404 que
   probar, encuentra la regla.
3. El cliente solo puede aceptar (si está sonando o en curso), rechazar (si
   está sonando) o colgar. Su token de LiveKit solo se emite al aceptar una
   llamada que inició el equipo en una conversación suya de su empresa.

Por empresa (`ajustes`): llamadas y vídeo activables (`PORTAL_CHAT_CALLS_ENABLED`,
`PORTAL_CHAT_VIDEO_ENABLED`); apagados → 403 `portal_llamadas_desactivadas` /
`portal_videollamadas_desactivadas`. Una llamada que suena más de
`PORTAL_CHAT_CALL_RING_SECONDS` pasa a perdida (`missed`).

Sin grabación ni transcripción: la sala es de LiveKit con tokens sin permiso de
grabador y la llamada no pasa por el asistente de reuniones. El aviso al
cliente lo dice («esta llamada no se graba»).

Auditoría (`portal_conversation_audits`): `call_started`, `call_accepted`,
`call_declined`, `call_missed`, `call_joined`, `call_ended` y
`call_start_denied` (intento del cliente).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.portal_conversations import PortalConversationCall, PortalConversationStatus
from app.services.portal_conversation_service import ajustes as _ajustes
from app.services.portal_conversation_service import en_vivo
from app.services.portal_conversation_service._comun import (
    _audit,
    _conversacion_del_cliente,
    _conversacion_del_equipo,
    _equipo_participa,
    _is_legacy_conversation_id,
    _now,
)

TIPOS = ("audio", "video")
VIVAS = ("ringing", "active")
#: Vida del token de LiveKit de una llamada del portal (s).
TTL_DEL_TOKEN = 2 * 3600


def _sala(call_id: str) -> str:
    return f"contec-portal-{call_id}"


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=_now().tzinfo)


def _caducar_si_no_contestan(db: Session, conversation, call: PortalConversationCall) -> bool:
    """Una llamada que suena más de lo configurado pasa a perdida. True si cambió."""
    if call.status != "ringing" or call.created_at is None:
        return False
    tono = _ajustes.leer(db, conversation.organization_id).segundos_de_tono
    if _now() - _aware(call.created_at) <= timedelta(seconds=tono):
        return False
    call.status = "missed"
    call.ended_at = _now()
    _audit(db, conversation, "portal_conversation.call_missed", target_type="call", target_id=call.id,
           details={"kind": call.kind})
    return True


def _llamada(db: Session, conversation, call_id: str) -> PortalConversationCall:
    call = db.query(PortalConversationCall).filter(
        PortalConversationCall.id == call_id,
        PortalConversationCall.conversation_id == conversation.id,
        PortalConversationCall.organization_id == conversation.organization_id,
    ).first()
    if call is None:
        raise error(404, "portal_llamada_no_encontrada")
    if _caducar_si_no_contestan(db, conversation, call):
        db.commit()
    return call


def _salida(call: PortalConversationCall) -> dict:
    return {
        "id": call.id, "conversation_id": call.conversation_id, "kind": call.kind, "status": call.status,
        "initiated_by_user_id": call.initiated_by_user_id,
        "answered_by_client_id": call.answered_by_client_id,
        "created_at": str(call.created_at)[:19] if call.created_at else None,
        "answered_at": str(call.answered_at)[:19] if call.answered_at else None,
        "ended_at": str(call.ended_at)[:19] if call.ended_at else None,
        "duration_seconds": call.duration_seconds or 0,
        "is_recorded": False,
    }


def _con_token(call: PortalConversationCall, *, identidad: str, nombre: str, rol: str) -> dict:
    from app.services.collaboration.livekit import issue_access_token, url
    salida = _salida(call)
    salida.update({
        "role": rol,
        "livekit_url": url(),
        "livekit_room": call.livekit_room,
        "livekit_token": issue_access_token(room=call.livekit_room, identity=identidad, name=nombre,
                                            is_recorder=False, ttl_seconds=TTL_DEL_TOKEN),
    })
    return salida


def _avisar(db: Session, conversation, call: PortalConversationCall, **excepto) -> None:
    en_vivo.avisar(db, conversation, "call", {"call_id": call.id, "status": call.status, "kind": call.kind},
                   **excepto)


def _hay_cliente(conversation) -> bool:
    return any(p.removed_at is None and (p.client_user_id or p.client_org_id) for p in conversation.participants) \
        or bool(conversation.created_by_client_id)


# ── Equipo ───────────────────────────────────────────────────────────────────

def iniciar(db: Session, conversation_id: str, kind: str, current_user) -> dict:
    """El operador llama al cliente. Comprobaciones antes de crear nada."""
    if kind not in TIPOS:
        raise error(422, "portal_llamada_tipo_no_valido", tipo=kind)
    if _is_legacy_conversation_id(conversation_id):
        raise error(422, "portal_llamada_no_disponible")
    conversation = _conversacion_del_equipo(db, conversation_id, current_user)
    ajustes = _ajustes.leer(db, conversation.organization_id)
    if not ajustes.llamadas:
        raise error(403, "portal_llamadas_desactivadas")
    if kind == "video" and not ajustes.video:
        raise error(403, "portal_videollamadas_desactivadas")
    if conversation.status in (PortalConversationStatus.closed, PortalConversationStatus.archived):
        raise error(409, "conversacion_cerrada")
    if not _hay_cliente(conversation):
        raise error(422, "portal_llamada_sin_cliente")
    if not _equipo_participa(db, conversation, current_user):
        raise error(403, "portal_llamada_sin_acceso")
    en_curso = db.query(PortalConversationCall).filter(
        PortalConversationCall.conversation_id == conversation.id,
        PortalConversationCall.status.in_(VIVAS),
    ).all()
    for c in en_curso:
        _caducar_si_no_contestan(db, conversation, c)
    if any(c.status in VIVAS for c in en_curso):
        db.commit()
        raise error(409, "portal_llamada_en_curso")
    call = PortalConversationCall(
        organization_id=conversation.organization_id, conversation_id=conversation.id,
        initiated_by_user_id=current_user.id, kind=kind, status="ringing", livekit_room="pendiente",
    )
    db.add(call)
    db.flush()
    call.livekit_room = _sala(call.id)
    _audit(db, conversation, "portal_conversation.call_started", actor_user_id=current_user.id,
           target_type="call", target_id=call.id, details={"kind": kind})
    db.commit()
    _avisar(db, conversation, call, excepto_usuario=current_user.id)
    return _con_token(call, identidad=f"user:{current_user.id}", nombre=current_user.full_name, rol="host")


def unirse_como_equipo(db: Session, conversation_id: str, call_id: str, current_user) -> dict:
    conversation = _conversacion_del_equipo(db, conversation_id, current_user)
    if not _equipo_participa(db, conversation, current_user):
        raise error(403, "portal_llamada_sin_acceso")
    call = _llamada(db, conversation, call_id)
    if call.status not in VIVAS:
        raise error(409, "portal_llamada_terminada")
    _audit(db, conversation, "portal_conversation.call_joined", actor_user_id=current_user.id,
           target_type="call", target_id=call.id)
    db.commit()
    return _con_token(call, identidad=f"user:{current_user.id}", nombre=current_user.full_name, rol="participant")


def colgar_como_equipo(db: Session, conversation_id: str, call_id: str, current_user) -> dict:
    conversation = _conversacion_del_equipo(db, conversation_id, current_user)
    if not _equipo_participa(db, conversation, current_user):
        raise error(403, "portal_llamada_sin_acceso")
    call = _llamada(db, conversation, call_id)
    return _terminar(db, conversation, call, user_id=current_user.id)


def listar_como_equipo(db: Session, conversation_id: str, current_user, limite: int = 20) -> list[dict]:
    if _is_legacy_conversation_id(conversation_id):
        return []
    conversation = _conversacion_del_equipo(db, conversation_id, current_user)
    return _listar(db, conversation, limite)


# ── Cliente ──────────────────────────────────────────────────────────────────

def iniciar_como_cliente(db: Session, conversation_id: str, current_client, kind: Optional[str] = None) -> None:
    """El cliente NUNCA inicia: 403 con código, y el intento queda auditado."""
    if not _is_legacy_conversation_id(conversation_id):
        try:
            conversation = _conversacion_del_cliente(db, conversation_id, current_client)
        except ValueError:
            conversation = None
        if conversation is not None:
            _audit(db, conversation, "portal_conversation.call_start_denied", actor_client_id=current_client.id,
                   target_type="call", status="denied", details={"kind": kind, "motivo": "solo_operador"})
            db.commit()
    raise error(403, "portal_llamada_solo_operador")


def aceptar(db: Session, conversation_id: str, call_id: str, current_client) -> dict:
    conversation = _conversacion_del_cliente(db, conversation_id, current_client)
    call = _llamada(db, conversation, call_id)
    if call.status not in VIVAS:
        raise error(409, "portal_llamada_terminada")
    if not call.initiated_by_user_id:
        # Defensa en profundidad: solo se entra en llamadas que inició el equipo.
        raise error(403, "portal_llamada_solo_operador")
    if call.status == "ringing":
        call.status = "active"
        call.answered_at = _now()
        call.answered_by_client_id = current_client.id
    _audit(db, conversation, "portal_conversation.call_accepted", actor_client_id=current_client.id,
           target_type="call", target_id=call.id, details={"kind": call.kind})
    db.commit()
    _avisar(db, conversation, call, excepto_cliente=current_client.id)
    return _con_token(call, identidad=f"client:{current_client.id}", nombre=current_client.full_name,
                      rol="participant")


def rechazar(db: Session, conversation_id: str, call_id: str, current_client) -> dict:
    conversation = _conversacion_del_cliente(db, conversation_id, current_client)
    call = _llamada(db, conversation, call_id)
    if call.status != "ringing":
        raise error(409, "portal_llamada_terminada")
    call.status = "declined"
    call.declined_by_client_id = current_client.id
    call.ended_at = _now()
    _audit(db, conversation, "portal_conversation.call_declined", actor_client_id=current_client.id,
           target_type="call", target_id=call.id, details={"kind": call.kind})
    db.commit()
    _avisar(db, conversation, call, excepto_cliente=current_client.id)
    return _salida(call)


def colgar_como_cliente(db: Session, conversation_id: str, call_id: str, current_client) -> dict:
    conversation = _conversacion_del_cliente(db, conversation_id, current_client)
    call = _llamada(db, conversation, call_id)
    return _terminar(db, conversation, call, client_id=current_client.id)


def listar_como_cliente(db: Session, conversation_id: str, current_client, limite: int = 20) -> list[dict]:
    if _is_legacy_conversation_id(conversation_id):
        return []
    conversation = _conversacion_del_cliente(db, conversation_id, current_client)
    return _listar(db, conversation, limite)


def sonando_para_cliente(db: Session, current_client) -> list[dict]:
    """Llamadas que suenan ahora para el cliente, en cualquiera de sus conversaciones."""
    from app.models.portal_conversations import PortalConversation
    filas = db.query(PortalConversationCall).filter(
        PortalConversationCall.organization_id == current_client.organization_id,
        PortalConversationCall.status == "ringing",
    ).order_by(PortalConversationCall.created_at.desc()).limit(20).all()
    salida = []
    cambios = False
    for call in filas:
        try:
            conversation = _conversacion_del_cliente(db, call.conversation_id, current_client)
        except ValueError:
            continue
        if _caducar_si_no_contestan(db, conversation, call):
            cambios = True
            continue
        conv = db.get(PortalConversation, call.conversation_id)
        salida.append({**_salida(call), "conversation_title": conv.title if conv else None})
    if cambios:
        db.commit()
    return salida


# ── Común ────────────────────────────────────────────────────────────────────

def _terminar(db: Session, conversation, call: PortalConversationCall, *, user_id=None, client_id=None) -> dict:
    if call.status not in VIVAS:
        return _salida(call)
    ahora = _now()
    if call.status == "active" and call.answered_at is not None:
        call.duration_seconds = max(0, int((ahora - _aware(call.answered_at)).total_seconds()))
    call.status = "ended"
    call.ended_at = ahora
    call.ended_by_user_id = user_id
    call.ended_by_client_id = client_id
    _audit(db, conversation, "portal_conversation.call_ended", actor_user_id=user_id, actor_client_id=client_id,
           target_type="call", target_id=call.id,
           details={"kind": call.kind, "duration_seconds": call.duration_seconds})
    db.commit()
    _avisar(db, conversation, call, excepto_usuario=user_id, excepto_cliente=client_id)
    return _salida(call)


def _listar(db: Session, conversation, limite: int) -> list[dict]:
    filas = db.query(PortalConversationCall).filter(
        PortalConversationCall.conversation_id == conversation.id,
        PortalConversationCall.organization_id == conversation.organization_id,
    ).order_by(PortalConversationCall.created_at.desc()).limit(limite).all()
    cambios = any([_caducar_si_no_contestan(db, conversation, c) for c in filas])
    if cambios:
        db.commit()
    return [_salida(c) for c in filas]
