"""Canales conversacionales del service desk (mejoras de mercado 16-11-2026).

- Slack: botones de la tarjeta del ticket (firma de Slack).
- WhatsApp Business (Meta Cloud API): alta del webhook y mensajes (firma
  `X-Hub-Signature-256` con el secreto de la empresa del numero).
- Chat en vivo del portal: el cliente habla con el asistente y pide una
  persona; los agentes lo atienden desde su bandeja de conversaciones.

Los webhooks no llevan sesion: se autentican por firma y la empresa sale del
workspace o del numero. El chat del portal va con la sesion del cliente; la
bandeja, con la del agente y su empresa.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.async_db import run_db
from app.core.config import settings as app_settings
from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.deps import get_current_portal_client, require_admin, require_internal_user
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import canal_slack, canal_whatsapp, conversaciones

router = APIRouter(prefix="/channels", tags=["Service Desk - Canales"])


class MensajeIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=conversaciones.MAX_MENSAJE)


class RespuestaIn(MensajeIn):
    # Traduccion en tiempo real: la vista previa en el idioma del cliente.
    client_text: Optional[str] = Field(None, max_length=conversaciones.MAX_MENSAJE)
    client_language: Optional[str] = Field(None, max_length=16)


class ChatIn(BaseModel):
    body: Optional[str] = Field(None, max_length=conversaciones.MAX_MENSAJE)
    language: Optional[str] = Field(None, max_length=8)


# ── Slack ─────────────────────────────────────────────────────────────────────

@router.post("/slack/interactions", include_in_schema=False, summary="Botones de la tarjeta de Slack")
async def slack_interactions(request: Request, db: Session = Depends(get_db)):
    cuerpo = await request.body()
    payload, usuario = await run_db(canal_slack.leer_interaccion, db, cuerpo,
                                    request.headers.get("X-Slack-Request-Timestamp", ""),
                                    request.headers.get("X-Slack-Signature", ""))
    mensaje = await run_db(canal_slack.procesar_interaccion, db, payload, usuario)
    if mensaje:
        await run_db(canal_slack.responder_por_url, db, payload.get("response_url"), mensaje)
    # Slack solo necesita un 200 rapido; la tarjeta se actualiza por response_url.
    return {}


# ── WhatsApp ──────────────────────────────────────────────────────────────────

@router.get("/whatsapp/webhook", include_in_schema=False, summary="Alta del webhook de WhatsApp (Meta)")
def whatsapp_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge", max_length=200),
    db: Session = Depends(get_db),
):
    if hub_mode != "subscribe" or not canal_whatsapp.comprobar_alta(db, hub_verify_token):
        raise ErrorDeDominio(403, "Verify token no válido")
    return PlainTextResponse(hub_challenge or "")


@router.post("/whatsapp/webhook", include_in_schema=False, summary="Mensajes de WhatsApp (Meta Cloud API)")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    import json
    cuerpo = await request.body()
    try:
        payload = json.loads(cuerpo or b"{}")
    except ValueError:
        raise ErrorDeDominio(400, "Cuerpo ilegible")
    return APIResponse.ok(data=await run_db(canal_whatsapp.procesar, db, cuerpo,
                                            request.headers.get("X-Hub-Signature-256"), payload))


# ── Chat en vivo del portal ───────────────────────────────────────────────────

@router.post("/livechat", summary="Portal: abrir (o seguir) el chat en vivo")
def livechat_start(payload: ChatIn, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=conversaciones.abrir_chat_del_portal(db, client, payload.body, payload.language))


@router.get("/livechat/{conv_id}/messages", summary="Portal: mensajes del chat (desde uno dado)")
def livechat_messages(conv_id: str, after: Optional[str] = Query(None, max_length=36),
                      db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    conv = conversaciones.del_cliente(db, conv_id, client)
    return APIResponse.ok(data={"conversation": conversaciones.serializar(db, conv),
                                "messages": conversaciones.mensajes(db, conv, after, para_cliente=True)})


@router.post("/livechat/{conv_id}/messages", summary="Portal: escribir en el chat")
def livechat_send(conv_id: str, payload: MensajeIn, db: Session = Depends(get_db),
                  client=Depends(get_current_portal_client)):
    conv = conversaciones.del_cliente(db, conv_id, client)
    if conv.status == "closed":
        raise error_con_codigo(409, "conversacion_cerrada")
    return APIResponse.ok(data=conversaciones.mensaje_del_cliente(db, conv, payload.body, client_user=client,
                                                                  con_bot=True))


@router.post("/livechat/{conv_id}/agent", summary="Portal: pedir hablar con una persona")
def livechat_agent(conv_id: str, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    conv = conversaciones.pedir_agente(db, conversaciones.del_cliente(db, conv_id, client), client_user=client)
    return APIResponse.ok(data=conversaciones.serializar(db, conv))


# ── Bandeja del agente ────────────────────────────────────────────────────────

@router.get("/conversations", summary="Conversaciones de los canales de la empresa")
def list_conversations(status: Optional[str] = Query(None, pattern="^(bot|waiting_agent|agent|closed)$"),
                       page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=MAX_TAMANO_DE_PAGINA),
                       db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    r = conversaciones.listar(db, current_user.organization_id, status, page, page_size)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.get("/conversations/{conv_id}", summary="Una conversación con sus mensajes")
def get_conversation(conv_id: str, after: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                     current_user: User = Depends(require_internal_user)):
    conv = conversaciones._de_la_empresa(db, conv_id, current_user.organization_id)
    return APIResponse.ok(data={"conversation": conversaciones.serializar(db, conv),
                                "messages": conversaciones.mensajes(db, conv, after)})


@router.post("/conversations/{conv_id}/take", summary="Tomar la conversación (traspaso a agente)")
def take_conversation(conv_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=conversaciones.serializar(db, conversaciones.tomar(db, conv_id, current_user)))


@router.post("/conversations/{conv_id}/reply", summary="Contestar al cliente por su canal")
def reply_conversation(conv_id: str, payload: RespuestaIn, db: Session = Depends(get_db),
                       current_user: User = Depends(require_internal_user)):
    m = conversaciones.responder(db, conv_id, current_user, payload.body, client_text=payload.client_text,
                                 client_language=payload.client_language)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(m))


@router.post("/conversations/{conv_id}/close", summary="Cerrar la conversación")
def close_conversation(conv_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=conversaciones.serializar(db, conversaciones.cerrar(db, conv_id, current_user)))


@router.get("/status", summary="Qué canales tiene configurados la empresa (admin)")
def channels_status(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services.integration_credentials_service import get_credential
    from app.services.integrations import secreto_de_firma_de_slack
    org = current_user.organization_id
    whatsapp = bool(get_credential(db, "whatsapp", "phone_number_id", org)) and bool(
        canal_whatsapp._secreto(db, "app_secret", org)) and bool(canal_whatsapp._secreto(db, "access_token", org))
    return APIResponse.ok(data={
        "slack": bool(secreto_de_firma_de_slack(db, org)),
        "teams": bool(app_settings.TEAMS_BOT_APP_ID),
        "whatsapp": whatsapp,
        "livechat": True,
        "endpoints": {
            "slack_commands": "/api/v1/integrations-hub/slack/commands",
            "slack_interactions": "/api/v1/sd/channels/slack/interactions",
            "whatsapp_webhook": "/api/v1/sd/channels/whatsapp/webhook",
            "teams_messages": "/api/v1/integrations-hub/teams/commands",
        },
    })
