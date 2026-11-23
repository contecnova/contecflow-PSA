"""Logger y la excepcion `NotFoundError`, compartidos.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging


logger = logging.getLogger("app.services.advanced_config_service")


# ── Custom exceptions ─────────────────────────────────────────────────────────

class NotFoundError(ValueError):
    pass


# ── Auditoría de la configuración avanzada (M91, auditoría 22-11-2026) ────────
#
# Roles, tipos de tarea, tablas y líneas de tarifa, numeraciones, campos
# personalizados, políticas de vacaciones y oficinas se cambiaban sin dejar
# rastro. Un único `before_flush` anota en `audit_log` cada alta, cambio y baja
# de esas tablas, con quien lo hace (`session.info["current_user"]`, lo publica
# `get_current_user`) y lo que cambia; así ninguna función se queda sin auditar.

def _auditar_configuracion(session, _contexto, _instancias) -> None:
    from sqlalchemy import inspect as _inspect
    from app.models import advanced_config as m
    tipos = tuple(t for t in (getattr(m, n, None) for n in (
        "CustomRole", "TaskType", "RateTable", "RateEntry", "NumberingSequence", "CustomField",
        "VacationPolicy", "Office", "AlertConfig")) if t is not None)
    if not tipos:
        return
    actor = session.info.get("current_user")
    from app.services.audit import audit_log

    def _cambios(obj) -> dict:
        salida = {}
        for attr in _inspect(obj).attrs:
            h = attr.history
            if h.has_changes():
                salida[attr.key] = {"old": str(h.deleted[0]) if h.deleted else None,
                                    "new": str(h.added[0]) if h.added else None}
        return salida

    filas = [("CREATE", o) for o in session.new if isinstance(o, tipos)]
    filas += [("UPDATE", o) for o in session.dirty if isinstance(o, tipos) and session.is_modified(o)]
    filas += [("DELETE", o) for o in session.deleted if isinstance(o, tipos)]
    for accion, obj in filas:
        try:
            audit_log(session, actor, accion, f"advanced_config.{obj.__tablename__}", getattr(obj, "id", None),
                      str(getattr(obj, "name", None) or getattr(obj, "label", None) or getattr(obj, "entity", None) or ""),
                      new_values=_cambios(obj) if accion == "UPDATE" else None)
        except Exception:
            logger.warning("auditoría de configuración avanzada: no se pudo anotar", exc_info=True)


def _registrar() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session as _Session
    if not event.contains(_Session, "before_flush", _auditar_configuracion):
        event.listen(_Session, "before_flush", _auditar_configuracion)


_registrar()
