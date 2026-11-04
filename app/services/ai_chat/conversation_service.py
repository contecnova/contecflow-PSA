"""
ai_conversation_service — AI conversation management (create, retrieve, archive).
"""
from sqlalchemy.orm import joinedload, Session

from app.models.ai_chat import AIConversation


def list_conversations(db: Session, user_id: str) -> list:
    """List active conversations for a user, ordered by recency."""
    convs = db.query(AIConversation).filter(
        AIConversation.user_id == user_id,
        AIConversation.is_archived == False,
    ).order_by(AIConversation.updated_at.desc()).limit(50).all()
    return [{
        "id": c.id, "title": c.title or "Nueva conversación",
        "context_type": c.context_type,
        "message_count": len(c.messages),
        "updated_at": str(c.updated_at or c.created_at)[:16],
    } for c in convs]


def get_conversation(db: Session, conv_id: str, user_id: str) -> dict:
    """Get full conversation with message history."""
    conv = db.query(AIConversation).options(joinedload(AIConversation.messages)).filter(
        AIConversation.id == conv_id,
        AIConversation.user_id == user_id,
    ).first()
    if not conv:
        raise ValueError("not_found")
    return {
        "id": conv.id, "title": conv.title,
        "context_type": conv.context_type,
        "messages": [{
            "id": m.id, "role": m.role, "content": m.content,
            "created_at": str(m.created_at)[:19],
        } for m in conv.messages],
    }


def archive_conversation(db: Session, conv_id: str, user_id: str) -> dict:
    """Archive a conversation."""
    conv = db.query(AIConversation).filter(
        AIConversation.id == conv_id,
        AIConversation.user_id == user_id,
    ).first()
    if not conv:
        raise ValueError("not_found")
    conv.is_archived = True
    db.commit()
    return {"ok": True}


def archive_all_conversations(db: Session, user_id: str) -> dict:
    """Archive all active conversations for a user."""
    updated = db.query(AIConversation).filter(
        AIConversation.user_id == user_id,
        AIConversation.is_archived == False,
    ).update({AIConversation.is_archived: True}, synchronize_session=False)
    db.commit()
    return {"ok": True, "archived": updated}


def get_or_create_conversation(db: Session, conversation_id, user_id: str, context_type=None, context_id=None):
    """Get existing conversation or create new one."""
    conv = None
    if conversation_id:
        conv = db.query(AIConversation).filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == user_id,
        ).first()
    if not conv and context_type == "inline_editor":
        # El editor en linea pide una reescritura suelta: una sola conversacion
        # por usuario, no una nueva por cada «/mejorar» en el historial.
        conv = db.query(AIConversation).filter(
            AIConversation.user_id == user_id,
            AIConversation.context_type == "inline_editor",
        ).order_by(AIConversation.created_at.desc()).first()
    if not conv:
        conv = AIConversation(
            user_id=user_id,
            context_type=context_type,
            context_id=context_id,
        )
        db.add(conv); db.flush()
    return conv
