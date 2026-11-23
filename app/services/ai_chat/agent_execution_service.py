"""
ai_agent_execution_service — AI agent execution management and step tracking.
"""
import json
import logging
from sqlalchemy.orm import Session, joinedload

from app.models.ai_chat import AIAgentExecution

_logger = logging.getLogger("v16_core")


def create_agent_execution(db: Session, user_id: str, instruction: str):
    """Create a new agent execution task.

    Baja (auditoría 22-11-2026): con la empresa de la persona (antes sin
    `organization_id`: la ejecución quedaba fuera del filtro y de la retención).
    """
    from app.models.user import User
    org = (db.info or {}).get("organization_id") or db.query(User.organization_id).filter(
        User.id == user_id).scalar()
    execution = AIAgentExecution(
        organization_id=org,
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


def get_agent_detail_with_steps(db: Session, exec_id: str, user_id: str) -> dict:
    """Get full agent execution detail with all tool call steps.

    Segunda auditoria 2026-11: solo el dueno. Antes se buscaba por id sin
    filtrar por usuario, y cualquiera con el id leia la instruccion, el
    resultado y las llamadas a herramientas de otro. Misma regla que el
    historial (`list_agent_executions`) y el sondeo (`get_agent_status`).
    """
    execution = db.query(AIAgentExecution).options(
        joinedload(AIAgentExecution.steps)
    ).filter(
        AIAgentExecution.id == exec_id,
        AIAgentExecution.user_id == user_id,
    ).first()
    if not execution:
        raise ValueError("not_found")
    steps = []
    if hasattr(execution, "steps"):
        steps = [{
            # Auditoría 22-11-2026 (A7): id y estado para aprobar o rechazar el paso.
            "id": s.id,
            "status": s.status,
            "requires_approval": bool(s.requires_approval),
            "is_approved": s.is_approved,
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


def decidir_paso(db: Session, usuario, exec_id: str, step_id: str, aprobar: bool) -> dict:
    """Aprobación humana de una escritura del agente (auditoría 22-11-2026, A7).

    Antes el agente devolvía «pending_approval» y decía «apruébalo vía
    /agent/{id}/approve (futuro)»: ese endpoint no existía, así que las
    escrituras sin `auto_approve` no se ejecutaban nunca. Ahora quien lanzó la
    ejecución aprueba (o rechaza) cada paso pendiente y se ejecuta EXACTAMENTE
    la herramienta y los argumentos guardados, con sus permisos, sin volver a
    preguntar al modelo. Queda auditado.
    """
    from datetime import datetime, timezone
    from app.core.codigos_de_error import error
    from app.models.ai_chat import AIAgentStep
    from app.services.audit import audit_log
    execution = db.query(AIAgentExecution).filter(
        AIAgentExecution.id == exec_id, AIAgentExecution.user_id == usuario.id,
    ).first()
    if not execution:
        raise error(404, "no_encontrado", que="ejecucion")
    paso = db.query(AIAgentStep).filter(
        AIAgentStep.id == step_id, AIAgentStep.execution_id == execution.id,
    ).with_for_update().first()
    if not paso:
        raise error(404, "no_encontrado", que="paso")
    if not paso.requires_approval or paso.is_approved is not None:
        raise error(409, "agente_paso_no_pendiente")
    ahora = datetime.now(timezone.utc)
    if aprobar:
        from app.services.ai_chat.tool_execution_service import execute_tool
        try:
            entrada = json.loads(paso.tool_input or "{}")
        except ValueError:
            entrada = {}
        resultado = execute_tool(paso.tool_name, entrada, db, usuario)
        paso.tool_output = json.dumps(resultado, default=str)
        paso.status = "failed" if isinstance(resultado, dict) and "error" in resultado else "done"
        paso.is_approved = True
    else:
        resultado = {"status": "rejected"}
        paso.status = "skipped"
        paso.is_approved = False
    execution.approved_by = usuario.id
    execution.approved_at = ahora
    quedan = db.query(AIAgentStep.id).filter(
        AIAgentStep.execution_id == execution.id, AIAgentStep.requires_approval.is_(True),
        AIAgentStep.is_approved.is_(None), AIAgentStep.id != paso.id,
    ).first()
    if not quedan and execution.status == "awaiting_approval":
        execution.status = "done"
    audit_log(db, usuario, "AI_AGENT_APPROVE" if aprobar else "AI_AGENT_REJECT", "ai_agent_steps", paso.id,
              paso.tool_name, new_values={"execution_id": execution.id, "tool": paso.tool_name,
                                          "approved": bool(aprobar)})
    db.commit()
    return {"execution_id": execution.id, "step_id": paso.id, "tool": paso.tool_name,
            "approved": bool(aprobar), "status": paso.status, "result": resultado,
            "execution_status": execution.status}


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
            from app.models.ai_chat import AIAgentStep
            pasos = (final or {}).get("steps") or []
            pendiente = [isinstance(p, dict) and isinstance(p.get("output"), dict)
                         and p["output"].get("status") == "pending_approval" for p in pasos]
            ejecucion = AIAgentExecution(
                user_id=usuario.id, organization_id=getattr(usuario, "organization_id", None),
                instruction=instruccion,
                status=("awaiting_approval" if any(pendiente) else "done") if final and not error else "failed",
                result=(final or {}).get("result"), steps_count=len(pasos),
                error=(error or None) and str(error)[:500], completed_at=datetime.now(timezone.utc),
            )
            db.add(ejecucion)
            db.flush()
            # Auditoría 22-11-2026 (A7): los pasos, también en streaming, para
            # poder aprobar después las escrituras pendientes.
            for p, pend in zip(pasos, pendiente):  # noqa: B905
                if not isinstance(p, dict):
                    continue
                db.add(AIAgentStep(
                    execution_id=ejecucion.id, organization_id=getattr(usuario, "organization_id", None),
                    step_number=int(p.get("step") or 0), tool_name=str(p.get("tool") or "")[:100],
                    tool_input=json.dumps(p.get("input"), default=str),
                    tool_output=json.dumps(p.get("output"), default=str),
                    status="pending_approval" if pend else "done", requires_approval=pend,
                ))
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
    except Exception:
        logging.getLogger(__name__).exception("NexusAgent: no se pudo guardar la ejecucion en streaming")
