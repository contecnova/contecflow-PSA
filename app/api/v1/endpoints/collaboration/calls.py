"""Voice/video calls — LiveKit autohosteado."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationCall, CollaborationCallParticipant,
    CollaborationConversation, CollaborationRecording, CollaborationTranscript,
)
from app.schemas.collaboration import CallStartIn, CallSummaryOut, CallTokenOut
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.collaboration.livekit import issue_access_token, url as lk_url

router = APIRouter()


def _room_name(call_id: str) -> str:
    return f"contec-{call_id}"


@router.post("/calls/start", response_model=CallTokenOut, summary="Iniciar llamada")
def start_call(payload: CallStartIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, payload.conversation_id)
    org = _org(current_user)
    call = CollaborationCall(
        organization_id=org,
        conversation_id=payload.conversation_id,
        initiated_by=current_user.id,
        kind=payload.kind,
        status="active",
        livekit_room="placeholder",
        started_at=datetime.utcnow(),
    )
    db.add(call)
    db.flush()
    call.livekit_room = _room_name(call.id)
    # Add initiator as host participant
    db.add(CollaborationCallParticipant(
        organization_id=org, call_id=call.id, user_id=current_user.id,
        joined_at=datetime.utcnow(), role="host",
    ))
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="call.started", entity_type="call", entity_id=call.id,
        payload={"conversation_id": payload.conversation_id, "kind": payload.kind},
    )
    db.commit()
    token = issue_access_token(
        room=call.livekit_room, identity=str(current_user.id),
        name=current_user.full_name or current_user.username or current_user.email,
    )
    return CallTokenOut(
        call_id=call.id, livekit_url=lk_url(),
        livekit_room=call.livekit_room, livekit_token=token,
        kind=call.kind, role="host",
    )


@router.post("/calls/{call_id}/join", response_model=CallTokenOut, summary="Unirse a llamada")
def join_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id, CollaborationCall.organization_id == org).first()
    if not call:
        raise HTTPException(404, "Llamada no encontrada")
    assert_conversation_access(db, current_user, call.conversation_id)
    # Track participant
    p = db.query(CollaborationCallParticipant).filter(
        CollaborationCallParticipant.call_id == call_id, CollaborationCallParticipant.user_id == current_user.id,
    ).first()
    if not p:
        db.add(CollaborationCallParticipant(
            organization_id=org, call_id=call_id, user_id=current_user.id,
            joined_at=datetime.utcnow(), role="participant",
        ))
        db.commit()
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="call.joined", entity_type="call", entity_id=call_id, payload={},
    )
    db.commit()
    token = issue_access_token(
        room=call.livekit_room, identity=str(current_user.id),
        name=current_user.full_name or current_user.username or current_user.email,
    )
    return CallTokenOut(
        call_id=call.id, livekit_url=lk_url(),
        livekit_room=call.livekit_room, livekit_token=token,
        kind=call.kind, role="participant",
    )


@router.post("/calls/{call_id}/leave", summary="Salir de llamada")
def leave_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(CollaborationCallParticipant).filter(
        CollaborationCallParticipant.call_id == call_id, CollaborationCallParticipant.user_id == current_user.id,
        CollaborationCallParticipant.left_at == None,
    ).first()
    if p:
        p.left_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.post("/calls/{call_id}/end", summary="Cerrar llamada")
def end_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id, CollaborationCall.organization_id == org).first()
    if not call:
        raise HTTPException(404, "Llamada no encontrada")
    if call.status == "ended":
        return {"ok": True}
    now = datetime.utcnow()
    call.status = "ended"
    call.ended_at = now
    if call.started_at:
        call.duration_seconds = int((now - call.started_at).total_seconds())
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="call.ended", entity_type="call", entity_id=call_id,
        payload={"duration_seconds": call.duration_seconds},
    )
    db.commit()
    # Trigger post-call summarization (Nexus IA) — async
    from app.services.collaboration._queue import task_queue
    from app.services.collaboration import bots as bot_svc
    task_queue.enqueue(bot_svc.summarize_call, call_id, org)
    return {"ok": True}


@router.post("/calls/{call_id}/recording/start", summary="Iniciar grabación")
def start_recording(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id, CollaborationCall.organization_id == org).first()
    if not call:
        raise HTTPException(404, "Llamada no encontrada")
    call.is_recorded = True
    rec = CollaborationRecording(
        organization_id=org, call_id=call_id,
        storage_provider="local",
        storage_key=f"recordings/{call_id}.webm",
        started_at=datetime.utcnow(),
        status="recording",
    )
    db.add(rec)
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="call.recording_started", entity_type="call", entity_id=call_id, payload={},
    )
    db.commit()
    return {"recording_id": rec.id}


@router.get("/calls/{call_id}", response_model=CallSummaryOut, summary="Resumen llamada")
def get_call(call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id, CollaborationCall.organization_id == org).first()
    if not call:
        raise HTTPException(404, "Llamada no encontrada")
    assert_conversation_access(db, current_user, call.conversation_id)
    transcript = db.query(CollaborationTranscript).filter(CollaborationTranscript.call_id == call_id).first()
    parts = db.query(CollaborationCallParticipant).filter(CollaborationCallParticipant.call_id == call_id).all()
    return CallSummaryOut(
        id=call.id, conversation_id=call.conversation_id, kind=call.kind, status=call.status,
        started_at=call.started_at, ended_at=call.ended_at, duration_seconds=call.duration_seconds,
        is_recorded=call.is_recorded, has_transcript=call.has_transcript, has_summary=call.has_summary,
        summary_text=transcript.summary if transcript else None,
        actions=transcript.actions_json if transcript else [],
        participants=[{"user_id": p.user_id, "client_user_id": p.client_user_id, "role": p.role,
                       "joined_at": p.joined_at, "left_at": p.left_at} for p in parts],
    )


@router.post("/calls/{call_id}/transcribe-chunk", summary="Subir chunk de audio para transcribir (Whisper)")
async def transcribe_chunk(
    call_id: str,
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _org(current_user)
    call = db.query(CollaborationCall).filter(CollaborationCall.id == call_id, CollaborationCall.organization_id == org).first()
    if not call:
        raise HTTPException(404, "Llamada no encontrada")
    assert_conversation_access(db, current_user, call.conversation_id)
    data = await audio.read()
    from app.services.collaboration._transcription import transcribe_audio_chunk
    text = transcribe_audio_chunk(data, audio.filename or "chunk.webm")
    if text:
        # Append a transcript segment row
        from app.models.collaboration import CollaborationTranscript
        existing = db.query(CollaborationTranscript).filter(CollaborationTranscript.call_id == call_id).first()
        if existing:
            existing.text = (existing.text or "") + "\n" + text
            seg = list(existing.segments_json or [])
            seg.append({"speaker": current_user.id, "text": text, "ts": datetime.utcnow().isoformat()})
            existing.segments_json = seg
        else:
            db.add(CollaborationTranscript(
                organization_id=org, call_id=call_id, language="es",
                text=text, segments_json=[{"speaker": current_user.id, "text": text, "ts": datetime.utcnow().isoformat()}],
            ))
            call.has_transcript = True
        db.commit()
    return {"text": text or ""}


@router.get("/conversations/{conversation_id}/calls", response_model=List[CallSummaryOut], summary="Historial de llamadas")
def list_calls(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_conversation_access(db, current_user, conversation_id)
    rows = db.query(CollaborationCall).filter(CollaborationCall.conversation_id == conversation_id).order_by(CollaborationCall.started_at.desc()).limit(50).all()
    return [CallSummaryOut(
        id=c.id, conversation_id=c.conversation_id, kind=c.kind, status=c.status,
        started_at=c.started_at, ended_at=c.ended_at, duration_seconds=c.duration_seconds,
        is_recorded=c.is_recorded, has_transcript=c.has_transcript, has_summary=c.has_summary,
    ) for c in rows]
