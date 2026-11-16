"""Permisos por proyecto (`project_permissions`) que se aplican.

Auditoria 2026-11. La pantalla /project-permissions guardaba un nivel y tres
interruptores por persona y proyecto, y ninguna comprobacion los leia (solo se
usaban como lista de destinatarios de avisos). Ahora, en cada peticion con un
`{project_id}` en la ruta, si la persona tiene una fila activa y no caducada
para ese proyecto:

- `none`: no entra (403), y el proyecto desaparece de su lista;
- `viewer`: solo lee (GET/HEAD/OPTIONS);
- `member`, `manager`, `owner`: lo que ya le permita su rol;
- `can_see_financials = false`: ni EVM, ni rentabilidad, ni ingresos;
- `can_export = false`: ninguna ruta de exportacion;
- `can_see_rates = false`: sin el coste de las imputaciones ajenas.

Ademas, una fila `viewer` o superior hace que el proyecto aparezca en la lista
de un PM o de un empleado que no lo veria por su rol.

Lo que NO hace: un nivel alto no da permisos que el rol no tenga (un empleado
`manager` de un proyecto sigue sin poder lo que solo puede un PM). Un admin no
se restringe nunca.

`can_see_rates = false` (revisión 2026-11): en la lista de imputaciones, las de
otras personas en ese proyecto salen sin coste (coste = horas × tarifa).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio

_LECTURA = {"GET", "HEAD", "OPTIONS"}
_FINANCIEROS = {"evm", "profitability", "revenue-forecast", "revenue", "margin", "budget"}


def _activas(db: Session, user_id: str):
    from app.models.enterprise import ProjectPermission
    ahora = datetime.now(timezone.utc)
    return db.query(ProjectPermission).filter(
        ProjectPermission.user_id == user_id, ProjectPermission.is_active.is_(True),
        or_(ProjectPermission.expires_at.is_(None), ProjectPermission.expires_at > ahora))


def _exento(user) -> bool:
    return bool(getattr(user, "is_superadmin", False)) or getattr(user.role, "value", user.role) == "admin"


#: Motivo de denegación (código estable) -> mensaje del 403. Revisión GRC
#: 16-11-2026: `decidir` devolvía el mensaje en castellano y el explicador de
#: accesos lo usaba como clave de traducción (`grc.acceso_detalle_<motivo>`),
#: así que en inglés y chino salía en castellano y la consola avisaba de una
#: clave inexistente. Ahora devuelve el código; el mensaje sólo lo pone el 403.
MOTIVOS = {
    "project_level_none": "No tienes acceso a este proyecto",
    "project_viewer_read_only": "En este proyecto solo tienes acceso de lectura",
    "project_no_financials": "No puedes ver los datos financieros de este proyecto",
    "project_no_export": "No puedes exportar datos de este proyecto",
}


def decidir(db: Session, user, metodo: str, ruta: str, proyecto) -> tuple[Optional[str], Optional[str]]:
    """(nivel de la fila, código del motivo de la denegación o None) para ese proyecto.

    Revisión 2026-11: la usan `comprobar` y el explicador de accesos. El código
    es una clave de `MOTIVOS`.
    """
    if not proyecto or _exento(user):
        return None, None
    from app.models.enterprise import ProjectPermission
    fila = _activas(db, user.id).filter(ProjectPermission.project_id == proyecto).first()
    if fila is None:
        return None, None
    nivel = getattr(fila.level, "value", fila.level)
    segmentos = set(ruta.strip("/").split("/"))
    if nivel == "none":
        return nivel, "project_level_none"
    if nivel == "viewer" and metodo.upper() not in _LECTURA:
        return nivel, "project_viewer_read_only"
    if fila.can_see_financials is False and segmentos & _FINANCIEROS:
        return nivel, "project_no_financials"
    if fila.can_export is False and any("export" in s for s in segmentos):
        return nivel, "project_no_export"
    return nivel, None


def comprobar(db: Session, user, request: Request) -> None:
    _nivel, motivo = decidir(db, user, request.method, request.url.path,
                             (request.path_params or {}).get("project_id"))
    if motivo:
        raise ErrorDeDominio(status.HTTP_403_FORBIDDEN, MOTIVOS[motivo])


def vetados_y_concedidos(db: Session, user) -> tuple[set[str], set[str]]:
    """(proyectos con nivel none, proyectos con viewer o mas) para las listas."""
    if _exento(user):
        return set(), set()
    vetados, concedidos = set(), set()
    for fila in _activas(db, user.id):
        nivel = getattr(fila.level, "value", fila.level)
        (vetados if nivel == "none" else concedidos).add(fila.project_id)
    return vetados, concedidos


def proyectos_sin_tarifas(db: Session, user) -> set[str]:
    """Proyectos donde la persona no ve las tarifas de los demás (`can_see_rates = false`)."""
    if _exento(user):
        return set()
    from app.models.enterprise import ProjectPermission
    return {pid for (pid,) in _activas(db, user.id).filter(ProjectPermission.can_see_rates.is_(False))
            .with_entities(ProjectPermission.project_id).all()}
