"""Ganchos de altas y bajas de personas: los llaman los caminos que crean o
desactivan usuarios (alta y baja manual, SCIM y el cambio de estado).

- `al_desactivar`: abre la baja de ALM (licencias y devoluciones). En la baja
  manual, antes, `comprobar_baja_manual` aplica la política de equipo sin
  devolver. Desde SCIM nunca bloquea ni rompe la petición del proveedor de
  identidad: si ALM falla, se deshace solo lo de ALM y queda en el registro.
- `al_crear`: propone el kit de alta (si `ALM_KIT_ON_HIRE`).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)


def comprobar_baja_manual(db: Session, user: User, confirmar: bool) -> None:
    from app.services.alm_integracion.bajas import comprobar_desactivacion_manual
    comprobar_desactivacion_manual(db, user, confirmar)


def al_desactivar(db: Session, user: User, motivo: str, actor=None, *, confirmada: bool = False,
                  tolerante: bool = False) -> Optional[dict]:
    """La baja de ALM de `user`, en la transacción de quien desactiva (no confirma).

    ``tolerante``: un fallo de ALM no corta la desactivación (SCIM, trabajos);
    se hace en un punto de guardado para deshacer solo lo de ALM.
    """
    from app.services.alm_integracion.bajas import al_dar_de_baja, serializar_baja
    if not tolerante:
        baja = al_dar_de_baja(db, user, motivo, actor, confirmada_con_pendientes=confirmada)
        return serializar_baja(db, baja)
    punto = db.begin_nested()
    try:
        baja = al_dar_de_baja(db, user, motivo, actor, confirmada_con_pendientes=confirmada)
        punto.commit()
        return serializar_baja(db, baja)
    except Exception:
        punto.rollback()
        logger.exception("ALM: no se pudo abrir la baja de %s (%s); la desactivación sigue", user.id, motivo)
        return None


def al_crear(db: Session, user: User, actor=None) -> None:
    """Propone el kit de alta. Nunca corta el alta."""
    from app.services.alm_integracion.kits import proponer
    punto = db.begin_nested()
    try:
        proponer(db, user, actor)
        punto.commit()
    except Exception:
        punto.rollback()
        logger.exception("ALM: no se pudo proponer el kit de alta de %s", user.id)
