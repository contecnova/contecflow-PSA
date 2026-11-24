"""Voice/video calls — LiveKit autohosteado.

Auditoria 2026-08 (hallazgo 22). Los 18 puntos de acceso a base de este fichero
estan en `app/services/collaboration/calls.py`, junto con los tres valores que
estaban en duro —los dos topes de frecuencia y el del historial, ahora ajustes
declarados— y el idioma de la transcripcion, que ahora sale de
`DEFAULT_LANGUAGE` en vez de un `"es"` fijo.
"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.core.uploads import read_upload_within_limit_sync, validate_audio_upload, safe_filename
from app.db.session import get_db
from app.models.user import User
from app.schemas.collaboration import CallStartIn, CallSummaryOut, CallTokenOut
from app.services.collaboration import calls as svc
from app.services.reuniones.transaccion import confirmar
from app.services.collaboration._permissions import _org
from app.services.collaboration.livekit import issue_access_token, url as lk_url

router = APIRouter()


def _token_de(call, user, *, role: str) -> CallTokenOut:
    """El token de LiveKit de esa llamada para ese usuario."""
    datos = svc.datos_de_token(call, user, role=role)
    return CallTokenOut(
        call_id=call.id, livekit_url=lk_url(),
        livekit_room=datos["room"],
        livekit_token=issue_access_token(
            room=datos["room"], identity=datos["identity"], name=datos["name"]),
        kind=call.kind, role=role,
    )


@router.post("/calls/start", response_model=APIResponse[CallTokenOut], summary="Iniciar llamada")
def start_call(payload: CallStartIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("colaboracion.usar")),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    call = svc.start_call(
        db, current_user,
        conversation_id=payload.conversation_id, kind=payload.kind,
    )
    return APIResponse.ok(data=_token_de(call, current_user, role="host"))


@router.post("/calls/{call_id}/join", response_model=APIResponse[CallTokenOut], summary="Unirse a llamada")
def join_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    call = svc.join_call(db, current_user, call_id)
    # 19-11-2026: con el asistente de reuniones grabando, quien entra pasa a ser
    # participante de la reunión (su consentimiento queda pendiente).
    from app.services.reuniones import llamadas as asistente
    asistente.al_unirse(db, current_user, call_id)
    confirmar(db)
    return APIResponse.ok(data=_token_de(call, current_user, role="participant"))


@router.post("/calls/{call_id}/leave", summary="Salir de llamada")
def leave_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.leave_call(db, current_user, call_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/calls/{call_id}/end", summary="Cerrar llamada")
def end_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("colaboracion.usar")),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    recien_cerrada = svc.end_call(db, current_user, call_id)
    if recien_cerrada:
        # El resumen post-llamada (Nexus IA) se encola solo la primera vez: dos
        # participantes que cuelgan a la vez no deben generar dos resumenes.
        from app.services.collaboration import bots as bot_svc
        from app.services.collaboration._queue import task_queue
        task_queue.enqueue(bot_svc.summarize_call, call_id, _org(current_user))
        # 19-11-2026: si el asistente de reuniones grababa, se analiza, se hace
        # el acta y se publica el enlace en la conversación.
        from app.services.reuniones import llamadas as asistente
        if asistente.reunion_de(db, call_id) is not None:
            task_queue.enqueue(asistente.cerrar, call_id, _org(current_user))
    return APIResponse.ok(data={"ok": True})


@router.post("/calls/{call_id}/recording/start", summary="Iniciar grabación")
def start_recording(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("colaboracion.usar")),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    return APIResponse.ok(
        data={"recording_id": svc.start_recording(db, current_user, call_id)})


@router.get("/calls/{call_id}", response_model=APIResponse[CallSummaryOut], summary="Resumen llamada")
def get_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(
        data=CallSummaryOut(**svc.call_summary(db, current_user, call_id)))


@router.post("/calls/{call_id}/transcribe-chunk", summary="Subir chunk de audio para transcribir (Whisper)")
def transcribe_chunk(
    call_id: str,
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("colaboracion.usar")),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    # La llamada se comprueba ANTES de leer el fichero: no tiene sentido
    # descargar audio de una llamada a la que no se tiene acceso.
    svc.exigir_llamada_accesible(db, current_user, call_id)
    # 24-11-2026 (migración 214): con clientes del portal solo se transcribe si la empresa
    # lo permite y han consentido grabar y transcribir (docs/portal/CHAT_DEL_PORTAL.md §11).
    from app.services.collaboration import portal_chat
    portal_chat.exigir_grabacion_consentida(db, call_id, transcripcion=True)
    # Auditoria 2026-11: `def` (threadpool). La transcripcion es un POST de
    # hasta 30 s o un subproceso de whisper: en `async def` paraba el bucle.
    datos = read_upload_within_limit_sync(audio, 25 * 1024 * 1024)
    validate_audio_upload(audio.filename or "", datos)

    # 19-11-2026: con el asistente de reuniones grabando, el audio solo va a los
    # proveedores de voz que la empresa permite para reuniones (externos solo
    # con activación y contrato) y nada de quien dijo «no».
    from app.services.reuniones import llamadas as asistente
    texto = asistente.transcribir_si_graba(db, current_user, call_id, datos, audio.filename or "chunk.webm",
                                           audio.content_type or "audio/webm")
    if texto is None:
        from app.services.collaboration._transcription import transcribe_audio_chunk
        texto = transcribe_audio_chunk(datos, audio.filename or "chunk.webm", db=db,
                                       org_id=getattr(current_user, "organization_id", None),
                                       user_id=current_user.id)
    if texto:
        svc.append_transcript_segment(db, current_user, call_id, texto)
        # 19-11-2026: los mismos subtítulos alimentan al asistente de reuniones si
        # está grabando (hablante = quien sube su propio audio; respeta su «no»).
        if asistente.registrar_fragmento(db, current_user, call_id, texto, datos,
                                         audio.content_type or "audio/webm"):
            confirmar(db)
    return {"text": texto or ""}


@router.get("/conversations/{conversation_id}/calls", response_model=APIListResponse[CallSummaryOut], summary="Historial de llamadas")
def list_calls(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        CallSummaryOut(**svc.resumen_de_llamada_para_lista(c))
        for c in svc.list_calls(db, current_user, conversation_id)
    ]
    return APIListResponse.ok(items=items, total=len(items))
