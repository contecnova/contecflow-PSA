from app.core.tareas_diferidas import ProgramadorDeTareas
from typing import Optional

from app.db.contexto_de_tenant import fijar_contexto
from app.db.session import SessionLocal
from app.services.semantic_classifier import SemanticAssigner
import logging

logger = logging.getLogger(__name__)

# Auditoría 22-11-2026 (informe 03, fila kb_*/semantic_feedback; M8): estas
# tareas abren su `SessionLocal()` cuando la petición ya terminó. Reciben la
# empresa del ticket (`org_id`) y trabajan en ella; sin empresa (llamadas
# antiguas) es trabajo de sistema declarado, por id.
_MOTIVO = "retroalimentación semántica en segundo plano (por id)"


def enqueue_profile_refresh(background_tasks: ProgramadorDeTareas, user_id: str,
                            org_id: Optional[str] = None) -> None:

    def _run():
        db = fijar_contexto(SessionLocal(), org_id, _MOTIVO)
        try:
            SemanticAssigner(db).refresh_user_profile(user_id)
        except Exception:
            logger.debug("_run: fallo best-effort ignorado", exc_info=True)
        finally:
            db.close()

    background_tasks.add_task(_run)


def enqueue_reassign_feedback(background_tasks: ProgramadorDeTareas, item_id: str, item_type: str,
                              org_id: Optional[str] = None, nuevo_user_id: Optional[str] = None) -> None:
    """Reasignado: la sugerencia de la IA se rechaza si la nueva persona no es la sugerida.

    23-11-2026: antes solo se tocaba si `was_accepted` era None (una sugerencia
    ya confirmada seguía contando como acierto tras reasignarla) y se marcaba
    False aunque se volviera a la persona sugerida.
    """

    def _run():
        from app.services.semantic_engine_service import resolver_por_reasignacion
        db = fijar_contexto(SessionLocal(), org_id, _MOTIVO)
        try:
            if resolver_por_reasignacion(db, item_type, item_id, nuevo_user_id) is not None:
                db.commit()
        except Exception:
            logger.warning("_run: excepcion ignorada", exc_info=True)
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(_run)


def enqueue_cierre_semantico(background_tasks: ProgramadorDeTareas, item_type: str, item_id: str,
                             org_id: Optional[str] = None) -> None:
    """Resuelto o cerrado: historial del nivel 3 (`SemEmbeddingCache`) y veredicto de la sugerencia.

    23-11-2026: el historial con decaimiento del nivel 3 no tenía datos porque
    nada lo alimentaba. Quien resolvió es la persona asignada al cerrar.
    """

    def _run():
        from app.services.semantic_engine_service import _item_de_la_empresa, cerrar_item, texto_del_item
        db = fijar_contexto(SessionLocal(), org_id, _MOTIVO)
        try:
            item = _item_de_la_empresa(db, item_type, item_id)
            if item is not None:
                quien = getattr(item, "assigned_to_user_id", None) or getattr(item, "assignee_id", None)
                calidad = getattr(item, "csat_score", None)
                cerrar_item(db, item_type, item_id, texto=texto_del_item(item), user_id=quien,
                            calidad=float(calidad) if isinstance(calidad, (int, float)) else None)
                db.commit()
        except Exception:
            logger.warning("_run: excepcion ignorada", exc_info=True)
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(_run)


def registrar_cierre_semantico(db, item, item_type: str = "ticket") -> bool:
    """Lo mismo que `enqueue_cierre_semantico`, en la sesión del llamante (sin confirmar).

    23-11-2026: para los cierres que no pasan por el PATCH (automatismos de IA,
    agente autónomo, catálogo, Jira y el cierre automático de los
    auto-resueltos). Va en un punto de guardado: si falla (p. ej. el
    codificador), se registra en el log y no deshace el cierre.
    """
    from app.services.semantic_engine_service import cerrar_item, texto_del_item
    if item is None:
        return False
    try:
        with db.begin_nested():
            quien = getattr(item, "assigned_to_user_id", None) or getattr(item, "assignee_id", None)
            calidad = getattr(item, "csat_score", None)
            cerrar_item(db, item_type, item.id, texto=texto_del_item(item), user_id=quien,
                        calidad=float(calidad) if isinstance(calidad, (int, float)) else None)
        return True
    except Exception:
        logger.warning("registrar_cierre_semantico: excepcion ignorada", exc_info=True)
        return False


def enqueue_routing_outcome(background_tasks: ProgramadorDeTareas, ticket_id: str,
                            org_id: Optional[str] = None) -> None:
    """Record ML routing outcome (resolution time + CSAT) when a ticket is resolved/closed."""

    def _run():
        from app.models.service_desk import Ticket
        from app.services.service_desk.ml_routing_service import record_routing_outcome

        db = fijar_contexto(SessionLocal(), org_id, _MOTIVO)
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if ticket:
                record_routing_outcome(db, ticket)
                db.commit()
        except Exception:
            logger.warning("_run: excepcion ignorada", exc_info=True)
            db.rollback()
        finally:
            db.close()

    background_tasks.add_task(_run)
