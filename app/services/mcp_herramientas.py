"""Herramientas MCP para agentes de código (OpenCode, Claude Code…), 23-11-2026.

Un desarrollador o un técnico, sin salir de su editor o su terminal, ve sus
tareas y tickets, busca tickets, proyectos y tareas, comenta y cambia estados,
imputa horas, arranca y para el cronómetro, abre un cambio por el flujo de
cambios y, si él mismo lo comparte, lee sus notas de «Mi cuaderno». Guía:
`docs/integraciones/MCP.md`.

Nada nuevo por debajo: cada herramienta declara su **ruta REST equivalente**
(`Politica`: método, ruta y capacidad) y llama al MISMO servicio que esa ruta:

- la capacidad es la de la ruta (`requiere_capacidad`), y además se miran el
  módulo cerrado por el rol (`modulos.modulo_cerrado`), la matriz GRC
  (`grc_enforce.decidir`) y el ABAC del prefijo y del recurso
  (`enforce_abac`), como en `get_current_user` para una petición REST;
- el alcance de los datos y las reglas (transiciones de tareas, tickets y
  cambios, la puerta de alta de imputaciones `crear_imputacion_validada`, el
  cronómetro, el CAB y el catálogo de cambios estándar) son los del servicio;
- el aislamiento por empresa es el de la sesión (`TenantSession`, la empresa
  de la credencial; `TENANT_SESION_SIN_CONTEXTO=cerrar`).

Las listas van paginadas (`page`, `page_size` ≤ 100). Un fallo de negocio sale
con el código del catálogo (`app/core/codigos_de_error.py`). El registro, el
límite de uso y el modo de escritura los pone `mcp_service`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.service_desk._enums import TicketStatus
from app.services.ai_chat.tool_execution.politica import Politica

logger = logging.getLogger(__name__)

TAM_PAGINA_DEFECTO = 25
TAM_PAGINA_MAX = 100
_TEXTO_MAX = 4000          # descripciones y textos largos que se devuelven
_COMENTARIO_MAX = 2000
_NOTA_MAX = 20000

_GET, _POST, _PATCH = "GET", "POST", "PATCH"


class ArgumentosNoValidos(ValueError):
    """Los argumentos no cumplen el esquema de la herramienta."""


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    titulo: str
    descripcion: str
    propiedades: dict
    politica: Politica
    escribe: bool
    manejador: Callable[[Session, Any, dict], dict]
    requeridos: tuple = ()
    #: Argumento que identifica el recurso de la ruta (ABAC por recurso).
    recurso: Optional[str] = None
    #: Herramienta de «Mi cuaderno»: además, `MCP_NOTEBOOK_ENABLED` de la empresa.
    cuaderno: bool = False
    #: Lectura que deja rastro en `audit_log` (datos personales: las notas).
    auditar_lectura: bool = False
    #: Idempotente (anotación MCP `idempotentHint`).
    idempotente: bool = False
    extra: dict = field(default_factory=dict)

    def esquema(self) -> dict:
        return {"type": "object", "properties": self.propiedades, "required": list(self.requeridos),
                "additionalProperties": False}


# ── Utilidades ──────────────────────────────────────────────────────────────

_PAGINACION = {
    "page": {"type": "integer", "minimum": 1, "default": 1, "description": "Page number (1-based)."},
    "page_size": {"type": "integer", "minimum": 1, "maximum": TAM_PAGINA_MAX, "default": TAM_PAGINA_DEFECTO,
                  "description": f"Items per page (1-{TAM_PAGINA_MAX})."},
}


def _pagina(args: dict) -> tuple[int, int]:
    return int(args.get("page") or 1), int(args.get("page_size") or TAM_PAGINA_DEFECTO)


def _lista(items: list, page: int, page_size: int, total: Optional[int] = None) -> dict:
    """Sobre de lista: con `total` si se conoce; si no, `has_more` por página llena."""
    hay_mas = (page * page_size < total) if total is not None else len(items) >= page_size
    return {"items": items, "page": page, "page_size": page_size, "total": total,
            "has_more": hay_mas, "next_page": page + 1 if hay_mas else None}


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _valor(v):
    return getattr(v, "value", v)


def _recortar(texto: Optional[str], maximo: int) -> Optional[str]:
    if texto is None:
        return None
    return texto if len(texto) <= maximo else texto[:maximo] + "…"


_TIPOS = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def validar(h: Herramienta, args: dict) -> dict:
    """Comprueba `args` contra el esquema (lo que usamos de JSON Schema) y pone los defectos."""
    desconocidos = sorted(set(args) - set(h.propiedades))
    if desconocidos:
        raise ArgumentosNoValidos(f"unknown argument(s): {', '.join(desconocidos)}")
    for r in h.requeridos:
        if args.get(r) in (None, ""):
            raise ArgumentosNoValidos(f"'{r}' is required")
    salida = {}
    for nombre, spec in h.propiedades.items():
        if nombre not in args or args[nombre] is None:
            if "default" in spec:
                salida[nombre] = spec["default"]
            continue
        v = args[nombre]
        tipo = spec.get("type")
        esperado = _TIPOS.get(tipo)
        if tipo in ("integer", "number") and isinstance(v, bool):
            raise ArgumentosNoValidos(f"'{nombre}' must be {tipo}")
        if tipo == "integer" and isinstance(v, float) and v.is_integer():
            v = int(v)
        if esperado and not isinstance(v, esperado):
            raise ArgumentosNoValidos(f"'{nombre}' must be {tipo}")
        if "enum" in spec and v not in spec["enum"]:
            raise ArgumentosNoValidos(f"'{nombre}' must be one of: {', '.join(map(str, spec['enum']))}")
        if "minimum" in spec and v < spec["minimum"]:
            raise ArgumentosNoValidos(f"'{nombre}' must be >= {spec['minimum']}")
        if "maximum" in spec and v > spec["maximum"]:
            raise ArgumentosNoValidos(f"'{nombre}' must be <= {spec['maximum']}")
        if tipo == "string":
            v = v.strip()
            if spec.get("maxLength") and len(v) > spec["maxLength"]:
                raise ArgumentosNoValidos(f"'{nombre}' is longer than {spec['maxLength']} characters")
            if spec.get("minLength") and len(v) < spec["minLength"]:
                raise ArgumentosNoValidos(f"'{nombre}' needs at least {spec['minLength']} characters")
            if spec.get("format") == "date":
                try:
                    date.fromisoformat(v)
                except ValueError as exc:
                    raise ArgumentosNoValidos(f"'{nombre}' must be a date YYYY-MM-DD") from exc
        salida[nombre] = v
    for r in h.requeridos:
        if salida.get(r) in (None, ""):
            raise ArgumentosNoValidos(f"'{r}' is required")
    return salida


# ── Puertas: capacidad, módulo, GRC, ABAC ───────────────────────────────────

def cuaderno_por_mcp_encendido(db: Session, org_id: Optional[str]) -> bool:
    from app.services.settings_service import get_runtime_bool
    return bool(get_runtime_bool(db, "MCP_NOTEBOOK_ENABLED", org_id, default=False))


def denegacion(db: Session, user, h: Herramienta) -> Optional[tuple[str, dict]]:
    """`(codigo, params)` si `user` no puede usar `h` (lo mismo que su ruta REST), o None."""
    from app.core import capacidades as _capacidades
    from app.core.grc_catalog import action_for, module_for_path
    from app.core.grc_enforce import decidir
    from app.core.modulos import modulo_cerrado

    p = h.politica
    if p.capacidad is not None and not _capacidades.tiene(db, user, p.capacidad):
        return "mcp_herramienta_sin_capacidad", {"herramienta": h.nombre, "capacidad": p.capacidad}
    ruta = "/api/v1" + p.ruta
    modulo = modulo_cerrado(db, user, ruta)
    if modulo:
        return "mcp_herramienta_modulo_cerrado", {"herramienta": h.nombre, "modulo": modulo}
    modulo_grc, accion = module_for_path(ruta), action_for(p.metodo, ruta)
    if modulo_grc and accion and decidir(db, user, modulo_grc, accion, getattr(user, "organization_id", None))["denied"]:
        return "mcp_herramienta_grc", {"herramienta": h.nombre, "accion": accion, "modulo": modulo_grc}
    if h.cuaderno and not cuaderno_por_mcp_encendido(db, getattr(user, "organization_id", None)):
        return "mcp_cuaderno_apagado", {}
    return None


def aplicar_abac(db: Session, user, h: Herramienta, args: dict) -> None:
    """El ABAC del prefijo de la ruta equivalente (como `aplicar_abac_a_principal`)."""
    from app.core.abac_dependency import _resolve_coverage
    from app.core.abac_enforce import enforce_abac
    cobertura = _resolve_coverage("/api/v1" + h.politica.ruta)
    if cobertura is None:
        return
    tipo, accion = cobertura
    enforce_abac(db, user, tipo, resource_id=args.get(h.recurso) if h.recurso else None, action=accion)


# ── Resolución de referencias (id o código) dentro del alcance ─────────────

def _proyecto(db: Session, user, ref: Optional[str]):
    """Proyecto por id, código o nombre entre los que ve `user` (`scope_projects_query`)."""
    if not ref:
        return None
    from app.services.ai_chat.tool_execution.politica import buscar_proyecto
    p = buscar_proyecto(db, user, ref)
    if p is None:
        raise error(404, "no_encontrado", que="proyecto")
    return p


def _id_de_tarea(db: Session, user, ref: str) -> str:
    from app.models.task import Task
    from app.services.task_service import task_query_for_user
    fila = task_query_for_user(db, user).with_entities(Task.id).filter(or_(Task.id == ref, Task.code == ref)).first()
    if fila is None:
        raise error(404, "no_encontrado", que="tarea")
    return fila[0]


def _id_de_ticket(db: Session, user, ref: str) -> str:
    from app.models.service_desk import Ticket
    from app.services.service_desk.scoping import scope_ticket_query
    fila = scope_ticket_query(db.query(Ticket.id), db, user).filter(or_(Ticket.id == ref, Ticket.number == ref)).first()
    if fila is None:
        raise error(404, "no_encontrado", que="ticket")
    return fila[0]


def _cambio(db: Session, user, ref: str):
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import scope_change_query
    c = scope_change_query(db.query(ITSMChangeRequest), db, user).filter(
        or_(ITSMChangeRequest.id == ref, ITSMChangeRequest.number == ref)).first()
    if c is None:
        raise error(404, "no_encontrado", detail="Change request no encontrado", que="solicitud_de_cambio")
    return c


# ── Tareas ──────────────────────────────────────────────────────────────────

def _tarea_corta(t) -> dict:
    proyecto = getattr(t, "project", None)
    asignado = getattr(t, "assignee", None)
    return {"id": t.id, "code": t.code, "title": t.title, "status": _valor(t.status), "priority": _valor(t.priority),
            "project": {"id": t.project_id, "code": getattr(proyecto, "code", None), "name": getattr(proyecto, "name", None)},
            "assignee": getattr(asignado, "full_name", None), "due_date": _iso(t.due_date),
            "estimated_hours": t.estimated_hours}


def _listar_tareas(db: Session, user, args: dict, mias: bool) -> dict:
    from app.core.abac_enforce import enforce_abac
    from app.models.task import ESTADOS_DE_TAREA_TERMINADOS, Task
    from app.services.task_service import build_task_list_query
    enforce_abac(db, user, "task", action="read")
    page, page_size = _pagina(args)
    proyecto = _proyecto(db, user, args.get("project"))
    estado = args.get("status")
    q = build_task_list_query(db, user, assigned_to_me=mias, project_id=proyecto.id if proyecto else None,
                              status=estado, search=args.get("query"))
    if not estado and not args.get("include_done"):
        q = q.filter(Task.status.notin_(ESTADOS_DE_TAREA_TERMINADOS))
    total = q.count()
    filas = q.offset((page - 1) * page_size).limit(page_size).all()
    return _lista([_tarea_corta(t) for t in filas], page, page_size, total)


def list_my_tasks(db: Session, user, args: dict) -> dict:
    return _listar_tareas(db, user, args, mias=True)


def search_tasks(db: Session, user, args: dict) -> dict:
    return _listar_tareas(db, user, args, mias=False)


def get_task(db: Session, user, args: dict) -> dict:
    from app.core.abac_enforce import enforce_abac
    from app.services.task_service import get_task_record
    from app.services.tasks.core import _TASK_VALID_TRANSITIONS
    tid = _id_de_tarea(db, user, args["task"])
    enforce_abac(db, user, "task", tid, action="read")
    t = get_task_record(db, tid, user)
    comentarios = sorted(t.comments or [], key=lambda c: c.created_at or 0)[-20:]
    return {**_tarea_corta(t), "description": _recortar(t.description, _TEXTO_MAX),
            "blocked_reason": t.blocked_reason, "start_date": _iso(t.start_date), "progress_pct": t.progress_pct,
            "allowed_next_statuses": sorted(_valor(s) for s in _TASK_VALID_TRANSITIONS.get(t.status, set())),
            "comments": [{"id": c.id, "author": getattr(c.author, "full_name", None),
                          "content": _recortar(c.content, _COMENTARIO_MAX), "created_at": _iso(c.created_at)}
                         for c in comentarios]}


def add_task_comment(db: Session, user, args: dict) -> dict:
    from app.schemas import TaskCommentCreate
    from app.services.task_service import add_comment_record
    tid = _id_de_tarea(db, user, args["task"])
    c = add_comment_record(db, tid, TaskCommentCreate(content=args["content"]), user)
    return {"id": c.id, "task_id": tid, "created_at": _iso(c.created_at)}


def change_task_status(db: Session, user, args: dict) -> dict:
    from app.core.abac_enforce import enforce_abac
    from app.models.task import TaskStatus
    from app.schemas import TaskUpdate
    from app.services.task_service import update_task_record
    tid = _id_de_tarea(db, user, args["task"])
    enforce_abac(db, user, "task", tid, action="update")
    datos: dict = {"status": TaskStatus(args["status"])}
    if args.get("reason"):
        datos["move_reason"] = args["reason"]
    if args.get("blocked_reason"):
        datos["blocked_reason"] = args["blocked_reason"]
    t, _ = update_task_record(db, tid, TaskUpdate(**datos), user)
    return _tarea_corta(t)


# ── Tickets ─────────────────────────────────────────────────────────────────

_CAMPOS_TICKET = ("id", "number", "title", "status", "priority", "ticket_type", "assigned_to_name",
                  "assigned_group_name", "project_name", "requester_name", "sla_resolution_due",
                  "sla_resolution_breached", "created_at")


def _ticket_corto(d: dict) -> dict:
    return {k: d.get(k) for k in _CAMPOS_TICKET}


def search_tickets(db: Session, user, args: dict) -> dict:
    from app.services.service_desk.ticket_read_service import list_tickets_payload
    from app.services.sla_service import ticket_out
    page, page_size = _pagina(args)
    proyecto = _proyecto(db, user, args.get("project"))
    datos = list_tickets_payload(db=db, current_user=user, ticket_out=ticket_out, status=args.get("status"),
                                 priority=args.get("priority"), project_id=proyecto.id if proyecto else None,
                                 search=args.get("query"), page=page, page_size=page_size)
    return _lista([_ticket_corto(t) for t in datos["tickets"]], page, page_size, datos.get("total"))


def list_my_tickets(db: Session, user, args: dict) -> dict:
    from app.services.service_desk.ticket_read_service import my_queue_payload
    from app.services.sla_service import ticket_out
    page, page_size = _pagina(args)
    todos = my_queue_payload(db, user, ticket_out)
    inicio = (page - 1) * page_size
    return _lista([_ticket_corto(t) for t in todos[inicio:inicio + page_size]], page, page_size, len(todos))


def get_ticket(db: Session, user, args: dict) -> dict:
    from app.models.service_desk import TicketStatus
    from app.services.service_desk.ticket_read_service import ticket_detail_payload
    from app.services.sla_service import ticket_out
    tid = _id_de_ticket(db, user, args["ticket"])
    d = ticket_detail_payload(db, user, tid, ticket_out)
    comentarios = list(d.get("comments") or [])[-30:]
    return {**_ticket_corto(d), "description": _recortar(d.get("description"), _TEXTO_MAX),
            "urgency": d.get("urgency"), "impact": d.get("impact"), "support_level": d.get("support_level"),
            "ci_name": d.get("ci_name"), "resolution": d.get("resolution"), "resolution_code": d.get("resolution_code"),
            "statuses": [s.value for s in TicketStatus],
            "comments": [{"id": c.get("id"), "author": c.get("author_name"), "is_public": c.get("is_public"),
                          "body": _recortar(c.get("body"), _COMENTARIO_MAX), "created_at": _iso(c.get("created_at"))}
                         for c in comentarios]}


def add_ticket_comment(db: Session, user, args: dict) -> dict:
    from app.services.service_desk.comment_service import add_internal_comment, get_scoped_ticket_or_404
    from app.services.service_desk.ticket_ops_service import commit_or_rollback
    tid = _id_de_ticket(db, user, args["ticket"])
    ticket = get_scoped_ticket_or_404(db, user, tid)
    publico = bool(args.get("is_public"))
    c = add_internal_comment(db, ticket, tid, args["body"], publico, user)
    commit_or_rollback(db)
    db.refresh(c)
    return {"id": c.id, "ticket_id": tid, "number": ticket.number, "is_public": publico, "created_at": _iso(c.created_at)}


def _efectos_de_fondo(efectos: dict, ticket, tid: str) -> None:
    """Las tareas de fondo del PATCH REST (perfil e historial semánticos), en línea y sin romper la llamada."""
    from app.core.tareas_diferidas import EnElMomento
    from app.services.service_desk.semantic_feedback_service import (
        enqueue_cierre_semantico, enqueue_profile_refresh, enqueue_routing_outcome)
    fondo = EnElMomento()   # item 36: sin `fastapi.BackgroundTasks` en un servicio
    org = getattr(ticket, "organization_id", None)
    try:
        if efectos.get("refresh_profile"):
            enqueue_profile_refresh(fondo, ticket.assigned_to_user_id, org_id=org)
            # 23-11-2026: historial del nivel 3 y veredicto de la sugerencia, como el PATCH.
            enqueue_cierre_semantico(fondo, "ticket", tid, org_id=org)
        if efectos.get("record_routing_outcome"):
            enqueue_routing_outcome(fondo, tid, org_id=org)
    except Exception:  # noqa: BLE001 - como en segundo plano: no deshace el cambio de estado
        logger.warning("mcp: tarea de fondo del ticket no ejecutada", exc_info=True)


def change_ticket_status(db: Session, user, args: dict) -> dict:
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.sla_service import ticket_out
    from app.services.service_desk.ticket_ops_service import commit_or_rollback
    from app.services.service_desk.ticket_update_service import apply_ticket_update, get_scoped_ticket_or_404
    tid = _id_de_ticket(db, user, args["ticket"])
    ticket = get_scoped_ticket_or_404(db, user, tid)
    datos = {k: args[k] for k in ("status", "resolution", "resolution_code") if args.get(k)}
    efectos = apply_ticket_update(db=db, ticket=ticket, ticket_id=tid, payload=TicketUpdateIn(**datos),
                                  current_user_id=user.id, old_assigned_to=ticket.assigned_to_user_id,
                                  old_support_level=ticket.support_level,
                                  organization_id=getattr(user, "organization_id", None))
    commit_or_rollback(db)
    db.refresh(ticket)
    _efectos_de_fondo(efectos or {}, ticket, tid)
    return _ticket_corto(ticket_out(ticket))


# ── Proyectos ───────────────────────────────────────────────────────────────

def list_projects(db: Session, user, args: dict) -> dict:
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    page, page_size = _pagina(args)
    q = scope_projects_query(db.query(Project), db, user)
    texto = args.get("query")
    if texto:
        q = q.filter(or_(Project.name.ilike(f"%{texto}%"), Project.code.ilike(f"%{texto}%")))
    if args.get("status"):
        from app.models.project import ProjectStatus
        if args["status"] not in {s.value for s in ProjectStatus}:
            raise error(422, "estado_no_valido", estado=args["status"])
        q = q.filter(Project.status == ProjectStatus(args["status"]))
    total = q.count()
    filas = q.order_by(Project.name).offset((page - 1) * page_size).limit(page_size).all()
    return _lista([{"id": p.id, "code": p.code, "name": p.name, "status": _valor(p.status)} for p in filas],
                  page, page_size, total)


# ── Horas y cronómetro ──────────────────────────────────────────────────────

def _imputacion(i) -> dict:
    return {"id": i.id, "date": _iso(i.date), "hours": i.hours, "project_id": i.project_id, "task_id": i.task_id,
            "is_billable": bool(getattr(i, "is_billable", False))}


def _tarea_del_proyecto(db: Session, user, ref: Optional[str], proyecto_id: str) -> Optional[str]:
    if not ref:
        return None
    from app.models.task import Task
    tid = _id_de_tarea(db, user, ref)
    if db.query(Task.id).filter(Task.id == tid, Task.project_id == proyecto_id).first() is None:
        raise error(404, "tarea_no_en_proyecto")
    return tid


def log_time(db: Session, user, args: dict) -> dict:
    from app.core.timeutil import today_for_user
    from app.services.imputation_service.alta import crear_imputacion_validada
    proyecto = _proyecto(db, user, args["project"])
    fecha = date.fromisoformat(args["date"]) if args.get("date") else today_for_user(user)
    i = crear_imputacion_validada(user, db, project_id=proyecto.id, fecha=fecha, horas=args["hours"],
                                  task_id=_tarea_del_proyecto(db, user, args.get("task"), proyecto.id),
                                  description=args.get("description"), is_billable=bool(args.get("is_billable")),
                                  force_duplicate=bool(args.get("force_duplicate")))
    return _imputacion(i)


def _cronometro(timer) -> dict:
    from app.services.imputation_service import timer_out
    return {"active": True, **timer_out(timer).model_dump(mode="json")}


def get_timer(db: Session, user, args: dict) -> dict:
    from app.services.imputation_service import get_current_timer_record
    timer = get_current_timer_record(db, user)
    return _cronometro(timer) if timer else {"active": False}


def start_timer(db: Session, user, args: dict) -> dict:
    from app.schemas.time_tracking import TimerStartPayload
    from app.services.imputation_service import get_current_timer_record, start_timer_session
    proyecto = _proyecto(db, user, args["project"])
    tarea = _tarea_del_proyecto(db, user, args.get("task"), proyecto.id)
    start_timer_session(TimerStartPayload(project_id=proyecto.id, task_id=tarea), user, db)
    return _cronometro(get_current_timer_record(db, user))


def stop_timer(db: Session, user, args: dict) -> dict:
    from app.models.imputation import TimerSession
    from app.schemas.time_tracking import TimerStopPayload
    from app.services.imputation_service import get_current_timer_record, stop_timer_session
    datos = {k: args[k] for k in ("description", "is_billable", "hours", "force_duplicate") if k in args}
    if args.get("task"):
        actual = get_current_timer_record(db, user)
        proyecto_id = actual.project_id if isinstance(actual, TimerSession) else None
        datos["task_id"] = _tarea_del_proyecto(db, user, args["task"], proyecto_id) if proyecto_id else _id_de_tarea(db, user, args["task"])
    i = stop_timer_session(TimerStopPayload(**datos), user, db)
    return {"stopped": True, "imputation": _imputacion(i)}


# ── Cambios (ITSM) ──────────────────────────────────────────────────────────

def list_standard_changes(db: Session, user, args: dict) -> dict:
    from app.services.service_desk.cambios_estandar_service import listar_modelos
    page, page_size = _pagina(args)
    modelos = listar_modelos(db, user, solo_vigentes=True)
    texto = (args.get("query") or "").lower()
    if texto:
        modelos = [m for m in modelos if texto in (m.get("name") or "").lower()
                   or texto in (m.get("description") or "").lower()]
    inicio = (page - 1) * page_size
    return _lista(modelos[inicio:inicio + page_size], page, page_size, len(modelos))


def _cambio_con_estado(db: Session, change, full: bool = False) -> dict:
    from app.models.service_desk._enums import TRANSICIONES_DE_CAMBIO
    from app.services.service_desk import cab_workflow_service as cab
    from app.services.service_desk.change_service import serialize_change
    d = serialize_change(change, full=full)
    if full:
        for k in ("description", "implementation_plan", "rollback_plan", "test_plan", "business_justification",
                  "impact_description", "pir_notes"):
            d[k] = _recortar(d.get(k), _TEXTO_MAX)
    flujo = cab.get_workflow(db, change_id=change.id)
    d["cab"] = ({"status": flujo["status"], "quorum": flujo.get("quorum"), "meeting": flujo.get("meeting"),
                 "votes": [{"name": v.get("name"), "decision": v.get("decision"), "voted_at": v.get("voted_at")}
                           for v in flujo.get("votes") or []]} if flujo else None)
    d["allowed_next_statuses"] = sorted(TRANSICIONES_DE_CAMBIO.get(d.get("status") or "", frozenset()))
    return d


_CAMPOS_DE_CAMBIO = ("title", "description", "change_type", "standard_model_id", "risk", "priority",
                     "implementation_plan", "rollback_plan", "test_plan", "business_justification",
                     "impact_description", "planned_start", "planned_end", "affected_cis", "related_ticket_id",
                     "downtime_minutes")


def open_change(db: Session, user, args: dict) -> dict:
    from app.services.service_desk.change_service import create_change_record, update_change_record
    from app.services.service_desk.ticket_ops_service import commit_or_rollback
    datos = {k: args[k] for k in _CAMPOS_DE_CAMBIO if args.get(k) not in (None, "", [])}
    if datos.get("related_ticket_id"):
        datos["related_ticket_id"] = _id_de_ticket(db, user, datos["related_ticket_id"])
    change = create_change_record(db, user, datos)
    commit_or_rollback(db)
    db.refresh(change)
    if args.get("submit"):
        update_change_record(db, user, change.id, {"status": "submitted"})
        commit_or_rollback(db)
        db.refresh(change)
    return _cambio_con_estado(db, change)


def get_change(db: Session, user, args: dict) -> dict:
    return _cambio_con_estado(db, _cambio(db, user, args["change"]), full=True)


def list_changes(db: Session, user, args: dict) -> dict:
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import build_change_list_query, serialize_change
    page, page_size = _pagina(args)
    q = build_change_list_query(db, user, args.get("status"), args.get("change_type"), None, None)
    if args.get("mine", True):
        q = q.filter(or_(ITSMChangeRequest.requester_id == user.id, ITSMChangeRequest.owner_id == user.id))
    total = q.count()
    filas = q.order_by(ITSMChangeRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    campos = ("id", "number", "title", "change_type", "status", "risk", "priority", "planned_start", "planned_end",
              "requester", "owner", "created_at")
    return _lista([{k: serialize_change(c).get(k) for k in campos} for c in filas], page, page_size, total)


# ── Mi cuaderno (solo lo que su dueño comparte con sus agentes) ─────────────

def _paginas_compartidas(db: Session, user):
    """Páginas vivas de cuadernos PROPIOS compartidos con sus agentes (`target_type = agents`)."""
    from app.models.cuaderno import Notebook, NotebookPage as P, NotebookSection, NotebookShare as S
    from app.services.cuaderno.compartir import AGENTES
    filas = db.query(S.notebook_id, S.section_id).join(Notebook, Notebook.id == S.notebook_id).filter(
        S.target_type == AGENTES, S.target_id == user.id, Notebook.owner_id == user.id).all()
    cuadernos = {n for n, s in filas if not s}
    secciones = {s for _, s in filas if s}
    return db.query(P, Notebook.title, NotebookSection.title) \
        .join(Notebook, Notebook.id == P.notebook_id) \
        .join(NotebookSection, NotebookSection.id == P.section_id) \
        .filter(P.owner_id == user.id, Notebook.owner_id == user.id,
                P.deleted_at.is_(None), Notebook.deleted_at.is_(None), NotebookSection.deleted_at.is_(None),
                or_(P.notebook_id.in_(cuadernos or {""}), P.section_id.in_(secciones or {""})))


def search_notebook(db: Session, user, args: dict) -> dict:
    from app.models.cuaderno import NotebookPage as P
    from app.services.cuaderno.servicio import _fragmento
    page, page_size = _pagina(args)
    q = _paginas_compartidas(db, user)
    texto = (args.get("query") or "").strip()
    if texto:
        patron = f"%{texto.lower()}%"
        q = q.filter(or_(func.lower(P.title).like(patron), func.lower(P.content_text).like(patron)))
    total = q.count()
    filas = q.order_by(P.updated_at.desc().nullslast(), P.created_at.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return _lista([{"id": p.id, "title": p.title, "notebook": nb, "section": sec,
                    "snippet": _fragmento(p.content_text or "", texto) if texto else (p.content_text or "")[:160],
                    "updated_at": _iso(p.updated_at or p.created_at)} for p, nb, sec in filas],
                  page, page_size, total)


def get_notebook_page(db: Session, user, args: dict) -> dict:
    from app.models.cuaderno import NotebookPage as P
    fila = _paginas_compartidas(db, user).filter(P.id == args["page_id"]).first()
    if fila is None:
        raise error(404, "mcp_cuaderno_no_compartido")
    p, nb, sec = fila
    texto = p.content_text or ""
    return {"id": p.id, "title": p.title, "notebook": nb, "section": sec, "text": _recortar(texto, _NOTA_MAX),
            "truncated": len(texto) > _NOTA_MAX, "updated_at": _iso(p.updated_at or p.created_at)}


# ── Catálogo ────────────────────────────────────────────────────────────────

def _s(descripcion: str, **extra) -> dict:
    return {"type": "string", "description": descripcion, **extra}


_TAREA = _s("Task id or code (e.g. TSK-042).", maxLength=60)
_TICKET = _s("Ticket id or number (e.g. INC-00123).", maxLength=60)
_PROYECTO = _s("Project id, code or name (among the projects you can see).", maxLength=200)
_ESTADOS_TAREA = ["backlog", "todo", "in_progress", "blocked", "in_review", "done", "cancelled"]
# Los del enum (sin lista escrita a mano: un estado nuevo entra solo).
_ESTADOS_TICKET = [s.value for s in TicketStatus]


def _h(nombre, titulo, descripcion, propiedades, politica, manejador, *, escribe=False, requeridos=(), **kw):
    return Herramienta(nombre=nombre, titulo=titulo, descripcion=descripcion, propiedades=propiedades,
                       politica=politica, escribe=escribe, manejador=manejador, requeridos=tuple(requeridos), **kw)


HERRAMIENTAS: tuple[Herramienta, ...] = (
    # Tareas
    _h("list_my_tasks", "My tasks",
       "List the tasks assigned to you (open ones unless you pass a status or include_done). Paginated.",
       {"status": _s("Filter by status; one value or CSV (backlog, todo, in_progress, blocked, in_review, done, cancelled)."),
        "project": _PROYECTO, "include_done": {"type": "boolean", "default": False,
                                               "description": "Also list done and cancelled tasks."},
        **_PAGINACION},
       Politica(_GET, "/tasks", None), list_my_tasks, idempotente=True),
    _h("search_tasks", "Search tasks",
       "Search the tasks you can see by text (title, code), project or status. Paginated.",
       {"query": _s("Text to look for.", maxLength=200), "project": _PROYECTO,
        "status": _s("Filter by status; one value or CSV."),
        "include_done": {"type": "boolean", "default": False, "description": "Include done and cancelled tasks."},
        **_PAGINACION},
       Politica(_GET, "/tasks", None), search_tasks, idempotente=True),
    _h("get_task", "Task detail",
       "Detail of a task: description, status, the statuses it can move to, and its latest comments.",
       {"task": _TAREA}, Politica(_GET, "/tasks/{task_id}", None), get_task, requeridos=("task",),
       recurso="task", idempotente=True),
    _h("add_task_comment", "Comment on a task",
       "Add a comment to a task you can work on (its project manager, assignee or reporter).",
       {"task": _TAREA, "content": _s("Comment text.", minLength=1, maxLength=10000)},
       Politica(_POST, "/tasks/{task_id}/comments", "tareas.trabajar"), add_task_comment, escribe=True,
       requeridos=("task", "content"), recurso="task"),
    _h("change_task_status", "Change task status",
       "Move a task to another status with the same transition rules as the app (see allowed_next_statuses in get_task).",
       {"task": _TAREA, "status": _s("New status.", enum=_ESTADOS_TAREA),
        "reason": _s("Why it moves (kept in the movement log).", maxLength=500),
        "blocked_reason": _s("Reason when the new status is blocked.", maxLength=2000)},
       Politica(_PATCH, "/tasks/{task_id}", None), change_task_status, escribe=True,
       requeridos=("task", "status"), recurso="task"),
    # Tickets
    _h("list_my_tickets", "My tickets", "Your service desk work queue (tickets assigned to you). Paginated.",
       {**_PAGINACION}, Politica(_GET, "/sd/tickets/my-queue", None), list_my_tickets, idempotente=True),
    _h("search_tickets", "Search tickets",
       "Search the service desk tickets you can see by text, status, priority or project. Paginated.",
       {"query": _s("Text to look for (title, number, description).", maxLength=200),
        "status": _s("Filter by status.", enum=_ESTADOS_TICKET),
        "priority": _s("Filter by priority (e.g. p1_critical, p2_high, p3_medium, p4_low)."),
        "project": _PROYECTO, **_PAGINACION},
       Politica(_GET, "/sd/tickets", None), search_tickets, idempotente=True),
    _h("get_ticket", "Ticket detail",
       "Detail of a ticket: description, status, SLA, resolution and its latest comments (public and internal).",
       {"ticket": _TICKET}, Politica(_GET, "/sd/tickets/{ticket_id}", None), get_ticket, requeridos=("ticket",),
       recurso="ticket", idempotente=True),
    _h("add_ticket_comment", "Comment on a ticket",
       "Add a comment to a ticket. Internal by default; set is_public=true only for a reply the customer must see.",
       {"ticket": _TICKET, "body": _s("Comment text.", minLength=1, maxLength=20000),
        "is_public": {"type": "boolean", "default": False,
                      "description": "true: visible to the customer (and notified). false: internal note."}},
       Politica(_POST, "/sd/tickets/{ticket_id}/comments", "sd.trabajar"), add_ticket_comment, escribe=True,
       requeridos=("ticket", "body"), recurso="ticket"),
    _h("change_ticket_status", "Change ticket status",
       "Change the status of a ticket with the same rules as the app (resolving may require resolution text).",
       {"ticket": _TICKET, "status": _s("New status.", enum=_ESTADOS_TICKET),
        "resolution": _s("Resolution text (when resolving or closing).", maxLength=20000),
        "resolution_code": _s("Standard resolution code, if your company uses them.", maxLength=100)},
       Politica(_PATCH, "/sd/tickets/{ticket_id}", None), change_ticket_status, escribe=True,
       requeridos=("ticket", "status"), recurso="ticket"),
    # Proyectos
    _h("list_projects", "Search projects", "Search the projects you can see by name or code. Paginated.",
       {"query": _s("Text in the name or code.", maxLength=200),
        "status": _s("Filter by status (e.g. planning, active, on_hold, completed)."), **_PAGINACION},
       Politica(_GET, "/projects", None), list_projects, idempotente=True),
    # Horas
    _h("log_time", "Log time",
       "Log hours on a project (optionally a task) through the same validated entry as the timesheet form: "
       "period lock, daily and weekly caps, duplicates and overtime rules apply.",
       {"project": _PROYECTO, "hours": {"type": "number", "minimum": 0.01, "maximum": 24,
                                         "description": "Hours to log (0 < hours <= 24)."},
        "date": _s("Day, YYYY-MM-DD (default: today in your time zone).", format="date"),
        "task": _s("Task id or code inside that project (optional).", maxLength=60),
        "description": _s("What you did.", maxLength=2000),
        "is_billable": {"type": "boolean", "default": False, "description": "Billable hours."},
        "force_duplicate": {"type": "boolean", "default": False,
                            "description": "Log it even if a similar entry already exists that day."}},
       Politica(_POST, "/imputations", None), log_time, escribe=True, requeridos=("project", "hours")),
    _h("get_timer", "Timer status", "Your running work timer, if any (project, task, elapsed seconds).",
       {}, Politica(_GET, "/imputations/timer/current", None), get_timer, idempotente=True),
    _h("start_timer", "Start timer",
       "Start your work timer on a project (and optionally a task assigned to you). Only one can run at a time.",
       {"project": _PROYECTO, "task": _s("Task id or code inside that project (optional).", maxLength=60)},
       Politica(_POST, "/imputations/timer/start", None), start_timer, escribe=True, requeridos=("project",)),
    _h("stop_timer", "Stop timer",
       "Stop your running timer and log its time through the validated timesheet entry.",
       {"description": _s("What you did.", maxLength=2000),
        "is_billable": {"type": "boolean", "default": True, "description": "Billable hours."},
        "task": _s("Task id or code to log the time on (optional).", maxLength=60),
        "hours": {"type": "number", "minimum": 0.01, "maximum": 24,
                  "description": "Real hours to log if the timer was left running (at most the measured time)."},
        "force_duplicate": {"type": "boolean", "default": False,
                            "description": "Log it even if a similar entry already exists that day."}},
       Politica(_POST, "/imputations/timer/stop", None), stop_timer, escribe=True),
    # Cambios
    _h("list_standard_changes", "Standard changes",
       "The company's catalogue of approved standard changes (pre-approved by the CAB) that are valid today. "
       "Use one of them with open_change(standard_model_id=…) to skip the CAB when it fits.",
       {"query": _s("Text in the name or description.", maxLength=200), **_PAGINACION},
       Politica(_GET, "/sd/standard-changes", "sd.completo"), list_standard_changes, idempotente=True),
    _h("open_change", "Open a change",
       "Open an ITSM change request through the change flow. The server decides the type: it is standard only "
       "with a standard_model_id that fits; otherwise normal and it goes to the CAB when submitted.",
       {"title": _s("Short title.", minLength=3, maxLength=300),
        "description": _s("What changes and why.", minLength=3, maxLength=20000),
        "change_type": _s("Requested type.", enum=["normal", "standard", "emergency"]),
        "standard_model_id": _s("Standard change model id (from list_standard_changes).", maxLength=36),
        "risk": _s("Risk.", enum=["low", "medium", "high", "critical"]),
        "priority": _s("Priority (e.g. p1_critical, p2_high, p3_medium, p4_low)."),
        "implementation_plan": _s("Implementation plan.", maxLength=20000),
        "rollback_plan": _s("Rollback plan.", maxLength=20000),
        "test_plan": _s("Test plan.", maxLength=20000),
        "business_justification": _s("Business justification.", maxLength=20000),
        "impact_description": _s("Expected impact.", maxLength=20000),
        "planned_start": _s("Planned start, ISO 8601 date-time."),
        "planned_end": _s("Planned end, ISO 8601 date-time."),
        "downtime_minutes": {"type": "integer", "minimum": 0, "description": "Expected downtime in minutes."},
        "affected_cis": {"type": "array", "items": {"type": "string"}, "description": "Affected CI ids."},
        "related_ticket_id": _s("Related ticket id or number.", maxLength=60),
        "submit": {"type": "boolean", "default": False,
                   "description": "Submit it now (standard and low risk: auto-approved; otherwise to the CAB)."}},
       Politica(_POST, "/sd/changes", "sd.administrar"), open_change, escribe=True,
       requeridos=("title", "description")),
    _h("get_change", "Change status",
       "Status of a change request: type, risk, plans, CAB workflow and votes, and the statuses it can move to.",
       {"change": _s("Change id or number (e.g. CHG00042).", maxLength=60)},
       Politica(_GET, "/sd/changes/{change_id}", None), get_change, requeridos=("change",), recurso="change",
       idempotente=True),
    _h("list_changes", "List changes", "Change requests you can see (yours by default). Paginated.",
       {"mine": {"type": "boolean", "default": True, "description": "Only the ones you requested or own."},
        "status": _s("Filter by status (draft, submitted, cab_review, approved, scheduled, in_progress, "
                     "implemented, post_review, closed_success, closed_failed, cancelled)."),
        "change_type": _s("Filter by type.", enum=["normal", "standard", "emergency"]), **_PAGINACION},
       Politica(_GET, "/sd/changes", None), list_changes, idempotente=True),
    # Mi cuaderno
    _h("search_notebook", "Search my shared notes",
       "Search your own «My notebook» pages, only in notebooks or sections you have shared with your coding "
       "agents (private by default). Paginated.",
       {"query": _s("Text in the title or body (optional).", maxLength=200), **_PAGINACION},
       Politica(_GET, "/notebook/search", "cuaderno.usar"), search_notebook, cuaderno=True,
       auditar_lectura=True, idempotente=True),
    _h("get_notebook_page", "Read a shared note",
       "Plain text of one of your notebook pages, only if it is in a notebook or section shared with your agents.",
       {"page_id": _s("Page id (from search_notebook).", maxLength=36)},
       Politica(_GET, "/notebook/pages/{page_id}", "cuaderno.usar"), get_notebook_page, requeridos=("page_id",),
       recurso="page_id", cuaderno=True, auditar_lectura=True, idempotente=True),
)

POR_NOMBRE: dict[str, Herramienta] = {h.nombre: h for h in HERRAMIENTAS}


def _comprobar_catalogo() -> None:
    """Nombres únicos, sin chocar con las del asistente, y capacidades del catálogo."""
    from app.core.capacidades import CAPACIDADES
    from app.services.ai_chat.tool_execution.schema import AGENT_TOOLS
    if len(POR_NOMBRE) != len(HERRAMIENTAS):
        raise RuntimeError("Herramientas MCP con nombre repetido")
    choques = set(POR_NOMBRE) & {t["name"] for t in AGENT_TOOLS}
    if choques:
        raise RuntimeError(f"Herramientas MCP con el nombre de una del asistente: {sorted(choques)}")
    malas = [h.nombre for h in HERRAMIENTAS if h.politica.capacidad and h.politica.capacidad not in CAPACIDADES]
    if malas:
        raise RuntimeError(f"Herramientas MCP con una capacidad fuera del catálogo: {malas}")


_comprobar_catalogo()
