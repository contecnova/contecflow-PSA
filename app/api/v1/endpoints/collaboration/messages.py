"""Messages, threads, reactions, mentions, reads, pins, saved."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationMention, CollaborationMessage,
)
from app.schemas.collaboration import (
    MessageCreate, MessageOut, MessageUpdate, MessageVersionOut,
    PinIn, ReactionToggle, ReadUpdate, SaveIn,
)
from app.services.collaboration import messages as msg_svc
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.traffic_control_service import consume_quota
from app.core.responses import APIListResponse, APIResponse

router = APIRouter()

MSG_USER_LIMIT_PER_MIN = 40
MSG_CONV_LIMIT_PER_MIN = 160


@router.get("/conversations/{conversation_id}/messages", response_model=APIListResponse[MessageOut], summary="Listar mensajes")
def list_messages(
    conversation_id: str,
    before: Optional[str] = None,
    limit: int = Query(50, le=200),
    thread_root: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Membership + ABAC explícito por conversación (defensa en profundidad).
    assert_conversation_access(db, current_user, conversation_id)
    enforce_abac(db, current_user, "collaboration_message", resource_id=conversation_id, action="read")
    rows = msg_svc.list_messages(db, current_user, conversation_id, before=before, limit=limit, thread_root=thread_root)
    items = [MessageOut(**msg_svc._serialize_message(db, m)) for m in rows]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/messages", response_model=APIResponse[MessageOut], summary="Enviar mensaje")
def send_message(payload: MessageCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Membership + ABAC por conversación cuando se envía por conversation_id.
    if payload.conversation_id:
        assert_conversation_access(db, current_user, payload.conversation_id)
        enforce_abac(db, current_user, "collaboration_message", resource_id=payload.conversation_id, action="send")

    org = _org(current_user)
    user_quota = consume_quota(
        db,
        scope="collab.message.user",
        tenant_id=org,
        subject=current_user.id,
        limit=MSG_USER_LIMIT_PER_MIN,
        window_seconds=60,
    )
    if not user_quota["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Message rate limit exceeded. Retry in {user_quota['retry_after']}s",
        )

    conv_subject = payload.conversation_id or payload.channel_id or payload.direct_id or payload.group_id or "unknown"
    conv_quota = consume_quota(
        db,
        scope="collab.message.channel",
        tenant_id=org,
        subject=conv_subject,
        limit=MSG_CONV_LIMIT_PER_MIN,
        window_seconds=60,
    )
    if not conv_quota["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Channel traffic limit exceeded. Retry in {conv_quota['retry_after']}s",
        )
    msg = msg_svc.send_message(
        db, current_user,
        body=payload.body,
        conversation_id=payload.conversation_id,
        channel_id=payload.channel_id,
        direct_id=payload.direct_id,
        group_id=payload.group_id,
        parent_message_id=payload.parent_message_id,
        type=payload.type,
        metadata_json=payload.metadata_json,
        mention_user_ids=payload.mention_user_ids,
        mention_client_ids=payload.mention_client_ids,
        is_everyone=payload.is_everyone,
        scheduled_for=payload.scheduled_for,
        linked_task_id=payload.linked_task_id,
        linked_ticket_id=payload.linked_ticket_id,
    )
    # If the message contains slash commands (/ask /task etc) trigger bot pipeline
    try:
        from app.services.collaboration import bots as bot_svc
        bot_svc.maybe_handle_inline_command(db, current_user, msg)
    except Exception:  # noqa: S110
        pass  # bots are best-effort
    return APIResponse.ok(data=MessageOut(**msg_svc._serialize_message(db, msg)))


@router.patch("/messages/{message_id}", response_model=APIResponse[MessageOut], summary="Editar mensaje")
def edit_message(message_id: str, payload: MessageUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg = msg_svc.edit_message(db, current_user, message_id, payload.body or "", payload.metadata_json)
    return APIResponse.ok(data=MessageOut(**msg_svc._serialize_message(db, msg)))


@router.delete("/messages/{message_id}", summary="Borrar mensaje")
def delete_message(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_message", message_id, action="delete")
    msg_svc.delete_message(db, current_user, message_id)
    return APIResponse.ok(data={"deleted": True})


@router.get("/messages/{message_id}/versions", response_model=APIListResponse[MessageVersionOut], summary="Historial del mensaje")
def get_versions(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = msg_svc.get_message_versions(db, current_user, message_id)
    items = [MessageVersionOut(
        id=r.id, body=r.body, edited_by_user_id=r.edited_by_user_id, edited_at=r.edited_at
    ) for r in rows]
    return APIListResponse.ok(items=items, total=len(items))


# ── Reactions ────────────────────────────────────────────────────────────────
@router.post("/messages/{message_id}/reactions", summary="Toggle reacción")
def toggle_reaction(message_id: str, payload: ReactionToggle, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=msg_svc.toggle_reaction(db, current_user, message_id, payload.emoji))


# ── Reads ────────────────────────────────────────────────────────────────────
@router.post("/conversations/{conversation_id}/read", summary="Marcar leído")
def mark_read(conversation_id: str, payload: ReadUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.mark_read(db, current_user, conversation_id, payload.last_message_id)
    return APIResponse.ok(data={"ok": True})


# ── Pins ─────────────────────────────────────────────────────────────────────
@router.post("/conversations/{conversation_id}/pins", summary="Pinear mensaje")
def pin(conversation_id: str, payload: PinIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.pin_message(db, current_user, payload.message_id)
    return APIResponse.ok(data={"ok": True})


@router.delete("/conversations/{conversation_id}/pins/{message_id}", summary="Quitar pin")
def unpin(conversation_id: str, message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_message", message_id, action="delete")
    msg_svc.unpin_message(db, current_user, message_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/conversations/{conversation_id}/pins", summary="Lista de pins")
def list_pins(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIListResponse.ok(items=msg_svc.list_pins(db, current_user, conversation_id))


# ── Saved ────────────────────────────────────────────────────────────────────
@router.post("/saved", summary="Guardar mensaje (mis guardados)")
def save_msg(payload: SaveIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.save_message(db, current_user, payload.message_id, payload.note)
    return APIResponse.ok(data={"ok": True})


@router.delete("/saved/{message_id}", summary="Quitar de guardados")
def unsave_msg(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_abac(db, current_user, "collaboration_saved_message", message_id, action="delete")
    msg_svc.unsave_message(db, current_user, message_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/saved", response_model=APIListResponse[dict], summary="Mis mensajes guardados")
def list_saved(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = msg_svc.list_saved(db, current_user)
    out = []
    for r in rows:
        m = db.query(CollaborationMessage).filter(CollaborationMessage.id == r.message_id).first()
        if m:
            out.append({
                "id": r.id, "message_id": r.message_id, "note": r.note, "saved_at": r.saved_at,
                "preview": (m.body or "")[:200],
                "conversation_id": m.conversation_id,
            })
    return APIListResponse.ok(items=out, total=len(out))


# ── Mentions (mine) ──────────────────────────────────────────────────────────
@router.post("/messages/{message_id}/link", summary="Anclar mensaje a entidad PSA (task/ticket/deliverable/risk)")
def link_message(
    message_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.collaboration import audit_log
    from app.services.collaboration._permissions import _org as _org_fn
    org = _org_fn(current_user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    assert_conversation_access(db, current_user, msg.conversation_id)
    kind = (payload.get("kind") or "").lower()
    eid = payload.get("id")
    if kind not in {"task", "ticket", "deliverable", "risk"}:
        raise HTTPException(400, "kind debe ser task|ticket|deliverable|risk")
    setattr(msg, f"linked_{kind}_id", eid)
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="message.linked", entity_type="message", entity_id=message_id,
        payload={"kind": kind, "linked_id": eid},
    )
    db.commit()
    return APIResponse.ok(data={"ok": True, "kind": kind, "linked_id": eid})


@router.get("/messages/{message_id}/link/candidates", summary="Buscar candidatos para anclar")
def link_candidates(
    message_id: str,
    kind: str = Query(...),
    q: str = Query(""),
    limit: int = Query(10, le=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.collaboration._permissions import _org as _org_fn
    org = _org_fn(current_user)
    msg = db.query(CollaborationMessage).filter(
        CollaborationMessage.id == message_id, CollaborationMessage.organization_id == org,
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if kind == "task":
        from app.models.task import Task
        from app.models.collaboration import CollaborationChannel
        ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == msg.conversation_id).first()
        qx = db.query(Task)
        if hasattr(Task, "organization_id"):
            qx = qx.filter(Task.organization_id == org)
        if ch and ch.project_id:
            qx = qx.filter(Task.project_id == ch.project_id)
        if q:
            qx = qx.filter(Task.title.ilike(f"%{q}%"))
        rows = qx.order_by(Task.created_at.desc()).limit(limit).all()
        return APIListResponse.ok(items=[{"id": t.id, "label": f"{t.code or '?'} · {t.title}"} for t in rows])
    if kind == "ticket":
        from app.models.service_desk import Ticket
        qx = db.query(Ticket)
        if hasattr(Ticket, "organization_id"):
            qx = qx.filter(Ticket.organization_id == org)
        if q:
            qx = qx.filter(Ticket.title.ilike(f"%{q}%"))
        rows = qx.order_by(Ticket.created_at.desc()).limit(limit).all()
        return APIListResponse.ok(items=[{"id": t.id, "label": f"{getattr(t, 'number', t.id[:8])} · {t.title}"} for t in rows])
    return APIListResponse.ok(items=[])


@router.get("/mentions", summary="Mis menciones recientes")
def list_my_mentions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationMention).filter(
        CollaborationMention.mentioned_user_id == current_user.id,
    ).order_by(CollaborationMention.created_at.desc()).limit(100).all()
    out = []
    for r in rows:
        m = db.query(CollaborationMessage).filter(CollaborationMessage.id == r.message_id).first()
        if m and m.status != "deleted":
            out.append({
                "id": r.id, "message_id": r.message_id,
                "preview": (m.body or "")[:200],
                "conversation_id": m.conversation_id,
                "created_at": r.created_at,
            })
    return APIListResponse.ok(items=out)
