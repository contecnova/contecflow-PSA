"""Las operaciones de auto-resolucion que lanza la API, con su transaccion.

Auditoria 2026-11 (#21). Estas escrituras —y sus `commit()`— estaban en
`endpoints/service_desk/ai_auto_resolution.py`: el endpoint decidia la frontera
de la transaccion. Se movieron tal cual; el endpoint conserva lo que es suyo
(quien puede llamar y buscar el ticket de su organizacion) y llama aqui.

El trabajo diario (`lanzar_trabajo`) incluye el camino asincrono: la tarea de
fondo abre su propia sesion. Recibe `programar` —el `add_task` de FastAPI— para
no depender del framework.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.db.session import SessionLocal
from app.models.service_desk import Ticket, TicketStatus
from app.services.service_desk.ai_auto_resolution_service import (
    analyze_ticket_for_resolution,
    anotar_en_el_historial,
    cerrojo_del_trabajo,
    estado_del_trabajo,
    guardar_estado_del_trabajo,
    record_resolution_feedback,
    run_auto_close_job,
    run_daily_auto_resolution_job,
    save_auto_resolution_config,
    validate_auto_resolution,
)

# El nombre del logger es el que tenia en el endpoint: no cambia donde se lee.
_logger = logging.getLogger("sd_auto_resolution_endpoint")


def aplicar_auto_resolucion(db: Session, ticket: Ticket, current_user, force: bool) -> dict:
    """Analiza el ticket y, si la confianza llega (o `force`), lo resuelve y confirma."""
    if ticket.status in [TicketStatus.resolved, TicketStatus.closed]:
        raise ErrorDeDominio(status_code=400, detail="Ticket already resolved/closed")

    # Analyze first
    analysis = analyze_ticket_for_resolution(db, ticket, current_user)

    # Auditoria 2026-11: era 0.65 fijo, distinto del 0.80 configurable del agente
    # autonomo: el mismo ticket se resolvia o no segun el camino. Ahora ambos usan
    # SD_AUTONOMY_RESOLVE_THRESHOLD de la organizacion; quien lo pide puede forzar.
    from app.services.settings_service import get_runtime_float
    umbral = get_runtime_float(db, "SD_AUTONOMY_RESOLVE_THRESHOLD", ticket.organization_id) or 0.80
    if analysis["confidence"] < umbral and not force:
        raise ErrorDeDominio(
            status_code=400,
            detail=f"Confidence too low ({analysis['confidence']*100:.1f}%). "
                   f"Use ?force=true to override.",
        )

    # Apply resolution
    ticket.status = TicketStatus.resolved
    ticket.resolution_text = analysis["suggestion"]
    ticket.resolution = analysis["suggestion"]
    ticket.root_cause = analysis.get("root_cause", "")
    ticket.auto_resolved = True
    ticket.auto_resolved_at = datetime.now(timezone.utc)
    ticket.auto_resolved_by = current_user.username
    ticket.auto_resolved_confidence = analysis["confidence"]

    if analysis["kb_sources"]:
        ticket.resolution_kb_articles = json.dumps(
            [s["number"] for s in analysis["kb_sources"]]
        )

    db.commit()

    return {
        "message": f"✅ Ticket {ticket.number} auto-resolved with {analysis['confidence']*100:.1f}% confidence",
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
    }


def validar_auto_resolucion(db: Session, ticket: Ticket) -> dict:
    result = validate_auto_resolution(db, ticket)
    db.commit()
    return result


def registrar_valoracion(db: Session, ticket: Ticket, exito: bool) -> None:
    record_resolution_feedback(db, ticket, exito)
    db.commit()


def guardar_configuracion(db: Session, cambios: dict) -> dict:
    cfg = save_auto_resolution_config(db, cambios)
    db.commit()
    return cfg


def cerrar_resueltos(db: Session, organization_id: str | None) -> dict:
    stats = run_auto_close_job(db, organization_id)
    db.commit()
    return stats


# ── El trabajo diario ───────────────────────────────────────────────────────

def ya_esta_corriendo(db, org) -> dict:
    """La respuesta cuando el cerrojo está tomado.

    Auditoría 2026-09 (hallazgo 18): estaba escrita dos veces, una por camino.
    Es la misma respuesta y tiene que seguir siéndolo: dos versiones que
    divergieran darían una señal distinta según por dónde se preguntara.
    """
    return {
        "status": "already_running",
        "message": "Auto-resolution job is already running",
        "runtime": estado_del_trabajo(db, org),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def registrar_fallo_del_trabajo(db, org, comenzado, exc) -> None:
    """Anota que la pasada falló, dejando la sesión utilizable.

    **Quien llama tiene que haber deshecho la transacción antes.** No se hace
    aquí a propósito: `tests/test_commit_rollback.py` busca el `rollback()` en
    el cuerpo del manejador de excepciones por AST y no sigue las llamadas, así
    que esconderlo aquí lo dejaría invisible para el guardián.

    Si ni el registro se puede escribir, se deja la sesión limpia y se calla:
    quien llama propaga el error ORIGINAL, que es el que hay que leer.
    """
    terminado = datetime.now(timezone.utc)
    registro = {
        "status": "failed",
        "started_at": comenzado.isoformat(),
        "completed_at": terminado.isoformat(),
        "duration_ms": int((terminado - comenzado).total_seconds() * 1000),
        "stats": None,
        "error": str(exc)[:240],
    }
    try:
        guardar_estado_del_trabajo(
            db, {"running": False, "last_job_id": None, **registro}, org,
        )
        anotar_en_el_historial(db, registro, org)
        db.commit()
    except Exception:
        db.rollback()
        _logger.exception("no se pudo registrar el fallo del job de auto-resolucion")


def lanzar_trabajo(db: Session, org: str | None, limit: int, run_async: bool,
                   programar: Callable) -> dict:
    """Lanza la pasada de auto-resolucion de la organizacion `org`.

    Asincrona: toma el cerrojo, deja el estado «running» confirmado y programa
    la tarea de fondo con `programar(funcion, *args)`; la tarea libera el
    cerrojo. Sincrona: toma el cerrojo, ejecuta y lo libera en un `finally`.
    Con el cerrojo tomado devuelve `already_running` sin ejecutar nada.
    """
    cerrojo = cerrojo_del_trabajo(org)
    safe_limit = max(1, min(int(limit), 500))

    if run_async:
        if not cerrojo.acquire(blocking=False):
            return ya_esta_corriendo(db, org)

        job_id = str(uuid4())
        guardar_estado_del_trabajo(db, {
                "running": True,
                "status": "running",
                "last_job_id": job_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "stats": None,
                "error": None,
            },
            org,
        )
        db.commit()

        def _run_job_in_background(limit_to_use: int, queued_job_id: str) -> None:
            session = SessionLocal()
            # Auditoria 2026-08 (hallazgo 22). Este es un trabajo de fondo, asi
            # que la rama de «sesion no inicializada» de `TenantSession` esta
            # pensada para el — pero **la organizacion se conoce** (`org`, del
            # sujeto que lanzo la pasada), y el trabajo la pasa explicita a
            # cada servicio. Publicarla en la sesion no cambia el
            # comportamiento y anade la capa implicita detras de la explicita,
            # que es justo lo que faltaba en los otros ocho sitios.
            if org:
                session.info["organization_id"] = org
                session.info["is_superadmin"] = False
            run_started = datetime.now(timezone.utc)
            try:
                stats = run_daily_auto_resolution_job(session, limit=limit_to_use, organization_id=org)
                run_finished = datetime.now(timezone.utc)
                duration_ms = int((run_finished - run_started).total_seconds() * 1000)
                run_record = {
                    "status": "completed",
                    "started_at": run_started.isoformat(),
                    "completed_at": run_finished.isoformat(),
                    "duration_ms": duration_ms,
                    "stats": stats,
                    "error": None,
                }
                guardar_estado_del_trabajo(session, {
                        "running": False,
                        "last_job_id": queued_job_id,
                        **run_record,
                    },
                    org,
                )
                anotar_en_el_historial(session, run_record, org)
                session.commit()
                _logger.info(
                    "Auto-resolution background job %s finished: %s",
                    queued_job_id,
                    stats,
                )
            except Exception as exc:
                run_finished = datetime.now(timezone.utc)
                duration_ms = int((run_finished - run_started).total_seconds() * 1000)
                try:
                    fail_record = {
                        "status": "failed",
                        "started_at": run_started.isoformat(),
                        "completed_at": run_finished.isoformat(),
                        "duration_ms": duration_ms,
                        "stats": None,
                        "error": str(exc)[:240],
                    }
                    guardar_estado_del_trabajo(session, {
                            "running": False,
                            "last_job_id": queued_job_id,
                            **fail_record,
                        },
                        org,
                    )
                    anotar_en_el_historial(session, fail_record, org)
                    session.commit()
                except Exception:
                    _logger.warning("_run_job_in_background: excepcion ignorada", exc_info=True)
                    session.rollback()
                _logger.exception(
                    "Auto-resolution background job %s failed: %s",
                    queued_job_id,
                    exc,
                )
            finally:
                session.close()
                cerrojo.release()

        programar(_run_job_in_background, safe_limit, job_id)
        return {
            "status": "queued",
            "job_id": job_id,
            "limit": safe_limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Camino sincrono ─────────────────────────────────────────────────────
    #
    # Auditoria 2026-08 (hallazgo 22). Dos cosas que este bloque no hacia y el
    # camino asincrono de arriba SI hace. La señal fue la asimetria: dos
    # caminos para el mismo trabajo, uno correcto y el otro no.
    #
    # 1. El guardia `already_running` protegia SOLO el camino asincrono. El lock
    #    se toma en la rama `run_async=True` y se libera en su `finally`; esta
    #    rama no lo tocaba, asi que dos llamadas con `run_async=False` podian
    #    solaparse entre si y con una asincrona ya en cola. El trabajo resuelve
    #    tickets automaticamente: solapar dos pasadas puede resolver el mismo
    #    ticket dos veces.
    #
    # 2. El `except` escribia el registro de fallo y hacia `commit()` SIN
    #    `rollback()` antes. Si el fallo original era de base —y lo probable es
    #    que lo sea, porque el trabajo escribe en base— la sesion queda en
    #    transaccion abortada: el registro del fallo no se escribia nunca, el
    #    panel se quedaba diciendo «running» para siempre, y el error real
    #    quedaba tapado por un `PendingRollbackError`.
    if not cerrojo.acquire(blocking=False):
        return ya_esta_corriendo(db, org)

    try:
        sync_started = datetime.now(timezone.utc)
        guardar_estado_del_trabajo(db, {
                "running": True,
                "status": "running",
                "last_job_id": None,
                "started_at": sync_started.isoformat(),
                "completed_at": None,
                "duration_ms": None,
                "stats": None,
                "error": None,
            },
            org,
        )
        db.commit()

        try:
            stats = run_daily_auto_resolution_job(db, limit=safe_limit, organization_id=org)
            sync_finished = datetime.now(timezone.utc)
            duration_ms = int((sync_finished - sync_started).total_seconds() * 1000)
            sync_record = {
                "status": "completed",
                "started_at": sync_started.isoformat(),
                "completed_at": sync_finished.isoformat(),
                "duration_ms": duration_ms,
                "stats": stats,
                "error": None,
            }
            guardar_estado_del_trabajo(db, {"running": False, "last_job_id": None, **sync_record}, org)
            anotar_en_el_historial(db, sync_record, org)
            db.commit()
        except Exception as exc:
            # El `rollback()` se queda AQUI, a la vista, y no dentro del
            # ayudante. Dos motivos, y el segundo es el que manda:
            #
            #  · Deshacer antes de intentar escribir el registro de fallo es lo
            #    que impide que un fallo de base deje la sesion abortada y el
            #    `commit()` de abajo reviente con `PendingRollbackError`,
            #    tapando el error real. Ese era el defecto de 2026-08.
            #  · `tests/test_commit_rollback.py` lo busca **en el cuerpo del
            #    manejador**, por AST, y no sigue las llamadas. Esconderlo tras
            #    una funcion lo deja invisible para el guardian — que es justo
            #    como este defecto volvio cinco veces antes de que existiera.
            #    La conservadurismo del guardian es correcta aqui.
            db.rollback()
            registrar_fallo_del_trabajo(db, org, sync_started, exc)
            raise

        return {
            **stats,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        cerrojo.release()
