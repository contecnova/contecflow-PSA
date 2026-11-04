"""
ai_agent_execution_service — AI agent execution management and step tracking.
"""
import json
import logging
from sqlalchemy.orm import Session, joinedload

from app.models.ai_chat import AIAgentExecution

_logger = logging.getLogger("v16_core")


def create_agent_execution(db: Session, user_id: str, instruction: str):
    """Create a new agent execution task."""
    execution = AIAgentExecution(
        user_id=user_id,
        instruction=instruction,
        status="queued",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def get_agent_status(db: Session, exec_id: str, user_id: str) -> dict:
    """Get execution status for a specific agent run."""
    execution = db.query(AIAgentExecution).filter(
        AIAgentExecution.id == exec_id,
        AIAgentExecution.user_id == user_id,
    ).first()
    if not execution:
        raise ValueError("not_found")
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "result": execution.result,
        "steps_count": len(execution.steps) if hasattr(execution, "steps") else 0,
        "created_at": str(execution.created_at)[:19],
        # Auditoria 2026-08: aqui habia `execution.updated_at`, y esa columna
        # **no existe** en `ai_agent_executions`. La marca de fin es
        # `completed_at`. El `if ... else None` no protegia de nada: el
        # `AttributeError` salta al **leer** el atributo, antes de evaluar la
        # condicion, asi que `get_agent_status` reventaba SIEMPRE — el estado de
        # una ejecucion de agente de IA no se podia consultar.
        #
        # La clave de la respuesta se conserva para no cambiar el contrato.
        "updated_at": (
            str(execution.completed_at)[:19] if execution.completed_at else None),
    }


def list_agent_executions(db: Session, user_id: str, limit: int = 20) -> list:
    """List all agent executions for a user."""
    execs = db.query(AIAgentExecution).filter(
        AIAgentExecution.user_id == user_id,
    ).order_by(AIAgentExecution.created_at.desc()).limit(limit).all()
    return [{
        "execution_id": e.id,
        # Auditoria 2026-11: la pantalla leia `id` y `result`, que no venian.
        "id": e.id,
        "instruction": e.instruction[:100],
        "status": e.status,
        "result": e.result,
        "steps_count": e.steps_count,
        "created_at": str(e.created_at)[:19],
    } for e in execs]


def get_agent_detail_with_steps(db: Session, exec_id: str) -> dict:
    """Get full agent execution detail with all tool call steps."""
    execution = db.query(AIAgentExecution).options(
        joinedload(AIAgentExecution.steps)
    ).filter(AIAgentExecution.id == exec_id).first()
    if not execution:
        raise ValueError("not_found")
    steps = []
    if hasattr(execution, "steps"):
        steps = [{
            "step": s.step_number,
            "tool": s.tool_name,
            "input": json.loads(s.tool_input or "{}"),
            "output": json.loads(s.tool_output or "{}"),
        } for s in sorted(execution.steps, key=lambda x: x.step_number)]
    return {
        "execution_id": execution.id,
        "instruction": execution.instruction,
        "status": execution.status,
        "result": execution.result,
        "steps": steps,
        "created_at": str(execution.created_at)[:19],
    }


def guardar_ejecucion_en_streaming(usuario, instruccion: str, final, error) -> None:
    """Guarda en el historial una ejecucion hecha en streaming.

    La respuesta en streaming sigue viva despues de que la peticion cierre su
    sesion, asi que se abre una propia y se le publica el tenant del usuario.
    Un fallo aqui no rompe la respuesta: queda en el log.
    """
    from datetime import datetime, timezone
    from app.db.session import SessionLocal, publicar_contexto_de_tenant
    try:
        with SessionLocal() as db:
            publicar_contexto_de_tenant(db, usuario)
            db.add(AIAgentExecution(
                user_id=usuario.id, organization_id=getattr(usuario, "organization_id", None),
                instruction=instruccion, status="done" if final and not error else "failed",
                result=(final or {}).get("result"), steps_count=len((final or {}).get("steps") or []),
                error=(error or None) and str(error)[:500], completed_at=datetime.now(timezone.utc),
            ))
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
    except Exception:
        logging.getLogger(__name__).exception("NexusAgent: no se pudo guardar la ejecucion en streaming")
