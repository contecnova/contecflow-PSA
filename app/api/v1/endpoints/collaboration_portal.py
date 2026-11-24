"""Portal-facing collaboration endpoints (ClientUser).

These let portal clients participate in collaboration conversations they have
been invited to (cross-org groups / direct chats / shared channels).

Endpoints:
  GET  /portal/collaboration/conversations
  GET  /portal/collaboration/conversations/{id}/messages
  POST /portal/collaboration/messages
  POST /portal/collaboration/messages/{id}/reactions
  POST /portal/collaboration/conversations/{id}/read
  GET  /portal/collaboration/notifications
  GET  /portal/collaboration/notifications/unread-count
  POST /portal/collaboration/notifications/mark-all-read
  POST /portal/collaboration/notifications/{id}/read
  GET  /portal/collaboration/search

24-11-2026 (chat del portal en colaboración, docs/portal/CHAT_DEL_PORTAL.md §9):

  GET    /portal/collaboration/settings                      ajustes del chat (adjuntos; nunca «llamar»)
  POST   /portal/collaboration/conversations/{id}/attachments  subir imagen o fichero (validado)
  GET    /portal/collaboration/attachments/{id}              descargar (solo participantes, misma empresa)
  PUT    /portal/collaboration/messages/{id}                 editar el propio (con rastro y plazo)
  DELETE /portal/collaboration/messages/{id}                 borrar el propio (con rastro)
  GET    /portal/collaboration/messages/{id}/versions        rastro del propio mensaje
  GET    /portal/collaboration/calls/ringing                 llamadas del equipo que suenan
  POST   /portal/collaboration/calls                         SIEMPRE 403 `portal_llamada_solo_operador`
  POST   /portal/collaboration/calls/{id}/accept|decline|end aceptar, rechazar, colgar

Auditoria 2026-08 (hallazgo 22). Las 21 consultas y escrituras de este fichero
estan en `app/services/collaboration/portal.py`, y con ellas se corrigio que el
portal era **una segunda via de envio de mensajes sin los controles de la
primera**: sus mensajes no se indexaban para busqueda —lo que solo importa con
el backend OpenSearch, donde quedaban invisibles; con Postgres o SQLite la
busqueda lee la tabla—, no pasaban por DLP, no creaban hilos, y su reparto de
notificaciones era parcial
y se protegia con una comparacion entre dos espacios de identificadores que
nunca podia ser falsa. Ahora el envio es el unico que hay,
`messages.send_message`, con el remitente marcado como cliente.
"""
from typing import Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints.client_portal import get_current_client
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.schemas.collaboration import (
    MessageCreate,
    MessageOut,
    ReactionToggle,
    ReadUpdate,
    SearchHit,
    SearchResponse,
)
from app.services.collaboration import portal as svc
from app.services.collaboration import portal_chat as chat
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


@router.get("/conversations", response_model=APIListResponse[dict], summary="Mis conversaciones (cliente)")
def list_conversations(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = svc.list_conversations(db, current_client)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/conversations/{conversation_id}/messages", response_model=APIListResponse[MessageOut], summary="Mensajes (cliente)")
def list_messages(
    conversation_id: str,
    before: Optional[str] = None,
    limit: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.services.collaboration.messages import _serialize_message

    filas = svc.list_messages(
        db, current_client, conversation_id, before=before, limit=limit)
    items = [MessageOut(**_serialize_message(db, m)) for m in filas]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/messages", response_model=APIResponse[MessageOut], summary="Enviar mensaje (cliente)")
def send_message(
    payload: MessageCreate,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.services.collaboration.messages import _serialize_message

    msg = svc.send_message(db, current_client, payload)
    return APIResponse.ok(data=MessageOut(**_serialize_message(db, msg)))


@router.post("/messages/{message_id}/reactions", response_model=APIResponse[dict], summary="Toggle reacción (cliente)")
def toggle_reaction(
    message_id: str,
    payload: ReactionToggle,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(
        data=svc.toggle_reaction(db, current_client, message_id, payload.emoji))


@router.post("/conversations/{conversation_id}/read", response_model=APIResponse[dict], summary="Marcar leído (cliente)")
def mark_read(
    conversation_id: str,
    payload: ReadUpdate,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    svc.mark_read(db, current_client, conversation_id, payload.last_message_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/notifications", response_model=APIListResponse[dict], summary="Notificaciones del cliente")
def list_notifs(
    unread_only: bool = False,
    limit: Optional[int] = Query(None, ge=1, le=100),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = svc.list_notifications(db, current_client, unread_only=unread_only, limit=limit)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/notifications/unread-count", response_model=APIResponse[dict], summary="Notificaciones sin leer (cliente)")
def unread_count(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """El número de la campana del portal: sólo las del cliente que llama."""
    return APIResponse.ok(data={"unread_count": svc.count_unread_notifications(db, current_client)})


@router.post("/notifications/{notif_id}/read", response_model=APIResponse[dict], summary="Marcar una leída (cliente)")
def mark_one_read(
    notif_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    svc.mark_notification_read(db, current_client, notif_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/notifications/mark-all-read", response_model=APIResponse[dict], summary="Marcar todas leídas (cliente)")
def mark_all_read(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(
        data={"marked": svc.mark_all_notifications_read(db, current_client)})


@router.get("/search", response_model=APIResponse[SearchResponse], summary="Búsqueda en mis conversaciones")
def search(
    q: str = Query("", max_length=500),
    limit: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    hits = svc.search(db, current_client, query=q, limit=limit)
    return APIResponse.ok(
        data=SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits)))


# ── 24-11-2026: chat del portal completo (docs/portal/CHAT_DEL_PORTAL.md §9) ──

class _EdicionIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=20000)


class _LlamadaIn(BaseModel):
    conversation_id: Optional[str] = None
    kind: Optional[str] = None


def _serializar(db: Session, msg) -> MessageOut:
    from app.services.collaboration.messages import _serialize_message
    return MessageOut(**_serialize_message(db, msg))


@router.get("/settings", response_model=APIResponse[dict], summary="Ajustes del chat del portal (cliente)")
def chat_settings(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.services.portal_conversation_service import ajustes
    datos = ajustes.leer(db, current_client.organization_id).salida()
    datos["can_call"] = False  # el cliente nunca inicia llamadas
    return APIResponse.ok(data=datos)


@router.post("/conversations/{conversation_id}/attachments", response_model=APIResponse[MessageOut],
             summary="Subir imagen o fichero (cliente)")
def upload_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    parent_message_id: Optional[str] = Form(None),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    msg = chat.subir_adjunto(db, current_client, conversation_id, file, caption, parent_message_id)
    return APIResponse.ok(data=_serializar(db, msg))


@router.get("/attachments/{attachment_id}", summary="Descargar adjunto (cliente participante)")
def download_attachment(
    attachment_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    datos, mime, nombre = chat.descargar_adjunto(db, current_client, attachment_id)
    return Response(content=datos, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre or 'archivo')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


@router.put("/messages/{message_id}", response_model=APIResponse[MessageOut], summary="Editar el propio mensaje (cliente)")
def edit_message(
    message_id: str,
    payload: _EdicionIn,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=_serializar(db, chat.editar(db, current_client, message_id, payload.body)))


@router.delete("/messages/{message_id}", response_model=APIResponse[MessageOut], summary="Borrar el propio mensaje (cliente)")
def delete_message(
    message_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=_serializar(db, chat.borrar(db, current_client, message_id)))


@router.get("/messages/{message_id}/versions", response_model=APIListResponse[dict], summary="Rastro del propio mensaje (cliente)")
def message_versions(
    message_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = [{"id": v.id, "change_type": v.change_type, "body": v.body,
              "edited_at": v.edited_at.isoformat() if v.edited_at else None}
             for v in chat.versiones_del_cliente(db, current_client, message_id)]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/calls/ringing", response_model=APIListResponse[dict], summary="Llamadas del equipo que suenan (cliente)")
def ringing_calls(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = chat.sonando(db, current_client)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/calls", summary="El cliente NO puede iniciar llamadas: siempre 403")
def start_call(
    payload: Optional[_LlamadaIn] = None,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Regla «solo el operador llama» impuesta en el servidor; el intento queda auditado."""
    chat.iniciar_denegado(db, current_client, payload.conversation_id if payload else None,
                          payload.kind if payload else None)


@router.post("/calls/{call_id}/accept", response_model=APIResponse[dict], summary="Aceptar la llamada del equipo (cliente)")
def accept_call(
    call_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=chat.aceptar(db, current_client, call_id))


@router.post("/calls/{call_id}/decline", response_model=APIResponse[dict], summary="Rechazar la llamada del equipo (cliente)")
def decline_call(
    call_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=chat.rechazar(db, current_client, call_id))


@router.post("/calls/{call_id}/end", response_model=APIResponse[dict], summary="Colgar (cliente)")
def end_call(
    call_id: str,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(data=chat.colgar(db, current_client, call_id))
