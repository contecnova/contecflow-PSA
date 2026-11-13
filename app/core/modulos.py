"""Acceso por modulo de los roles (`custom_roles.module_access`).

Auditoria 2026-11. La tabla se editaba en Ajustes > Roles y nadie la leia; y no
habia forma de asignar un rol personalizado a una persona. Ahora:

- El rol base (`users.role`: admin, pm, team_lead, hr, employee, subcontractor)
  sigue decidiendo que puede hacer cada uno. El acceso por modulo **solo
  restringe**: nunca da a nadie algo que su rol base no tuviera.
- Manda el rol personalizado asignado (`users.custom_role_id`); si no tiene, la
  fila de sistema de su rol base en su organizacion.
- Un modulo marcado como `false` se cierra en la API (403 en sus rutas) y en la
  pantalla (desaparece del menu y su ruta lleva a /403). Un modulo que no
  aparece en el JSON queda abierto.
- Un admin (y el superadmin) no se restringe nunca: es quien puede deshacerlo.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import Request, status
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio

#: modulo -> (prefijos de la API, rutas de la pantalla). Los nombres son los
#: de `advanced_config_service.DEFAULT_MODULES`.
MODULOS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "dashboard":     (("/api/v1/dashboard",), ("/projects-dashboard", "/executive", "/team-dashboard")),
    "projects":      (("/api/v1/projects", "/api/v1/portfolios", "/api/v1/milestones", "/api/v1/epics",
                       "/api/v1/sprints"),
                      ("/projects", "/portfolio", "/sprints", "/sprint-planning", "/sprint-charts", "/epics",
                       "/epic-gantt", "/gantt")),
    "tasks":         (("/api/v1/tasks", "/api/v1/task-dependencies"), ("/tasks", "/kanban-advanced")),
    "imputations":   (("/api/v1/imputations",), ("/imputar", "/time", "/timer")),
    "timesheets":    (("/api/v1/timesheets",), ("/timesheets",)),
    "resources":     (("/api/v1/resources", "/api/v1/resource-forecast", "/api/v1/resource-demand"),
                      ("/resources", "/resource-forecast", "/resource-scheduler")),
    "capacity":      (("/api/v1/capacity",), ("/capacity",)),
    "profitability": (("/api/v1/profitability", "/api/v1/revenue", "/api/v1/revenue-forecast"),
                      ("/profitability", "/finance-dashboard", "/revenue")),
    "pipeline":      (("/api/v1/pipeline",), ("/pipeline",)),
    "contracts":     (("/api/v1/contracts", "/api/v1/contracts-ai"), ("/contracts", "/contracts-ai")),
    "risks":         (("/api/v1/risks", "/api/v1/risk-scores"), ("/risks", "/risk-scores")),
    "changes":       (("/api/v1/changes",), ("/changes",)),
    "deliverables":  (("/api/v1/deliverables",), ("/deliverables",)),
    "skills":        (("/api/v1/skills",), ("/skills",)),
    "absences":      (("/api/v1/absences",), ("/absences",)),
    "reports":       (("/api/v1/reports", "/api/v1/analytics", "/api/v1/bi"),
                      ("/reports", "/report-builder", "/bi", "/data-explorer")),
    "alerts":        (("/api/v1/alerts",), ("/alerts",)),
    "exports":       (("/api/v1/pdf",), ("/exports",)),
    "settings":      (("/api/v1/settings", "/api/v1/advanced-config"), ("/settings",)),
}

#: Lecturas que la propia aplicacion necesita para arrancar, aunque el modulo
#: este cerrado (zona horaria, moneda, tiempo de inactividad).
_SIEMPRE = ("/api/v1/settings/org-defaults", "/api/v1/settings/general")


def _cubre(ruta: str, prefijo: str) -> bool:
    return ruta == prefijo or ruta.startswith(prefijo + "/")


def _rol_efectivo(db: Session, user):
    from app.db.session import sin_filtro_de_tenant
    from app.models.advanced_config import CustomRole

    org = getattr(user, "organization_id", None)
    with sin_filtro_de_tenant(db):
        if getattr(user, "custom_role_id", None):
            rol = db.query(CustomRole).filter(CustomRole.id == user.custom_role_id,
                                              CustomRole.is_active.is_(True),
                                              CustomRole.organization_id == org).first()
            if rol is not None:
                return rol
        base = getattr(user.role, "value", user.role)
        return db.query(CustomRole).filter(CustomRole.name == base, CustomRole.is_system.is_(True),
                                           CustomRole.is_active.is_(True),
                                           CustomRole.organization_id == org).first() if org else None


def vetados(db: Session, user) -> set[str]:
    """Modulos cerrados para `user` (vacio para admin y superadmin)."""
    if getattr(user, "is_superadmin", False) or getattr(user.role, "value", user.role) == "admin":
        return set()
    rol = _rol_efectivo(db, user)
    if rol is None or not rol.module_access:
        return set()
    try:
        acceso = json.loads(rol.module_access) or {}
    except ValueError:
        return set()
    return {m for m in MODULOS if acceso.get(m) is False}


def modulo_cerrado(db: Session, user, ruta: str) -> Optional[str]:
    """El modulo cerrado para `user` al que pertenece la ruta, o None.

    Revisión 2026-11: la misma decisión la usan `comprobar` y el explicador de
    accesos, para que lo que este cuenta sea lo que de verdad pasa.
    """
    if not ruta.startswith("/api/") or ruta in _SIEMPRE:
        return None
    for modulo in sorted(vetados(db, user)):
        if any(_cubre(ruta, p) for p in MODULOS[modulo][0]):
            return modulo
    return None


def comprobar(db: Session, user, request: Request) -> None:
    """403 si la ruta pertenece a un modulo cerrado para este usuario."""
    modulo = modulo_cerrado(db, user, request.url.path)
    if modulo:
        raise ErrorDeDominio(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Tu rol no tiene acceso al módulo «{modulo}»")


def rutas_cerradas(db: Session, user) -> list[str]:
    """Rutas de la pantalla que el menu esconde y el enrutador lleva a /403."""
    return sorted({r for m in vetados(db, user) for r in MODULOS[m][1]})


def con_rutas_cerradas(db: Session, user):
    """El usuario con `blocked_routes` puesto, para `UserPublic`."""
    user.blocked_routes = rutas_cerradas(db, user)
    return user


def validar_acceso(module_access: Optional[dict]) -> None:
    if not module_access:
        return
    desconocidos = sorted(set(module_access) - set(MODULOS))
    if desconocidos:
        raise ErrorDeDominio(422, f"Módulos desconocidos: {', '.join(desconocidos)}")
