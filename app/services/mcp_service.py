"""Servidor MCP: las herramientas de NexusAgent para agentes externos, con gobierno.

Revisión 2026-11 (lo que contecintelligence ya tenía). Un agente externo —Claude,
un copiloto propio, otro producto— se conecta por MCP (JSON-RPC 2.0 sobre HTTP)
y usa las MISMAS herramientas que NexusAgent (`AGENT_TOOLS`), ejecutadas como el
dueño de la credencial: ve lo que él ve y nada más.

Sin SDK, como en contecintelligence: cuatro métodos (`initialize`, `ping`,
`tools/list`, `tools/call`) y un despacho que se prueba sin HTTP.

Gobierno, sin inventar nada nuevo:

- **Encendido por empresa**: el módulo `mcp` de *Gobernanza IA → Módulos*. A
  diferencia del resto, sin fila está APAGADO: es una puerta nueva hacia fuera.
- **Solo lectura** salvo `MCP_ALLOW_WRITE`; y una clave de API de alcance
  `read` solo ve las de lectura aunque la empresa permita escribir.
- **Límite diario** por usuario: el mismo de la gobernanza (`max_actions_per_day`).
- **Auditoría**: cada llamada queda en el registro de IA con el módulo `mcp`.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
MODULO = "mcp"

#: Las que escriben. Las de lectura empiezan por get_ o search_; una herramienta
#: nueva que no sea ni una cosa ni otra rompe la importación (abajo), para que
#: nadie exponga una escritura como si fuera lectura.
ESCRITURA = frozenset({"create_task", "update_task", "create_risk", "update_project_status",
                       "update_ticket_status", "reassign_tickets", "send_notification"})


def _herramientas() -> list[dict]:
    from app.services.ai_chat.tool_execution.schema import AGENT_TOOLS
    return AGENT_TOOLS


def _clasificar() -> None:
    sueltas = [h["name"] for h in _herramientas()
               if h["name"] not in ESCRITURA and not h["name"].startswith(("get_", "search_"))]
    if sueltas:
        raise RuntimeError(f"Herramientas MCP sin clasificar como lectura o escritura: {sueltas}")


_clasificar()


def _error(rid: Any, codigo: int, mensaje: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": codigo, "message": mensaje}}


def _resultado(rid: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _fallo_de_herramienta(mensaje: str) -> dict:
    """Fallo de la herramienta, no del protocolo: el modelo lo lee y puede corregir."""
    return {"content": [{"type": "text", "text": mensaje}], "isError": True}


# ── Gobierno ────────────────────────────────────────────────────────────────

def encendido(db: Session, org_id: Optional[str]) -> bool:
    from app.models.ai_chat import AIGovernanceConfig
    fila = db.query(AIGovernanceConfig).filter(AIGovernanceConfig.module == MODULO).first()
    return bool(fila and fila.is_enabled)


def permite_escribir(db: Session, org_id: Optional[str], alcances: Optional[list]) -> bool:
    from app.services.settings_service import get_runtime_bool
    if not get_runtime_bool(db, "MCP_ALLOW_WRITE", org_id):
        return False
    # Sesión o token propio: sin alcances que recortar. Clave de API: necesita write/admin.
    return alcances is None or bool(set(alcances) & {"write", "admin"})


def herramientas_para(db: Session, user, alcances: Optional[list]) -> list[dict]:
    escribe = permite_escribir(db, getattr(user, "organization_id", None), alcances)
    salida = []
    for h in _herramientas():
        es_escritura = h["name"] in ESCRITURA
        if es_escritura and not escribe:
            continue
        salida.append({"name": h["name"], "description": h.get("description", ""),
                       "inputSchema": h.get("input_schema") or {"type": "object", "properties": {}},
                       "annotations": {"readOnlyHint": not es_escritura, "destructiveHint": False}})
    return salida


def _auditar(db: Session, user, herramienta: str, argumentos: dict, salida: str, estado: str) -> None:
    from app.services.ai_chat.core_service import log_action
    try:
        log_action(db, user.id, MODULO, herramienta,
                   json.dumps(argumentos, ensure_ascii=False, default=str)[:200], salida[:200], status=estado)
        db.commit()   # también confirma lo que haya escrito la herramienta (las de escritura no confirman)
    except Exception:
        db.rollback()
        logger.warning("mcp: no se pudo auditar %s", herramienta, exc_info=True)


# ── Despacho ────────────────────────────────────────────────────────────────

def despachar(db: Session, user, mensaje: Any, alcances: Optional[list] = None) -> Optional[dict]:
    """Un mensaje JSON-RPC → su respuesta, o None si era una notificación."""
    if not isinstance(mensaje, dict):
        return _error(None, INVALID_REQUEST, "se esperaba un único objeto JSON-RPC")
    if mensaje.get("jsonrpc") != "2.0":
        return _error(mensaje.get("id"), INVALID_REQUEST, "falta jsonrpc: '2.0'")
    metodo, params, rid = mensaje.get("method"), mensaje.get("params"), mensaje.get("id")
    notificacion = "id" not in mensaje
    if not isinstance(metodo, str):
        return None if notificacion else _error(rid, INVALID_REQUEST, "falta 'method'")
    params = {} if params is None else params
    if not isinstance(params, dict):
        return None if notificacion else _error(rid, INVALID_PARAMS, "'params' debe ser un objeto")
    if notificacion:
        return None

    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        return _resultado(rid, {
            "protocolVersion": pedida if pedida in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "contecflow", "title": "Contecflow", "version": "1"},
            "instructions": ("Datos de proyectos, tareas, tickets, finanzas y equipo de la empresa, con los "
                             "permisos del usuario dueño de la credencial. Las herramientas get_/search_ leen; "
                             "las que escriben solo aparecen si la empresa lo permite."),
        })
    if metodo == "ping":
        return _resultado(rid, {})
    if metodo == "tools/list":
        return _resultado(rid, {"tools": herramientas_para(db, user, alcances)})
    if metodo in ("resources/list", "prompts/list"):
        return _resultado(rid, {metodo.split("/")[0]: []})
    if metodo != "tools/call":
        return _error(rid, METHOD_NOT_FOUND, f"método no soportado: {metodo}")

    nombre = params.get("name")
    disponibles = {h["name"] for h in herramientas_para(db, user, alcances)}
    if not isinstance(nombre, str) or nombre not in {h["name"] for h in _herramientas()}:
        return _error(rid, INVALID_PARAMS, f"herramienta desconocida: {nombre}")
    argumentos = params.get("arguments") or {}
    if not isinstance(argumentos, dict):
        return _error(rid, INVALID_PARAMS, "'arguments' debe ser un objeto")
    if nombre not in disponibles:
        _auditar(db, user, nombre, argumentos, "denegada: escritura no permitida", "blocked")
        return _resultado(rid, _fallo_de_herramienta(
            f"'{nombre}' escribe, y la escritura por MCP no está permitida para esta empresa o credencial"))
    from app.services.ai_chat.rate_limit_service import check_rate_limit
    limite = check_rate_limit(db, user.id, MODULO)
    if limite:
        return _resultado(rid, _fallo_de_herramienta(limite))
    from app.services.ai_chat.tool_execution.executor import execute_tool
    salida = execute_tool(nombre, argumentos, db, user)
    texto = json.dumps(salida, ensure_ascii=False, default=str)
    error = isinstance(salida, dict) and salida.get("error")
    _auditar(db, user, nombre, argumentos, texto, "error" if error else "success")
    if error:
        return _resultado(rid, _fallo_de_herramienta(str(salida["error"])))
    return _resultado(rid, {"content": [{"type": "text", "text": texto}], "isError": False,
                            "structuredContent": salida if isinstance(salida, dict) else {"result": salida}})
