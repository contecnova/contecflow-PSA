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
- `can_export = false`: ninguna ruta de exportacion.

Ademas, una fila `viewer` o superior hace que el proyecto aparezca en la lista
de un PM o de un empleado que no lo veria por su rol.

Lo que NO hace: un nivel alto no da permisos que el rol no tenga (un empleado
`manager` de un proyecto sigue sin poder lo que solo puede un PM), y
`can_see_rates` no tiene ruta por proyecto a la que aplicarse. Un admin no se
restringe nunca.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

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


def comprobar(db: Session, user, request: Request) -> None:
    proyecto = (request.path_params or {}).get("project_id")
    if not proyecto or _exento(user):
        return
    from app.models.enterprise import ProjectPermission
    fila = _activas(db, user.id).filter(ProjectPermission.project_id == proyecto).first()
    if fila is None:
        return
    nivel = getattr(fila.level, "value", fila.level)
    segmentos = set(request.url.path.strip("/").split("/"))
    if nivel == "none":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes acceso a este proyecto")
    if nivel == "viewer" and request.method not in _LECTURA:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "En este proyecto solo tienes acceso de lectura")
    if fila.can_see_financials is False and segmentos & _FINANCIEROS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes ver los datos financieros de este proyecto")
    if fila.can_export is False and any("export" in s for s in segmentos):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes exportar datos de este proyecto")


def vetados_y_concedidos(db: Session, user) -> tuple[set[str], set[str]]:
    """(proyectos con nivel none, proyectos con viewer o mas) para las listas."""
    if _exento(user):
        return set(), set()
    vetados, concedidos = set(), set()
    for fila in _activas(db, user.id):
        nivel = getattr(fila.level, "value", fila.level)
        (vetados if nivel == "none" else concedidos).add(fila.project_id)
    return vetados, concedidos
