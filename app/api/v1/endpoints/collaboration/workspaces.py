"""Workspace + Teams + Channels + Conversations + Presence + Search + Notifications endpoints."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.schemas.collaboration import (
    ChannelCreate, ChannelMemberOut, ChannelOut, ChannelUpdate,
    ConversationOut, DirectOpenIn, DraftIn,
    GroupCreate, NotificationRuleIn, PresenceIn, SearchHit,
    SearchResponse, TeamCreate,
    TeamMemberOut, TeamMemberUpsert, TeamOut, TeamUpdate, WorkspaceOut,
    WorkspaceUpdate,
)
from app.services.collaboration._permissions import (
    _org,
)
from app.services.collaboration._search import search_engine
from app.services.collaboration import workspaces as ws_svc
from app.core.responses import APIListResponse, APIResponse

router = APIRouter()


# ── Workspace ───────────────────────────────────────────────────────────────
@router.get("/workspace", response_model=APIResponse[WorkspaceOut], summary="Mi workspace (lazy-create)")
def my_workspace(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = ws_svc.get_or_create_workspace(db, current_user)
    return APIResponse.ok(data=WorkspaceOut(
        id=ws.id, organization_id=ws.organization_id, name=ws.name,
        icon_url=ws.icon_url, primary_color=ws.primary_color,
        settings=ws.settings or {}, is_active=ws.is_active,
    ))


@router.patch("/workspace", response_model=APIResponse[WorkspaceOut], summary="Actualizar workspace")
def update_workspace(payload: WorkspaceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = ws_svc.update_workspace(db, current_user, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=WorkspaceOut(
        id=ws.id, organization_id=ws.organization_id, name=ws.name,
        icon_url=ws.icon_url, primary_color=ws.primary_color,
        settings=ws.settings or {}, is_active=ws.is_active,
    ))


# ── Teams ────────────────────────────────────────────────────────────────────
@router.get("/teams", response_model=APIListResponse[TeamOut], summary="Listar mis equipos")
def list_teams(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out: List[TeamOut] = [
        TeamOut(
            id=r.equipo.id, name=r.equipo.name, slug=r.equipo.slug,
            description=r.equipo.description, is_private=r.equipo.is_private,
            project_id=r.equipo.project_id, is_archived=r.equipo.is_archived,
            member_count=r.miembros, channel_count=r.canales,
            created_at=r.equipo.created_at,
        )
        for r in ws_svc.list_teams_con_recuentos(db, current_user)
    ]
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/teams", response_model=APIResponse[TeamOut], summary="Crear equipo")
def create_team(payload: TeamCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = ws_svc.create_team(
        db, current_user,
        name=payload.name, slug=payload.slug, description=payload.description,
        is_private=payload.is_private, project_id=payload.project_id,
    )
    return APIResponse.ok(data=TeamOut(
        id=t.id, name=t.name, slug=t.slug, description=t.description,
        is_private=t.is_private, project_id=t.project_id, is_archived=t.is_archived,
        member_count=1, channel_count=1, created_at=t.created_at,
    ))


@router.patch("/teams/{team_id}", response_model=APIResponse[TeamOut], summary="Actualizar equipo")
def update_team(team_id: str, payload: TeamUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = ws_svc.update_team(db, current_user, team_id, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=TeamOut(
        id=t.id, name=t.name, slug=t.slug, description=t.description,
        is_private=t.is_private, project_id=t.project_id, is_archived=t.is_archived,
        created_at=t.created_at,
    ))


@router.get("/teams/{team_id}/members", response_model=APIListResponse[TeamMemberOut], summary="Miembros del equipo")
def list_team_members(team_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = [TeamMemberOut(**m) for m in ws_svc.list_team_members(db, current_user, team_id)]
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/teams/{team_id}/members", summary="Añadir miembros al equipo")
def add_team_members(team_id: str, payload: TeamMemberUpsert, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = ws_svc.add_team_members(db, current_user, team_id, payload.user_ids, role=payload.role)
    return APIResponse.ok(data={"added": n})


@router.delete("/teams/{team_id}/members/{user_id}", summary="Quitar miembro del equipo")
def remove_team_member(team_id: str, user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_team", team_id, action="delete")
    ws_svc.remove_team_member(db, current_user, team_id, user_id)
    return APIResponse.ok(data={"removed": True})


# ── Channels ─────────────────────────────────────────────────────────────────
@router.get("/channels", response_model=APIListResponse[ChannelOut], summary="Listar canales accesibles")
def list_channels(team_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out: List[ChannelOut] = [
        ChannelOut(
            id=r.canal.id, conversation_id=r.canal.conversation_id,
            team_id=r.canal.team_id, name=r.canal.name, slug=r.canal.slug,
            topic=r.canal.topic, description=r.canal.description,
            channel_type=r.canal.channel_type, is_default=r.canal.is_default,
            is_archived=r.canal.is_archived, project_id=r.canal.project_id,
            member_count=r.miembros,
            # El no-leido por canal se sirve en `/conversations`, que lo calcula
            # en una sola consulta agrupada. Aqui se manda 0 igual que antes en
            # vez de repetir ese calculo por canal.
            unread_count=0,
            last_activity_at=None,
        )
        for r in ws_svc.list_channels_con_recuentos(db, current_user, team_id=team_id)
    ]
    return APIListResponse.ok(items=out, total=len(out))


@router.post("/channels", response_model=APIResponse[ChannelOut], summary="Crear canal")
def create_channel(payload: ChannelCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = ws_svc.create_channel(
        db, current_user,
        team_id=payload.team_id, name=payload.name, slug=payload.slug,
        topic=payload.topic, description=payload.description,
        channel_type=payload.channel_type, is_default=payload.is_default,
        project_id=payload.project_id, initial_member_ids=payload.initial_member_ids,
    )
    return APIResponse.ok(data=ChannelOut(
        id=c.id, conversation_id=c.conversation_id, team_id=c.team_id,
        name=c.name, slug=c.slug, topic=c.topic, description=c.description,
        channel_type=c.channel_type, is_default=c.is_default, is_archived=c.is_archived,
        project_id=c.project_id, member_count=1,
    ))


@router.patch("/channels/{channel_id}", response_model=APIResponse[ChannelOut], summary="Actualizar canal")
def update_channel(channel_id: str, payload: ChannelUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ch = ws_svc.update_channel(db, current_user, channel_id, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=ChannelOut(
        id=ch.id, conversation_id=ch.conversation_id, team_id=ch.team_id,
        name=ch.name, slug=ch.slug, topic=ch.topic, description=ch.description,
        channel_type=ch.channel_type, is_default=ch.is_default, is_archived=ch.is_archived,
        project_id=ch.project_id,
    ))


@router.post("/channels/{channel_id}/members", summary="Añadir miembros al canal")
def add_channel_members(channel_id: str, payload: TeamMemberUpsert, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = ws_svc.add_channel_members(db, current_user, channel_id, payload.user_ids)
    return APIResponse.ok(data={"added": n})


@router.get("/channels/{channel_id}/members", response_model=APIListResponse[ChannelMemberOut], summary="Miembros del canal")
def list_channel_members(channel_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = [
        ChannelMemberOut(**m)
        for m in ws_svc.list_channel_members(db, current_user, channel_id)
    ]
    return APIListResponse.ok(items=out, total=len(out))


# ── Direct + Group ───────────────────────────────────────────────────────────
@router.post("/direct/open", summary="Abrir o reusar conversación 1:1")
def open_direct(payload: DirectOpenIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = ws_svc.open_direct(
        db, current_user,
        target_user_id=payload.user_id,
        target_client_id=payload.client_user_id,
    )
    return APIResponse.ok(data={"id": d.id, "conversation_id": d.conversation_id})


@router.post("/groups", summary="Crear grupo ad-hoc")
def create_group(payload: GroupCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = ws_svc.create_group(
        db, current_user,
        title=payload.title,
        user_ids=payload.user_ids, client_user_ids=payload.client_user_ids,
    )
    return APIResponse.ok(data={"id": g.id, "conversation_id": g.conversation_id})


# ── Conversation members (group + private channel via conversation_id) ──────
@router.get("/conversations/{conversation_id}/members", summary="Listar miembros de la conversación")
def list_conversation_members(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return APIListResponse.ok(
        items=ws_svc.list_conversation_members(db, current_user, conversation_id))


@router.post("/conversations/{conversation_id}/members", summary="Añadir miembros a un grupo")
def add_conversation_members(
    conversation_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = ws_svc.add_conversation_members(
        db, current_user, conversation_id,
        payload.get("user_ids") or [], payload.get("client_user_ids") or [])
    return APIResponse.ok(data={"added": n})


@router.delete("/conversations/{conversation_id}/members/{user_id}", summary="Quitar miembro de un grupo")
def remove_conversation_member(
    conversation_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_abac(db, current_user, "collaboration_conversation", conversation_id, action="delete")
    ws_svc.remove_conversation_member(db, current_user, conversation_id, user_id)
    return APIResponse.ok(data={"ok": True})


# ── Conversation listing (sidebar) ───────────────────────────────────────────
@router.get("/conversations", summary="Lista unificada de conversaciones (sidebar)")
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(items=ws_svc.list_conversations_for_user(db, current_user))


@router.get("/conversations/{conversation_id}", response_model=APIResponse[ConversationOut], summary="Detalle de conversación")
def get_conversation(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(
        data=ConversationOut(**ws_svc.conversation_detail(db, current_user, conversation_id)))


# ── Presence ─────────────────────────────────────────────────────────────────
@router.get("/presence", summary="Presencia de mi org (con nombre de usuario)")
def list_presence(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(items=ws_svc.list_presence(db, current_user))


@router.post("/presence/me", summary="Actualizar mi presencia")
def update_presence(payload: PresenceIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    estado = ws_svc.update_presence(
        db, current_user, status=payload.status, custom_message=payload.custom_message)
    return APIResponse.ok(data={"status": estado})


# ── Drafts ──────────────────────────────────────────────────────────────────
@router.put("/conversations/{conversation_id}/draft", summary="Guardar borrador")
def upsert_draft(conversation_id: str, payload: DraftIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.messages import upsert_draft as _upsert
    _upsert(db, current_user, conversation_id, payload.body, payload.metadata_json, payload.parent_message_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/conversations/{conversation_id}/draft", summary="Leer mi borrador")
def get_draft(conversation_id: str, parent_message_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.messages import get_draft as _get
    d = _get(db, current_user, conversation_id, parent_message_id)
    if not d:
        return APIResponse.ok(data={"body": "", "metadata_json": {}})
    return APIResponse.ok(data={"body": d.body, "metadata_json": d.metadata_json or {}})


# ── Notifications ────────────────────────────────────────────────────────────
@router.get("/notifications", summary="Mis notificaciones")
def list_notifications(unread_only: bool = False, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(
        items=ws_svc.list_notifications(db, current_user, unread_only=unread_only))


@router.post("/notifications/mark-all-read", summary="Marcar todas como leídas")
def mark_all_notifications_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(
        data={"marked": ws_svc.mark_all_notifications_read(db, current_user)})


@router.post("/notifications/{notif_id}/read", summary="Marcar notificación leída")
def mark_notif_read(notif_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws_svc.mark_notification_read(db, current_user, notif_id)
    return APIResponse.ok(data={"ok": True})


# ── Notification rules ──────────────────────────────────────────────────────
@router.get("/notification-rules", summary="Mis reglas de notificación")
def list_rules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(items=ws_svc.list_notification_rules(db, current_user))


@router.put("/notification-rules", summary="Crear / actualizar regla")
def upsert_rule(payload: NotificationRuleIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rid = ws_svc.upsert_notification_rule(
        db, current_user, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data={"id": rid})


# ── Search ───────────────────────────────────────────────────────────────────
@router.get("/search/saved", summary="Mis búsquedas guardadas")
def list_saved_searches(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(items=ws_svc.list_saved_searches(db, current_user))


@router.post("/search/saved", summary="Guardar búsqueda")
def save_search(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=ws_svc.save_search(
        db, current_user,
        name=payload.get("name") or "", query=payload.get("query") or "",
        is_pinned=bool(payload.get("is_pinned", False)),
    ))


@router.delete("/search/saved/{saved_id}", summary="Eliminar búsqueda guardada")
def delete_saved_search(saved_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_saved_search", saved_id, action="delete")
    ws_svc.delete_saved_search(db, current_user, saved_id)
    return APIResponse.ok(data={"ok": True})


@router.post("/search/saved/{saved_id}/run", response_model=APIResponse[SearchResponse], summary="Ejecutar búsqueda guardada")
def run_saved_search(saved_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    consulta = ws_svc.registrar_uso_de_busqueda(db, current_user, saved_id)
    hits = search_engine.search(
        db, organization_id=_org(current_user), query=consulta,
        conversation_ids=ws_svc.conversaciones_accesibles(db, current_user),
        limit=ws_svc.MAX_RESULTADOS_DE_BUSQUEDA,
    )
    return APIResponse.ok(data=SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits)))


@router.get("/mention-suggestions", summary="Sugerencias para autocomplete @")
def mention_suggestions(
    q: str = Query("", max_length=80),
    conversation_id: Optional[str] = None,
    limit: int = Query(8, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve users mencionables (limitados a la org y a los miembros del canal
    si se pasa conversation_id) + grupos `everyone`/`channel`/`here`."""
    return APIResponse.ok(data=ws_svc.mention_suggestions(
        db, current_user, q=q, conversation_id=conversation_id, limit=limit))


@router.get("/search", response_model=APIResponse[SearchResponse], summary="Búsqueda global")
def search(
    q: str = Query("", min_length=0, max_length=500),
    conversation_id: Optional[str] = None,
    author_user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _org(current_user)
    # Acotado a las conversaciones a las que el usuario tiene acceso; si pide una
    # concreta, el servicio comprueba que sea suya antes de restringir a ella.
    accessible = ws_svc.conversaciones_accesibles(db, current_user, conversation_id)
    hits = search_engine.search(
        db, organization_id=org, query=q,
        conversation_ids=accessible, author_user_id=author_user_id,
        date_from=date_from, date_to=date_to, limit=limit,
    )
    return APIResponse.ok(data=SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits)))
