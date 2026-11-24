"""Grabación con aviso y consentimiento de las llamadas con clientes del portal (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §11. Migración 214. Sustituye la regla
anterior «con clientes nunca se graba» (409 `portal_llamada_no_se_graba`).

Reglas, impuestas aquí (servidor) para los tres chats del portal
(`colaboracion`: pestaña «Chat»; `conversacion`: conversaciones formales;
`en_vivo`: chat en vivo de Soporte):

1. **Activable por empresa** (grupo `portal_chat`): apagado por defecto. Sin
   él, proponer o grabar → 409 `portal_grabacion_desactivada`; transcribir sin
   `PORTAL_CHAT_TRANSCRIPTION_ENABLED` → 409 `portal_transcripcion_desactivada`.
2. **Solo el operador propone** (`proponer`, ruta con `clientes.llamar`); el
   cliente no tiene ninguna vía para iniciar una grabación.
3. **Consentimiento explícito de CADA cliente** de la llamada en su pantalla
   (`responder`). Hasta que todos dicen que sí no se graba nada; uno que dice
   que no cancela la ronda. Grabar o transcribir por otra vía (grabación del
   chat interno, subtítulos, asistente de reuniones) sin consentimiento → 409
   `portal_grabacion_sin_consentimiento` (`exigir_consentimiento`).
4. **Retirada** (`retirar`): el cliente puede retirar el consentimiento en
   cualquier momento; la grabación se para al instante.
5. **Evidencia**: cada respuesta guarda quién, cuándo, llamada, texto aceptado
   (y su SHA-256), idioma, IP y navegador (`portal_call_recording_consents`).
6. **Indicador**: `estado` dice a todos si se está grabando (la interfaz enseña
   «Grabando» a operador y cliente).

Reutiliza la grabación y la transcripción del chat interno: en `colaboracion`
la grabación es una `CollaborationRecording` y la transcripción la
`CollaborationTranscript` / el asistente de reuniones. En `conversacion` y
`en_vivo` la ronda guarda el inicio y el fin (la sala es de LiveKit, como en el
chat interno; sin transcripción en el servidor para esos dos canales).

GRC: auditoría (`audit_logs`, recurso `portal_call_recording`: propuesta,
consentimiento dado/denegado/retirado, inicio/fin, descargas), retención por
empresa (`purgar_caducadas`, en la pasada diaria de `retencion.pasada_diaria`)
con bloqueo legal (`app/db/bloqueo_legal.py`: tipos
`portal_call_recording_consents`, `collaboration_recordings`,
`collaboration_transcripts`) y RGPD (`copia_rgpd`, `suprimir_rgpd`).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.grabacion_con_clientes import CANALES, PortalCallRecordingConsent
from app.services.portal_conversation_service import ajustes as _ajustes

log = logging.getLogger(__name__)

RECURSO = "portal_call_recording"
#: Texto del aviso por defecto (castellano canónico; la interfaz lo enseña en el
#: idioma del cliente y la evidencia guarda este texto más el idioma).
AVISO_POR_DEFECTO = (
    "Esta llamada se va a grabar{y_transcribir} para dejar constancia de lo acordado. "
    "Solo se graba si das tu consentimiento; puedes retirarlo en cualquier momento y la grabación se para. "
    "La grabación se conserva {dias} días y solo la ve el personal autorizado de la empresa."
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── La llamada, sea del chat que sea ─────────────────────────────────────────

@dataclass
class Llamada:
    canal: str
    id: str
    conversation_id: str
    organization_id: str
    viva: bool
    clientes: list = field(default_factory=list)
    obj: Any = None
    conversacion: Any = None


def _clientes_de_conversacion_formal(conversation) -> list[str]:
    ids = [p.client_user_id for p in conversation.participants if p.removed_at is None and p.client_user_id]
    if conversation.created_by_client_id and conversation.created_by_client_id not in ids:
        ids.append(conversation.created_by_client_id)
    return ids


def cargar(db: Session, canal: str, call_id: str, organization_id: Optional[str]) -> Llamada:
    """La llamada de esa empresa en ese canal (404 si no existe o es de otra empresa)."""
    if canal not in CANALES:
        raise error(404, "portal_llamada_no_encontrada")
    if canal == "colaboracion":
        from app.models.collaboration import CollaborationCall
        from app.services.collaboration.portal_chat import clientes_de
        c = db.query(CollaborationCall).filter(CollaborationCall.id == call_id,
                                               CollaborationCall.organization_id == organization_id).first()
        if c is None:
            raise error(404, "portal_llamada_no_encontrada")
        estado = getattr(c.status, "value", c.status)
        return Llamada(canal, c.id, c.conversation_id, c.organization_id, estado == "active",
                       sorted(clientes_de(db, c.conversation_id)), c)
    if canal == "conversacion":
        from app.models.portal_conversations import PortalConversation, PortalConversationCall
        c = db.query(PortalConversationCall).filter(PortalConversationCall.id == call_id,
                                                    PortalConversationCall.organization_id == organization_id).first()
        if c is None:
            raise error(404, "portal_llamada_no_encontrada")
        conv = db.get(PortalConversation, c.conversation_id)
        clientes = _clientes_de_conversacion_formal(conv) if conv is not None else []
        return Llamada(canal, c.id, c.conversation_id, c.organization_id, c.status in ("ringing", "active"),
                       clientes, c, conv)
    from app.models.service_desk import ChannelConversation
    from app.models.service_desk.mercado import ChannelCall
    c = db.query(ChannelCall).filter(ChannelCall.id == call_id, ChannelCall.organization_id == organization_id).first()
    if c is None:
        raise error(404, "portal_llamada_no_encontrada")
    conv = db.get(ChannelConversation, c.conversation_id)
    clientes = [conv.client_user_id] if conv is not None and conv.client_user_id else []
    return Llamada(canal, c.id, c.conversation_id, c.organization_id, c.status in ("ringing", "active"),
                   clientes, c, conv)


def exigir_acceso_del_operador(db: Session, usuario, llamada: Llamada) -> None:
    """El operador participa en la conversación de la llamada (misma empresa, ya filtrada en `cargar`)."""
    if llamada.canal == "colaboracion":
        from app.services.collaboration._permissions import assert_conversation_access
        assert_conversation_access(db, usuario, llamada.conversation_id)
        return
    if llamada.canal == "conversacion":
        from app.services.portal_conversation_service._comun import _equipo_participa
        if llamada.conversacion is None or not _equipo_participa(db, llamada.conversacion, usuario):
            raise error(403, "portal_llamada_sin_acceso")
        return
    from app.core.capacidades import tiene
    if not (getattr(usuario, "is_superadmin", False) or tiene(db, usuario, "sd.completo")):
        raise error(403, "portal_llamada_sin_acceso")


def exigir_acceso_del_cliente(cliente, llamada: Llamada) -> None:
    if llamada.organization_id != getattr(cliente, "organization_id", None) or cliente.id not in llamada.clientes:
        raise error(404, "portal_llamada_no_encontrada")


# ── Rondas ───────────────────────────────────────────────────────────────────

def _filas(db: Session, llamada: Llamada, ronda: Optional[int] = None) -> list[PortalCallRecordingConsent]:
    q = db.query(PortalCallRecordingConsent).filter(
        PortalCallRecordingConsent.organization_id == llamada.organization_id,
        PortalCallRecordingConsent.channel == llamada.canal,
        PortalCallRecordingConsent.call_id == llamada.id,
    )
    if ronda is not None:
        q = q.filter(PortalCallRecordingConsent.round == ronda)
    return q.order_by(PortalCallRecordingConsent.round, PortalCallRecordingConsent.created_at).all()


def _ronda_actual(db: Session, llamada: Llamada) -> tuple[int, list[PortalCallRecordingConsent]]:
    ultima = db.query(func.max(PortalCallRecordingConsent.round)).filter(
        PortalCallRecordingConsent.organization_id == llamada.organization_id,
        PortalCallRecordingConsent.channel == llamada.canal,
        PortalCallRecordingConsent.call_id == llamada.id,
    ).scalar()
    if not ultima:
        return 0, []
    return int(ultima), _filas(db, llamada, int(ultima))


def _grabando(filas: list[PortalCallRecordingConsent]) -> bool:
    return bool(filas) and all(f.status == "granted" for f in filas) \
        and any(f.recording_started_at is not None and f.recording_ended_at is None for f in filas)


def _abierta(filas: list[PortalCallRecordingConsent]) -> bool:
    """Ronda pendiente de respuestas o grabando."""
    if not filas:
        return False
    if _grabando(filas):
        return True
    return any(f.status == "pending" for f in filas) and not any(f.status in ("denied", "cancelled") for f in filas)


def grabando(db: Session, canal: str, call_id: str, organization_id: str) -> bool:
    try:
        llamada = cargar(db, canal, call_id, organization_id)
    except Exception:  # noqa: BLE001 - sin llamada, no se graba
        return False
    return _grabando(_ronda_actual(db, llamada)[1])


def texto_del_aviso(aj, transcribir: bool) -> str:
    if aj.aviso_de_grabacion:
        return aj.aviso_de_grabacion
    return AVISO_POR_DEFECTO.format(y_transcribir=" y transcribir" if transcribir else "",
                                    dias=aj.dias_grabaciones)


def estado(db: Session, llamada: Llamada, *, cliente=None) -> dict:
    """Lo que pintan las dos pantallas: si se puede grabar, si se está grabando y quién ha respondido."""
    aj = _ajustes.leer(db, llamada.organization_id)
    ronda, filas = _ronda_actual(db, llamada)
    mia = next((f for f in filas if cliente is not None and f.client_user_id == cliente.id), None)
    transcribir = bool(filas) and filas[0].purpose == "recording_transcript"
    return {
        "channel": llamada.canal, "call_id": llamada.id, "conversation_id": llamada.conversation_id,
        "with_clients": bool(llamada.clientes),
        "recording_enabled": bool(aj.llamadas and aj.grabacion),
        "transcription_enabled": bool(aj.llamadas and aj.grabacion and aj.transcripcion),
        "recording": _grabando(filas), "open": _abierta(filas), "round": ronda,
        "purpose": filas[0].purpose if filas else None, "transcribe": transcribir,
        "notice": filas[0].notice_text if filas else texto_del_aviso(aj, False),
        "custom_notice": bool(aj.aviso_de_grabacion),
        "retention_days": aj.dias_grabaciones,
        "consents": [{"client_user_id": f.client_user_id if cliente is None else None,
                      "status": f.status, "decided_at": f.decided_at.isoformat() if f.decided_at else None}
                     for f in filas],
        "my_consent": mia.status if mia is not None else None,
        "pending_for_me": bool(mia is not None and mia.status == "pending" and _abierta(filas)),
    }


# ── Auditoría y avisos ───────────────────────────────────────────────────────

def _auditar(db: Session, llamada: Llamada, accion: str, *, usuario=None, cliente=None, datos: Optional[dict] = None,
             ip: Optional[str] = None, ua: Optional[str] = None) -> None:
    from app.services.audit import audit_log
    meta = {"channel": llamada.canal, "call_id": llamada.id, "conversation_id": llamada.conversation_id,
            **(datos or {})}
    if cliente is not None:
        meta["actor_client_id"] = cliente.id
    entrada = audit_log(db, usuario, f"portal_recording.{accion}", RECURSO, llamada.id, llamada.canal,
                        metadata=meta, ip_address=ip, user_agent=(ua or None) and ua[:400])
    entrada.organization_id = llamada.organization_id


def _avisar(db: Session, llamada: Llamada) -> None:
    """Empuja «cambió la grabación» a los dos lados. Nunca lanza; llamar tras `commit`."""
    datos = {"call_id": llamada.id, "recording": grabando(db, llamada.canal, llamada.id, llamada.organization_id)}
    try:
        if llamada.canal == "colaboracion":
            from app.services.collaboration.portal_chat import _publicar
            _publicar(llamada.conversation_id, "call.recording", None, datos)
        elif llamada.canal == "conversacion" and llamada.conversacion is not None:
            from app.services.portal_conversation_service import en_vivo
            en_vivo.avisar(db, llamada.conversacion, "call_recording", datos)
        elif llamada.conversacion is not None:
            from app.services.service_desk import canales_en_vivo
            canales_en_vivo._a_operadores(llamada.conversacion, "call_recording", datos)
            canales_en_vivo._al_cliente(llamada.conversacion, "call_recording", datos)
    except Exception:  # noqa: BLE001 - el aviso es un extra; las pantallas consultan el estado
        log.debug("grabación del portal: aviso no enviado", exc_info=True)


# ── Operador ─────────────────────────────────────────────────────────────────

def proponer(db: Session, usuario, llamada: Llamada, transcribir: bool = False) -> dict:
    """El operador propone grabar: nace una ronda con una fila pendiente por cliente. Idempotente."""
    aj = _ajustes.leer(db, llamada.organization_id)
    if not (aj.llamadas and aj.grabacion):
        raise error(409, "portal_grabacion_desactivada")
    if transcribir and not aj.transcripcion:
        raise error(409, "portal_transcripcion_desactivada")
    if not llamada.viva:
        raise error(409, "portal_llamada_terminada")
    if not llamada.clientes:
        raise error(422, "portal_llamada_sin_cliente")
    ronda, filas = _ronda_actual(db, llamada)
    if _abierta(filas):
        return estado(db, llamada)
    texto = texto_del_aviso(aj, transcribir)
    huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    finalidad = "recording_transcript" if transcribir else "recording"
    for client_id in llamada.clientes:
        db.add(PortalCallRecordingConsent(
            organization_id=llamada.organization_id, channel=llamada.canal, call_id=llamada.id,
            conversation_id=llamada.conversation_id, round=ronda + 1, client_user_id=client_id,
            proposed_by_user_id=usuario.id, proposed_at=_ahora(), purpose=finalidad,
            notice_text=texto, notice_sha256=huella, status="pending",
        ))
    _auditar(db, llamada, "proposed", usuario=usuario,
             datos={"round": ronda + 1, "purpose": finalidad, "clients": len(llamada.clientes), "notice_sha256": huella})
    db.commit()
    _avisar(db, llamada)
    return estado(db, llamada)


def detener(db: Session, usuario, llamada: Llamada) -> dict:
    """El operador para la grabación (o retira la propuesta pendiente)."""
    _, filas = _ronda_actual(db, llamada)
    if _grabando(filas):
        _parar(db, llamada, filas, motivo="operator_stopped", usuario=usuario)
    elif _abierta(filas):
        for f in filas:
            if f.status == "pending":
                f.status = "cancelled"
        _auditar(db, llamada, "proposal_cancelled", usuario=usuario, datos={"round": filas[0].round})
    db.commit()
    _avisar(db, llamada)
    return estado(db, llamada)


# ── Cliente ──────────────────────────────────────────────────────────────────

def responder(db: Session, cliente, llamada: Llamada, acepta: bool, *, ip: Optional[str] = None,
              ua: Optional[str] = None, idioma: Optional[str] = None) -> dict:
    """El cliente da o niega su consentimiento a la propuesta en curso (evidencia completa)."""
    exigir_acceso_del_cliente(cliente, llamada)
    _, filas = _ronda_actual(db, llamada)
    mia = next((f for f in filas if f.client_user_id == cliente.id), None)
    if mia is None or mia.status != "pending" or not _abierta(filas) or not llamada.viva:
        raise error(409, "portal_grabacion_sin_propuesta")
    mia.status = "granted" if acepta else "denied"
    mia.decided_at = _ahora()
    mia.ip_address = (ip or "")[:64] or None
    mia.user_agent = (ua or "")[:400] or None
    mia.notice_lang = (idioma or "")[:10] or None
    _auditar(db, llamada, "consent_granted" if acepta else "consent_denied", cliente=cliente, ip=ip, ua=ua,
             datos={"round": mia.round, "purpose": mia.purpose, "notice_sha256": mia.notice_sha256,
                    "lang": mia.notice_lang})
    if not acepta:
        for f in filas:
            if f.status == "pending":
                f.status = "cancelled"
    elif all(f.status == "granted" for f in filas):
        _iniciar(db, llamada, filas)
    db.commit()
    _avisar(db, llamada)
    return estado(db, llamada, cliente=cliente)


def retirar(db: Session, cliente, llamada: Llamada, *, ip: Optional[str] = None, ua: Optional[str] = None) -> dict:
    """El cliente retira su consentimiento: la grabación se para en el acto."""
    exigir_acceso_del_cliente(cliente, llamada)
    _, filas = _ronda_actual(db, llamada)
    mia = next((f for f in filas if f.client_user_id == cliente.id), None)
    if mia is None or mia.status not in ("granted", "pending"):
        raise error(409, "portal_grabacion_sin_propuesta")
    estaba_grabando = _grabando(filas)
    mia.status = "withdrawn"
    mia.withdrawn_at = _ahora()
    _auditar(db, llamada, "consent_withdrawn", cliente=cliente, ip=ip, ua=ua, datos={"round": mia.round})
    if estaba_grabando:
        _parar(db, llamada, filas, motivo="consent_withdrawn")
    else:
        for f in filas:
            if f.status == "pending":
                f.status = "cancelled"
    db.commit()
    _avisar(db, llamada)
    return estado(db, llamada, cliente=cliente)


# ── Inicio y fin de la grabación ─────────────────────────────────────────────

def _iniciar(db: Session, llamada: Llamada, filas: list[PortalCallRecordingConsent]) -> None:
    ahora = _ahora()
    grabacion_id = None
    if llamada.canal == "colaboracion":
        from app.models.collaboration import CollaborationRecording
        from app.services.collaboration.calls import EXTENSION_DE_GRABACION, PROVEEDOR_DE_GRABACION
        rec = CollaborationRecording(
            organization_id=llamada.organization_id, call_id=llamada.id, storage_provider=PROVEEDOR_DE_GRABACION,
            storage_key=f"recordings/{llamada.id}-r{filas[0].round}.{EXTENSION_DE_GRABACION}",
            started_at=ahora, status="recording",
        )
        db.add(rec)
        db.flush()
        grabacion_id = rec.id
        llamada.obj.is_recorded = True
    for f in filas:
        f.recording_started_at = ahora
        f.recording_id = grabacion_id
    _auditar(db, llamada, "recording_started", datos={"round": filas[0].round, "recording_id": grabacion_id,
                                                       "purpose": filas[0].purpose})


def _parar(db: Session, llamada: Llamada, filas: list[PortalCallRecordingConsent], *, motivo: str,
           usuario=None) -> None:
    ahora = _ahora()
    for f in filas:
        if f.recording_started_at is not None and f.recording_ended_at is None:
            f.recording_ended_at = ahora
    rec_id = next((f.recording_id for f in filas if f.recording_id), None)
    if llamada.canal == "colaboracion":
        if rec_id:
            from app.models.collaboration import CollaborationRecording
            rec = db.get(CollaborationRecording, rec_id)
            if rec is not None and rec.ended_at is None:
                rec.ended_at = ahora
                rec.status = "ready"
                if rec.started_at is not None:
                    inicio = rec.started_at if rec.started_at.tzinfo else rec.started_at.replace(tzinfo=timezone.utc)
                    rec.duration_seconds = max(0, int((ahora - inicio).total_seconds()))
        # El asistente de reuniones, si grababa esta llamada, se para también.
        try:
            from app.services.reuniones import llamadas as asistente
            reunion = asistente.reunion_de(db, llamada.id)
            if reunion is not None and reunion.status == "grabando":
                asistente._terminar(db, reunion, usuario)
        except Exception:  # noqa: BLE001 - parar la grabación no depende del acta
            log.warning("grabación del portal: no se pudo cerrar el asistente de %s", llamada.id, exc_info=True)
    _auditar(db, llamada, "recording_stopped", usuario=usuario,
             datos={"round": filas[0].round, "reason": motivo, "recording_id": rec_id})


def al_terminar_llamada(db: Session, canal: str, call_id: str, organization_id: str) -> None:
    """Al colgar: se para lo que se grabe y se cancela lo pendiente. No confirma; nunca lanza."""
    try:
        llamada = cargar(db, canal, call_id, organization_id)
        _, filas = _ronda_actual(db, llamada)
        if _grabando(filas):
            _parar(db, llamada, filas, motivo="call_ended")
        else:
            for f in filas:
                if f.status == "pending":
                    f.status = "cancelled"
    except Exception:  # noqa: BLE001 - colgar no puede fallar por la grabación
        log.warning("grabación del portal: cierre al colgar %s/%s", canal, call_id, exc_info=True)


# ── Reglas para las otras vías (grabación del chat interno, subtítulos, asistente) ──

def exigir_consentimiento(db: Session, canal: str, call_id: str, organization_id: str, *,
                          transcripcion: bool = False) -> Optional[str]:
    """Con clientes en la llamada: empresa que lo permite y consentimiento de todos, grabando ahora.

    Devuelve el id de la `CollaborationRecording` de la ronda (canal colaboración)
    o `None` si la llamada no tiene clientes (la regla no aplica).
    """
    llamada = cargar(db, canal, call_id, organization_id)
    if not llamada.clientes:
        return None
    aj = _ajustes.leer(db, organization_id)
    if not (aj.llamadas and aj.grabacion):
        raise error(409, "portal_grabacion_desactivada")
    if transcripcion and not aj.transcripcion:
        raise error(409, "portal_transcripcion_desactivada")
    _, filas = _ronda_actual(db, llamada)
    if not _grabando(filas):
        raise error(409, "portal_grabacion_sin_consentimiento")
    if transcripcion and filas[0].purpose != "recording_transcript":
        raise error(409, "portal_grabacion_sin_consentimiento")
    return next((f.recording_id for f in filas if f.recording_id), "") or ""


# ── Descarga (solo personal autorizado de la misma empresa) ──────────────────

def descargar_transcripcion(db: Session, usuario, llamada: Llamada) -> tuple[bytes, str]:
    """La transcripción de una llamada grabada con consentimiento (texto). Auditada."""
    if not _filas(db, llamada):
        raise error(404, "no_encontrado", detail="Grabación no encontrada", que="grabacion")
    texto = ""
    if llamada.canal == "colaboracion":
        from app.models.collaboration import CollaborationTranscript
        t = db.query(CollaborationTranscript).filter(CollaborationTranscript.call_id == llamada.id,
                                                     CollaborationTranscript.organization_id == llamada.organization_id
                                                     ).first()
        texto = t.text if t is not None else ""
    if not texto:
        raise error(404, "no_encontrado", detail="Transcripción no encontrada", que="transcripcion")
    _auditar(db, llamada, "transcript_downloaded", usuario=usuario, datos={"bytes": len(texto.encode("utf-8"))})
    db.commit()
    return texto.encode("utf-8"), f"transcripcion-{llamada.id}.txt"


def evidencia(db: Session, usuario, llamada: Llamada) -> list[dict]:
    """Los consentimientos de la llamada (evidencia para el operador). Auditado como consulta."""
    filas = _filas(db, llamada)
    _auditar(db, llamada, "evidence_viewed", usuario=usuario, datos={"rows": len(filas)})
    db.commit()
    return [_fila(f) for f in filas]


def _fila(f: PortalCallRecordingConsent) -> dict:
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {"id": f.id, "channel": f.channel, "call_id": f.call_id, "conversation_id": f.conversation_id,
            "round": f.round, "client_user_id": f.client_user_id, "proposed_by_user_id": f.proposed_by_user_id,
            "proposed_at": iso(f.proposed_at), "purpose": f.purpose, "notice_text": f.notice_text,
            "notice_sha256": f.notice_sha256, "notice_lang": f.notice_lang, "status": f.status,
            "decided_at": iso(f.decided_at), "withdrawn_at": iso(f.withdrawn_at), "ip_address": f.ip_address,
            "user_agent": f.user_agent, "recording_started_at": iso(f.recording_started_at),
            "recording_ended_at": iso(f.recording_ended_at)}


# ── Retención (pasada diaria) ────────────────────────────────────────────────

def purgar_caducadas(db: Session, organization_id: str) -> dict:
    """Borra grabaciones, transcripciones y consentimientos vencidos que no estén bajo bloqueo legal.

    - grabaciones (`collaboration_recordings` de llamadas con consentimiento):
      `PORTAL_CHAT_RECORDING_RETENTION_DAYS` desde que acabaron;
    - transcripciones de esas llamadas: `PORTAL_CHAT_TRANSCRIPT_RETENTION_DAYS`;
    - consentimientos (evidencia): lo que dure la mayor de las dos.
    """
    from app.db.bloqueo_legal import _condicion_bloqueada, bloqueos_activos
    from app.models.collaboration import CollaborationRecording, CollaborationTranscript
    aj = _ajustes.leer(db, organization_id)
    ahora = _ahora()
    bloqueos = bloqueos_activos(db, organization_id)
    informe = {"recordings": 0, "transcripts": 0, "consents": 0}

    grabaciones = {r for (r,) in db.query(PortalCallRecordingConsent.recording_id).filter(
        PortalCallRecordingConsent.organization_id == organization_id,
        PortalCallRecordingConsent.recording_id.isnot(None)).distinct()}
    llamadas = {c for (c,) in db.query(PortalCallRecordingConsent.call_id).filter(
        PortalCallRecordingConsent.organization_id == organization_id,
        PortalCallRecordingConsent.channel == "colaboracion").distinct()}
    if grabaciones:
        q = db.query(CollaborationRecording).filter(
            CollaborationRecording.organization_id == organization_id,
            CollaborationRecording.id.in_(grabaciones),
            CollaborationRecording.ended_at.isnot(None),
            CollaborationRecording.ended_at < ahora - timedelta(days=aj.dias_grabaciones),
            ~_condicion_bloqueada("collaboration_recordings", CollaborationRecording, bloqueos))
        for r in q.all():
            db.delete(r)
            informe["recordings"] += 1
    if llamadas:
        q = db.query(CollaborationTranscript).filter(
            CollaborationTranscript.organization_id == organization_id,
            CollaborationTranscript.call_id.in_(llamadas),
            CollaborationTranscript.created_at < ahora - timedelta(days=aj.dias_transcripciones),
            ~_condicion_bloqueada("collaboration_transcripts", CollaborationTranscript, bloqueos))
        for t in q.all():
            db.delete(t)
            informe["transcripts"] += 1
    dias = max(aj.dias_grabaciones, aj.dias_transcripciones)
    M = PortalCallRecordingConsent
    q = db.query(M).filter(
        M.organization_id == organization_id,
        func.coalesce(M.recording_ended_at, M.withdrawn_at, M.decided_at, M.proposed_at) < ahora - timedelta(days=dias),
        M.status != "pending",
        ~_condicion_bloqueada("portal_call_recording_consents", M, bloqueos))
    for f in q.all():
        db.delete(f)
        informe["consents"] += 1
    if any(informe.values()):
        from app.services.audit import audit_log
        entrada = audit_log(db, None, "portal_recording.retention_purge", RECURSO, None, "retention",
                            metadata={"organization_id": organization_id, **informe, "active_holds": len(bloqueos)})
        entrada.organization_id = organization_id
    db.commit()
    return informe


# ── RGPD (copia y supresión del usuario del portal) ──────────────────────────

def copia_rgpd(db: Session, client_ids: list[str], org: str) -> dict:
    if not client_ids:
        return {"portal_call_recordings": {"consents": []}}
    filas = db.query(PortalCallRecordingConsent).filter(
        PortalCallRecordingConsent.organization_id == org,
        PortalCallRecordingConsent.client_user_id.in_(client_ids)).all()
    return {"portal_call_recordings": {"consents": [_fila(f) for f in filas]}}


def exigir_sin_bloqueo_legal_rgpd(db: Session, client_ids: list[str], org: str) -> None:
    """409 si algún consentimiento suyo (o la grabación/transcripción de esa llamada) está bajo bloqueo legal."""
    from app.db.bloqueo_legal import _condicion_bloqueada, bloqueos_activos
    from app.models.collaboration import CollaborationRecording, CollaborationTranscript
    if not client_ids:
        return
    bloqueos = bloqueos_activos(db, org)
    if not bloqueos:
        return
    M = PortalCallRecordingConsent
    base = db.query(M).filter(M.organization_id == org, M.client_user_id.in_(client_ids))
    if base.filter(_condicion_bloqueada("portal_call_recording_consents", M, bloqueos)).first() is not None:
        raise error(409, "bloqueo_legal_no_suprimible", casos="portal_call_recording_consents")
    grabaciones = [r for (r,) in base.with_entities(M.recording_id).filter(M.recording_id.isnot(None))]
    if grabaciones and db.query(CollaborationRecording).filter(
            CollaborationRecording.id.in_(grabaciones),
            _condicion_bloqueada("collaboration_recordings", CollaborationRecording, bloqueos)).first() is not None:
        raise error(409, "bloqueo_legal_no_suprimible", casos="collaboration_recordings")
    llamadas = [c for (c,) in base.with_entities(M.call_id).filter(M.channel == "colaboracion")]
    if llamadas and db.query(CollaborationTranscript).filter(
            CollaborationTranscript.call_id.in_(llamadas),
            _condicion_bloqueada("collaboration_transcripts", CollaborationTranscript, bloqueos)).first() is not None:
        raise error(409, "bloqueo_legal_no_suprimible", casos="collaboration_transcripts")


def suprimir_rgpd(db: Session, client_ids: list[str], org: str) -> dict:
    """Borra sus consentimientos y las grabaciones y transcripciones de las llamadas en que consintió.

    Comprueba antes el bloqueo legal (409). No hace commit (lo hace la solicitud RGPD).
    """
    from app.models.collaboration import CollaborationRecording, CollaborationTranscript
    if not client_ids:
        return {"consents": 0, "recordings": 0, "transcripts": 0}
    exigir_sin_bloqueo_legal_rgpd(db, client_ids, org)
    M = PortalCallRecordingConsent
    filas = db.query(M).filter(M.organization_id == org, M.client_user_id.in_(client_ids)).all()
    grabaciones = {f.recording_id for f in filas if f.recording_id}
    llamadas = {f.call_id for f in filas if f.channel == "colaboracion" and f.status in ("granted", "withdrawn")
                and f.recording_started_at is not None}
    n_grab = 0
    for r in db.query(CollaborationRecording).filter(CollaborationRecording.organization_id == org,
                                                     CollaborationRecording.id.in_(grabaciones or {""})).all():
        db.delete(r)
        n_grab += 1
    n_trans = 0
    for t in db.query(CollaborationTranscript).filter(CollaborationTranscript.organization_id == org,
                                                      CollaborationTranscript.call_id.in_(llamadas or {""})).all():
        db.delete(t)
        n_trans += 1
    for f in filas:
        db.delete(f)
    db.flush()
    return {"consents": len(filas), "recordings": n_grab, "transcripts": n_trans}
