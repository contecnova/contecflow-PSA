"""Servidor MCP: herramientas de Contecflow para agentes externos y de código, con gobierno.

Revisión 2026-11 (lo que contecintelligence ya tenía): un agente externo
—Claude, un copiloto propio, otro producto— se conecta por MCP (JSON-RPC 2.0
sobre HTTP) y usa las herramientas de NexusAgent (`AGENT_TOOLS`), ejecutadas
como el dueño de la credencial: ve lo que él ve y nada más.

23-11-2026 (agentes de código, `docs/integraciones/MCP.md`): además, las
herramientas de trabajo diario de `app/services/mcp_herramientas.py` (tareas,
tickets, proyectos, horas y cronómetro, cambios y, si su dueño las comparte,
notas de «Mi cuaderno»), pensadas para OpenCode y Claude Code. Cada una exige
la MISMA capacidad que su ruta REST y pasa por el módulo del rol, la matriz
GRC, el ABAC y el aislamiento por empresa. Las del asistente, además, piden
`ia.usar` (antes era la puerta del endpoint, que ahora es `mcp.usar`).

Sin SDK, como en contecintelligence: `initialize`, `ping`, `tools/list`
(paginado con `cursor`), `tools/call`; `resources/list`,
`resources/templates/list` y `prompts/list` vacíos. Un despacho que se prueba
sin HTTP. El transporte (Streamable HTTP, una respuesta JSON por POST) y las
cabeceras están en `app/api/v1/endpoints/mcp.py`.

Gobierno, sin inventar nada nuevo:

- **Encendido por empresa**: el módulo `mcp` de *Gobernanza IA → Módulos* (y
  Configuración → Agentes de código). Sin fila está APAGADO: es una puerta hacia fuera.
- **Escritura** según `MCP_WRITE_MODE`: `off` (por defecto, no se ven),
  `approval` (cada llamada abre una aprobación «mcp_action» y se ejecuta solo si
  una persona la aprueba; el agente sigue el estado con `mcp_action_status`) o
  `direct`. Una credencial de solo lectura (`read`, `mcp:read`) nunca ve las que escriben.
- **Límites**: por credencial y minuto (`MCP_RATE_LIMIT_PER_MINUTE`, en el
  endpoint) y diario por usuario (`max_actions_per_day` de la gobernanza).
- **Registro**: cada llamada en el registro de IA (`ai_action_logs`, módulo
  `mcp`, con IP; retención configurable), sin datos personales (solo ids y
  claves de los argumentos). Cada escritura, cada lectura de notas y cada
  conexión (`initialize`), también en `audit_log` con canal `mcp`, credencial,
  empresa e IP.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: La primera es la que se ofrece si el cliente pide una que no conocemos.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
#: Error del servidor (rango -32000..-32099 de JSON-RPC): apagado, límite de uso, origen.
SERVER_ERROR = -32000
MODULO = "mcp"
TAM_PAGINA_HERRAMIENTAS = 100

#: Las del asistente que escriben. Las de lectura empiezan por get_ o search_; una
#: herramienta nueva que no sea ni una cosa ni otra rompe la importación (abajo),
#: para que nadie exponga una escritura como si fuera lectura.
ESCRITURA = frozenset({"create_task", "update_task", "create_risk", "update_project_status",
                       "update_ticket_status", "reassign_tickets", "send_notification"})
#: Alcances de credencial que permiten escribir.
ALCANCES_DE_ESCRITURA = frozenset({"write", "admin", "mcp:write"})


def _herramientas() -> list[dict]:
    from app.services.ai_chat.tool_execution.schema import AGENT_TOOLS
    return AGENT_TOOLS


def _clasificar() -> None:
    sueltas = [h["name"] for h in _herramientas()
               if h["name"] not in ESCRITURA and not h["name"].startswith(("get_", "search_"))]
    if sueltas:
        raise RuntimeError(f"Herramientas MCP sin clasificar como lectura o escritura: {sueltas}")


_clasificar()


@dataclass
class Contexto:
    """Quién llama y por dónde: para recortar, limitar y auditar."""
    alcances: Optional[list] = None          #: None = sesión o token propio (sin recorte)
    credencial_tipo: str = "sesion"          #: sesion | api_key | oauth
    credencial_id: Optional[str] = None
    ip: Optional[str] = None
    agente: Optional[str] = None             #: User-Agent del cliente MCP

    @classmethod
    def de_peticion(cls, request) -> "Contexto":
        from app.core.network import extract_client_ip
        delegada = getattr(request.state, "credencial_delegada", None) or {}
        return cls(alcances=delegada.get("alcances") if delegada else None,
                   credencial_tipo=delegada.get("tipo") or "sesion", credencial_id=delegada.get("id"),
                   ip=extract_client_ip(request), agente=(request.headers.get("user-agent") or "")[:200] or None)


# ── Mensajes JSON-RPC ───────────────────────────────────────────────────────

def _error(rid: Any, codigo: int, mensaje: str, codigo_propio: Optional[str] = None,
           params: Optional[dict] = None) -> dict:
    error = {"code": codigo, "message": mensaje}
    if codigo_propio:
        error["data"] = {"code": codigo_propio, "params": params or {}}
    return {"jsonrpc": "2.0", "id": rid, "error": error}


def error_con_codigo(rid: Any, codigo: int, codigo_propio: str, **params) -> dict:
    """Error de protocolo con el código del catálogo (`data.code`) y su texto."""
    from app.core.codigos_de_error import texto
    return _error(rid, codigo, texto(codigo_propio, params), codigo_propio, params)


def _resultado(rid: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _fallo(codigo: str, params: Optional[dict] = None, mensaje: Optional[str] = None) -> dict:
    """Fallo de la herramienta, no del protocolo: el modelo lo lee y puede corregir."""
    from app.core.codigos_de_error import texto
    mensaje = mensaje or texto(codigo, params or {})
    return {"content": [{"type": "text", "text": mensaje}], "isError": True,
            "structuredContent": {"error": {"code": codigo, "params": params or {}, "message": mensaje}}}


def _fallo_de_herramienta(mensaje: str) -> dict:
    """Compatibilidad: fallo con texto libre (herramientas del asistente)."""
    return {"content": [{"type": "text", "text": mensaje}], "isError": True}


def _texto(datos: Any) -> dict:
    estructurado = datos if isinstance(datos, dict) else {"result": datos}
    return {"content": [{"type": "text", "text": json.dumps(datos, ensure_ascii=False, default=str)}],
            "isError": False, "structuredContent": json.loads(json.dumps(estructurado, default=str))}


# ── Gobierno ────────────────────────────────────────────────────────────────

def encendido(db: Session, org_id: Optional[str]) -> bool:
    from app.services.governance_service import config_de_modulo
    fila = config_de_modulo(db, org_id, MODULO)
    return bool(fila and fila.is_enabled)


MODOS_DE_ESCRITURA = ("off", "approval", "direct")
ESTADO = "mcp_action_status"


def modo_de_escritura(db: Session, org_id: Optional[str]) -> str:
    from app.services.settings_service import get_runtime_str
    modo = (get_runtime_str(db, "MCP_WRITE_MODE", org_id) or "off").strip().lower()
    return modo if modo in MODOS_DE_ESCRITURA else "off"   # un valor raro no abre la puerta


def permite_escribir(db: Session, org_id: Optional[str], alcances: Optional[list]) -> bool:
    if modo_de_escritura(db, org_id) == "off":
        return False
    # Sesión o token propio: sin alcances que recortar. Credencial: necesita write, admin o mcp:write.
    return alcances is None or bool(set(alcances) & ALCANCES_DE_ESCRITURA)


def puede_usar_el_asistente(db: Session, user) -> bool:
    """Las herramientas de NexusAgent piden, además de la suya, `ia.usar`."""
    from app.core import capacidades as _capacidades
    return _capacidades.tiene(db, user, "ia.usar")


def _anotaciones(titulo: str, escribe: bool, idempotente: bool) -> dict:
    return {"title": titulo, "readOnlyHint": not escribe, "destructiveHint": False,
            "idempotentHint": idempotente, "openWorldHint": False}


_NOTA_DE_APROBACION = (" REQUIERE APROBACIÓN HUMANA: la llamada no se ejecuta al momento; devuelve un "
                       "action_id y se ejecuta si una persona la aprueba (consúltalo con mcp_action_status).")


def herramientas_para(db: Session, user, alcances: Optional[list]) -> list[dict]:
    """Las herramientas que `user` (con estos alcances) puede usar ahora, en formato MCP."""
    from app.services.ai_chat.tool_execution.politica import codigo_de_denegacion
    from app.services.mcp_herramientas import HERRAMIENTAS, denegacion
    org = getattr(user, "organization_id", None)
    escribe = permite_escribir(db, org, alcances)
    con_aprobacion = escribe and modo_de_escritura(db, org) == "approval"
    salida = []
    # Trabajo diario (agentes de código): capacidad de su ruta, módulo, GRC.
    for h in HERRAMIENTAS:
        if h.escribe and not escribe:
            continue
        if denegacion(db, user, h):
            continue
        descripcion = h.descripcion + (_NOTA_DE_APROBACION if h.escribe and con_aprobacion else "")
        salida.append({"name": h.nombre, "title": h.titulo, "description": descripcion, "inputSchema": h.esquema(),
                       "annotations": _anotaciones(h.titulo, h.escribe, h.idempotente)})
    # Las del asistente (NexusAgent): además `ia.usar`. Segunda auditoría 2026-11:
    # solo las que su rol puede usar (`tool_execution.politica`).
    if puede_usar_el_asistente(db, user):
        for h in _herramientas():
            es_escritura = h["name"] in ESCRITURA
            if es_escritura and not escribe:
                continue
            if codigo_de_denegacion(db, user, h["name"]):
                continue
            descripcion = h.get("description", "") + (_NOTA_DE_APROBACION if es_escritura and con_aprobacion else "")
            salida.append({"name": h["name"], "description": descripcion,
                           "inputSchema": h.get("input_schema") or {"type": "object", "properties": {}},
                           "annotations": _anotaciones(h["name"], es_escritura, False)})
    if con_aprobacion:
        salida.append({"name": ESTADO, "title": "MCP action status",
                       "description": "Estado de una escritura pedida por MCP que espera aprobación "
                       "(pending, executed, failed, rejected) y, si se ejecutó, su resultado.",
                       "inputSchema": {"type": "object", "properties": {"action_id": {"type": "string"}},
                                       "required": ["action_id"]},
                       "annotations": _anotaciones("MCP action status", False, True)})
    return salida


def es_escritura(nombre: str) -> bool:
    from app.services.mcp_herramientas import POR_NOMBRE
    h = POR_NOMBRE.get(nombre)
    return h.escribe if h is not None else nombre in ESCRITURA


def _motivo_de_denegacion(db: Session, user, nombre: str, alcances: Optional[list]) -> tuple[str, dict, Optional[str]]:
    """`(codigo, params, mensaje)` de por qué `nombre` no está disponible para `user`."""
    from app.services.mcp_herramientas import POR_NOMBRE, denegacion
    h = POR_NOMBRE.get(nombre)
    if h is not None:
        motivo = denegacion(db, user, h)
        if motivo:
            return motivo[0], motivo[1], None
    elif nombre != ESTADO:
        if not puede_usar_el_asistente(db, user):
            return "mcp_herramienta_ia", {"herramienta": nombre}, None
        from app.services.ai_chat.tool_execution.politica import codigo_de_denegacion, denegacion as texto_de
        motivo = codigo_de_denegacion(db, user, nombre)
        if motivo:
            return motivo[0], motivo[1], texto_de(db, user, nombre)
    return "mcp_escritura_no_permitida", {"herramienta": nombre}, None


# ── Registro (uso y auditoría) ──────────────────────────────────────────────

#: Argumentos que se registran con su valor (ids, estados, cifras): nunca texto libre.
_ARGUMENTOS_REGISTRABLES = frozenset({
    "task", "ticket", "project", "change", "page_id", "status", "page", "page_size", "hours", "date",
    "is_public", "is_billable", "submit", "mine", "change_type", "risk", "priority", "include_done",
    "force_duplicate", "standard_model_id", "action_id", "project_id", "task_id", "ticket_id", "risk_level",
})


def resumen_de_argumentos(argumentos: dict) -> dict:
    """Lo que se guarda de los argumentos: ids, estados y cifras; del texto libre, solo su longitud."""
    salida: dict = {}
    for k, v in (argumentos or {}).items():
        if k in _ARGUMENTOS_REGISTRABLES and (isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 64)):
            salida[k] = v
        elif isinstance(v, str):
            salida[k] = f"<{len(v)} car.>"
        else:
            salida[k] = f"<{type(v).__name__}>"
    return salida


def _registrar(db: Session, user, ctx: Contexto, nombre: str, argumentos: dict, estado: str,
               codigo: Optional[str] = None, auditar: bool = False, accion: str = "MCP_TOOL_CALL") -> None:
    """Uso en `ai_action_logs` y, si `auditar`, en `audit_log` (canal mcp). Confirma."""
    from app.services.ai_chat.core_service import log_action
    from app.services.audit import audit_log
    resumen = resumen_de_argumentos(argumentos)
    try:
        log_action(db, user.id, MODULO, nombre, json.dumps(resumen, ensure_ascii=False, default=str)[:300],
                   codigo or "ok", status=estado, ip_address=ctx.ip)
        if auditar:
            recurso = next((str(resumen[k]) for k in ("task", "ticket", "change", "page_id", "project")
                            if isinstance(resumen.get(k), str)), None)
            audit_log(db, user, accion, "mcp_tool", recurso[:36] if recurso else None, nombre,
                      metadata={"canal": "mcp", "herramienta": nombre, "estado": estado, "codigo": codigo,
                                "credencial": {"tipo": ctx.credencial_tipo, "id": ctx.credencial_id},
                                "empresa": getattr(user, "organization_id", None), "argumentos": resumen},
                      ip_address=ctx.ip, user_agent=ctx.agente)
        db.commit()   # también confirma lo que haya escrito una herramienta del asistente (no confirman)
    except Exception:
        db.rollback()
        logger.warning("mcp: no se pudo registrar la llamada a %s", nombre, exc_info=True)


def auditar_conexion(db: Session, user, ctx: Contexto, cliente: Optional[dict]) -> None:
    """Cada `initialize` (un agente que se conecta) queda en `audit_log`."""
    from app.services.audit import audit_log
    cliente = cliente if isinstance(cliente, dict) else {}
    try:
        audit_log(db, user, "MCP_CONNECT", "mcp", None, str(cliente.get("name") or "")[:60] or None,
                  metadata={"canal": "mcp", "cliente": {"name": str(cliente.get("name") or "")[:60],
                                                        "version": str(cliente.get("version") or "")[:30]},
                            "credencial": {"tipo": ctx.credencial_tipo, "id": ctx.credencial_id},
                            "empresa": getattr(user, "organization_id", None)},
                  ip_address=ctx.ip, user_agent=ctx.agente)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("mcp: no se pudo auditar la conexión", exc_info=True)


# ── Límite de uso por credencial ────────────────────────────────────────────

_limitador = None


def _estrategia():
    """Ventana fija por minuto en Redis si lo hay (compartido entre procesos); si no, en memoria."""
    global _limitador
    if _limitador is None:
        from limits.storage import storage_from_string
        from limits.strategies import FixedWindowRateLimiter
        from app.core.config import settings
        from app.core.entorno import en_pruebas
        almacen = None
        if settings.REDIS_URL and not en_pruebas():
            try:
                almacen = storage_from_string(settings.REDIS_URL)
                if not almacen.check():
                    almacen = None
            except Exception:
                logger.warning("mcp: Redis no disponible para el límite de uso; en memoria", exc_info=True)
                almacen = None
        _limitador = FixedWindowRateLimiter(almacen or storage_from_string("memory://"))
    return _limitador


def reiniciar_limites() -> None:
    """Para las pruebas: olvida los contadores en memoria."""
    global _limitador
    _limitador = None


def clave_de_limite(user, ctx: Contexto) -> str:
    if ctx.credencial_id:
        return f"{ctx.credencial_tipo}:{ctx.credencial_id}"
    return f"usuario:{user.id}"


def consumir_limite(db: Session, org_id: Optional[str], clave: str) -> Optional[tuple[int, int]]:
    """None si puede seguir; `(n, segundos)` si la credencial pasó de `n` llamadas este minuto."""
    from app.services.settings_service import get_runtime_int
    n = get_runtime_int(db, "MCP_RATE_LIMIT_PER_MINUTE", org_id, default=60)
    if n is None:
        n = 60
    if n <= 0:
        return None
    from limits import RateLimitItemPerMinute
    item = RateLimitItemPerMinute(n)
    try:
        limitador = _estrategia()
        if limitador.hit(item, MODULO, clave):
            return None
        reinicio = limitador.get_window_stats(item, MODULO, clave)[0]
        return n, max(1, int(reinicio - time.time()) + 1)
    except Exception:
        logger.warning("mcp: límite de uso no comprobado", exc_info=True)
        return None


# ── Ejecución ───────────────────────────────────────────────────────────────

def _motivo_de_excepcion(exc: Exception, nombre: str) -> tuple[str, dict, str]:
    from pydantic import ValidationError
    from app.core.codigos_de_error import ErrorConCodigo, texto
    from app.services.mcp_herramientas import ArgumentosNoValidos
    if isinstance(exc, ErrorDeDominio):
        codigo = exc.code or f"http_{exc.status_code}"
        return codigo, exc.params or {}, str(exc.detail if exc.detail is not None else texto(codigo, exc.params))
    # `HTTPException` de FastAPI/Starlette (item 36: sin importarla en un servicio).
    if hasattr(exc, "status_code") and hasattr(exc, "detail"):
        codigo = getattr(exc, "code", None) or f"http_{exc.status_code}"
        return codigo, getattr(exc, "params", None) or {}, str(exc.detail)
    if isinstance(exc, ErrorConCodigo):
        return exc.codigo, exc.params, str(exc)
    if isinstance(exc, (ArgumentosNoValidos, ValidationError)):
        detalle = str(exc) if isinstance(exc, ArgumentosNoValidos) else \
            "; ".join(f"{'.'.join(map(str, e.get('loc') or ()))}: {e.get('msg')}" for e in exc.errors())[:300]
        params = {"herramienta": nombre, "detalle": detalle}
        return "mcp_argumentos_no_validos", params, texto("mcp_argumentos_no_validos", params)
    logger.exception("mcp: fallo inesperado en la herramienta %s", nombre)   # sin argumentos: datos personales
    params = {"herramienta": nombre}
    return "mcp_error_interno", params, texto("mcp_error_interno", params)


def ejecutar(db: Session, user, nombre: str, argumentos: dict,
             deshacer: bool = True) -> tuple[Any, Optional[tuple[str, dict, str]]]:
    """`(salida, None)` o `(None, (codigo, params, mensaje))`.

    `deshacer`: con un fallo se deshace lo que la herramienta dejó a medias (no
    desde el motor de aprobaciones, que tiene su propia transacción abierta).
    """
    from app.services.mcp_herramientas import POR_NOMBRE, aplicar_abac, validar
    h = POR_NOMBRE.get(nombre)
    if h is None:
        from app.services.ai_chat.tool_execution.executor import execute_tool
        salida = execute_tool(nombre, argumentos, db, user)
        if isinstance(salida, dict) and salida.get("error"):
            return None, ("herramienta_con_error", {"herramienta": nombre}, str(salida["error"]))
        return salida, None
    try:
        argumentos = validar(h, argumentos)
        aplicar_abac(db, user, h, argumentos)
        return h.manejador(db, user, argumentos), None
    except Exception as exc:  # noqa: BLE001 - todo fallo vuelve al agente con su código
        logger.debug("ejecutar: excepcion ignorada", exc_info=True)
        if deshacer:
            db.rollback()
        return None, _motivo_de_excepcion(exc, nombre)


# ── Escrituras con aprobación ───────────────────────────────────────────────

def _pedir_aprobacion(db: Session, user, nombre: str, argumentos: dict, ctx: Optional[Contexto] = None) -> dict:
    from app.models.ai_chat import MCPPendingAction
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine.requests import create_approval_request
    ctx = ctx or Contexto()
    accion = MCPPendingAction(organization_id=user.organization_id, user_id=user.id, tool=nombre,
                              arguments=json.dumps(argumentos, ensure_ascii=False, default=str))
    db.add(accion)
    db.flush()
    resumen = f"Agente externo (MCP): {nombre} {json.dumps(resumen_de_argumentos(argumentos), ensure_ascii=False)}"[:500]
    try:
        req = create_approval_request(
            ApprovalRequestIn(entity_type="mcp_action", entity_id=accion.id, entity_summary=resumen,
                              context={"tool": nombre}), db, user, confirmar=False)
    except ErrorDeDominio:
        db.rollback()
        _registrar(db, user, ctx, nombre, argumentos, "blocked", "mcp_sin_flujo_de_aprobacion", auditar=True)
        return _fallo("mcp_sin_flujo_de_aprobacion")
    accion.approval_request_id = req.id
    if req.status == "approved":           # auto-aprobación por regla del flujo
        aplicar_decision(accion.id, "approved", db)
    _registrar(db, user, ctx, nombre, argumentos, "pending_approval", f"pendiente {accion.id}", auditar=True,
               accion="MCP_TOOL_APPROVAL")
    db.refresh(accion)
    return _texto({"status": accion.status if accion.status != "pending" else "pending_approval",
                   "action_id": accion.id, "approval_request_id": req.id,
                   "message": "Pendiente de aprobación humana. Consulta el estado con mcp_action_status."
                   if accion.status == "pending" else "Aprobada por regla y ejecutada."})


def _estado_de(db: Session, user, argumentos: dict) -> dict:
    from app.models.ai_chat import MCPPendingAction
    accion = db.query(MCPPendingAction).filter(MCPPendingAction.id == str(argumentos.get("action_id") or ""),
                                               MCPPendingAction.user_id == user.id).first()
    if accion is None:
        return _fallo("mcp_accion_no_encontrada")
    return _texto({"action_id": accion.id, "tool": accion.tool, "status": accion.status,
                   "result": json.loads(accion.result) if accion.result else None,
                   "decided_at": accion.decided_at.isoformat() if accion.decided_at else None})


def aplicar_decision(accion_id: str, decision: str, db: Session) -> None:
    """La llama el motor de aprobaciones al decidir (`_apply_entity_final_decision`). No confirma
    (salvo lo que confirme el servicio de una herramienta de trabajo diario)."""
    from datetime import datetime, timezone
    from app.models.ai_chat import MCPPendingAction
    from app.models.user import User
    from app.services.audit import audit_log
    accion = db.get(MCPPendingAction, accion_id)
    if accion is None or accion.status != "pending":
        return                             # nunca dos veces
    accion.decided_at = datetime.now(timezone.utc)
    if decision != "approved":
        accion.status = "rejected"
        return
    usuario = db.get(User, accion.user_id)
    if usuario is None or not usuario.is_active:
        accion.status, accion.result = "failed", json.dumps({"error": "el dueño de la credencial ya no está activo"})
        return
    argumentos = json.loads(accion.arguments or "{}")
    salida, fallo = ejecutar(db, usuario, accion.tool, argumentos, deshacer=False)
    accion = db.get(MCPPendingAction, accion_id)
    accion.status = "failed" if fallo else "executed"
    resultado = {"error": {"code": fallo[0], "params": fallo[1], "message": fallo[2]}} if fallo else salida
    accion.result = json.dumps(resultado, ensure_ascii=False, default=str)[:20000]
    from app.services.ai_chat.core_service import log_action
    log_action(db, usuario.id, MODULO, accion.tool, f"aprobada {accion.id}", fallo[0] if fallo else "ok",
               status="error" if fallo else "success")
    audit_log(db, usuario, "MCP_TOOL_CALL", "mcp_tool", accion.id, accion.tool,
              metadata={"canal": "mcp", "herramienta": accion.tool, "aprobada": accion.id,
                        "estado": "error" if fallo else "success", "codigo": fallo[0] if fallo else None,
                        "empresa": accion.organization_id, "argumentos": resumen_de_argumentos(argumentos)})


# ── Despacho ────────────────────────────────────────────────────────────────

def _tools_list(db: Session, user, ctx: Contexto, rid: Any, params: dict) -> dict:
    todas = herramientas_para(db, user, ctx.alcances)
    cursor = params.get("cursor")
    try:
        inicio = int(cursor) if cursor not in (None, "") else 0
    except (TypeError, ValueError):
        return error_con_codigo(rid, INVALID_PARAMS, "mcp_mensaje_no_valido", motivo="cursor")
    inicio = max(0, inicio)
    pagina = {"tools": todas[inicio:inicio + TAM_PAGINA_HERRAMIENTAS]}
    if inicio + TAM_PAGINA_HERRAMIENTAS < len(todas):
        pagina["nextCursor"] = str(inicio + TAM_PAGINA_HERRAMIENTAS)
    return _resultado(rid, pagina)


def _tools_call(db: Session, user, ctx: Contexto, rid: Any, params: dict) -> dict:
    from app.services.mcp_herramientas import POR_NOMBRE
    nombre = params.get("name")
    conocidas = set(POR_NOMBRE) | {h["name"] for h in _herramientas()} | {ESTADO}
    if not isinstance(nombre, str) or nombre not in conocidas:
        return error_con_codigo(rid, INVALID_PARAMS, "mcp_herramienta_desconocida", herramienta=str(nombre)[:80])
    argumentos = params.get("arguments") or {}
    if not isinstance(argumentos, dict):
        return error_con_codigo(rid, INVALID_PARAMS, "mcp_argumentos_no_validos", herramienta=nombre,
                                detalle="'arguments' must be an object")
    escribe = es_escritura(nombre)
    disponibles = {h["name"] for h in herramientas_para(db, user, ctx.alcances)}
    if nombre not in disponibles:
        codigo, datos, mensaje = _motivo_de_denegacion(db, user, nombre, ctx.alcances)
        _registrar(db, user, ctx, nombre, argumentos, "blocked", codigo, auditar=escribe)
        return _resultado(rid, _fallo(codigo, datos, mensaje))
    if nombre == ESTADO:
        return _resultado(rid, _estado_de(db, user, argumentos))
    from app.services.ai_chat.rate_limit_service import limite_de_uso
    limite = limite_de_uso(db, user.id, MODULO)
    if limite:
        _registrar(db, user, ctx, nombre, argumentos, "blocked", limite[0], auditar=escribe)
        return _resultado(rid, _fallo(limite[0], limite[1], limite[2]))
    if escribe and modo_de_escritura(db, user.organization_id) == "approval":
        h = POR_NOMBRE.get(nombre)
        if h is not None:     # se valida antes de pedir la aprobación: no se aprueba algo inválido
            from app.services.mcp_herramientas import ArgumentosNoValidos, validar
            try:
                argumentos = validar(h, argumentos)
            except ArgumentosNoValidos as exc:
                codigo, datos, mensaje = _motivo_de_excepcion(exc, nombre)
                _registrar(db, user, ctx, nombre, argumentos, "error", codigo, auditar=True)
                return _resultado(rid, _fallo(codigo, datos, mensaje))
        return _resultado(rid, _pedir_aprobacion(db, user, nombre, argumentos, ctx))
    salida, fallo = ejecutar(db, user, nombre, argumentos)
    h = POR_NOMBRE.get(nombre)
    auditar = escribe or bool(h and h.auditar_lectura)
    accion = "MCP_TOOL_CALL" if escribe else "MCP_TOOL_READ"
    if fallo:
        _registrar(db, user, ctx, nombre, argumentos, "error", fallo[0], auditar=auditar, accion=accion)
        return _resultado(rid, _fallo(*fallo))
    _registrar(db, user, ctx, nombre, argumentos, "success", None, auditar=auditar, accion=accion)
    return _resultado(rid, _texto(salida))


def despachar(db: Session, user, mensaje: Any, alcances: Optional[list] = None,
              contexto: Optional[Contexto] = None) -> Optional[dict]:
    """Un mensaje JSON-RPC → su respuesta, o None si era una notificación o una respuesta del cliente."""
    ctx = contexto or Contexto(alcances=alcances)
    if not isinstance(mensaje, dict):
        return error_con_codigo(None, INVALID_REQUEST, "mcp_mensaje_no_valido", motivo="se esperaba un objeto")
    if mensaje.get("jsonrpc") != "2.0":
        return error_con_codigo(mensaje.get("id"), INVALID_REQUEST, "mcp_mensaje_no_valido", motivo="jsonrpc: '2.0'")
    metodo, params, rid = mensaje.get("method"), mensaje.get("params"), mensaje.get("id")
    notificacion = "id" not in mensaje
    if "method" not in mensaje and ("result" in mensaje or "error" in mensaje):
        return None                        # respuesta del cliente a una petición nuestra: 202
    if not isinstance(metodo, str):
        return None if notificacion else error_con_codigo(rid, INVALID_REQUEST, "mcp_mensaje_no_valido",
                                                          motivo="method")
    params = {} if params is None else params
    if not isinstance(params, dict):
        return None if notificacion else error_con_codigo(rid, INVALID_PARAMS, "mcp_mensaje_no_valido",
                                                          motivo="params")
    if notificacion:
        return None

    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        auditar_conexion(db, user, ctx, params.get("clientInfo"))
        return _resultado(rid, {
            "protocolVersion": pedida if pedida in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "contecflow", "title": NOMBRE_DEL_PRODUCTO, "version": "2"},
            "instructions": (
                "Contecflow work data with the permissions of the credential's owner. Daily work: "
                "list_my_tasks, list_my_tickets, search_tasks, search_tickets, list_projects, get_task, get_ticket; "
                "add_task_comment, change_task_status, add_ticket_comment, change_ticket_status; log_time, "
                "get_timer, start_timer, stop_timer; list_standard_changes, open_change, get_change, list_changes; "
                "search_notebook and get_notebook_page only for notes the user shared with agents. Tools that "
                "write appear only if the company allows writing over MCP and the credential can write. Lists are "
                "paginated (page, page_size). Errors carry a stable code in structuredContent.error.code."),
        })
    if metodo == "ping":
        return _resultado(rid, {})
    if metodo == "tools/list":
        return _tools_list(db, user, ctx, rid, params)
    if metodo in ("resources/list", "resources/templates/list", "prompts/list"):
        clave = {"resources/list": "resources", "resources/templates/list": "resourceTemplates",
                 "prompts/list": "prompts"}[metodo]
        return _resultado(rid, {clave: []})
    if metodo == "tools/call":
        return _tools_call(db, user, ctx, rid, params)
    return error_con_codigo(rid, METHOD_NOT_FOUND, "mcp_metodo_no_soportado", metodo=metodo[:80])


# ── Configuración (Configuración → Agentes de código) ───────────────────────

def catalogo_para(db: Session, user) -> list[dict]:
    """Todas las herramientas de trabajo diario con si `user` puede usarlas y por qué no."""
    from app.services.mcp_herramientas import HERRAMIENTAS, denegacion
    salida = []
    for h in HERRAMIENTAS:
        motivo = denegacion(db, user, h)
        salida.append({"name": h.nombre, "title": h.titulo, "description": h.descripcion, "writes": h.escribe,
                       "capability": h.politica.capacidad, "route": f"{h.politica.metodo} /api/v1{h.politica.ruta}",
                       "notebook": h.cuaderno, "available": motivo is None,
                       "reason": {"code": motivo[0], "params": motivo[1]} if motivo else None})
    return salida
