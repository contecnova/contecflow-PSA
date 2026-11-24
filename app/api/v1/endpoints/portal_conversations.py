from typing import List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import desde_valor
from app.core.deps import get_current_client, requiere_capacidad
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.models.user import User
from app.core.responses import APIListResponse, APIResponse
import app.services.portal_conversation_service as _svc
# 24-11-2026: chat del portal completo (docs/portal/CHAT_DEL_PORTAL.md).
from app.services.portal_conversation_service import adjuntos as _adjuntos
from app.services.portal_conversation_service import ajustes as _ajustes_chat
from app.services.portal_conversation_service import interaccion as _interaccion
from app.services.portal_conversation_service import llamadas as _llamadas


router = APIRouter(prefix="/conversations", tags=["Portal Conversations"])


class ConversationCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    topic_type: str = "general"
    project_id: Optional[str] = None
    client_org_id: Optional[str] = None
    source_resource_type: Optional[str] = None
    source_resource_id: Optional[str] = None
    visibility_policy_key: Optional[str] = None
    internal_user_ids: List[str] = Field(default_factory=list)
    client_user_ids: List[str] = Field(default_factory=list)


class ConversationMessageIn(BaseModel):
    body: str = Field(..., min_length=1)
    parent_message_id: Optional[str] = None
    message_type: str = "text"
    is_internal_note: bool = False


class ParticipantAssignIn(BaseModel):
    internal_user_ids: List[str] = Field(default_factory=list)
    client_user_ids: List[str] = Field(default_factory=list)
    role_in_conversation: str = "agent"


class PolicyUpdateIn(BaseModel):
    is_active: Optional[bool] = None
    requires_client_message_approval: Optional[bool] = None
    requires_team_message_approval: Optional[bool] = None
    redact_sensitive_content: Optional[bool] = None
    allow_legacy_federation: Optional[bool] = None
    assignment_mode: Optional[str] = None
    default_group_id: Optional[str] = None
    default_role_key: Optional[str] = None
    first_response_hours: Optional[int] = None
    escalation_hours: Optional[int] = None
    approval_role_key: Optional[str] = None
    approval_user_id: Optional[str] = None
    sensitive_keywords: Optional[List[str]] = None


class ReviewDecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    note: Optional[str] = None


class MessageEditIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=20000)


class ReactionIn(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)


class CallStartIn(BaseModel):
    kind: str = Field("audio", pattern="^(audio|video)$")


def _no_encontrada(fn, *args):
    """Los servicios lanzan `ErrorConCodigo` (ValueError) al no ver la conversación: 404 con código."""
    try:
        return fn(*args)
    except ValueError as exc:
        raise desde_valor(404, exc)


def _fichero(datos: bytes, mime: str, nombre: str) -> Response:
    """Descarga de un adjunto: siempre como fichero, con el tipo real y sin adivinar.

    `nosniff` y `attachment`: el navegador no lo interpreta (un HTML o un SVG
    nunca se ejecuta en nuestro origen); la vista previa de imágenes la hace la
    pantalla con un blob.
    """
    return Response(content=datos, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre or 'archivo')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


def _ajustes_salida(db: Session, organization_id: Optional[str]) -> dict:
    return _ajustes_chat.leer(db, organization_id).salida()


@router.get("/team", summary="Conversaciones gobernadas del equipo interno")
def list_team_conversations(
    project_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    assigned_to_me: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_svc.list_team_conversations(current_user, db, project_id, client_org_id, assigned_to_me))


@router.get("/team/policies", summary="Políticas GRC de conversaciones del portal")
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_svc.list_policies(current_user, db))


@router.get("/team/settings", summary="Ajustes del chat del portal (adjuntos, llamadas) para el equipo")
def get_team_chat_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    from app.core.capacidades import tiene
    datos = _ajustes_salida(db, current_user.organization_id)
    datos["can_call"] = bool(datos["calls_enabled"] and tiene(db, current_user, "clientes.llamar"))
    return APIResponse.ok(data=datos)


@router.put("/team/policies/{topic_type}", summary="Actualizar política GRC por tipo de conversación")
def update_policy(
    topic_type: str,
    payload: PolicyUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.update_policy(topic_type, payload.model_dump(exclude_unset=True), current_user, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/team", summary="Crear conversación gobernada desde equipo interno")
def create_team_conversation(
    payload: ConversationCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.create_team_conversation(payload, current_user, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.get("/team/{conversation_id}", summary="Detalle de conversación gobernada para equipo")
def get_team_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.get_team_conversation_detail(conversation_id, current_user, db))
    except ValueError as exc:
        raise desde_valor(404, exc)


@router.get("/team/{conversation_id}/messages", summary="Mensajes de conversación para equipo")
def get_team_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIListResponse.ok(items=_svc.list_team_messages(conversation_id, current_user, db))
    except ValueError as exc:
        raise desde_valor(404, exc)


@router.post("/team/{conversation_id}/messages", summary="Enviar mensaje en conversación como equipo")
def send_team_message(
    conversation_id: str,
    payload: ConversationMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.send_team_message(conversation_id, payload, current_user, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/team/{conversation_id}/participants", summary="Asignar participantes a una conversación")
def assign_participants(
    conversation_id: str,
    payload: ParticipantAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.assign_participants(conversation_id, payload, current_user, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/team/{conversation_id}/messages/{message_id}/review", summary="Aprobar o rechazar mensaje pendiente de revisión")
def review_message(
    conversation_id: str,
    message_id: str,
    payload: ReviewDecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    try:
        return APIResponse.ok(data=_svc.review_message(conversation_id, message_id, payload.decision, payload.note, current_user, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/team/{conversation_id}/attachments", summary="Subir imagen o fichero como equipo")
def upload_team_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    is_internal_note: bool = Form(False),
    parent_message_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_no_encontrada(
        _adjuntos.subir_como_equipo, db, conversation_id, file, caption, is_internal_note, parent_message_id,
        current_user))


@router.get("/team/{conversation_id}/attachments/{attachment_id}", summary="Descargar adjunto (participantes del equipo)")
def download_team_attachment(
    conversation_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    datos, mime, nombre = _no_encontrada(_adjuntos.descargar_como_equipo, db, conversation_id, attachment_id, current_user)
    return _fichero(datos, mime, nombre)


@router.put("/team/{conversation_id}/messages/{message_id}", summary="Editar el propio mensaje (equipo)")
def edit_team_message(
    conversation_id: str,
    message_id: str,
    payload: MessageEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.editar_como_equipo, db, conversation_id, message_id, payload.body, current_user))


@router.delete("/team/{conversation_id}/messages/{message_id}", summary="Borrar el propio mensaje (equipo)")
def delete_team_message(
    conversation_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.borrar_como_equipo, db, conversation_id, message_id, current_user))


@router.post("/team/{conversation_id}/messages/{message_id}/reactions", summary="Poner o quitar una reacción (equipo)")
def react_team_message(
    conversation_id: str,
    message_id: str,
    payload: ReactionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.reaccionar_como_equipo, db, conversation_id, message_id, payload.emoji, current_user))


@router.get("/team/{conversation_id}/messages/{message_id}/versions", summary="Rastro de ediciones y borrados de un mensaje")
def team_message_versions(
    conversation_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_no_encontrada(
        _interaccion.versiones, db, conversation_id, message_id, current_user))


@router.get("/team/{conversation_id}/calls", summary="Llamadas de la conversación (equipo)")
def list_team_calls(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIListResponse.ok(items=_no_encontrada(_llamadas.listar_como_equipo, db, conversation_id, current_user))


@router.post("/team/{conversation_id}/calls", summary="Llamar o videollamar al cliente (solo el equipo)")
def start_team_call(
    conversation_id: str,
    payload: CallStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.llamar")),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.iniciar, db, conversation_id, payload.kind, current_user))


@router.post("/team/{conversation_id}/calls/{call_id}/join", summary="Entrar en una llamada en curso (equipo)")
def join_team_call(
    conversation_id: str,
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.llamar")),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.unirse_como_equipo, db, conversation_id, call_id, current_user))


@router.post("/team/{conversation_id}/calls/{call_id}/end", summary="Colgar o cancelar una llamada (equipo)")
def end_team_call(
    conversation_id: str,
    call_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.colgar_como_equipo, db, conversation_id, call_id, current_user))


@router.post("/team/escalations/run", summary="Ejecutar escalados SLA de conversaciones")
def run_sla_escalations(
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("clientes.gestionar")),
):
    return APIResponse.ok(data=_svc.run_sla_escalations(current_user, db))


@router.get("", summary="Mis conversaciones gobernadas del portal")
def list_client_conversations(
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIListResponse.ok(items=_svc.list_client_conversations(current_client, db))


@router.get("/settings", summary="Ajustes del chat del portal para el cliente (adjuntos)")
def get_client_chat_settings(
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    datos = _ajustes_salida(db, current_client.organization_id)
    # El cliente no inicia llamadas nunca: no se le ofrece.
    datos["can_call"] = False
    return APIResponse.ok(data=datos)


@router.get("/calls/ringing", summary="Llamadas del equipo que suenan ahora para el cliente")
def client_ringing_calls(
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIListResponse.ok(items=_llamadas.sonando_para_cliente(db, current_client))


@router.post("", summary="Crear conversación gobernada desde el portal")
def create_client_conversation(
    payload: ConversationCreateIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIResponse.ok(data=_svc.create_client_conversation(payload, current_client, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.get("/{conversation_id}", summary="Detalle de conversación gobernada para cliente")
def get_client_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIResponse.ok(data=_svc.get_client_conversation_detail(conversation_id, current_client, db))
    except ValueError as exc:
        raise desde_valor(404, exc)


@router.get("/{conversation_id}/messages", summary="Mensajes visibles para cliente")
def get_client_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIListResponse.ok(items=_svc.list_client_messages(conversation_id, current_client, db))
    except ValueError as exc:
        raise desde_valor(404, exc)


@router.post("/{conversation_id}/messages", summary="Enviar mensaje como cliente")
def send_client_message(
    conversation_id: str,
    payload: ConversationMessageIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIResponse.ok(data=_svc.send_client_message(conversation_id, payload, current_client, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/{conversation_id}/bot-reply", summary="Generar respuesta L1 automática en chat portal")
def send_l1_bot_reply(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return APIResponse.ok(data=_svc.send_l1_bot_reply(conversation_id, current_client, db))
    except ValueError as exc:
        raise desde_valor(400, exc)


@router.post("/{conversation_id}/attachments", summary="Subir imagen o fichero como cliente")
def upload_client_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    parent_message_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(
        _adjuntos.subir_como_cliente, db, conversation_id, file, caption, parent_message_id, current_client))


@router.get("/{conversation_id}/attachments/{attachment_id}", summary="Descargar adjunto (participantes del portal)")
def download_client_attachment(
    conversation_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    datos, mime, nombre = _no_encontrada(
        _adjuntos.descargar_como_cliente, db, conversation_id, attachment_id, current_client)
    return _fichero(datos, mime, nombre)


@router.put("/{conversation_id}/messages/{message_id}", summary="Editar el propio mensaje (cliente)")
def edit_client_message(
    conversation_id: str,
    message_id: str,
    payload: MessageEditIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.editar_como_cliente, db, conversation_id, message_id, payload.body, current_client))


@router.delete("/{conversation_id}/messages/{message_id}", summary="Borrar el propio mensaje (cliente)")
def delete_client_message(
    conversation_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.borrar_como_cliente, db, conversation_id, message_id, current_client))


@router.post("/{conversation_id}/messages/{message_id}/reactions", summary="Poner o quitar una reacción (cliente)")
def react_client_message(
    conversation_id: str,
    message_id: str,
    payload: ReactionIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(
        _interaccion.reaccionar_como_cliente, db, conversation_id, message_id, payload.emoji, current_client))


@router.get("/{conversation_id}/calls", summary="Llamadas de la conversación (cliente)")
def list_client_calls(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIListResponse.ok(items=_no_encontrada(_llamadas.listar_como_cliente, db, conversation_id, current_client))


@router.post("/{conversation_id}/calls", summary="El cliente NO puede iniciar llamadas: siempre 403")
def start_client_call(
    conversation_id: str,
    payload: Optional[CallStartIn] = None,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    """Regla «solo el operador llama» impuesta en el servidor (docs/portal/CHAT_DEL_PORTAL.md).

    Responde 403 `portal_llamada_solo_operador` siempre y deja el intento en la
    auditoría de la conversación (`call_start_denied`).
    """
    _llamadas.iniciar_como_cliente(db, conversation_id, current_client, payload.kind if payload else None)


@router.post("/{conversation_id}/calls/{call_id}/accept", summary="Aceptar la llamada del equipo (cliente)")
def accept_client_call(
    conversation_id: str,
    call_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.aceptar, db, conversation_id, call_id, current_client))


@router.post("/{conversation_id}/calls/{call_id}/decline", summary="Rechazar la llamada del equipo (cliente)")
def decline_client_call(
    conversation_id: str,
    call_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.rechazar, db, conversation_id, call_id, current_client))


@router.post("/{conversation_id}/calls/{call_id}/end", summary="Colgar (cliente)")
def end_client_call(
    conversation_id: str,
    call_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return APIResponse.ok(data=_no_encontrada(_llamadas.colgar_como_cliente, db, conversation_id, call_id, current_client))
