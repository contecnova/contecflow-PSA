"""Canales conversacionales del service desk (mejoras de mercado 16-11-2026).

- Slack: botones de la tarjeta del ticket (firma de Slack) y Events API
  (17-11-2026): los mensajes de un hilo atado a un ticket entran como
  comentarios; un canal de entrada abre tickets.
- WhatsApp Business (Meta Cloud API): alta del webhook y mensajes (firma
  `X-Hub-Signature-256` con el secreto de la empresa del numero).
- Chat en vivo del portal: el cliente habla con el asistente y pide una
  persona; los agentes lo atienden desde su bandeja de conversaciones.
  24-11-2026 (docs/portal/CHAT_DEL_PORTAL.md §10): imagenes y ficheros,
  reacciones, citas, editar/borrar con rastro y llamadas que SOLO inicia el
  operador (`clientes.llamar`); la ruta del cliente para iniciar responde
  siempre 403 `portal_llamada_solo_operador`. Grabar (migracion 214): solo
  con la propuesta del operador y el consentimiento del cliente
  (`/portal-call-recording/...`); la ruta antigua responde 409
  `portal_grabacion_desactivada` o `portal_grabacion_sin_consentimiento`.

Los webhooks no llevan sesion: se autentican por firma y la empresa sale del
workspace o del numero. El chat del portal va con la sesion del cliente; la
bandeja, con la del agente y su empresa.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.async_db import run_db
from app.core.config import settings as app_settings
from app.core.constantes import MAX_TAMANO_DE_PAGINA
from app.core.deps import get_current_portal_client, requiere_capacidad
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error as error_con_codigo
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db, sesion_de_sistema
from app.models.user import User
from app.services.service_desk import canal_slack, canal_whatsapp, conversaciones
# 24-11-2026: chat en vivo completo (docs/portal/CHAT_DEL_PORTAL.md §10).
from app.services.service_desk import chat_en_vivo as _vivo

router = APIRouter(prefix="/channels", tags=["Service Desk - Canales"])


class MensajeIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=conversaciones.MAX_MENSAJE)
    # 24-11-2026: responder citando (mensaje de la misma conversacion).
    reply_to_message_id: Optional[str] = Field(None, max_length=36)


class EdicionIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=conversaciones.MAX_MENSAJE)


class ReaccionIn(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)


class LlamadaIn(BaseModel):
    kind: str = Field("audio", pattern="^(audio|video)$")


class RespuestaIn(MensajeIn):
    # Traduccion en tiempo real: la vista previa en el idioma del cliente.
    client_text: Optional[str] = Field(None, max_length=conversaciones.MAX_MENSAJE)
    client_language: Optional[str] = Field(None, max_length=16)


class AdjuntoIn(BaseModel):
    document_id: str = Field(..., min_length=1, max_length=36)
    caption: Optional[str] = Field(None, max_length=1024)


class ChatIn(BaseModel):
    body: Optional[str] = Field(None, max_length=conversaciones.MAX_MENSAJE)
    language: Optional[str] = Field(None, max_length=8)


# ── Slack ─────────────────────────────────────────────────────────────────────

@router.post("/slack/interactions", include_in_schema=False, summary="Botones de la tarjeta de Slack")
async def slack_interactions(request: Request, db: Session = Depends(sesion_de_sistema("slack: firma del workspace"))):
    cuerpo = await request.body()
    payload, usuario = await run_db(canal_slack.leer_interaccion, db, cuerpo,
                                    request.headers.get("X-Slack-Request-Timestamp", ""),
                                    request.headers.get("X-Slack-Signature", ""))
    mensaje = await run_db(canal_slack.procesar_interaccion, db, payload, usuario)
    if mensaje:
        await run_db(canal_slack.responder_por_url, db, payload.get("response_url"), mensaje)
    # Slack solo necesita un 200 rapido; la tarjeta se actualiza por response_url.
    return {}


@router.post("/slack/events", include_in_schema=False, summary="Events API de Slack (mensajes de hilos y canales)")
async def slack_events(request: Request, db: Session = Depends(sesion_de_sistema("slack: firma del workspace"))):
    """`url_verification` contesta el `challenge`; `event_callback` se verifica y se
    procesa fuera de la peticion (Slack reintenta si no hay 200 en 3 s)."""
    from app.core.segundo_plano import encolar
    cuerpo = await request.body()
    payload, org = await run_db(canal_slack.leer_evento, db, cuerpo,
                                request.headers.get("X-Slack-Request-Timestamp", ""),
                                request.headers.get("X-Slack-Signature", ""))
    if payload.get("type") == "url_verification":
        return PlainTextResponse(str(payload.get("challenge") or "")[:200])
    if payload.get("type") == "event_callback":
        db.info["organization_id"], db.info["is_superadmin"] = org, False
        await run_db(encolar, canal_slack.procesar_evento, payload, _organizacion=org, _sesion=db)
    return {}


# ── WhatsApp ──────────────────────────────────────────────────────────────────

@router.get("/whatsapp/webhook", include_in_schema=False, summary="Alta del webhook de WhatsApp (Meta)")
def whatsapp_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge", max_length=200),
    db: Session = Depends(sesion_de_sistema("whatsapp: verify token")),
):
    if hub_mode != "subscribe" or not canal_whatsapp.comprobar_alta(db, hub_verify_token):
        raise error_con_codigo(403, "metodo_canal_verify_token", detail="Verify token no válido")
    return PlainTextResponse(hub_challenge or "")


@router.post("/whatsapp/webhook", include_in_schema=False, summary="Mensajes de WhatsApp (Meta Cloud API)")
async def whatsapp_webhook(request: Request, db: Session = Depends(sesion_de_sistema("whatsapp: firma de Meta"))):
    import json
    cuerpo = await request.body()
    try:
        payload = json.loads(cuerpo or b"{}")
    except ValueError:
        raise error_con_codigo(400, "webhook_cuerpo_ilegible", detail="Cuerpo ilegible")
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
                                                                  con_bot=True,
                                                                  reply_to=payload.reply_to_message_id))


@router.post("/livechat/{conv_id}/agent", summary="Portal: pedir hablar con una persona")
def livechat_agent(conv_id: str, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    conv = conversaciones.pedir_agente(db, conversaciones.del_cliente(db, conv_id, client), client_user=client)
    return APIResponse.ok(data=conversaciones.serializar(db, conv))


# ── Chat en vivo completo: lado del cliente (24-11-2026) ──────────────────────

def _fichero(datos: bytes, mime: str, nombre: str):
    """Siempre como descarga, con el tipo real, `nosniff` y sin cache (como el chat del portal)."""
    from urllib.parse import quote
    from fastapi.responses import Response
    return Response(content=datos, media_type=mime, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(nombre or "archivo"),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


@router.get("/livechat/settings", summary="Portal: ajustes del chat en vivo (adjuntos; nunca llamar)")
def livechat_settings(db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=_vivo.ajustes_salida(db, client.organization_id))


@router.get("/livechat/calls/ringing", summary="Portal: llamadas del equipo que suenan en mi chat en vivo")
def livechat_ringing(db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIListResponse.ok(items=_vivo.sonando_para_cliente(db, client))


@router.post("/livechat/{conv_id}/attachments", summary="Portal: enviar imagen o fichero")
def livechat_upload(conv_id: str, file: UploadFile = File(...), caption: Optional[str] = Form(None),
                    reply_to_message_id: Optional[str] = Form(None), db: Session = Depends(get_db),
                    client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    m = _vivo.subir(db, conv, file, caption, reply_to_message_id, cliente=client)
    return APIResponse.ok(data=conversaciones.serializar_para_cliente(db, conv, m))


@router.get("/livechat/{conv_id}/attachments/{attachment_id}", summary="Portal: descargar un adjunto del chat")
def livechat_download(conv_id: str, attachment_id: str, db: Session = Depends(get_db),
                      client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    return _fichero(*_vivo.descargar(db, conv, attachment_id, cliente=client))


@router.put("/livechat/{conv_id}/messages/{message_id}", summary="Portal: editar el propio mensaje")
def livechat_edit(conv_id: str, message_id: str, payload: EdicionIn, db: Session = Depends(get_db),
                  client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    m = _vivo.editar(db, conv, message_id, payload.body, cliente=client)
    return APIResponse.ok(data=conversaciones.serializar_para_cliente(db, conv, m))


@router.delete("/livechat/{conv_id}/messages/{message_id}", summary="Portal: borrar el propio mensaje")
def livechat_delete(conv_id: str, message_id: str, db: Session = Depends(get_db),
                    client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    m = _vivo.borrar(db, conv, message_id, cliente=client)
    return APIResponse.ok(data=conversaciones.serializar_para_cliente(db, conv, m))


@router.post("/livechat/{conv_id}/messages/{message_id}/reactions", summary="Portal: poner o quitar una reacción")
def livechat_react(conv_id: str, message_id: str, payload: ReaccionIn, db: Session = Depends(get_db),
                   client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    return APIResponse.ok(data=_vivo.reaccionar(db, conv, message_id, payload.emoji, cliente=client))


@router.get("/livechat/{conv_id}/calls", summary="Portal: llamadas de mi chat en vivo")
def livechat_calls(conv_id: str, db: Session = Depends(get_db), client=Depends(get_current_portal_client)):
    return APIListResponse.ok(items=_vivo.listar_llamadas(db, _vivo.conversacion_del_cliente(db, conv_id, client)))


@router.post("/livechat/{conv_id}/calls", summary="Portal: el cliente NO puede iniciar llamadas (siempre 403)")
def livechat_call_start_denied(conv_id: str, payload: Optional[LlamadaIn] = None, db: Session = Depends(get_db),
                               client=Depends(get_current_portal_client)):
    """«Solo el operador llama», impuesto en el servidor: 403 `portal_llamada_solo_operador`
    siempre, y el intento queda en la auditoria (`livechat.call_start_denied`)."""
    _vivo.iniciar_como_cliente(db, conv_id, client, payload.kind if payload else None)


@router.post("/livechat/{conv_id}/calls/{call_id}/accept", summary="Portal: aceptar la llamada del equipo")
def livechat_call_accept(conv_id: str, call_id: str, db: Session = Depends(get_db),
                         client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    return APIResponse.ok(data=_vivo.aceptar(db, conv, call_id, client))


@router.post("/livechat/{conv_id}/calls/{call_id}/decline", summary="Portal: rechazar la llamada del equipo")
def livechat_call_decline(conv_id: str, call_id: str, db: Session = Depends(get_db),
                          client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    return APIResponse.ok(data=_vivo.rechazar(db, conv, call_id, client))


@router.post("/livechat/{conv_id}/calls/{call_id}/end", summary="Portal: colgar")
def livechat_call_end(conv_id: str, call_id: str, db: Session = Depends(get_db),
                      client=Depends(get_current_portal_client)):
    conv = _vivo.conversacion_del_cliente(db, conv_id, client)
    return APIResponse.ok(data=_vivo.colgar(db, conv, call_id, cliente=client))


@router.post("/livechat/{conv_id}/calls/{call_id}/recording",
             summary="Portal: estado de la grabación (solo con consentimiento; si no, 409)")
def livechat_call_recording(conv_id: str, call_id: str, db: Session = Depends(get_db),
                            client=Depends(get_current_portal_client)):
    return APIResponse.ok(data=_vivo.grabar_denegado(db, _vivo.conversacion_del_cliente(db, conv_id, client), call_id,
                                                     cliente=client))


# ── Bandeja del agente ────────────────────────────────────────────────────────

@router.get("/chat-settings", summary="Ajustes del chat en vivo para el operador (adjuntos, plazo, llamar)")
def operator_chat_settings(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.completo"))):
    return APIResponse.ok(data=_vivo.ajustes_salida(db, current_user.organization_id, current_user))

@router.get("/conversations", summary="Conversaciones de los canales de la empresa")
def list_conversations(status: Optional[str] = Query(None, pattern="^(bot|waiting_agent|agent|closed)$"),
                       channel: Optional[str] = Query(None, pattern="^(whatsapp|livechat|slack|teams)$"),
                       page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=MAX_TAMANO_DE_PAGINA),
                       db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.completo"))):
    r = conversaciones.listar(db, current_user.organization_id, status, page, page_size, channel)
    return APIListResponse.ok(items=r["items"], total=r["total"], page=page, page_size=page_size)


@router.get("/conversations/{conv_id}", summary="Una conversación con sus mensajes")
def get_conversation(conv_id: str, after: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("sd.completo"))):
    return APIResponse.ok(data=conversaciones.detalle_para_agente(db, conv_id, current_user.organization_id, after))


@router.post("/conversations/{conv_id}/take", summary="Tomar la conversación (traspaso a agente)")
def take_conversation(conv_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.completo"))):
    return APIResponse.ok(data=conversaciones.serializar(db, conversaciones.tomar(db, conv_id, current_user)))


@router.post("/conversations/{conv_id}/reply", summary="Contestar al cliente por su canal")
def reply_conversation(conv_id: str, payload: RespuestaIn, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("sd.completo"))):
    m = conversaciones.responder(db, conv_id, current_user, payload.body, client_text=payload.client_text,
                                 client_language=payload.client_language, reply_to=payload.reply_to_message_id)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(m, db))


@router.post("/conversations/{conv_id}/attachments", summary="Enviar un adjunto del ticket por el canal")
def send_attachment(conv_id: str, payload: AdjuntoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("sd.completo"))):
    m = conversaciones.enviar_adjunto(db, conv_id, current_user, payload.document_id, payload.caption)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(m, db))


@router.get("/tickets/{ticket_id}/conversations", summary="Conversaciones de canal abiertas de un ticket y sus adjuntos")
def ticket_channel_conversations(ticket_id: str, db: Session = Depends(get_db),
                                 current_user: User = Depends(requiere_capacidad("sd.completo"))):
    """Para enviar adjuntos desde la ficha del ticket (17-11-2026): el envio es
    `POST /conversations/{id}/attachments`, igual que en la bandeja."""
    return APIResponse.ok(data=conversaciones.del_ticket_para_adjuntos(db, ticket_id, current_user.organization_id))


@router.post("/conversations/{conv_id}/close", summary="Cerrar la conversación")
def close_conversation(conv_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.completo"))):
    return APIResponse.ok(data=conversaciones.serializar(db, conversaciones.cerrar(db, conv_id, current_user)))


# ── Chat en vivo completo: lado del operador (24-11-2026) ─────────────────────

@router.post("/conversations/{conv_id}/files", summary="Chat en vivo: enviar imagen o fichero al cliente")
def operator_upload(conv_id: str, file: UploadFile = File(...), caption: Optional[str] = Form(None),
                    reply_to_message_id: Optional[str] = Form(None), db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_adjunto_no_disponible")
    m = _vivo.subir(db, conv, file, caption, reply_to_message_id, usuario=current_user)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(m, db))


@router.get("/conversations/{conv_id}/files/{attachment_id}", summary="Chat en vivo: descargar un adjunto")
def operator_download(conv_id: str, attachment_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_adjunto_no_disponible")
    return _fichero(*_vivo.descargar(db, conv, attachment_id, usuario=current_user))


@router.put("/conversations/{conv_id}/messages/{message_id}", summary="Chat en vivo: editar el propio mensaje")
def operator_edit(conv_id: str, message_id: str, payload: EdicionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(
        _vivo.editar(db, conv, message_id, payload.body, usuario=current_user), db))


@router.delete("/conversations/{conv_id}/messages/{message_id}", summary="Chat en vivo: borrar el propio mensaje")
def operator_delete(conv_id: str, message_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user)
    return APIResponse.ok(data=conversaciones.serializar_mensaje(
        _vivo.borrar(db, conv, message_id, usuario=current_user), db))


@router.post("/conversations/{conv_id}/messages/{message_id}/reactions", summary="Chat en vivo: reacción")
def operator_react(conv_id: str, message_id: str, payload: ReaccionIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user)
    return APIResponse.ok(data=_vivo.reaccionar(db, conv, message_id, payload.emoji, usuario=current_user))


@router.get("/conversations/{conv_id}/messages/{message_id}/versions", summary="Chat en vivo: rastro de un mensaje")
def operator_versions(conv_id: str, message_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user)
    return APIListResponse.ok(items=_vivo.versiones(db, conv, message_id))


@router.get("/conversations/{conv_id}/calls", summary="Chat en vivo: llamadas de la conversación")
def operator_calls(conv_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_llamada_no_disponible")
    return APIListResponse.ok(items=_vivo.listar_llamadas(db, conv))


@router.post("/conversations/{conv_id}/calls", summary="Chat en vivo: llamar o videollamar al cliente (solo operador)")
def operator_call_start(conv_id: str, payload: LlamadaIn, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("clientes.llamar"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_llamada_no_disponible")
    return APIResponse.ok(data=_vivo.iniciar_llamada(db, conv, payload.kind, current_user))


@router.post("/conversations/{conv_id}/calls/{call_id}/join", summary="Chat en vivo: entrar en una llamada en curso")
def operator_call_join(conv_id: str, call_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("clientes.llamar"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_llamada_no_disponible")
    return APIResponse.ok(data=_vivo.unirse(db, conv, call_id, current_user))


@router.post("/conversations/{conv_id}/calls/{call_id}/end", summary="Chat en vivo: colgar o cancelar la llamada")
def operator_call_end(conv_id: str, call_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_llamada_no_disponible")
    return APIResponse.ok(data=_vivo.colgar(db, conv, call_id, usuario=current_user))


@router.post("/conversations/{conv_id}/calls/{call_id}/recording",
             summary="Chat en vivo: estado de la grabación (solo con consentimiento; si no, 409)")
def operator_call_recording(conv_id: str, call_id: str, db: Session = Depends(get_db),
                            current_user: User = Depends(requiere_capacidad("sd.completo"))):
    conv = _vivo.conversacion_del_operador(db, conv_id, current_user, "portal_llamada_no_disponible")
    return APIResponse.ok(data=_vivo.grabar_denegado(db, conv, call_id, usuario=current_user))


@router.get("/status", summary="Qué canales tiene configurados la empresa (admin)")
def channels_status(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("sd.administrar"))):
    from app.services.integration_credentials_service import get_credential
    from app.services.integrations import secreto_de_firma_de_slack
    org = current_user.organization_id
    whatsapp = bool(get_credential(db, "whatsapp", "phone_number_id", org)) and bool(
        canal_whatsapp._secreto(db, "app_secret", org)) and bool(canal_whatsapp._secreto(db, "access_token", org))
    return APIResponse.ok(data={
        "slack": bool(secreto_de_firma_de_slack(db, org)),
        "slack_threads": bool(canal_slack.token_del_bot(db, org)),
        "teams": bool(app_settings.TEAMS_BOT_APP_ID),
        "whatsapp": whatsapp,
        "livechat": True,
        "endpoints": {
            "slack_commands": "/api/v1/integrations-hub/slack/commands",
            "slack_interactions": "/api/v1/sd/channels/slack/interactions",
            "slack_events": "/api/v1/sd/channels/slack/events",
            "whatsapp_webhook": "/api/v1/sd/channels/whatsapp/webhook",
            "teams_messages": "/api/v1/integrations-hub/teams/commands",
        },
    })
