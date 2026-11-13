"""Flujos de automatizacion: pasos, reintentos, condiciones y la cola que los ejecuta.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
import time as _time_sleep
from datetime import datetime, timedelta, timezone
from app.models.billing_reports import AutomationWorkflow
from app.models.billing_reports import WorkflowExecution
from app.models.bookings import WorkflowQueueItem
from sqlalchemy.orm import joinedload
from app.core.errores import ErrorDeDominio

from app.services.bookings_service.aprovisionamiento import (
    _execute_step_action,
    _render_step_value,
    _validate_provision_url,
)
from app.services.bookings_service._comun import logger
from app.services.settings_service import outbound_http_timeout


def paso_de_workflow_propio(db, current_user, wf_id: str, step_id: str):
    """El paso de un workflow, si el workflow es de la organizacion. 404 si no.

    Auditoria 2026-08 (hallazgo 22). El endpoint que configura los reintentos de
    un paso lo buscaba asi:

        db.query(WorkflowStep).filter(
            WorkflowStep.id == step_id,
            WorkflowStep.workflow_id == wf_id,
        ).first()

    Los dos ids vienen de la ruta y **no habia ninguna comprobacion de a quien
    pertenece el workflow**. En produccion el filtro implicito de `TenantSession`
    lo evitaba —`WorkflowStep` tiene `organization_id`—, pero era la unica capa y
    esto **escribe**: cambia la politica de reintentos del paso de otro cliente.
    """

    from app.models.billing_reports import WorkflowStep

    consulta = db.query(WorkflowStep).filter(
        WorkflowStep.id == step_id,
        WorkflowStep.workflow_id == wf_id,
    )
    if not getattr(current_user, "is_superadmin", False):
        consulta = consulta.filter(
            WorkflowStep.organization_id
            == getattr(current_user, "organization_id", None))

    paso = consulta.first()
    if not paso:
        raise ErrorDeDominio(404, "Workflow step not found")
    return paso


def configurar_reintentos_de_paso(db, current_user, wf_id: str, step_id: str, payload: dict) -> dict:
    """Valida y guarda la politica de reintentos de un paso, y confirma."""
    max_retries = int(payload.get("max_retries", 0))
    delay_seconds = int(payload.get("delay_seconds", 0))
    backoff = str(payload.get("backoff", "none") or "none").lower()
    if max_retries < 0 or max_retries > 10:
        raise ErrorDeDominio(400, "max_retries must be between 0 and 10")
    if delay_seconds < 0 or delay_seconds > 120:
        raise ErrorDeDominio(400, "delay_seconds must be between 0 and 120")
    if backoff not in {"none", "linear", "exponential"}:
        raise ErrorDeDominio(400, "backoff must be one of: none, linear, exponential")

    step = paso_de_workflow_propio(db, current_user, wf_id, step_id)

    cfg = json.loads(step.config) if step.config else {}
    cfg["retry"] = {
        "max_retries": max_retries,
        "delay_seconds": delay_seconds,
        "backoff": backoff,
    }
    step.config = json.dumps(cfg)
    db.commit()
    return {
        "ok": True,
        "workflow_id": wf_id,
        "step_id": step_id,
        "retry": cfg["retry"],
    }


def _coerce_retry_policy(config: dict) -> dict:
    retry = config.get("retry") or {}
    max_retries = int(retry.get("max_retries", config.get("max_retries", 0)) or 0)
    delay_seconds = int(retry.get("delay_seconds", config.get("retry_delay_seconds", 0)) or 0)
    backoff = str(retry.get("backoff", "none") or "none").lower()
    if backoff not in {"none", "linear", "exponential"}:
        backoff = "none"
    return {
        "max_retries": max(0, min(max_retries, 10)),
        "delay_seconds": max(0, min(delay_seconds, 120)),
        "backoff": backoff,
    }


def _retry_sleep_seconds(policy: dict, retry_index: int) -> int:
    base = int(policy.get("delay_seconds", 0) or 0)
    if base <= 0:
        return 0
    mode = policy.get("backoff", "none")
    if mode == "exponential":
        return min(base * (2 ** max(retry_index - 1, 0)), 120)
    if mode == "linear":
        return min(base * max(retry_index, 1), 120)
    return min(base, 120)


# ── SSO ───────────────────────────────────────────────────────────────────────
# Auditoria 2026-11: el SSO que vivia aqui (initiate / oidc / saml) estaba roto
# y sin autenticar; se retiro. El de la aplicacion es routers/auth_sso.py.


# ── Workflow Queue ────────────────────────────────────────────────────────────

def enqueue_workflow_record(payload: dict, user_id, db) -> dict:
    workflow_id = payload.get("workflow_id")
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == workflow_id).first()
    if not wf: raise ErrorDeDominio(404, "Workflow no encontrado")
    execute_at = datetime.now(timezone.utc)
    if payload.get("delay_minutes"):
        execute_at += timedelta(minutes=int(payload["delay_minutes"]))
    item = WorkflowQueueItem(
        workflow_id=workflow_id,
        trigger_data=json.dumps(payload.get("context", {})),
        execute_at=execute_at,
        status="pending",
    )
    db.add(item); db.commit()
    return {"ok": True, "queue_id": item.id, "execute_at": execute_at.isoformat()}


# ── Cola de automatizaciones ─────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `process_workflow_queue_record` era
# complejidad 23: dos bucles anidados y un despacho de cuatro tipos de paso, todo
# en un ambito. Ahora cada tipo de paso es una funcion y los operadores de
# condicion son una tabla.


# Los cuatro operadores que puede usar un paso de condicion. Un operador
# desconocido da False —la condicion no se cumple—, que es lo que hacia la
# cadena de `or` original: ninguna de sus cuatro clausulas coincidia.
_OPERADORES_DE_CONDICION = {
    "equals": lambda a, b: str(a) == str(b),
    "not_equals": lambda a, b: str(a) != str(b),
    "greater_than": lambda a, b: float(a or 0) > float(b or 0),
    "less_than": lambda a, b: float(a or 0) < float(b or 0),
}

# Cuantos minutos es una unidad de espera.
_MINUTOS_POR_UNIDAD = {"minutes": 1, "hours": 60, "days": 1440}

# Intentos maximos por elemento de la cola antes de dejarlo. Tres porque el
# reintento cubre fallos transitorios (un webhook que no responde), no errores
# de configuracion, que no se arreglan repitiendo.
_MAX_INTENTOS = 3

# Cuantos elementos se procesan por pasada. El limite existe para que una cola
# atascada no monopolice el proceso: la siguiente pasada coge los siguientes.
_ELEMENTOS_POR_PASADA = 20

# Sentinela que devuelve un paso de espera: hay que cortar el recorrido de pasos
# porque la continuacion queda encolada para mas tarde.
_ESPERAR = object()


def _ejecutar_accion_con_reintentos(config: dict, context: dict, db,
                                    retry_policy: dict, step_result: dict, step) -> None:
    """Ejecuta la accion del paso, reintentando segun su politica.

    El resultado se escribe en `step_result`. `retry_attempts` cuenta los
    reintentos consumidos, no los intentos totales: es lo que se muestra en el
    historial de ejecucion.
    """
    max_retries = int(retry_policy.get("max_retries", 0))
    last_action_res = None
    for retry_idx in range(0, max_retries + 1):
        try:
            action_res = _execute_step_action(config, context, db)
            last_action_res = action_res
            if action_res.get("ok", True):
                step_result.update(action_res)
                return
            step_result["retry_attempts"] = retry_idx
        except Exception as e:
            logger.warning(
                "Workflow step %s action failed (attempt=%s): %s",
                getattr(step, "id", None), retry_idx, e, exc_info=True,
            )
            last_action_res = {"ok": False, "error": str(e)}
        if retry_idx < max_retries:
            step_result["retry_attempts"] = retry_idx + 1
            wait_s = _retry_sleep_seconds(retry_policy, retry_idx + 1)
            if wait_s > 0:
                _time_sleep.sleep(wait_s)
            continue
        step_result.update(last_action_res or {"ok": False, "error": "workflow_step_failed"})


def _encolar_continuacion(db, item, steps: list, step, config: dict,
                          now, step_result: dict):
    """Un paso de espera: se encola la continuacion y se cierra este elemento.

    No se duerme el proceso: se crea un elemento nuevo con la hora de despertar
    y el indice del paso siguiente, y este se marca como hecho. Asi una espera
    de tres dias no mantiene nada ocupado.
    """
    delay_minutes = config.get("duration", 60)
    unit = config.get("unit", "minutes")
    delay_minutes *= _MINUTOS_POR_UNIDAD.get(unit, 1)

    despertar = now + timedelta(minutes=delay_minutes)
    db.add(WorkflowQueueItem(
        workflow_id=item.workflow_id,
        trigger_data=item.trigger_data,
        execute_at=despertar,
        step_index=steps.index(step) + 1,
        status="pending",
    ))
    item.status = "done"
    step_result["waiting_until"] = despertar.isoformat()
    return _ESPERAR


def _evaluar_condicion(config: dict, context: dict) -> bool:
    """Compara un campo del contexto con un valor segun el operador del paso."""
    comparar = _OPERADORES_DE_CONDICION.get(config.get("operator", "equals"))
    if comparar is None:
        return False
    return bool(comparar(context.get(config.get("field")), config.get("value")))


def _ejecutar_webhook(config: dict, context: dict, step_result: dict, item) -> None:
    """Llama a un webhook externo, con proteccion contra SSRF.

    `_validate_provision_url` es lo que impide que un flujo configurado por un
    usuario apunte a la red interna: sin ella, un paso de webhook seria un
    proxy para sondear la infraestructura desde dentro.
    """
    try:
        import httpx as _httpx

        url = config.get("url")
        if not url:
            step_result["ok"] = False
            step_result["error"] = "webhook step requires 'url'"
            return

        _validate_provision_url(url)
        method = str(config.get("method", "POST")).upper()
        headers = _render_step_value(config.get("headers") or {}, context)
        payload_wh = _render_step_value(
            config.get("payload") or {"event": config.get("event"), "context": context},
            context,
        )
        with _httpx.Client(timeout=outbound_http_timeout(default=5.0)) as client:
            resp = client.request(method, url, headers=headers, json=payload_wh)
        step_result["http_status"] = resp.status_code
        step_result["response"] = resp.text[:1000]
    except ValueError as _ssrf_exc:
        step_result["ok"] = False
        step_result["error"] = f"SSRF protection blocked URL: {_ssrf_exc}"
    except Exception as e:
        logger.exception("Workflow webhook step failed for workflow=%s", item.workflow_id)
        step_result["ok"] = False
        step_result["error"] = str(e)[:100]


def _ejecutar_paso(db, item, steps: list, step, context: dict, now):
    """Ejecuta un paso y devuelve su resultado, o `_ESPERAR` si toca encolar.

    El `raise` de un paso fallido lo hace quien llama: aqui se rellena el
    resultado y se decide si el recorrido continua.
    """
    step_started_at = datetime.now(timezone.utc)
    config = json.loads(step.config) if step.config else {}
    retry_policy = _coerce_retry_policy(config)
    step_result = {
        "step": step.name or step.step_type,
        "ok": True,
        "retry_policy": retry_policy,
        "retry_attempts": 0,
    }

    if step.step_type == "action":
        _ejecutar_accion_con_reintentos(config, context, db, retry_policy, step_result, step)
    elif step.step_type == "wait":
        _encolar_continuacion(db, item, steps, step, config, now, step_result)
        return _ESPERAR, step_result
    elif step.step_type == "condition":
        step_result["condition_met"] = _evaluar_condicion(config, context)
    elif step.step_type == "webhook":
        _ejecutar_webhook(config, context, step_result, item)
    # Un tipo desconocido deja el paso como correcto y sigue, igual que antes.

    step_finished_at = datetime.now(timezone.utc)
    step_result["started_at"] = step_started_at.isoformat()
    step_result["completed_at"] = step_finished_at.isoformat()
    step_result["duration_ms"] = int(
        (step_finished_at - step_started_at).total_seconds() * 1000
    )
    step_result["execution_attempts"] = int(step_result.get("retry_attempts", 0)) + 1
    return None, step_result


def _anotar_metricas_del_flujo(results: list) -> None:
    """Añade a cada paso el resumen de la ejecucion completa.

    Se repite en todos los pasos a proposito: el historial se consulta por paso
    y asi cada fila lleva el contexto de su ejecucion sin tener que unir tablas.
    """
    total_duration_ms = int(sum((r.get("duration_ms") or 0) for r in results))
    total_retry_attempts = int(sum((r.get("retry_attempts") or 0) for r in results))
    for r in results:
        r["workflow_metrics"] = {
            "step_count": len(results),
            "total_duration_ms": total_duration_ms,
            "total_retry_attempts": total_retry_attempts,
        }


def _procesar_un_elemento(db, item, now) -> None:
    """Ejecuta los pasos pendientes de un elemento de la cola.

    Lanza si un paso falla: quien llama lo captura y decide si el elemento se
    reintenta o se marca como fallido definitivo.
    """
    wf = (db.query(AutomationWorkflow)
            .options(joinedload(AutomationWorkflow.steps))
            .filter(AutomationWorkflow.id == item.workflow_id)
            .first())
    if not wf or wf.status != "active":
        # Un flujo borrado o desactivado despues de encolar: el elemento se
        # cierra sin ejecutar nada y sin contarlo como error.
        item.status = "done"
        db.commit()
        return

    context = json.loads(item.trigger_data) if item.trigger_data else {}
    steps = sorted(wf.steps, key=lambda s: s.order)
    results = []

    for step in steps[item.step_index:]:
        senal, step_result = _ejecutar_paso(db, item, steps, step, context, now)
        results.append(step_result)
        if senal is _ESPERAR:
            # `break` y NO `return`: el original tambien salia del bucle y
            # seguia con el bloque de cierre de abajo, asi que un flujo que
            # queda esperando incrementa `success_count` y escribe un registro
            # de ejecucion «completed». Es discutible —el flujo esta suspendido,
            # no terminado— pero es el comportamiento actual y cambiarlo
            # alteraria las metricas de exito que se muestran.
            db.commit()
            break
        if not step_result.get("ok", True):
            raise RuntimeError(step_result.get("error") or "workflow_step_failed")

    _anotar_metricas_del_flujo(results)

    # Solo se crea el registro de ejecucion si el elemento no traia uno: los
    # elementos que continuan una espera comparten el registro del original.
    if not item.execution_id:
        db.add(WorkflowExecution(
            workflow_id=item.workflow_id, trigger_context=item.trigger_data,
            status="completed", steps_log=json.dumps(results),
            completed_at=now,
        ))

    wf.run_count = (wf.run_count or 0) + 1
    wf.success_count = (wf.success_count or 0) + 1
    wf.last_run_at = now
    item.status = "done"
    item.processed_at = now
    db.commit()


def process_workflow_queue_record(db, workflow_id: str | None = None) -> dict:
    """Procesa los elementos de la cola de automatizaciones que ya toca ejecutar."""
    now = datetime.now(timezone.utc)
    q = db.query(WorkflowQueueItem).filter(
        WorkflowQueueItem.status == "pending",
        WorkflowQueueItem.execute_at <= now,
        WorkflowQueueItem.attempts < _MAX_INTENTOS,
    )
    if workflow_id:
        q = q.filter(WorkflowQueueItem.workflow_id == workflow_id)
    pending = q.limit(_ELEMENTOS_POR_PASADA).all()

    processed = 0
    errors = 0
    for item in pending:
        # Se marca como «en proceso» y se cuenta el intento ANTES de ejecutar:
        # si el proceso muere a media, el elemento no queda pendiente para
        # siempre reintentandose sin cuenta.
        item.status = "processing"
        item.attempts += 1
        db.commit()
        try:
            # Revision multitenant 2026-11b: cada elemento en SU empresa. Llamado
            # por un superadmin (sesion sin filtro) los pasos corrian sin filtro
            # y lo que creaban quedaba sin empresa.
            from app.services.service_desk.ticket_events import como_organizacion
            with como_organizacion(db, item.organization_id):
                _procesar_un_elemento(db, item, now)
            if item.status == "done" and item.processed_at:
                processed += 1
        except Exception as e:
            logger.exception("Workflow queue item %s processing failed", item.id)
            # `rollback()` ANTES de escribir el estado de fallo. Si lo que fallo
            # fue una operacion de base —y procesar un elemento escribe en
            # base— la sesion queda en transaccion abortada, el `commit()` de
            # abajo revienta, y el `raise` sube y ABORTA EL BUCLE ENTERO: los
            # elementos siguientes no se procesan y este se queda en
            # `processing` para siempre, porque la consulta de pendientes solo
            # coge `pending`. Un fallo de un elemento atascaba la cola completa.
            # Auditoria 2026-08, hallazgo 22.
            db.rollback()
            item.status = "failed" if item.attempts >= _MAX_INTENTOS else "pending"
            item.last_error = str(e)[:500]
            errors += 1
            try:
                db.commit()
            except Exception:
                # Si tampoco se puede anotar el fallo, se deja la sesion limpia
                # y se sigue con el resto de la cola, que es mejor que perderlos.
                #
                # AVISO, y es `error` y no `exception` a proposito porque hace
                # falta que alguien lo vea: este elemento se queda en
                # `processing`, y NO HAY NINGUN BARRIDO que rescate ese estado
                # —comprobado: `"processing"` solo se escribe aqui y nadie lo
                # consulta—, asi que se queda ahi hasta que alguien lo mueva a
                # mano. Elegir `processing` en vez de `pending` fue deliberado
                # (ver el comentario de arriba: evita reintentos infinitos sin
                # cuenta), pero a esa decision le falta la otra mitad.
                db.rollback()
                logger.error(
                    "elemento %s de la cola de flujos ATASCADO en 'processing': "
                    "no se pudo registrar su fallo y no hay barrido que lo "
                    "rescate; requiere intervencion manual",
                    item.id, exc_info=True,
                )

    return {
        "processed": processed,
        "errors": errors,
        "remaining": db.query(WorkflowQueueItem)
                       .filter(WorkflowQueueItem.status == "pending").count(),
    }


def execute_workflow_now_record(workflow_id: str, context: dict, triggered_by, db) -> dict:
    """Enqueue and process one workflow immediately, returning execution summary."""
    enqueue_res = enqueue_workflow_record(
        {"workflow_id": workflow_id, "context": context or {}, "delay_minutes": 0},
        triggered_by,
        db,
    )
    process_res = process_workflow_queue_record(db, workflow_id=workflow_id)
    return {
        "ok": True,
        "workflow_id": workflow_id,
        "queue_id": enqueue_res.get("queue_id"),
        "processed": process_res.get("processed", 0),
        "errors": process_res.get("errors", 0),
    }
