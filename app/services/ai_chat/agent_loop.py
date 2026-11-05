"""
agent_loop — Shared tool-use loop for NexusAgent (SSE endpoint) and Celery worker.

Antes (item #54): el loop estaba duplicado en
  - app/api/v1/endpoints/ai_chat.py:545-637 (SSE streaming)
  - app/worker.py:660-755 (Celery background task)
Cualquier cambio (max_steps, manejo de tool_use, formato de mensajes) había que
replicarlo en 2 sitios → drift. Esta función centraliza el bucle y delega los
side-effects (emisión SSE, persistencia AIAgentStep) en callbacks.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def run_tool_use_loop(
    *,
    execute_tool: Callable[[str, dict, Any, Any], dict],
    instruction: str,
    system: str,
    tools: list,
    db,
    current_user,
    model: str,
    api_key: str,
    max_tokens: int = 4096,
    max_steps: int = 20,
    provider: str = "anthropic",
    base_url: str = "",

    auto_approve: bool = False,
    write_action_tools: frozenset[str] | None = None,
    on_step_start: Optional[Callable[[int, str, dict], None]] = None,
    on_step_done: Optional[Callable[[dict], None]] = None,
) -> tuple[str, list[dict], int]:
    """El bucle de uso de herramientas, con CUALQUIER proveedor.

    Auditoría 2026-09. Se llamaba «Anthropic tool-use loop» y lo era: recibía
    `call_claude` y leía `stop_reason` y bloques `tool_use`, que son el dialecto
    de un proveedor concreto. Ahora la traducción vive en
    `app.services.ai_tools` y aquí sólo queda el bucle, idéntico para los tres.

    Ya no recibe `call_claude` ni `extract_text`: los sustituye el adaptador,
    que además es el único sitio que sabe de formatos.

    Returns ``(result_text, steps_executed, step_count)``.

    ``on_step_start(step_num, tool_name, tool_input)`` se llama justo antes de
    ejecutar la tool — el SSE caller puede yield un evento aquí.

    ``on_step_done(step_dict)`` recibe ``{step, tool, input, output}`` después
    de ejecutar — el caller persiste en DB o envía SSE.
    """
    from app.services import ai_tools as _herr
    from app.services import ai_provider_service as _ia

    messages: list[dict] = _herr.primer_mensaje(provider, instruction)
    steps_done: list[dict] = []
    step_num = 0

    while step_num < max_steps:
        # Revisión 2026-11: gobernado (tope diario y registro de uso), no directo.
        turn = _ia.turno_de_agente(
            db, current_user,
            proveedor=provider, api_key=api_key, modelo=model, base_url=base_url,
            mensajes=messages, system=system, herramientas=tools,
            max_tokens=max_tokens,
        )

        if not turn.quiere_herramientas:
            # Ni `tool_use`, ni `tool_calls`, ni `functionCall`: el agente ha
            # terminado y lo que haya dicho es el resultado.
            return turn.texto, steps_done, step_num

        tool_results_content = []
        for llamada in turn.llamadas:
            tool_name = llamada.nombre
            tool_input = llamada.argumentos
            step_num += 1

            if on_step_start is not None:
                on_step_start(step_num, tool_name, tool_input)

            # Item #55: gate humano para acciones write si auto_approve=False.
            # En vez de ejecutar, devolvemos un resultado pending_approval que
            # el LLM verá en el siguiente turno y debe usar para informar al
            # usuario en lugar de re-intentar. La aprobación real se hará vía
            # endpoint /agent/{execution_id}/approve (futuro) o desde otra UI.
            is_write = (write_action_tools is not None
                        and tool_name in write_action_tools)
            if is_write and not auto_approve:
                tool_result = {
                    "status": "pending_approval",
                    "tool": tool_name,
                    "input": tool_input,
                    "message": (
                        f"Acción '{tool_name}' requiere confirmación humana. "
                        "No se ha ejecutado. Informa al usuario que apruebe "
                        "explícitamente antes de continuar."
                    ),
                }
            else:
                tool_result = execute_tool(tool_name, tool_input, db, current_user)

            step_data = {
                "step": step_num, "tool": tool_name,
                "input": tool_input, "output": tool_result,
            }
            steps_done.append(step_data)
            if on_step_done is not None:
                on_step_done(step_data)

            tool_results_content.append((llamada, tool_result))

        messages.extend(_herr.mensajes_del_turno(provider, turn, tool_results_content))

    return f"Agente completó {step_num} pasos.", steps_done, step_num
