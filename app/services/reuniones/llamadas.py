"""Cuarta vía (19-11-2026): llamadas de voz y vídeo del chat interno (LiveKit).

Arquitectura que se reutiliza: cada navegador de la llamada ya sube SU audio
en trozos a `POST /collaboration/calls/{id}/transcribe-chunk` para los
subtítulos en vivo (`_transcription.transcribe_audio_chunk`). Ese mismo
camino alimenta al asistente: cada trozo llega autenticado como la persona que
habla, así que aquí sí hay **hablantes reales, cada uno con su usuario**, sin
diarización.

- Activar (`activar`): cualquier participante interno de la llamada, con el
  aviso de grabación confirmado; se avisa además en el chat. Participantes de
  la reunión = miembros de la llamada (y quien entre después). Con
  consentimiento exigido, cada persona responde dentro de la propia llamada.
- Solo cuenta lo dicho DESPUÉS de activar: los subtítulos anteriores no se
  importan (no hubo aviso). Lo de quien dijo «no» no se guarda.
- Al colgar (`cerrar`, encolado por `end_call`): duración, análisis, acta y un
  mensaje en la conversación con el enlace a la reunión y al acta.
- Vinculación: la conversación, y el proyecto del canal (y su cliente).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.reuniones import config as cfg_mod
from app.services.reuniones.eventos import auditar, evento

logger = logging.getLogger(__name__)

ORIGEN = "chat_call"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _llamada(db: Session, usuario, call_id: str):
    from app.services.collaboration.calls import exigir_llamada_accesible
    return exigir_llamada_accesible(db, usuario, call_id)


def reunion_de(db: Session, call_id: str):
    from app.models.ai_chat import AIMeeting
    return (db.query(AIMeeting).filter(AIMeeting.call_id == call_id, AIMeeting.origin == ORIGEN)
            .order_by(AIMeeting.created_at.desc()).first())


def _canal(db: Session, conversation_id: str):
    from app.models.collaboration import CollaborationChannel
    return db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conversation_id).first()


def _añadir_miembro(db: Session, reunion, *, user_id=None, client_user_id=None):
    from app.services.reuniones.servicio import añadir_participante
    if user_id:
        return añadir_participante(db, reunion, user_id=user_id)
    if client_user_id:
        from app.models.client_portal import ClientUser
        cu = db.get(ClientUser, client_user_id)
        if cu is not None:
            return añadir_participante(db, reunion, name=cu.full_name, email=cu.email)
    return None


def estado(db: Session, usuario, call_id: str) -> dict:
    """Lo que pinta la llamada: si el asistente está activo y qué falta de mí."""
    llamada = _llamada(db, usuario, call_id)
    cfg = cfg_mod.leer(db, usuario.organization_id)
    reunion = reunion_de(db, llamada.id)
    yo = next((p for p in reunion.participantes if p.user_id == usuario.id), None) if reunion else None
    puede_parar = False
    if reunion is not None and reunion.status == "grabando":
        from app.services.reuniones.consultas import es_gestor
        puede_parar = reunion.notice_confirmed_by == usuario.id or es_gestor(db, usuario, reunion)
    return {"can_stop": puede_parar,"call_id": llamada.id, "active": bool(reunion and reunion.status == "grabando"),
            "meeting_id": reunion.id if reunion else None, "status": reunion.status if reunion else None,
            "notice_required": cfg["consent"]["notice_required"], "notice_text": cfg_mod.texto_del_aviso(cfg),
            "require_consent": bool(reunion.consent_required) if reunion else cfg["consent"]["require_consent"],
            "my_participant_id": getattr(yo, "id", None), "my_consent": getattr(yo, "consent", None)}


def activar(db: Session, usuario, call_id: str, aviso_confirmado: bool):
    """Pone el asistente a grabar la llamada. Idempotente. No confirma."""
    from app.models.ai_chat import AIMeeting
    from app.models.collaboration import CollaborationCallParticipant
    from app.services.reuniones.servicio import añadir_participante, fijar_retencion, _caducidad_audio
    llamada = _llamada(db, usuario, call_id)
    if str(getattr(llamada.status, "value", llamada.status)) == "ended":
        raise error(409, "reuniones_no_grabando", detail="La llamada ya terminó")
    ya = reunion_de(db, llamada.id)
    if ya is not None and ya.status == "grabando":
        return ya
    org = usuario.organization_id
    cfg = cfg_mod.leer(db, org)
    if cfg["consent"]["notice_required"] and not aviso_confirmado:
        raise error(422, "reuniones_sin_aviso")
    canal = _canal(db, llamada.conversation_id)
    proyecto = getattr(canal, "project_id", None)
    cliente = None
    if proyecto:
        from app.models.project import Project
        cliente = getattr(db.get(Project, proyecto), "client_id", None)
    reunion = AIMeeting(
        organization_id=org, title=f"Reunión del chat · {canal.name}" if canal else "Reunión del chat",
        origin=ORIGEN, platform="chat", call_id=llamada.id, conversation_id=llamada.conversation_id,
        project_id=proyecto, client_id=cliente, meeting_date=_ahora(), created_by=usuario.id,
        status="grabando", consent_required=bool(cfg["consent"]["require_consent"]),
        notice_confirmed_by=usuario.id, notice_confirmed_at=_ahora(), audio_expires_at=_caducidad_audio(db, org))
    db.add(reunion)
    db.flush()
    añadir_participante(db, reunion, user_id=usuario.id, role="organizador", consent=True, consent_method="self",
                        actor=usuario)
    for p in db.query(CollaborationCallParticipant).filter(CollaborationCallParticipant.call_id == llamada.id):
        _añadir_miembro(db, reunion, user_id=p.user_id, client_user_id=p.client_user_id)
    fijar_retencion(db, reunion)
    evento(db, reunion, "created", usuario, {"origin": ORIGEN, "call": llamada.id})
    evento(db, reunion, "notice_confirmed", usuario, {"source": "chat_call"})
    auditar(db, usuario, "RECORDING_START", reunion, metadata={"origin": ORIGEN, "call": llamada.id,
                                                              "notice_confirmed": True})
    from app.services.collaboration import audit_log
    audit_log.write(db, organization_id=org, actor_user_id=usuario.id, actor_client_id=None,
                    action="call.assistant_started", entity_type="call", entity_id=llamada.id,
                    payload={"meeting_id": reunion.id})
    _mensaje(db, org, llamada.conversation_id, "🔴 " + cfg_mod.texto_del_aviso(cfg),
             {"card": "meeting_assistant_notice", "meeting_id": reunion.id, "call_id": llamada.id,
              "require_consent": reunion.consent_required}, autor=usuario)
    return reunion


def al_unirse(db: Session, usuario, call_id: str) -> None:
    """Quien entra con el asistente activo pasa a ser participante (consentimiento pendiente)."""
    reunion = reunion_de(db, call_id)
    if reunion is not None and reunion.status == "grabando":
        _añadir_miembro(db, reunion, user_id=usuario.id)
        evento(db, reunion, "participant_added", usuario, {"name": usuario.full_name})


def transcribir_si_graba(db: Session, usuario, call_id: str, audio: bytes, nombre: str, mime: str
                         ) -> Optional[str]:
    """Con el asistente grabando, el texto del trozo con los STT permitidos para reuniones.

    `None` = el asistente no graba esta voz (no está activo o la persona dijo
    «no»): la llamada sigue con sus subtítulos de siempre. Si no hay STT
    permitido, `""` (no se cae a un proveedor externo sin contrato).
    """
    reunion = reunion_de(db, call_id)
    if reunion is None or reunion.status != "grabando":
        return None
    yo = next((p for p in reunion.participantes if p.user_id == usuario.id), None)
    if yo is not None and yo.consent is False:
        return None
    from app.services.reuniones.transcripcion import transcribir
    try:
        return (transcribir(db, reunion.organization_id, audio, nombre, mime).text or "").strip()
    except Exception:  # noqa: BLE001 - sin STT permitido o sin presupuesto: sin texto, sin caer a otro
        logger.warning("reuniones: trozo de la llamada %s sin transcribir", call_id, exc_info=True)
        return ""


def registrar_fragmento(db: Session, usuario, call_id: str, texto: str, audio: Optional[bytes] = None,
                        mime: str = "audio/webm") -> bool:
    """Un trozo de subtítulos (y su audio) de UNA persona, si el asistente graba. No confirma."""
    from app.models.reuniones import AIMeetingAudio, AIMeetingSegment
    reunion = reunion_de(db, call_id)
    if reunion is None or reunion.status != "grabando" or not (texto or "").strip():
        return False
    p = next((x for x in reunion.participantes if x.user_id == usuario.id), None) \
        or _añadir_miembro(db, reunion, user_id=usuario.id)
    if p is not None and p.consent is False:
        return False   # dijo que no: ni texto ni audio
    db.flush()
    desde = reunion.notice_confirmed_at or reunion.meeting_date or _ahora()
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    inicio = max(0, int((_ahora() - desde).total_seconds() * 1000))
    orden = max((s.orden for s in reunion.segmentos), default=-1) + 1
    reunion.segmentos.append(AIMeetingSegment(
        organization_id=reunion.organization_id, orden=orden, speaker=usuario.full_name or usuario.username,
        participant_id=getattr(p, "id", None), user_id=usuario.id, start_ms=inicio, end_ms=None,
        text=texto.strip()))
    if audio:
        from app.services.reuniones import almacen
        seq = len(reunion.audios)
        clave = almacen.guardar(reunion.organization_id, reunion.id, seq, audio, mime)
        reunion.audios.append(AIMeetingAudio(
            organization_id=reunion.organization_id, seq=seq, storage_key=clave, bytes=len(audio),
            mime=(mime or "audio/webm")[:100], offset_ms=inicio, transcribed=True, stt_provider="chat_call",
            expires_at=reunion.audio_expires_at))
    return True


def detener(db: Session, usuario, call_id: str):
    """Para la grabación antes de colgar y analiza lo que haya. No confirma."""
    from app.services.reuniones.consultas import es_gestor
    _llamada(db, usuario, call_id)
    reunion = reunion_de(db, call_id)
    if reunion is None or reunion.status != "grabando":
        raise error(409, "reuniones_no_grabando")
    if not (es_gestor(db, usuario, reunion) or reunion.notice_confirmed_by == usuario.id):
        raise error(403, "sin_permiso", detail="Solo quien activó el asistente o gestiona la reunión puede pararlo")
    _terminar(db, reunion, usuario)
    return reunion


def _terminar(db: Session, reunion, actor) -> None:
    from app.services.reuniones.analisis import analizar
    reunion.ends_at = _ahora()
    fin = max([s.start_ms or 0 for s in reunion.segmentos] + [0])
    reunion.duration_min = max(1, round(fin / 60000)) if fin else reunion.duration_min
    evento(db, reunion, "finished", actor, {"segments": len(reunion.segmentos)})
    analizar(db, reunion, actor)
    if reunion.status == "lista" and reunion.created_by:
        from app.models.user import User
        from app.services.reuniones.servicio import generar_acta
        autor = db.get(User, reunion.created_by)
        if autor is not None:
            try:
                generar_acta(db, autor, reunion)
            except Exception:  # noqa: BLE001 - sin almacén de documentos, la reunión sigue lista
                logger.warning("reuniones: no se pudo generar el acta de %s", reunion.id, exc_info=True)
    if reunion.conversation_id:
        enlace = f"/meetings-ai?meeting={reunion.id}"
        if reunion.status == "lista":
            cuerpo = f"📝 Acta de la reunión: {reunion.title}\n{(reunion.summary or '')[:600]}\n{enlace}"
        else:
            cuerpo = f"📝 Reunión del asistente: {reunion.title} ({reunion.status})\n{enlace}"
        _mensaje(db, reunion.organization_id, reunion.conversation_id, cuerpo,
                 {"card": "meeting_minutes", "meeting_id": reunion.id, "status": reunion.status,
                  "document_id": reunion.minutes_document_id, "link": enlace,
                  "actions": [a.description for a in reunion.actions][:20]})


def cerrar(call_id: str, organization_id: str) -> None:
    """Al colgar (cola de colaboración, como `bots.summarize_call`): sesión propia y contexto de la empresa."""
    from app.db.session import SessionLocal
    from app.services.service_desk.ticket_events import como_organizacion
    db = SessionLocal()
    try:
        with como_organizacion(db, organization_id):
            reunion = reunion_de(db, call_id)
            if reunion is None or reunion.status != "grabando":
                return
            _terminar(db, reunion, None)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("reuniones: cierre de la llamada %s", call_id)
    finally:
        db.close()


def _mensaje(db: Session, org: str, conversation_id: str, cuerpo: str, metadata: dict, autor=None) -> None:
    """Mensaje en la conversación: con el bot «pulse» si existe; si no, mensaje de sistema."""
    try:
        from app.models.collaboration import CollaborationBotApp, CollaborationMessage
        bot = db.query(CollaborationBotApp).filter(CollaborationBotApp.organization_id == org,
                                                   CollaborationBotApp.handle == "pulse").first()
        if bot is not None:
            from app.services.collaboration.bots import _post_bot_message
            _post_bot_message(db, organization_id=org, bot=bot, conversation_id=conversation_id, body=cuerpo,
                              metadata=metadata)
            return
        from app.core.timeutil import utcnow
        db.add(CollaborationMessage(organization_id=org, conversation_id=conversation_id,
                                    user_id=getattr(autor, "id", None), type="system", status="visible",
                                    body=cuerpo, metadata_json=metadata, sent_at=utcnow()))
        db.flush()
    except Exception:  # noqa: BLE001 - el aviso en el chat no impide grabar ni el acta
        logger.warning("reuniones: no se pudo publicar en la conversación %s", conversation_id, exc_info=True)


__all__ = ["activar", "al_unirse", "cerrar", "detener", "estado", "registrar_fragmento", "reunion_de"]
