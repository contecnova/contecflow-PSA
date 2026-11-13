"""Workflow execution engine.

Lee la versión publicada de un blueprint y avanza un `WorkflowRun` paso a paso.
Cada nodo es ejecutado por un *executor*; los executors devuelven el `branch`
que indica qué arista tomar (o `WAIT` para pausarse esperando intervención
externa).

Diseño:
    • Síncrono y simple — una transacción por avance.
    • Sin dependencias externas obligatorias (HTTP/notify hacen best-effort).
    • Soporta hasta MAX_STEPS por avance para detectar bucles infinitos.
    • Las decisiones se evalúan con un mini-DSL seguro (sin `eval`).

Flujo:
    start(blueprint_id, target_*)  → instancia run en nodo 'start' → advance()
    advance(run)                    → recorre nodos automáticos hasta `end` /
                                     pausa por approval/wait
    resume(run, branch=…)           → continúa desde un nodo 'waiting'
    cancel(run)                     → corta un run en marcha
    tick_waiting(db)                → wake-up de nodos `wait` cuyo wake_at <= now
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.workflow_designer import (
    WorkflowBlueprint,
    WorkflowBlueprintVersion,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunStep,
    WorkflowRunStepStatus,
)
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger(__name__)


WAIT = "__WAIT__"
MAX_STEPS_PER_ADVANCE = 50


# ── Mini-DSL de expresiones ──────────────────────────────────────────────────
# Soporta: campo OP valor   /   campo IN (lista)
# OP: == != < <= > >= contains startswith
# Valor: string literal "x", número, o lista [..,..]
_EXPR_RE = re.compile(
    r"""^\s*
        (?P<lhs>[A-Za-z_][\w.]*)\s*
        (?P<op>==|!=|<=|>=|<|>|in|contains|startswith)\s*
        (?P<rhs>.+?)\s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def _resolve(context: dict, path: str):
    cur = context
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def _parse_literal(s: str):
    s = s.strip()
    # tupla/lista
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
        inner = s[1:-1]
        return [_parse_literal(p) for p in _split_csv(inner)] if inner else []
    # string
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    # número
    try:
        if "." in s:
            return float(s)
        return int(s)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except ValueError:
        pass
    # bool / null / sin comillas → string libre
    low = s.lower()
    if low == "true": return True
    if low == "false": return False
    if low in ("null", "none"): return None
    return s


def _split_csv(s: str) -> list[str]:
    # split básico que respeta strings con comillas
    out, buf, in_str, sc = [], [], False, ""
    for c in s:
        if in_str:
            buf.append(c)
            if c == sc:
                in_str = False
        elif c in "'\"":
            in_str, sc = True, c
            buf.append(c)
        elif c == ",":
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
    if buf:
        out.append("".join(buf).strip())
    return out


#: Los operadores que entiende una expresión de decisión. Auditoría 2026-09
#: (hallazgo 18): eran nueve `if` con `return`, que es **una tabla escrita como
#: código**. Como tabla, añadir un operador es añadir una fila y se ve de un
#: vistazo cuáles toleran un lado izquierdo nulo y cuáles no.
#:
#: Las comparaciones de orden comprueban `lhs is not None` porque en Python 3
#: `None < 5` levanta `TypeError`, y una expresión de decisión que revienta
#: para un campo vacío detendría el flujo entero.
_OPERADORES = {
    "==":         lambda lhs, rhs: lhs == rhs,
    "!=":         lambda lhs, rhs: lhs != rhs,
    "<":          lambda lhs, rhs: lhs is not None and lhs < rhs,
    "<=":         lambda lhs, rhs: lhs is not None and lhs <= rhs,
    ">":          lambda lhs, rhs: lhs is not None and lhs > rhs,
    ">=":         lambda lhs, rhs: lhs is not None and lhs >= rhs,
    "in":         lambda lhs, rhs: lhs in (rhs or []),
    "contains":   lambda lhs, rhs: lhs is not None and rhs in lhs,
    "startswith": lambda lhs, rhs: isinstance(lhs, str) and lhs.startswith(str(rhs)),
}


def evaluate_expression(expr: str, context: dict) -> bool:
    """Evaluación segura de la expresión de un nodo de decisión.

    Segura significa que **no hay `eval`**: sólo estos nueve operadores sobre
    campos del contexto. Una expresión de flujo la escribe un administrador de
    cliente desde la interfaz, así que evaluar código sería ejecución remota.

    Una expresión vacía es `True` —un nodo sin condición siempre pasa— y una que
    no encaja con la forma `campo op valor` se trata como «¿tiene valor este
    campo?».
    """
    if not expr or not expr.strip():
        return True

    m = _EXPR_RE.match(expr)
    if not m:
        return bool(_resolve(context, expr.strip()))

    operador = _OPERADORES.get(m.group("op").lower())
    if operador is None:
        return False

    try:
        return operador(_resolve(context, m.group("lhs")), _parse_literal(m.group("rhs")))
    except Exception:
        # Comparar tipos incompatibles es un fallo de la expresión, no del
        # flujo: la rama no se toma y el flujo sigue por la otra.
        logger.debug("evaluate_expression: excepcion ignorada", exc_info=True)
        return False


# ── Helpers de versión / nodos ───────────────────────────────────────────────
def _get_published_version(db: Session, blueprint_id: str) -> Optional[WorkflowBlueprintVersion]:
    return (
        db.query(WorkflowBlueprintVersion)
        .filter(
            WorkflowBlueprintVersion.blueprint_id == blueprint_id,
            WorkflowBlueprintVersion.is_published == True,
        )
        .first()
    )


def _graph_of(version: WorkflowBlueprintVersion) -> dict:
    return json.loads(version.graph_json or "{}")


def _node_by_id(graph: dict, node_id: str) -> Optional[dict]:
    for n in graph.get("nodes", []):
        if str(n.get("id")) == str(node_id):
            return n
    return None


def _outgoing(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if str(e.get("source")) == str(node_id)]


def _start_node_id(graph: dict) -> Optional[str]:
    for n in graph.get("nodes", []):
        if n.get("type") == "start":
            return str(n.get("id"))
    return None


def _node_type(node: dict) -> str:
    return str(node.get("type") or (node.get("data") or {}).get("type") or "")


def _node_config(node: dict) -> dict:
    cfg = node.get("config")
    if cfg is not None:
        return cfg
    return (node.get("data") or {}).get("config") or {}


# ── Public API ──────────────────────────────────────────────────────────────
def start_run(
    db: Session,
    *,
    blueprint_id: str,
    target_entity_type: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    context: Optional[dict] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> WorkflowRun:
    bp = db.query(WorkflowBlueprint).filter(WorkflowBlueprint.id == blueprint_id).first()
    if not bp:
        raise ValueError("blueprint not found")
    pub = _get_published_version(db, blueprint_id)
    if not pub:
        raise ValueError("blueprint sin versión publicada — publica una versión antes de ejecutar")
    graph = _graph_of(pub)
    start_id = _start_node_id(graph)
    if not start_id:
        raise ValueError("blueprint sin nodo 'start'")

    run = WorkflowRun(
        organization_id=organization_id,
        blueprint_id=bp.id,
        blueprint_version_id=pub.id,
        blueprint_version=pub.version,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        status=WorkflowRunStatus.running,
        current_node_id=start_id,
        context_json=context or {},
        created_by_user_id=user_id,
    )
    db.add(run)
    db.flush()
    advance(db, run)
    return run


def _grafo_de_la_ejecucion(db: Session, run: WorkflowRun):
    """El grafo de la versión que esta ejecución está siguiendo, o `None`.

    Se busca primero la versión **anclada en la ejecución** y sólo después la
    publicada: una ejecución en curso tiene que seguir el plano con el que
    empezó, aunque se haya publicado otro por medio.
    """
    version = (
        db.query(WorkflowBlueprintVersion)
        .filter(WorkflowBlueprintVersion.id == run.blueprint_version_id)
        .first()
    ) or _get_published_version(db, run.blueprint_id)
    return _graph_of(version) if version else None


def _pausar_en(db: Session, run: WorkflowRun, node, ntype: str, payload: dict,
               wait_seconds=None) -> WorkflowRun:
    """Deja la ejecución esperando en este nodo.

    Dos motivos, misma consecuencia: un nodo humano —que espera a que alguien
    responda— o un temporizador, que además fija `wake_at` para que el
    planificador sepa cuándo volver.
    """
    if wait_seconds is not None:
        run.wake_at = datetime.now(timezone.utc) + timedelta(seconds=int(wait_seconds or 0))
        payload = {**payload, "wake_at": run.wake_at.isoformat()}

    db.add(WorkflowRunStep(
        run_id=run.id, node_id=str(node.get("id")), node_type=ntype,
        status=WorkflowRunStepStatus.waiting,
        branch_taken=None, payload_json=payload,
    ))
    run.status = WorkflowRunStatus.waiting
    db.flush()
    return run


def _ejecutar_un_nodo(db: Session, run: WorkflowRun, graph, node) -> Optional[WorkflowRun]:
    """Ejecuta un nodo y avanza. Devuelve la ejecución si hay que parar, o `None`.

    `None` significa «sigue el bucle»: el nodo era automático, se registró y se
    movió el puntero al siguiente.
    """
    ntype = _node_type(node)
    try:
        branch, payload, wait_seconds = _execute_node(ntype, _node_config(node), run, db)
    except Exception as exc:
        logger.debug("_ejecutar_un_nodo: excepcion ignorada", exc_info=True)
        _record_error(db, run, f"executor {ntype} falló: {exc}")
        return run

    if branch == WAIT:
        return _pausar_en(
            db, run, node, ntype, payload,
            wait_seconds=wait_seconds if ntype == "wait" else None,
        )

    db.add(WorkflowRunStep(
        run_id=run.id, node_id=str(node.get("id")), node_type=ntype,
        status=WorkflowRunStepStatus.done,
        branch_taken=branch, payload_json=payload,
        completed_at=datetime.now(timezone.utc),
    ))

    if ntype == "end":
        run.status = WorkflowRunStatus.completed
        run.completed_at = datetime.now(timezone.utc)
        run.current_node_id = None
        db.flush()
        return run

    siguiente = _pick_next(graph, str(node.get("id")), branch)
    if not siguiente:
        _record_error(db, run, f"sin transición desde {node.get('id')!r} branch={branch!r}")
        return run

    run.current_node_id = siguiente
    db.flush()
    return None


def advance(db: Session, run: WorkflowRun) -> WorkflowRun:
    """Ejecuta nodos automáticos hasta llegar a `end`, `wait` o un nodo humano."""
    if run.status != WorkflowRunStatus.running:
        return run

    graph = _grafo_de_la_ejecucion(db, run)
    if graph is None:
        run.status = WorkflowRunStatus.error
        run.last_error = "blueprint version not found"
        db.flush()
        return run

    pasos = 0
    while run.status == WorkflowRunStatus.running and run.current_node_id:
        pasos += 1
        # El tope corta los bucles del grafo: un flujo mal diseñado que vuelve
        # sobre sí mismo giraría aquí para siempre dentro de una petición.
        if pasos > MAX_STEPS_PER_ADVANCE:
            _record_error(db, run, "límite de pasos alcanzado en un solo avance (posible bucle)")
            return run

        node = _node_by_id(graph, run.current_node_id)
        if not node:
            _record_error(db, run, f"nodo {run.current_node_id} no existe en el grafo")
            return run

        parada = _ejecutar_un_nodo(db, run, graph, node)
        if parada is not None:
            return parada

    return run


def resume(
    db: Session,
    run: WorkflowRun,
    *,
    branch: Optional[str] = None,
    payload: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> WorkflowRun:
    """Reanuda un run en estado `waiting` (aprobación / wait expirado)."""
    if run.status != WorkflowRunStatus.waiting:
        raise ValueError(f"run no está en waiting (estado actual: {run.status})")

    pub = (
        db.query(WorkflowBlueprintVersion)
        .filter(WorkflowBlueprintVersion.id == run.blueprint_version_id)
        .first()
    )
    if not pub:
        _record_error(db, run, "blueprint version not found")
        return run
    graph = _graph_of(pub)
    node = _node_by_id(graph, run.current_node_id) if run.current_node_id else None
    if not node:
        _record_error(db, run, "nodo actual no existe")
        return run

    # Cierra la step pendiente con el branch indicado
    pending = (
        db.query(WorkflowRunStep)
        .filter(
            WorkflowRunStep.run_id == run.id,
            WorkflowRunStep.status == WorkflowRunStepStatus.waiting,
        )
        .order_by(WorkflowRunStep.created_at.desc())
        .first()
    )
    branch_final = branch or "next"
    if pending:
        pending.status = WorkflowRunStepStatus.done
        pending.branch_taken = branch_final
        pending.completed_at = datetime.now(timezone.utc)
        if payload:
            merged = dict(pending.payload_json or {})
            merged["resume"] = {"by": user_id, "payload": payload}
            pending.payload_json = merged

    next_node_id = _pick_next(graph, run.current_node_id, branch_final)
    if not next_node_id:
        _record_error(db, run, f"sin transición desde {run.current_node_id!r} branch={branch_final!r}")
        return run

    run.current_node_id = next_node_id
    run.wake_at = None
    run.status = WorkflowRunStatus.running
    db.flush()
    return advance(db, run)


def cancel_run(db: Session, run: WorkflowRun, reason: Optional[str] = None) -> WorkflowRun:
    if run.status in (WorkflowRunStatus.completed, WorkflowRunStatus.cancelled):
        return run
    run.status = WorkflowRunStatus.cancelled
    run.completed_at = datetime.now(timezone.utc)
    if reason:
        run.last_error = reason
    db.flush()
    return run


def tick_waiting(db: Session) -> int:
    """Escaneo periódico: despierta runs cuyos `wait` ya hayan expirado."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.status == WorkflowRunStatus.waiting,
            WorkflowRun.wake_at != None,
            WorkflowRun.wake_at <= now,
        )
        .all()
    )
    n = 0
    for r in rows:
        try:
            resume(db, r, branch="next")
            n += 1
        except Exception as exc:
            logger.warning("tick_waiting: run %s failed: %s", r.id, exc)
    if n:
        db.commit()
    return n


# ── Internal: executors por tipo ────────────────────────────────────────────
def _render_template(text: Optional[str], ctx: dict) -> str:
    """Best-effort {var} substitution from the run context; never raises."""
    if not text:
        return ""
    try:
        return text.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return text


# ── Ejecución de un nodo del flujo ───────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 + defecto encontrado de paso). `_execute_node`
# era complejidad 22: diez `if ntype == ...` secuenciales, cada uno con su
# `return` de tres elementos. Es una tabla de despacho escrita como una funcion.
#
# ── El desajuste que aparecio al escribir la tabla ────────────────────────────
#
# Cruzando la tabla con `NODE_CATALOG` del disenador aparecio que TRES CAPAS NO
# COINCIDEN sobre el tipo de nodo `action` («Accion»):
#
#   catalogo y `validate_graph` ....... lo aceptan
#   editor del disenador .............. NO ofrece ni un campo para configurarlo
#   este motor ........................ NO sabe ejecutarlo: lanza ValueError
#
# Comprobado por ejecucion:
#     _execute_node("action", {"action": "set_priority"}, run, db)
#     -> ValueError: tipo de nodo no soportado por el motor: action
#
# El catalogo lo incluye A PROPOSITO —su comentario lo dice— porque hay grafos
# que lo usan y `validate_graph` los rechazaba. Asi que NO se retira: retirarlo
# desharia ese arreglo y volveria a romper los grafos guardados.
#
# Tampoco se implementa aqui. `action` + `params` no dice que debe hacer, el
# disenador no ofrece campos para rellenarlo, y una de las acciones que su
# comentario menciona es `run_script`: ejecutar un script arbitrario guardado en
# una definicion de flujo es una superficie de ejecucion remota de codigo, y eso
# no se decide en un refactor de complejidad.
#
# Lo que SI se hace, que es lo que reduce el dano de verdad: `validate_graph`
# ahora AVISA al guardar cuando el grafo contiene un tipo que el motor no puede
# ejecutar. Antes el flujo se guardaba como valido y moria al llegar el primer
# caso real; ahora quien lo disena lo sabe en ese momento. Se usa el canal de
# avisos que ya existia para los ciclos, asi que no rompe nada.
#
# `TIPOS_EJECUTABLES` es lo que consulta ese aviso, y el test
# `test_el_catalogo_y_el_motor_solo_difieren_en_action` fija el desajuste
# exactamente: el dia que alguien implemente o retire `action`, el test avisa.


@dataclass(frozen=True, slots=True)
class _Nodo:
    """El entorno que ve un ejecutor de nodo.

    `ctx` es el contexto del run y se pasa como el MISMO diccionario que se
    guardara: el nodo `state` lo modifica y reasigna `run.context_json`, y la
    siguiente decision tiene que ver ese cambio.
    """

    config: dict
    ctx: dict
    run: "WorkflowRun"
    db: "Session"


# Cada ejecutor devuelve (rama_tomada, payload, segundos_de_espera).

def _nodo_inicio(n: _Nodo) -> tuple[str, dict, int]:
    return "next", {}, 0


def _nodo_fin(n: _Nodo) -> tuple[str, dict, int]:
    return "end", {}, 0


def _ticket_objetivo(n: _Nodo):
    if n.run.target_entity_type != "ticket" or not n.run.target_entity_id:
        return None
    from app.models.service_desk import Ticket
    return n.db.get(Ticket, n.run.target_entity_id)


def _nodo_estado(n: _Nodo) -> tuple[str, dict, int]:
    """Cambia el estado: en el contexto y, si el flujo va sobre un ticket, en él.

    Auditoria 2026-11: solo tocaba el contexto, asi que un flujo de ticket
    nunca movia el ticket. Se aplica con `apply_ticket_update`, el mismo
    camino que un agente: pausa y reanuda el SLA, sella la resolucion y deja
    historial. Un estado que no es de ticket es un error del flujo.
    """
    new_status = n.config.get("status")
    if new_status:
        n.ctx["status"] = new_status
        n.run.context_json = n.ctx
        ticket = _ticket_objetivo(n)
        if ticket is not None:
            from app.models.service_desk import TicketStatus
            from app.schemas.service_desk import TicketUpdateIn
            from app.services.service_desk.ticket_update_service import apply_ticket_update
            try:
                TicketStatus(new_status)
            except ValueError:
                return "failure", {"status": new_status, "error": "estado de ticket desconocido"}, 0
            apply_ticket_update(
                n.db, ticket, ticket.id, TicketUpdateIn(status=new_status),
                current_user_id=None, old_assigned_to=ticket.assigned_to_user_id,
                old_support_level=ticket.support_level,
            )
    return "next", {
        "status": new_status,
        "assignee_role": n.config.get("assignee_role"),
        "sla_hours": n.config.get("sla_hours"),
    }, 0


def _nodo_decision(n: _Nodo) -> tuple[str, dict, int]:
    expr = n.config.get("expression") or ""
    result = evaluate_expression(expr, n.ctx)
    return ("true" if result else "false"), {"expression": expr, "result": result}, 0


def _nodo_aprobacion(n: _Nodo) -> tuple[str, dict, int]:
    """Bloqueante: alguien externo debe llamar a /resume con approved/rejected."""
    return WAIT, {
        "approver_role": n.config.get("approver_role"),
        "deadline_hours": n.config.get("deadline_hours"),
    }, 0


def _nodo_espera(n: _Nodo) -> tuple[str, dict, int]:
    """Espera un numero de minutos. Un valor ilegible se trata como cero.

    Cero y no un error a proposito: un temporizador mal configurado no debe
    dejar el flujo colgado para siempre, sino seguir de inmediato.
    """
    try:
        seconds = int(n.config.get("wait_minutes") or 0) * 60
    except Exception:
        logger.warning("_nodo_espera: excepcion ignorada", exc_info=True)
        seconds = 0
    return WAIT, {
        "wait_minutes": n.config.get("wait_minutes"),
        "until_field": n.config.get("until_field"),
    }, seconds


def _destinatarios_del_flujo(n: _Nodo, recipients) -> Optional[list]:
    """Ids de usuario, o None si `recipients` es el nombre de un rol.

    Sobre un ticket se entienden `$assignee` (el agente) y `$group` (su cola);
    una lista son ids de usuario. Antes `$assignee` se tomaba por un rol y no
    avisaba a nadie.
    """
    if isinstance(recipients, (list, tuple)):
        return list(recipients)
    if not isinstance(recipients, str) or not recipients.startswith("$"):
        return None
    ticket = _ticket_objetivo(n)
    if ticket is None:
        return []
    ids: list = []
    for clave in (r.strip() for r in recipients.split(",")):
        if clave == "$assignee" and ticket.assigned_to_user_id:
            ids.append(ticket.assigned_to_user_id)
        elif clave == "$group" and ticket.assigned_group_id:
            from app.models.service_desk import AgentGroupMember
            ids += [r[0] for r in n.db.query(AgentGroupMember.user_id)
                    .filter(AgentGroupMember.group_id == ticket.assigned_group_id).all()]
        elif clave == "$requester" and ticket.requester_user_id:
            ids.append(ticket.requester_user_id)
    return list(dict.fromkeys(ids))


def _enviar_correos_del_flujo(n: _Nodo, ids: list, title: str, body: str) -> None:
    """Canal «correo» del nodo: ademas de la campana, un correo a cada usuario.

    Antes la pantalla ofrecia email, Slack y SMS y el motor solo avisaba en la
    campana. Se envia con el SMTP de la organizacion y queda en `email_logs`.
    """
    import html as _html
    from datetime import datetime as _dt, timezone as _tz
    from app.models.cab import EmailLog
    from app.models.user import User
    from app.services.service_desk import correo

    org = n.run.organization_id
    cuerpo = f"<p>{_html.escape(body or '')}</p>"
    for u in n.db.query(User).filter(User.id.in_([str(i) for i in ids]), User.is_active == True).all():  # noqa: E712
        if not u.email:
            continue
        r = correo.enviar(n.db, org, u.email, title, cuerpo, body or title)
        n.db.add(EmailLog(
            organization_id=org, to_address=u.email, subject=title[:500], body_preview=(body or "")[:500],
            status="sent" if r.enviado else "failed", error=r.error,
            sent_at=_dt.now(_tz.utc) if r.enviado else None,
            source="workflow", source_id=n.run.id,
        ))


def _nodo_notificar(n: _Nodo) -> tuple[str, dict, int]:
    """Notificacion real en la aplicacion.

    `recipients` puede ser el nombre de un rol (`notify_role`) o una lista de
    identificadores de usuario (`notify_user`).
    """
    from app.services.notifications import notify_role, notify_user

    title = _render_template(
        n.config.get("title") or n.config.get("template_id") or "Workflow notification",
        n.ctx,
    )
    body = _render_template(n.config.get("body") or n.config.get("message"), n.ctx)
    recipients = n.config.get("recipients") or n.config.get("role")
    resource_id = n.run.target_entity_id
    resource = n.run.target_entity_type or "workflow"
    delivered = 0
    # Auditoria 2026-11: el tipo era "workflow", que el enum de avisos no
    # tiene; en PostgreSQL el aviso no se podia guardar.
    tipo = "automation"
    try:
        ids = _destinatarios_del_flujo(n, recipients)
        if ids is not None:
            for uid in ids:
                notify_user(n.db, str(uid), tipo, title, body,
                            resource=resource, resource_id=resource_id)
                delivered += 1
        elif isinstance(recipients, str):
            delivered = notify_role(n.db, recipients, tipo, title, body,
                                    resource=resource, resource_id=resource_id,
                                    organization_id=n.run.organization_id)
            if n.config.get("channel") == "email":
                from app.models.user import User
                ids = [r[0] for r in n.db.query(User.id).filter(
                    User.role == recipients, User.is_active == True,  # noqa: E712
                    User.organization_id == n.run.organization_id).all()]
        if n.config.get("channel") == "email" and ids:
            _enviar_correos_del_flujo(n, ids, title, body)
    except Exception as exc:
        logger.warning("_nodo_notificar: excepcion ignorada", exc_info=True)
        return "failure", {
            "channel": n.config.get("channel"), "error": str(exc)[:300], "delivered": 0,
        }, 0
    return "next", {
        "channel": n.config.get("channel"),
        "recipients": recipients,
        "delivered": True,
        "notified_count": delivered,
    }, 0


def _nodo_llamada_http(n: _Nodo) -> tuple[str, dict, int]:
    """Llamada HTTP saliente. Cualquier fallo toma la rama `failure`.

    Las dos ramas estan declaradas en el catalogo (`success`/`failure`), asi que
    el flujo puede tratar el error; por eso aqui no se propaga la excepcion.
    """
    url = n.config.get("url")
    method = (n.config.get("method") or "GET").upper()
    body_template = n.config.get("body_template")
    body = None
    if body_template:
        try:
            body = json.loads(body_template)
        except Exception:
            logger.debug("_nodo_llamada_http: excepcion ignorada", exc_info=True)
            body = body_template
    try:
        # Auditoria 2026-11: la URL la escribe un PM y la respuesta se guarda en el
        # run (500 caracteres): era SSRF con lectura (metadatos cloud, red interna).
        from app.core.outbound_url import cliente_httpx, validate_outbound_url
        validate_outbound_url(url or "", field="url del nodo http_call")
        with cliente_httpx(timeout=outbound_http_timeout(default=10.0)) as cli:
            r = cli.request(
                method, url,
                json=body if isinstance(body, (dict, list)) else None,
                content=None if isinstance(body, (dict, list)) else body,
            )
        ok = 200 <= r.status_code < 300
        return ("success" if ok else "failure"), {
            "method": method, "url": url, "status_code": r.status_code,
            "response": (r.text or "")[:500],
        }, 0
    except Exception as exc:
        logger.warning("_nodo_llamada_http: excepcion ignorada", exc_info=True)
        return "failure", {"method": method, "url": url, "error": str(exc)[:500]}, 0


def _nodo_crear_ticket(n: _Nodo) -> tuple[str, dict, int]:
    """Creacion real de un ticket.

    Hereda la organizacion del run para el aislamiento de tenant, y el numero se
    pide al generador canonico en vez de calcularlo aqui.
    """
    from app.models.service_desk import Ticket, TicketPriority, TicketType
    from app.services.sla_service import next_ticket_number

    title = _render_template(
        n.config.get("title_template") or n.config.get("title") or "Workflow-created ticket",
        n.ctx,
    )
    try:
        ttype = TicketType(n.config.get("ticket_type") or "incident")
    except ValueError:
        ttype = TicketType.incident
    try:
        priority = TicketPriority(n.config.get("priority") or "p3_medium")
    except ValueError:
        priority = TicketPriority.p3_medium
    # `sd_tickets.description` es NOT NULL y el esquema de la API la declara
    # obligatoria (`description: str = Field(...)`), asi que el motor era la unica
    # via que intentaba crear un ticket sin ella: pasaba `... or None` y el INSERT
    # reventaba SIEMPRE que el nodo no traia plantilla de descripcion — y el
    # editor del disenador no ofrecia campo para escribirla, asi que el nodo tal
    # como se configura desde la interfaz no podia tener exito nunca. Se cae al
    # titulo, que es lo que una persona habria escrito, y la procedencia queda en
    # `source="workflow"`.
    description = _render_template(
        n.config.get("description_template") or n.config.get("description"), n.ctx
    ) or title
    try:
        ticket = Ticket(
            number=next_ticket_number(ttype.value, n.db, n.run.organization_id),
            ticket_type=ttype,
            title=title[:500],
            description=description,
            priority=priority,
            organization_id=n.run.organization_id,
            source="workflow",
        )
        n.db.add(ticket)
        n.db.flush()
    except Exception as exc:
        # El rollback no es opcional. Sin el, un flush fallido deja la sesion en
        # transaccion abortada y TODO lo que viene despues del nodo falla con
        # «transaction has been rolled back»: el registro del paso, el avance del
        # run e incluso `_record_error`, que es justo quien tiene que anotar el
        # problema. Un nodo que falla debe dejar el run anotable.
        logger.warning("_nodo_crear_ticket: excepcion ignorada", exc_info=True)
        n.db.rollback()
        return "failure", {
            "queue": n.config.get("queue"), "error": str(exc)[:300], "created": False,
        }, 0
    return "next", {
        "queue": n.config.get("queue"),
        "created": True,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    }, 0


# La tabla. `TIPOS_EJECUTABLES` la cruza el test con `ALLOWED_NODE_TYPES` del
# disenador, en las dos direcciones: un tipo en el catalogo que el motor no sepa
# ejecutar se guarda como valido y revienta al ejecutarse (es lo que pasaba con
# `action`), y un tipo ejecutable que no este en el catalogo no se puede
# disenar, asi que seria codigo muerto.
_EJECUTORES = {
    "start": _nodo_inicio,
    "end": _nodo_fin,
    "state": _nodo_estado,
    "decision": _nodo_decision,
    "approval": _nodo_aprobacion,
    "wait": _nodo_espera,
    "notify": _nodo_notificar,
    "http_call": _nodo_llamada_http,
    "create_ticket": _nodo_crear_ticket,
}

TIPOS_EJECUTABLES = frozenset(_EJECUTORES)


def _execute_node(ntype: str, config: dict, run: WorkflowRun, db: "Session") -> tuple[str, dict, int]:
    """Devuelve (branch_taken, payload_dict, wait_seconds_if_wait)."""
    ejecutar = _EJECUTORES.get(ntype)
    if ejecutar is None:
        raise ValueError(f"tipo de nodo no soportado por el motor: {ntype}")
    return ejecutar(_Nodo(
        config=config,
        ctx=dict(run.context_json or {}),
        run=run,
        db=db,
    ))


def _pick_next(graph: dict, source_id: str, branch: str) -> Optional[str]:
    edges = _outgoing(graph, source_id)
    # 1) coincidencia exacta de branch
    for e in edges:
        if str(e.get("branch") or e.get("type") or "next") == branch:
            return str(e.get("target"))
    # 2) si no hay match, toma el primero (default)
    if edges:
        return str(edges[0].get("target"))
    return None


def _record_error(db: Session, run: WorkflowRun, msg: str) -> None:
    run.status = WorkflowRunStatus.error
    run.last_error = msg
    run.completed_at = datetime.now(timezone.utc)
    db.add(WorkflowRunStep(
        run_id=run.id, node_id=str(run.current_node_id or ""), node_type="(engine)",
        status=WorkflowRunStepStatus.error, error=msg, payload_json={},
    ))
    db.flush()


# ── Serialización para API ──────────────────────────────────────────────────
def serialize_run(run: WorkflowRun) -> dict:
    return {
        "id": run.id,
        "blueprint_id": run.blueprint_id,
        "blueprint_version": run.blueprint_version,
        "target_entity_type": run.target_entity_type,
        "target_entity_id": run.target_entity_id,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "current_node_id": run.current_node_id,
        "wake_at": run.wake_at,
        "last_error": run.last_error,
        "context": run.context_json or {},
        "created_by_user_id": run.created_by_user_id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def serialize_step(step: WorkflowRunStep) -> dict:
    return {
        "id": step.id,
        "node_id": step.node_id,
        "node_type": step.node_type,
        "status": step.status.value if hasattr(step.status, "value") else step.status,
        "branch_taken": step.branch_taken,
        "payload": step.payload_json or {},
        "error": step.error,
        "created_at": step.created_at,
        "completed_at": step.completed_at,
    }
