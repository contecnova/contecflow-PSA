"""Llamadas de voz y vídeo: sesión, participantes, grabación y transcripción.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration/calls.py` con **18 puntos de acceso directo a base**.
Al moverlas se corrigieron además tres cosas que la regla de «no hardcodear
nada» no permite dejar:

  · los dos topes de frecuencia —8 llamadas iniciadas y 20 uniones por minuto—
    estaban escritos en el endpoint. Son valores de operación: quien despliega
    tiene que poder subirlos para un cliente con muchos usuarios sin tocar
    codigo. Ahora son `COLLAB_CALL_START_PER_MIN` y `COLLAB_CALL_JOIN_PER_MIN`;
  · el idioma de la transcripcion estaba fijo en `"es"`, y hay un
    `DEFAULT_LANGUAGE` en la configuracion desde siempre. Un tenant en otro
    idioma recibia sus transcripciones etiquetadas como españolas;
  · el tope del historial de llamadas de una conversacion estaba en 50.

Y un `db.commit()` de mas: `join_call` confirmaba dos veces —una tras crear el
participante y otra tras el registro de auditoria—. La primera era redundante y
partia en dos una operacion que es una.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationCall,
    CollaborationCallParticipant,
    CollaborationRecording,
    CollaborationTranscript,
)
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.traffic_control_service import consume_quota
from app.core.errores import ErrorDeDominio

#: Ventana de los topes de frecuencia, en segundos. Un minuto: es la unidad en
#: la que estan expresados los dos limites.
VENTANA_DE_CUOTA_SEGUNDOS = 60

#: Proveedor y extension de las grabaciones. Es la implementacion local que hay
#: hoy —el fichero se guarda junto a la aplicacion— y se deja con nombre para
#: que quien enchufe almacenamiento remoto sepa que hay que cambiar aqui.
PROVEEDOR_DE_GRABACION = "local"
EXTENSION_DE_GRABACION = "webm"


def _prefijo_de_sala(call_id: str) -> str:
    """El nombre de la sala en LiveKit.

    Lleva prefijo de producto porque una instancia de LiveKit puede servir a
    varias aplicaciones y los nombres de sala son un espacio plano.
    """
    return f"contec-{call_id}"


def _exigir_cuota(db: Session, org: str, user_id: str, *, ambito: str,
                  limite: int, accion: str) -> None:
    cuota = consume_quota(
        db, scope=ambito, tenant_id=org, subject=user_id,
        limit=limite, window_seconds=VENTANA_DE_CUOTA_SEGUNDOS,
    )
    if not cuota["allowed"]:
        raise ErrorDeDominio(
            status_code=429,
            detail=f"Call {accion} rate limit exceeded. "
                   f"Retry in {cuota['retry_after']}s",
        )


def _llamada_de_la_org(db: Session, call_id: str, org: str) -> CollaborationCall:
    call = (
        db.query(CollaborationCall)
        .filter(
            CollaborationCall.id == call_id,
            CollaborationCall.organization_id == org,
        )
        .first()
    )
    if not call:
        raise ErrorDeDominio(404, "Llamada no encontrada")
    return call


def start_call(db: Session, user, *, conversation_id: str, kind: str) -> CollaborationCall:
    """Abre una llamada en una conversación y mete a quien la inicia como anfitrión."""
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    _exigir_cuota(
        db, org, user.id, ambito="collab.call.start.user",
        limite=settings.COLLAB_CALL_START_PER_MIN, accion="start",
    )

    call = CollaborationCall(
        organization_id=org, conversation_id=conversation_id,
        initiated_by=user.id, kind=kind, status="active",
        # El nombre de sala se deriva del id, que no existe hasta el `flush`.
        # Se pone un valor de paso porque la columna no admite nulos.
        livekit_room="placeholder",
        started_at=utcnow(),
    )
    db.add(call)
    db.flush()
    call.livekit_room = _prefijo_de_sala(call.id)

    db.add(CollaborationCallParticipant(
        organization_id=org, call_id=call.id, user_id=user.id,
        joined_at=utcnow(), role="host",
    ))
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="call.started", entity_type="call", entity_id=call.id,
        payload={"conversation_id": conversation_id, "kind": kind},
    )
    db.commit()
    return call


def join_call(db: Session, user, call_id: str) -> CollaborationCall:
    """Une a alguien a una llamada, registrandolo si es su primera vez.

    Un solo `commit` al final: el endpoint confirmaba dos veces —tras crear el
    participante y tras el registro de auditoria— y eso partia en dos una
    operacion que es una sola.
    """
    org = _org(user)
    _exigir_cuota(
        db, org, user.id, ambito="collab.call.join.user",
        limite=settings.COLLAB_CALL_JOIN_PER_MIN, accion="join",
    )

    call = _llamada_de_la_org(db, call_id, org)
    assert_conversation_access(db, user, call.conversation_id)

    ya_estaba = (
        db.query(CollaborationCallParticipant)
        .filter(
            CollaborationCallParticipant.call_id == call_id,
            CollaborationCallParticipant.user_id == user.id,
        )
        .first()
    )
    if not ya_estaba:
        db.add(CollaborationCallParticipant(
            organization_id=org, call_id=call_id, user_id=user.id,
            joined_at=utcnow(), role="participant",
        ))
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="call.joined", entity_type="call", entity_id=call_id, payload={},
    )
    db.commit()
    return call


def leave_call(db: Session, user, call_id: str) -> None:
    """Marca la salida de la llamada.

    Sólo toca la participación que sigue abierta (`left_at` a nulo): quien entra
    y sale dos veces tiene dos filas, y marcar una cerrada otra vez perdería
    cuándo salió de verdad.
    """
    p = (
        db.query(CollaborationCallParticipant)
        .filter(
            CollaborationCallParticipant.call_id == call_id,
            CollaborationCallParticipant.user_id == user.id,
            CollaborationCallParticipant.left_at == None,  # noqa: E711
        )
        .first()
    )
    if p:
        p.left_at = utcnow()
        db.commit()


def end_call(db: Session, user, call_id: str) -> bool:
    """Cierra la llamada y calcula su duración.

    Devuelve si **esta** llamada la ha cerrado: cerrar una llamada ya cerrada no
    es un error —dos participantes pueden colgar a la vez— pero tampoco debe
    recalcular la duración ni volver a encolar el resumen.
    """
    org = _org(user)
    call = _llamada_de_la_org(db, call_id, org)
    if call.status == "ended":
        return False

    ahora = utcnow()
    call.status = "ended"
    call.ended_at = ahora
    if call.started_at:
        call.duration_seconds = int((ahora - call.started_at).total_seconds())
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="call.ended", entity_type="call", entity_id=call_id,
        payload={"duration_seconds": call.duration_seconds},
    )
    db.commit()
    return True


def start_recording(db: Session, user, call_id: str) -> str:
    """Marca la llamada como grabada y crea la fila de la grabación."""
    org = _org(user)
    call = _llamada_de_la_org(db, call_id, org)
    call.is_recorded = True
    rec = CollaborationRecording(
        organization_id=org, call_id=call_id,
        storage_provider=PROVEEDOR_DE_GRABACION,
        storage_key=f"recordings/{call_id}.{EXTENSION_DE_GRABACION}",
        started_at=utcnow(), status="recording",
    )
    db.add(rec)
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="call.recording_started", entity_type="call", entity_id=call_id,
        payload={},
    )
    db.commit()
    return rec.id


def call_summary(db: Session, user, call_id: str) -> dict:
    """El resumen de una llamada con su transcripción y sus participantes."""
    org = _org(user)
    call = _llamada_de_la_org(db, call_id, org)
    assert_conversation_access(db, user, call.conversation_id)
    transcripcion = (
        db.query(CollaborationTranscript)
        .filter(CollaborationTranscript.call_id == call_id)
        .first()
    )
    participantes = (
        db.query(CollaborationCallParticipant)
        .filter(CollaborationCallParticipant.call_id == call_id)
        .all()
    )
    return {
        "id": call.id, "conversation_id": call.conversation_id,
        "kind": call.kind, "status": call.status,
        "started_at": call.started_at, "ended_at": call.ended_at,
        "duration_seconds": call.duration_seconds,
        "is_recorded": call.is_recorded, "has_transcript": call.has_transcript,
        "has_summary": call.has_summary,
        "summary_text": transcripcion.summary if transcripcion else None,
        "actions": transcripcion.actions_json if transcripcion else [],
        "participants": [
            {
                "user_id": p.user_id, "client_user_id": p.client_user_id,
                "role": p.role, "joined_at": p.joined_at, "left_at": p.left_at,
            }
            for p in participantes
        ],
    }


def exigir_llamada_accesible(db: Session, user, call_id: str) -> CollaborationCall:
    """La llamada, comprobando acceso a su conversación. Para el endpoint de
    subida de audio, que necesita la llamada antes de leer el fichero."""
    call = _llamada_de_la_org(db, call_id, _org(user))
    assert_conversation_access(db, user, call.conversation_id)
    return call


def append_transcript_segment(
    db: Session, user, call_id: str, texto: str,
) -> None:
    """Añade un fragmento a la transcripción de la llamada.

    El idioma es el del usuario (o el de su organización; ver
    `formato_regional.idioma`), no un `"es"` fijo: un tenant que
    trabaja en otro idioma recibia sus transcripciones etiquetadas como
    españolas, y la etiqueta es lo que usa después el resumen automático.
    """
    from app.services.formato_regional import idioma
    org = _org(user)
    call = _llamada_de_la_org(db, call_id, org)
    fragmento = {
        "speaker": user.id, "text": texto, "ts": utcnow().isoformat(),
    }
    existente = (
        db.query(CollaborationTranscript)
        .filter(CollaborationTranscript.call_id == call_id)
        .first()
    )
    if existente:
        existente.text = (existente.text or "") + "\n" + texto
        # Se reasigna la lista entera en vez de mutarla: una columna JSON no
        # detecta el cambio si se le hace `append` en sitio.
        existente.segments_json = list(existente.segments_json or []) + [fragmento]
    else:
        db.add(CollaborationTranscript(
            organization_id=org, call_id=call_id,
            language=idioma(db, user_id=getattr(user, "id", None), org_id=org),
            text=texto, segments_json=[fragmento],
        ))
        call.has_transcript = True
    db.commit()


def list_calls(db: Session, user, conversation_id: str) -> list[CollaborationCall]:
    """El historial de llamadas de una conversación, de la más reciente."""
    assert_conversation_access(db, user, conversation_id)
    return (
        db.query(CollaborationCall)
        .filter(CollaborationCall.conversation_id == conversation_id)
        .order_by(CollaborationCall.started_at.desc())
        .limit(settings.COLLAB_CALL_HISTORY_LIMIT)
        .all()
    )


def resumen_de_llamada_para_lista(c: CollaborationCall) -> dict:
    """Los campos del historial. Va aparte porque el listado no trae ni
    transcripción ni participantes: pedirlos por llamada seria un N+1."""
    return {
        "id": c.id, "conversation_id": c.conversation_id, "kind": c.kind,
        "status": c.status, "started_at": c.started_at, "ended_at": c.ended_at,
        "duration_seconds": c.duration_seconds, "is_recorded": c.is_recorded,
        "has_transcript": c.has_transcript, "has_summary": c.has_summary,
    }


def datos_de_token(call: CollaborationCall, user, *, role: str) -> dict:
    """Lo que necesita el endpoint para emitir el token de LiveKit.

    El nombre que se manda a LiveKit cae del nombre completo al usuario y al
    correo: es lo que se muestra en la sala, y sin ninguno de los tres la
    persona aparece sin identificar.
    """
    return {
        "room": call.livekit_room,
        "identity": str(user.id),
        "name": user.full_name or user.username or user.email,
        "call": call,
        "role": role,
    }
