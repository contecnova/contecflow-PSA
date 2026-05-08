"""Messages, threads, reactions, mentions, reads, pins, saved."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationMention, CollaborationMessage,
    CollaborationMessageVersion,
)
from app.schemas.collaboration import (
    MessageCreate, MessageOut, MessageUpdate, MessageVersionOut,
    PinIn, ReactionToggle, ReadUpdate, SaveIn,
)
from app.services.collaboration import messages as msg_svc
from app.services.collaboration._permissions import _org, assert_conversation_access

router = APIRouter()


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut], summary="Listar mensajes")
def list_messages(
    conversation_id: str,
    before: Optional[str] = None,
    limit: int = Query(50, le=200),
    thread_root: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = msg_svc.list_messages(db, current_user, conversation_id, before=before, limit=limit, thread_root=thread_root)
    return [MessageOut(**msg_svc._serialize_message(db, m)) for m in rows]


@router.post("/messages", response_model=MessageOut, summary="Enviar mensaje")
def send_message(payload: MessageCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
    except Exception:
        pass  # bots are best-effort
    return MessageOut(**msg_svc._serialize_message(db, msg))


@router.patch("/messages/{message_id}", response_model=MessageOut, summary="Editar mensaje")
def edit_message(message_id: str, payload: MessageUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg = msg_svc.edit_message(db, current_user, message_id, payload.body or "", payload.metadata_json)
    return MessageOut(**msg_svc._serialize_message(db, msg))


@router.delete("/messages/{message_id}", summary="Borrar mensaje")
def delete_message(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.delete_message(db, current_user, message_id)
    return {"deleted": True}


@router.get("/messages/{message_id}/versions", response_model=List[MessageVersionOut], summary="Historial del mensaje")
def get_versions(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = msg_svc.get_message_versions(db, current_user, message_id)
    return [MessageVersionOut(
        id=r.id, body=r.body, edited_by_user_id=r.edited_by_user_id, edited_at=r.edited_at
    ) for r in rows]


# ── Reactions ────────────────────────────────────────────────────────────────
@router.post("/messages/{message_id}/reactions", summary="Toggle reacción")
def toggle_reaction(message_id: str, payload: ReactionToggle, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return msg_svc.toggle_reaction(db, current_user, message_id, payload.emoji)


# ── Reads ────────────────────────────────────────────────────────────────────
@router.post("/conversations/{conversation_id}/read", summary="Marcar leído")
def mark_read(conversation_id: str, payload: ReadUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.mark_read(db, current_user, conversation_id, payload.last_message_id)
    return {"ok": True}


# ── Pins ─────────────────────────────────────────────────────────────────────
@router.post("/conversations/{conversation_id}/pins", summary="Pinear mensaje")
def pin(conversation_id: str, payload: PinIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.pin_message(db, current_user, payload.message_id)
    return {"ok": True}


@router.delete("/conversations/{conversation_id}/pins/{message_id}", summary="Quitar pin")
def unpin(conversation_id: str, message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.unpin_message(db, current_user, message_id)
    return {"ok": True}


@router.get("/conversations/{conversation_id}/pins", summary="Lista de pins")
def list_pins(conversation_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return msg_svc.list_pins(db, current_user, conversation_id)


# ── Saved ────────────────────────────────────────────────────────────────────
@router.post("/saved", summary="Guardar mensaje (mis guardados)")
def save_msg(payload: SaveIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.save_message(db, current_user, payload.message_id, payload.note)
    return {"ok": True}


@router.delete("/saved/{message_id}", summary="Quitar de guardados")
def unsave_msg(message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg_svc.unsave_message(db, current_user, message_id)
    return {"ok": True}


@router.get("/saved", summary="Mis mensajes guardados")
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
    return out


# ── Mentions (mine) ──────────────────────────────────────────────────────────
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
    return out
