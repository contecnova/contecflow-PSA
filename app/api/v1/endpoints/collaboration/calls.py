"""Voice/video calls — LiveKit autohosteado.

Auditoria 2026-08 (hallazgo 22). Los 18 puntos de acceso a base de este fichero
estan en `app/services/collaboration/calls.py`, junto con los tres valores que
estaban en duro —los dos topes de frecuencia y el del historial, ahora ajustes
declarados— y el idioma de la transcripcion, que ahora sale de
`DEFAULT_LANGUAGE` en vez de un `"es"` fijo.
"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.schemas.collaboration import CallStartIn, CallSummaryOut, CallTokenOut
from app.services.collaboration import calls as svc
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
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    call = svc.start_call(
        db, current_user,
        conversation_id=payload.conversation_id, kind=payload.kind,
    )
    return APIResponse.ok(data=_token_de(call, current_user, role="host"))


@router.post("/calls/{call_id}/join", response_model=APIResponse[CallTokenOut], summary="Unirse a llamada")
def join_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    call = svc.join_call(db, current_user, call_id)
    return APIResponse.ok(data=_token_de(call, current_user, role="participant"))


@router.post("/calls/{call_id}/leave", summary="Salir de llamada")
def leave_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.leave_call(db, current_user, call_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/calls/{call_id}/end", summary="Cerrar llamada")
def end_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    recien_cerrada = svc.end_call(db, current_user, call_id)
    if recien_cerrada:
        # El resumen post-llamada (Nexus IA) se encola solo la primera vez: dos
        # participantes que cuelgan a la vez no deben generar dos resumenes.
        from app.services.collaboration import bots as bot_svc
        from app.services.collaboration._queue import task_queue
        task_queue.enqueue(bot_svc.summarize_call, call_id, _org(current_user))
    return APIResponse.ok(data={"ok": True})


@router.post("/calls/{call_id}/recording/start", summary="Iniciar grabación")
def start_recording(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    return APIResponse.ok(
        data={"recording_id": svc.start_recording(db, current_user, call_id)})


@router.get("/calls/{call_id}", response_model=APIResponse[CallSummaryOut], summary="Resumen llamada")
def get_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(
        data=CallSummaryOut(**svc.call_summary(db, current_user, call_id)))


@router.post("/calls/{call_id}/transcribe-chunk", summary="Subir chunk de audio para transcribir (Whisper)")
async def transcribe_chunk(
    call_id: str,
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: trabajo interno diario; lo que hay que excluir es al subcontratado
):
    # La llamada se comprueba ANTES de leer el fichero: no tiene sentido
    # descargar audio de una llamada a la que no se tiene acceso.
    svc.exigir_llamada_accesible(db, current_user, call_id)
    datos = await audio.read()

    from app.services.collaboration._transcription import transcribe_audio_chunk
    texto = transcribe_audio_chunk(datos, audio.filename or "chunk.webm", db=db,
                                   org_id=getattr(current_user, "organization_id", None))
    if texto:
        svc.append_transcript_segment(db, current_user, call_id, texto)
    return {"text": texto or ""}


@router.get("/conversations/{conversation_id}/calls", response_model=APIListResponse[CallSummaryOut], summary="Historial de llamadas")
def list_calls(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        CallSummaryOut(**svc.resumen_de_llamada_para_lista(c))
        for c in svc.list_calls(db, current_user, conversation_id)
    ]
    return APIListResponse.ok(items=items, total=len(items))
