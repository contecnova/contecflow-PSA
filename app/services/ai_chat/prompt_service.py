"""
ai_prompt_service — Prompt template management for AI modules.
"""
import logging
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_chat import AIPromptTemplate

_logger = logging.getLogger("v16_core")


def get_prompt(db: Session, module: str, default: str) -> str:
    """Return the active prompt template for *module* from the DB.
    Falls back to *default* if no active template exists or if the DB call fails.
    """
    try:
        tpl = db.query(AIPromptTemplate).filter(
            AIPromptTemplate.module == module,
            AIPromptTemplate.is_active == True,
        ).order_by(AIPromptTemplate.version.desc()).first()
        if tpl:
            return tpl.content
    except Exception as exc:
        _logger.warning(f"Could not load prompt template for '{module}': {exc}")
    return default


def list_prompts(db: Session, module=None) -> list:
    """List all prompt templates, optionally filtered by module."""
    q = db.query(AIPromptTemplate)
    if module:
        q = q.filter(AIPromptTemplate.module == module)
    templates = q.order_by(AIPromptTemplate.module, AIPromptTemplate.version.desc()).all()
    return [{
        "id": t.id, "module": t.module, "name": t.name,
        "version": t.version, "is_active": t.is_active,
        "content_preview": (t.content or "")[:200],
        "created_at": str(t.created_at)[:16],
    } for t in templates]


def get_prompt_detail(db: Session, prompt_id: str) -> dict:
    """Get full prompt template content."""
    tpl = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == prompt_id).first()
    if not tpl:
        raise ValueError("not_found")
    return {
        "id": tpl.id, "module": tpl.module, "name": tpl.name,
        "content": tpl.content, "version": tpl.version, "is_active": tpl.is_active,
        "created_at": str(tpl.created_at)[:16],
    }


def create_prompt_template(db: Session, payload, user_id: str) -> dict:
    """Create a new prompt template version."""
    max_version = db.query(func.max(AIPromptTemplate.version)).filter(
        AIPromptTemplate.module == payload.module,
    ).scalar() or 0

    if payload.is_active:
        db.query(AIPromptTemplate).filter(
            AIPromptTemplate.module == payload.module,
            AIPromptTemplate.is_active == True,
        ).update({"is_active": False})

    tpl = AIPromptTemplate(
        module=payload.module,
        name=payload.name,
        content=payload.content,
        version=max_version + 1,
        is_active=payload.is_active,
        created_by=user_id,
    )
    db.add(tpl); db.commit(); db.refresh(tpl)
    return {"id": tpl.id, "module": tpl.module, "version": tpl.version, "is_active": tpl.is_active}


def toggle_prompt_template(db: Session, prompt_id: str, payload: dict) -> dict:
    """Activate/deactivate a prompt template version."""
    tpl = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == prompt_id).first()
    if not tpl:
        raise ValueError("not_found")
    if "is_active" in payload:
        if payload["is_active"]:
            db.query(AIPromptTemplate).filter(
                AIPromptTemplate.module == tpl.module,
                AIPromptTemplate.id != prompt_id,
                AIPromptTemplate.is_active == True,
            ).update({"is_active": False})
        tpl.is_active = payload["is_active"]
    if "name" in payload:
        tpl.name = payload["name"]
    db.commit()
    return {"ok": True, "version": tpl.version, "is_active": tpl.is_active}


def delete_prompt_template(db: Session, prompt_id: str) -> dict:
    """Delete a prompt template."""
    tpl = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == prompt_id).first()
    if not tpl:
        raise ValueError("not_found")
    db.delete(tpl); db.commit()
    return {"ok": True}
