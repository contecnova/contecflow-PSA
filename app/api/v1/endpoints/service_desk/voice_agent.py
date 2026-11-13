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

from app.core.deps import get_current_user, require_admin
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
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
from app.core.config import settings
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter(prefix="/voice", tags=["Service Desk - Voice Agent IVR"])


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
    return APIResponse.ok(data=get_config(db, str(org_id) if org_id else None))


@router.put("/config", summary="Actualizar configuración del agente de voz")
@limiter.limit("20/minute")
def update_ivr_config(
    request: Request,
    body: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: configuracion: la forma de la ruta manda sobre el fichero
):
    org_id = getattr(current_user, "organization_id", None)
    updates = body.model_dump(exclude_none=True)
    return APIResponse.ok(data=update_config(db, str(org_id) if org_id else None, updates))


@router.post("/sessions", summary="Crear nueva sesión de llamada de voz", status_code=201)
@limiter.limit("60/minute")
def start_voice_session(
    request: Request,
    body: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: configuracion del agente de voz
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=create_session(db, str(org_id) if org_id else None, body.caller_id, body.channel))


@router.get("/sessions", summary="Listar sesiones de voz")
@limiter.limit("60/minute")
def get_voice_sessions(
    request: Request,
    status: Optional[str] = Query(None, description="active | closed"),
    limit: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = list_sessions(db, str(org_id) if org_id else None, status=status, limit=limit)
    return APIResponse.ok(data={"sessions": items, "count": len(items)})


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
    return APIResponse.ok(data=session)


@router.post("/sessions/{session_id}/turn", summary="Añadir turno de transcripción + clasificar intención")
@limiter.limit("120/minute")
def add_turn(
    request: Request,
    session_id: str,
    body: TranscriptTurn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: configuracion del agente de voz
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=add_transcript_turn(db, str(org_id) if org_id else None, session_id, body.speaker, body.text))


@router.post("/sessions/{session_id}/close", summary="Cerrar sesión de voz")
@limiter.limit("30/minute")
def end_session(
    request: Request,
    session_id: str,
    body: CloseSession,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: configuracion del agente de voz
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=close_session(db, str(org_id) if org_id else None, session_id, body.resolution))


@router.post("/sessions/{session_id}/ticket", summary="Crear ticket desde sesión de voz", status_code=201)
@limiter.limit("20/minute")
def create_ticket(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: configuracion del agente de voz
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=create_ticket_from_session(db, str(org_id) if org_id else None, session_id, current_user.id))


# ── Twilio Webhook (no auth — validated by Twilio signature) ──────────────────

def _rechazo_si_no_es_twilio(request: Request, form: dict):
    """Respuesta 403 en TwiML si la peticion no trae una firma de Twilio valida.

    Segunda auditoria 2026-11 (#9): la voz es MONO-ORGANIZACION por diseno —se
    verifica solo con el `TWILIO_AUTH_TOKEN` global y la sesion se crea sin
    organizacion—. El token por organizacion vale solo para el SMS entrante.
    """
    from fastapi import Response

    from app.services.service_desk.sms_service import validate_twilio_signature

    if validate_twilio_signature(str(request.url), form, request.headers.get("X-Twilio-Signature")):
        return None
    return Response(
        content='<?xml version="1.0"?><Response><Reject /></Response>',
        media_type="application/xml",
        status_code=403,
    )


@router.post(
    "/webhook/twilio",
    summary="Twilio IVR webhook — recibe llamadas y responde con TwiML",
    include_in_schema=False,
)
@limiter.limit("120/minute")
async def twilio_ivr_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Twilio calls this endpoint when a call is received.
    Validates the Twilio signature (X-Twilio-Signature header) and responds with TwiML.
    Creates a voice session for tracking.

    Production usage:
      1. Configure Twilio phone number webhook URL to point here.
      2. Set TWILIO_AUTH_TOKEN env var for signature validation.
      3. Optionally set TWILIO_ACCOUNT_SID for outbound calls.
    """
    from app.services.service_desk.voice_agent_service import get_config

    # ── Twilio signature validation ───────────────────────────────────────────
    # Auditoria 2026-11: solo se comprobaba si habia TWILIO_AUTH_TOKEN en el
    # entorno (fallaba abierta). Ahora usa el validador comun, que rechaza sin
    # token o sin firma.
    form_body = await request.form()
    rechazo = _rechazo_si_no_es_twilio(request, dict(form_body))
    if rechazo is not None:
        return rechazo

    # Audit #C7: async is needed for await request.form(); DB ops are
    # offloaded to the threadpool via run_db so the sync ORM never blocks
    # the event loop while Twilio waits for TwiML.
    from app.core.async_db import run_db

    # ── Parse Twilio form data ────────────────────────────────────────────────
    form_data = dict(form_body)
    caller_id = form_data.get("From", "unknown")
    call_sid  = form_data.get("CallSid", "")
    org_id    = None  # Mono-organización por diseño (segunda auditoría 2026-11, #9)

    # Create a tracking session
    session = await run_db(create_session, db, org_id, caller_id, channel="phone")
    await run_db(add_transcript_turn, db, org_id, session["id"], "bot", f"Incoming call from {caller_id} (SID: {call_sid})")

    # ── Load greeting from config ─────────────────────────────────────────────
    cfg = await run_db(get_config, db, org_id)
    greeting = cfg.get("greeting", "Gracias por llamar. ¿En qué le podemos ayudar?")
    language  = cfg.get("language", settings.DEFAULT_LANGUAGE)
    dtmf_menu = cfg.get("dtmf_menu", {})

    # ── Build TwiML response ──────────────────────────────────────────────────
    gather_verbs = "\n".join(
        f'<Say language="{language}">{item.get("label", key)}</Say>'
        for key, item in sorted((dtmf_menu or {}).items())
    )

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="{language}">{greeting}</Say>
  <Gather numDigits="1" action="/api/v1/sd/voice/webhook/twilio/gather?session_id={session['id']}" method="POST" timeout="5">
    {gather_verbs}
  </Gather>
  <Say language="{language}">No hemos recibido ninguna selección. Le transferimos con un agente.</Say>
  <Dial><Queue>general</Queue></Dial>
</Response>"""

    from fastapi import Response
    return Response(content=twiml, media_type="application/xml")


@router.post(
    "/webhook/twilio/gather",
    summary="Twilio IVR gather callback — procesa selección DTMF",
    include_in_schema=False,
)
@limiter.limit("120/minute")
async def twilio_gather_webhook(
    request: Request,
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Processes DTMF digit selection from a Twilio <Gather> verb."""
    from app.services.service_desk.voice_agent_service import get_config

    # Audit #C7: see twilio_ivr_webhook above for the same pattern.
    from app.core.async_db import run_db

    form_data = dict(await request.form())
    # Auditoria 2026-11: este callback no tenia ninguna autenticacion y escribia
    # en la transcripcion de cualquier `session_id`.
    rechazo = _rechazo_si_no_es_twilio(request, form_data)
    if rechazo is not None:
        return rechazo
    digit     = form_data.get("Digits", "")
    org_id    = None

    cfg = await run_db(get_config, db, org_id)
    dtmf_menu = cfg.get("dtmf_menu", {})
    language  = cfg.get("language", settings.DEFAULT_LANGUAGE)

    selected_option = (dtmf_menu or {}).get(digit, {})
    selected_label = selected_option.get("label", "") if isinstance(selected_option, dict) else str(selected_option)
    selected_queue = selected_option.get("intent", "general") if isinstance(selected_option, dict) else (selected_option or "general")

    if session_id:
        await run_db(add_transcript_turn, db, org_id, session_id, "user", f"DTMF selection: {digit} → {selected_label or selected_queue}")

    if digit and (selected_label or selected_queue):
        message = f"Ha seleccionado: {selected_label or selected_queue}. Le transferimos ahora."
    else:
        message = "Opción no válida. Le transferimos con un agente."

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="{language}">{message}</Say>
    <Dial><Queue>{selected_queue or 'general'}</Queue></Dial>
</Response>"""

    from fastapi import Response
    return Response(content=twiml, media_type="application/xml")
