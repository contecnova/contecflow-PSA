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


def evaluate_expression(expr: str, context: dict) -> bool:
    """Evaluación segura de la expresión de un nodo decisión."""
    if not expr or not expr.strip():
        return True
    m = _EXPR_RE.match(expr)
    if not m:
        # fallback: si la expresión es "campo" sin operador, comprueba truthy
        val = _resolve(context, expr.strip())
        return bool(val)
    lhs = _resolve(context, m.group("lhs"))
    op = m.group("op").lower()
    rhs = _parse_literal(m.group("rhs"))
    try:
        if op == "==":         return lhs == rhs
        if op == "!=":         return lhs != rhs
        if op == "<":          return lhs is not None and lhs < rhs
        if op == "<=":         return lhs is not None and lhs <= rhs
        if op == ">":          return lhs is not None and lhs > rhs
        if op == ">=":         return lhs is not None and lhs >= rhs
        if op == "in":         return lhs in (rhs or [])
        if op == "contains":   return lhs is not None and rhs in lhs
        if op == "startswith": return isinstance(lhs, str) and lhs.startswith(str(rhs))
    except Exception:
        return False
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


def advance(db: Session, run: WorkflowRun) -> WorkflowRun:
    """Ejecuta nodos automáticos hasta llegar a `end`, `wait` o un nodo humano."""
    if run.status not in (WorkflowRunStatus.running,):
        return run
    pub = (
        db.query(WorkflowBlueprintVersion)
        .filter(WorkflowBlueprintVersion.id == run.blueprint_version_id)
        .first()
    ) or _get_published_version(db, run.blueprint_id)
    if not pub:
        run.status = WorkflowRunStatus.error
        run.last_error = "blueprint version not found"
        db.flush()
        return run
    graph = _graph_of(pub)

    steps = 0
    while run.status == WorkflowRunStatus.running and run.current_node_id:
        steps += 1
        if steps > MAX_STEPS_PER_ADVANCE:
            _record_error(db, run, "límite de pasos alcanzado en un solo avance (posible bucle)")
            return run
        node = _node_by_id(graph, run.current_node_id)
        if not node:
            _record_error(db, run, f"nodo {run.current_node_id} no existe en el grafo")
            return run

        ntype = _node_type(node)
        config = _node_config(node)
        try:
            branch, payload, wait_seconds = _execute_node(ntype, config, run, db)
        except Exception as exc:
            _record_error(db, run, f"executor {ntype} falló: {exc}")
            return run

        # Caso 1: nodo bloqueante (approval) — graba step waiting + sale
        if branch == WAIT and ntype != "wait":
            step = WorkflowRunStep(
                run_id=run.id, node_id=str(node.get("id")), node_type=ntype,
                status=WorkflowRunStepStatus.waiting,
                branch_taken=None, payload_json=payload,
            )
            db.add(step)
            run.status = WorkflowRunStatus.waiting
            db.flush()
            return run

        # Caso 2: timer (wait) — programa wake_at y pausa
        if branch == WAIT and ntype == "wait":
            run.wake_at = datetime.now(timezone.utc) + timedelta(seconds=int(wait_seconds or 0))
            step = WorkflowRunStep(
                run_id=run.id, node_id=str(node.get("id")), node_type=ntype,
                status=WorkflowRunStepStatus.waiting,
                branch_taken=None, payload_json={**payload, "wake_at": run.wake_at.isoformat()},
            )
            db.add(step)
            run.status = WorkflowRunStatus.waiting
            db.flush()
            return run

        # Caso 3: nodo automático completado → registrar y mover
        step = WorkflowRunStep(
            run_id=run.id, node_id=str(node.get("id")), node_type=ntype,
            status=WorkflowRunStepStatus.done,
            branch_taken=branch, payload_json=payload,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(step)

        if ntype == "end":
            run.status = WorkflowRunStatus.completed
            run.completed_at = datetime.now(timezone.utc)
            run.current_node_id = None
            db.flush()
            return run

        next_node_id = _pick_next(graph, str(node.get("id")), branch)
        if not next_node_id:
            _record_error(db, run, f"sin transición desde {node.get('id')!r} branch={branch!r}")
            return run
        run.current_node_id = next_node_id
        db.flush()

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


def _execute_node(ntype: str, config: dict, run: WorkflowRun, db: "Session") -> tuple[str, dict, int]:
    """Devuelve (branch_taken, payload_dict, wait_seconds_if_wait)."""
    ctx = dict(run.context_json or {})

    if ntype == "start":
        return "next", {}, 0

    if ntype == "end":
        return "end", {}, 0

    if ntype == "state":
        # Aplica el cambio de estado al context (lo verá la siguiente decisión).
        new_status = config.get("status")
        if new_status:
            ctx["status"] = new_status
            run.context_json = ctx
        return "next", {"status": new_status, "assignee_role": config.get("assignee_role"), "sla_hours": config.get("sla_hours")}, 0

    if ntype == "decision":
        expr = config.get("expression") or ""
        result = evaluate_expression(expr, ctx)
        return ("true" if result else "false"), {"expression": expr, "result": result}, 0

    if ntype == "approval":
        # Bloqueante: alguien externo debe llamar a /resume con approved/rejected.
        return WAIT, {"approver_role": config.get("approver_role"), "deadline_hours": config.get("deadline_hours")}, 0

    if ntype == "wait":
        seconds = 0
        try:
            seconds = int(config.get("wait_minutes") or 0) * 60
        except Exception:
            seconds = 0
        return WAIT, {"wait_minutes": config.get("wait_minutes"), "until_field": config.get("until_field")}, seconds

    if ntype == "notify":
        # Real in-app notification via app.services.notifications. `recipients`
        # may be a role name (notify_role) or a list of user ids (notify_user).
        from app.services.notifications import notify_role, notify_user

        title = _render_template(config.get("title") or config.get("template_id") or "Workflow notification", ctx)
        body = _render_template(config.get("body") or config.get("message"), ctx)
        recipients = config.get("recipients") or config.get("role")
        resource_id = run.target_entity_id
        resource = run.target_entity_type or "workflow"
        delivered = 0
        try:
            if isinstance(recipients, str):
                delivered = notify_role(db, recipients, "workflow", title, body, resource=resource, resource_id=resource_id)
            elif isinstance(recipients, (list, tuple)):
                for uid in recipients:
                    notify_user(db, str(uid), "workflow", title, body, resource=resource, resource_id=resource_id)
                    delivered += 1
        except Exception as exc:
            return "failure", {"channel": config.get("channel"), "error": str(exc)[:300], "delivered": 0}, 0
        return "next", {
            "channel": config.get("channel"),
            "recipients": recipients,
            "delivered": True,
            "notified_count": delivered,
        }, 0

    if ntype == "http_call":
        url = config.get("url")
        method = (config.get("method") or "GET").upper()
        body_template = config.get("body_template")
        body = None
        if body_template:
            try: body = json.loads(body_template)
            except Exception: body = body_template
        try:
            import httpx  # noqa: WPS433
            with httpx.Client(timeout=10.0) as cli:
                r = cli.request(method, url, json=body if isinstance(body, (dict, list)) else None,
                                content=None if isinstance(body, (dict, list)) else body)
            ok = 200 <= r.status_code < 300
            return ("success" if ok else "failure"), {
                "method": method, "url": url, "status_code": r.status_code,
                "response": (r.text or "")[:500],
            }, 0
        except Exception as exc:
            return "failure", {"method": method, "url": url, "error": str(exc)[:500]}, 0

    if ntype == "create_ticket":
        # Real ticket creation. Inherits the run's organization for tenant
        # isolation; ticket number is allocated via the canonical generator.
        from app.models.service_desk import Ticket, TicketType, TicketPriority
        from app.services.sla_service import next_ticket_number

        title = _render_template(config.get("title_template") or config.get("title") or "Workflow-created ticket", ctx)
        try:
            ttype = TicketType(config.get("ticket_type") or "incident")
        except ValueError:
            ttype = TicketType.incident
        try:
            priority = TicketPriority(config.get("priority") or "p3_medium")
        except ValueError:
            priority = TicketPriority.p3_medium
        try:
            ticket = Ticket(
                number=next_ticket_number(ttype.value, db),
                ticket_type=ttype,
                title=title[:500],
                description=_render_template(config.get("description_template") or config.get("description"), ctx) or None,
                priority=priority,
                organization_id=run.organization_id,
                source="workflow",
            )
            db.add(ticket)
            db.flush()
        except Exception as exc:
            return "failure", {"queue": config.get("queue"), "error": str(exc)[:300], "created": False}, 0
        return "next", {
            "queue": config.get("queue"),
            "created": True,
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
        }, 0

    raise ValueError(f"tipo de nodo no soportado por el motor: {ntype}")


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
