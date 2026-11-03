"""Entradas de APScheduler para las automatizaciones (las mismas que el beat)."""
import logging

from app.db.session import worker_db_session

logger = logging.getLogger(__name__)


def procesar_eventos_job() -> None:
    from app.services.automation_events import procesar_pendientes
    with worker_db_session() as db:
        resultado = procesar_pendientes(db)
    if resultado.get("events"):
        logger.info("Automatizaciones: %s", resultado)


def escanear_job() -> None:
    from app.services.automations_service import escanear
    with worker_db_session() as db:
        logger.info("Automatizaciones, barrido: %s", escanear(db))
