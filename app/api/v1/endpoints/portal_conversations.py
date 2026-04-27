from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_client, require_any_manager
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.models.user import User
import app.services.portal_conversation_service as _svc


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


@router.get("/team", summary="Conversaciones gobernadas del equipo interno")
def list_team_conversations(
    project_id: Optional[str] = None,
    client_org_id: Optional[str] = None,
    assigned_to_me: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_team_conversations(current_user, db, project_id, client_org_id, assigned_to_me)


@router.get("/team/policies", summary="Políticas GRC de conversaciones del portal")
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_policies(current_user, db)


@router.put("/team/policies/{topic_type}", summary="Actualizar política GRC por tipo de conversación")
def update_policy(
    topic_type: str,
    payload: PolicyUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.update_policy(topic_type, payload.model_dump(exclude_unset=True), current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/team", summary="Crear conversación gobernada desde equipo interno")
def create_team_conversation(
    payload: ConversationCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.create_team_conversation(payload, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/team/{conversation_id}", summary="Detalle de conversación gobernada para equipo")
def get_team_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.get_team_conversation_detail(conversation_id, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/team/{conversation_id}/messages", summary="Mensajes de conversación para equipo")
def get_team_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.list_team_messages(conversation_id, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/team/{conversation_id}/messages", summary="Enviar mensaje en conversación como equipo")
def send_team_message(
    conversation_id: str,
    payload: ConversationMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.send_team_message(conversation_id, payload, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/team/{conversation_id}/participants", summary="Asignar participantes a una conversación")
def assign_participants(
    conversation_id: str,
    payload: ParticipantAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.assign_participants(conversation_id, payload, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/team/{conversation_id}/messages/{message_id}/review", summary="Aprobar o rechazar mensaje pendiente de revisión")
def review_message(
    conversation_id: str,
    message_id: str,
    payload: ReviewDecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        return _svc.review_message(conversation_id, message_id, payload.decision, payload.note, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/team/escalations/run", summary="Ejecutar escalados SLA de conversaciones")
def run_sla_escalations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.run_sla_escalations(current_user, db)


@router.get("", summary="Mis conversaciones gobernadas del portal")
def list_client_conversations(
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    return _svc.list_client_conversations(current_client, db)


@router.post("", summary="Crear conversación gobernada desde el portal")
def create_client_conversation(
    payload: ConversationCreateIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return _svc.create_client_conversation(payload, current_client, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{conversation_id}", summary="Detalle de conversación gobernada para cliente")
def get_client_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return _svc.get_client_conversation_detail(conversation_id, current_client, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{conversation_id}/messages", summary="Mensajes visibles para cliente")
def get_client_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return _svc.list_client_messages(conversation_id, current_client, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{conversation_id}/messages", summary="Enviar mensaje como cliente")
def send_client_message(
    conversation_id: str,
    payload: ConversationMessageIn,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return _svc.send_client_message(conversation_id, payload, current_client, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{conversation_id}/bot-reply", summary="Generar respuesta L1 automática en chat portal")
def send_l1_bot_reply(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_client: ClientUser = Depends(get_current_client),
):
    try:
        return _svc.send_l1_bot_reply(conversation_id, current_client, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))