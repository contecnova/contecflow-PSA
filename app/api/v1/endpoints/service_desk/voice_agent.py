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
#
# Segunda auditoria 2026-11 (#19): varias organizaciones. La organizacion sale
# del numero llamado (`To`, ajuste por organizacion `TWILIO_PHONE_NUMBERS` o
# credencial `twilio.from_number`), la firma se verifica con su token y la
# llamada se atiende en su contexto. Numero desconocido: `<Reject/>` (200 si la
# firma es de Twilio con el token global, para que Twilio cuelgue sin error de
# aplicacion; 403 si no). Firma invalida: 403.

def _twiml(cuerpo: str, status_code: int = 200):
    from fastapi import Response

    return Response(content=f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{cuerpo}</Response>',
                    media_type="application/xml", status_code=status_code)


async def _llamada_verificada(request: Request, db: Session):
    """`(form, org_id, None)` si se atiende; `(form, None, respuesta)` si no."""
    from app.core.async_db import run_db
    from app.services.service_desk.voice_agent_service import (
        LLAMADA_ACEPTADA,
        LLAMADA_NUMERO_DESCONOCIDO,
        verificar_llamada_de_twilio,
    )
    from app.services.service_desk.sms_service import urls_de_firma_de_twilio

    form = dict(await request.form())
    veredicto, org_id = await run_db(
        verificar_llamada_de_twilio, db, urls_de_firma_de_twilio(request), form,
        request.headers.get("X-Twilio-Signature"))
    if veredicto == LLAMADA_ACEPTADA:
        return form, org_id, None
    if veredicto == LLAMADA_NUMERO_DESCONOCIDO:
        return form, None, _twiml('<Reject reason="rejected" />')
    return form, None, _twiml("<Reject />", status_code=403)


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

    Production usage:
      1. Configure the Twilio phone number's voice webhook URL to point here.
      2. Declare the number in the organization's `TWILIO_PHONE_NUMBERS`
         runtime setting (or its `twilio.from_number` credential).
      3. Give the organization its own auth token (credential `twilio.auth_token`
         or setting `TWILIO_AUTH_TOKEN`); without one the global env token is used.
    """
    from html import escape

    from app.core.async_db import run_db
    from app.services.service_desk.voice_agent_service import atender_llamada_de_twilio

    # Audit #C7: async is needed for await request.form(); DB ops are
    # offloaded to the threadpool via run_db so the sync ORM never blocks
    # the event loop while Twilio waits for TwiML.
    form, org_id, rechazo = await _llamada_verificada(request, db)
    if rechazo is not None:
        return rechazo

    # Segunda auditoria 2026-11 (#19): `create_session` devuelve
    # `{session, greeting}` y aqui se leia `session["id"]` (KeyError: el webhook
    # respondia 500 a toda llamada). Ahora el servicio da el id.
    atendida = await run_db(atender_llamada_de_twilio, db, org_id,
                            form.get("From", "unknown"), form.get("CallSid", ""))
    cfg = atendida["config"]
    greeting = cfg.get("greeting", "Gracias por llamar. ¿En qué le podemos ayudar?")
    language = escape(str(cfg.get("language", settings.DEFAULT_LANGUAGE)))
    dtmf_menu = cfg.get("dtmf_menu", {})

    # El texto de la configuracion se escapa: va dentro de XML.
    gather_verbs = "\n".join(
        f'<Say language="{language}">{escape(str(item.get("label", key)))}</Say>'
        for key, item in sorted((dtmf_menu or {}).items())
    )
    accion = escape(f"/api/v1/sd/voice/webhook/twilio/gather?session_id={atendida['session_id']}")
    return _twiml(f"""
  <Say language="{language}">{escape(str(greeting))}</Say>
  <Gather numDigits="1" action="{accion}" method="POST" timeout="5">
    {gather_verbs}
  </Gather>
  <Say language="{language}">No hemos recibido ninguna selección. Le transferimos con un agente.</Say>
  <Dial><Queue>general</Queue></Dial>
""")


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
    from html import escape

    from app.core.async_db import run_db
    from app.services.service_desk.voice_agent_service import registrar_opcion_de_twilio

    # Auditoria 2026-11: este callback no tenia ninguna autenticacion y escribia
    # en la transcripcion de cualquier `session_id`. Ahora firma de la
    # organizacion del numero llamado y solo sesiones de esa organizacion.
    form, org_id, rechazo = await _llamada_verificada(request, db)
    if rechazo is not None:
        return rechazo
    digit = form.get("Digits", "")
    opcion = await run_db(registrar_opcion_de_twilio, db, org_id, session_id, digit)
    elegida = opcion["label"] or opcion["queue"]

    if digit and elegida:
        message = f"Ha seleccionado: {elegida}. Le transferimos ahora."
    else:
        message = "Opción no válida. Le transferimos con un agente."

    return _twiml(f"""
  <Say language="{escape(str(opcion["language"]))}">{escape(message)}</Say>
  <Dial><Queue>{escape(str(opcion["queue"]))}</Queue></Dial>
""")
