"""
voice_agent.py — IVR / Voice Agent endpoints for Service Desk.

Routes:
  GET  /sd/voice/config                         — IVR configuration
  PUT  /sd/voice/config                         — update IVR configuration
  POST /sd/voice/sessions                       — create a new voice session
  GET  /sd/voice/sessions                       — list voice sessions
  GET  /sd/voice/sessions/{session_id}          — get single session
  POST /sd/voice/sessions/{session_id}/turn     — add transcript turn + classify intent
  POST /sd/voice/sessions/{session_id}/close    — close session
  POST /sd/voice/sessions/{session_id}/ticket   — create ticket from session
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.voice_agent_service import (
    get_config,
    update_config,
    create_session,
    add_transcript_turn,
    close_session,
    create_ticket_from_session,
    list_sessions,
)

router = APIRouter(prefix="/sd/voice", tags=["Service Desk - Voice Agent IVR"])


class ConfigUpdate(BaseModel):
    greeting: Optional[str] = None
    language: Optional[str] = None
    max_silence_seconds: Optional[int] = None
    dtmf_menu: Optional[dict] = None
    intent_keywords: Optional[dict] = None


class SessionCreate(BaseModel):
    caller_id: str = Field(..., description="Phone number or caller identifier")
    channel: str = Field("phone", description="phone | sip | web")


class TranscriptTurn(BaseModel):
    speaker: str = Field(..., description="user | bot | agent")
    text: str = Field(..., min_length=1)


class CloseSession(BaseModel):
    resolution: str = Field("resolved", description="resolved | transferred | abandoned | voicemail")


@router.get("/config", summary="Obtener configuración del agente de voz IVR")
@limiter.limit("60/minute")
def get_ivr_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_config(db, str(org_id) if org_id else None)


@router.put("/config", summary="Actualizar configuración del agente de voz")
@limiter.limit("20/minute")
def update_ivr_config(
    request: Request,
    body: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    updates = body.model_dump(exclude_none=True)
    return update_config(db, str(org_id) if org_id else None, updates)


@router.post("/sessions", summary="Crear nueva sesión de llamada de voz", status_code=201)
@limiter.limit("60/minute")
def start_voice_session(
    request: Request,
    body: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return create_session(db, str(org_id) if org_id else None, body.caller_id, body.channel)


@router.get("/sessions", summary="Listar sesiones de voz")
@limiter.limit("60/minute")
def get_voice_sessions(
    request: Request,
    status: Optional[str] = Query(None, description="active | closed"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = list_sessions(db, str(org_id) if org_id else None, status=status, limit=limit)
    return {"sessions": items, "count": len(items)}


@router.get("/sessions/{session_id}", summary="Detalle de sesión de voz")
@limiter.limit("60/minute")
def get_voice_session(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi import HTTPException
    org_id = getattr(current_user, "organization_id", None)
    sessions_svc = list_sessions(db, str(org_id) if org_id else None, limit=10000)
    session = next((s for s in sessions_svc if s["id"] == session_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/turn", summary="Añadir turno de transcripción + clasificar intención")
@limiter.limit("120/minute")
def add_turn(
    request: Request,
    session_id: str,
    body: TranscriptTurn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return add_transcript_turn(db, str(org_id) if org_id else None, session_id, body.speaker, body.text)


@router.post("/sessions/{session_id}/close", summary="Cerrar sesión de voz")
@limiter.limit("30/minute")
def end_session(
    request: Request,
    session_id: str,
    body: CloseSession,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return close_session(db, str(org_id) if org_id else None, session_id, body.resolution)


@router.post("/sessions/{session_id}/ticket", summary="Crear ticket desde sesión de voz", status_code=201)
@limiter.limit("20/minute")
def create_ticket(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return create_ticket_from_session(db, str(org_id) if org_id else None, session_id, current_user.id)
