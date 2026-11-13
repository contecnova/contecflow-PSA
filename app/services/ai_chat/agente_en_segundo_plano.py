"""NexusAgent fuera de la peticion: lo que ejecuta `app.worker.run_agent_task`.

Segunda auditoria 2026-11 (#37): eran 185 lineas dentro de la tarea de Celery.
La tarea es ahora un envoltorio; aqui queda la logica, que se puede probar sin
Celery. Corre en la empresa de quien lo pidio (`publicar_contexto_de_tenant`).

Los importes son diferidos a proposito: las pruebas sustituyen
`app.db.session.worker_db_session` y `ai_provider_service.get_default_provider`.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EjecucionNoEncontrada(LookupError):
    """La ejecucion o el usuario que la pidio ya no existen."""


def ejecutar_agente(execution_id: str, instruction: str, user_id: str, auto_approve: bool = False) -> dict:
    """Corre el bucle del agente y deja el resultado en `AIAgentExecution`.

    Lanza si algo falla (tras marcar la ejecucion como fallida), para que la
    tarea quede en FAILURE con su traza. Un bloqueo de gobernanza no es un
    fallo del sistema: queda en la ejecucion y se devuelve.
    """
    from app.core.config import settings
    from app.db import session as _sesion
    from app.models.ai_chat import AIAgentExecution, AIAgentStep
    from app.models.user import User
    from app.services.ai_chat_service import (
        AGENT_TOOLS,
        build_agent_system_prompt as _build_agent_system_prompt,
        execute_tool as _execute_tool,
        log_action as _log_action,
    )

    with _sesion.worker_db_session() as db:
        execution = None
        try:
            execution = db.query(AIAgentExecution).filter(AIAgentExecution.id == execution_id).first()
            if not execution:
                raise EjecucionNoEncontrada(f"ejecucion {execution_id} no encontrada")

            current_user = db.query(User).filter(User.id == user_id).first()
            if not current_user:
                raise EjecucionNoEncontrada(f"usuario {user_id} no encontrado")

            execution.status = "running"
            db.commit()
            # Revision 2026-11: todo corre en la empresa de quien lo pidio; y
            # (2026-11b) en la que lo pidio, la de la ejecucion, no la de su ficha.
            from app.services.entrada_service import fijar_organizacion_activa
            fijar_organizacion_activa(db, current_user, getattr(execution, "organization_id", None))
            _sesion.publicar_contexto_de_tenant(db, current_user)

            t0 = time.time()
            system = _build_agent_system_prompt(db, current_user)

            from app.core.encryption import decrypt_value
            from app.services import ai_tools as _herr
            from app.services.ai_provider_service import call_ai
            from app.services.ai_provider_service import get_default_provider as _gdp

            active_prov = _gdp(db, is_superadmin=bool(current_user.is_superadmin),
                               organization_id=current_user.organization_id)
            # Se pregunta por la CAPACIDAD (herramientas), no por la marca.
            agent_proveedor = (active_prov.provider if active_prov else "anthropic")
            # La clave viaja cifrada; `decrypt_value` deja intacto lo que no lo este.
            agent_clave = decrypt_value(active_prov.api_key) if (active_prov and active_prov.api_key) else None
            agent_base_url = (getattr(active_prov, "api_base_url", "") or "") if active_prov else ""
            if not agent_base_url and agent_proveedor in _herr.FAMILIA_OPENAI:
                agent_base_url = _herr.base_url_por_defecto(agent_proveedor)

            if not (_herr.soporta_herramientas(agent_proveedor) and agent_clave):
                try:
                    result_summary = call_ai(
                        db,
                        messages=[{"role": "user", "content": instruction}],
                        system=system + "\n\nNota: ejecuta un análisis y plan de acción sin usar herramientas reales.",
                        module="nexusagent", user_id=user_id, max_tokens=800,
                        organization_id=current_user.organization_id,
                    )
                except Exception:
                    logger.warning("NexusAgent: sin proveedor de IA utilizable", exc_info=True)
                    result_summary = (
                        f"⚠ Sin proveedor IA configurado. Instrucción recibida: *{instruction}*\n\n"
                        f"Configura un proveedor en IA & Conectores para ejecutar instrucciones reales."
                    )
                execution.status = "done"
                execution.result = result_summary
                execution.completed_at = datetime.now(timezone.utc)
                _log_action(db, current_user.id, "nexusagent", "execute",
                            instruction[:200], result_summary[:200], status="success")
                db.commit()
                return {"ok": True}

            agent_model = (active_prov.default_model if active_prov else None) or settings.CONTECFLOW_AI_MODEL

            from app.services.ai_chat.agent_loop import run_tool_use_loop
            from app.services.ai_chat.tool_execution_service import WRITE_ACTION_TOOLS

            def _persist_step(step_data: dict):
                tool_result = step_data["output"]
                db.add(AIAgentStep(
                    execution_id=execution.id,
                    step_number=step_data["step"],
                    tool_name=step_data["tool"],
                    tool_input=json.dumps(step_data["input"]),
                    tool_output=json.dumps(tool_result),
                    status="done" if "error" not in tool_result else "failed",
                ))
                db.flush()

            # Revision 2026-11: politicas de gobernanza de entrada y salida.
            from app.services.ai_provider_service import guardrail_de_instruccion, guardrail_de_respuesta
            instruction, bloqueo = guardrail_de_instruccion(db, current_user, instruction)
            if bloqueo:
                execution.status = "failed"
                execution.error = bloqueo
                db.commit()
                return {"ok": False, "bloqueado": bloqueo}

            result_summary, _steps, step_num = run_tool_use_loop(
                execute_tool=_execute_tool,
                instruction=instruction,
                system=system,
                tools=AGENT_TOOLS,
                db=db,
                current_user=current_user,
                model=agent_model,
                api_key=agent_clave,
                max_tokens=4096,
                max_steps=20,
                auto_approve=bool(auto_approve),
                write_action_tools=WRITE_ACTION_TOOLS,
                on_step_done=_persist_step,
                provider=agent_proveedor,
                base_url=agent_base_url,
            )

            latency = int((time.time() - t0) * 1000)
            result_summary = guardrail_de_respuesta(db, current_user, result_summary)
            execution.status = "done"
            execution.result = result_summary
            execution.steps_count = step_num
            execution.completed_at = datetime.now(timezone.utc)
            _log_action(db, current_user.id, "nexusagent", "execute",
                        instruction[:200], result_summary[:200],
                        tokens=0, latency=latency, status="success")
            db.commit()
            return {"ok": True, "steps": step_num}

        except Exception as exc:
            logger.error("NexusAgent: la ejecucion %s fallo", execution_id, exc_info=True)
            if execution is not None:
                try:
                    execution.status = "failed"
                    execution.error = str(exc)[:500]
                    execution.completed_at = datetime.now(timezone.utc)
                    db.commit()
                except Exception:
                    logger.warning("NexusAgent: no se pudo marcar la ejecucion como fallida", exc_info=True)
                    db.rollback()
            raise
