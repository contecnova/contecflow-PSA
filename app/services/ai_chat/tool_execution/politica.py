"""Quién puede usar cada herramienta del asistente (chat, agente y MCP).

Segunda auditoría 2026-11. Las herramientas eran una API paralela sin guardas:
por MCP (que admite a cualquier empleado) se leían los usuarios con su correo,
los contratos o las imputaciones de toda la empresa, y se cambiaba el estado de
cualquier proyecto o ticket. Ahora cada herramienta declara su **endpoint REST
equivalente** y hereda sus dos guardas de entrada:

- el rol (la misma dependencia `RequireRole` que la ruta; `None` = cualquier sesión);
- la matriz GRC: el módulo sale de la ruta (`grc_catalog.module_for_path`), como
  en `enforce_grc_matrix`, y la acción es la del método.

El ALCANCE de los datos (qué proyectos, tickets o personas ve) lo aplica cada
herramienta con las mismas funciones que su listado (`scope_projects_query`,
`scope_ticket_query`, `politica_de_visibilidad`...), y las que escriben llaman
al mismo servicio que el endpoint (con su ABAC). Una herramienta sin política
no se ejecuta: falla cerrada (`tests/test_herramientas_ia_alcance_2026_11.py`
comprueba que todas la tienen y que su ruta existe).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import (
    RequireRole,
    require_admin_or_hr,
    require_admin_or_pm,
    require_any_manager,
    require_internal_user,
)


@dataclass(frozen=True)
class Politica:
    metodo: str                   #: método HTTP del endpoint equivalente
    ruta: str                     #: su ruta bajo /api/v1, tal como está registrada
    roles: Optional[RequireRole]  #: su guarda de rol; None = cualquier sesión


_GET, _POST, _PATCH = "GET", "POST", "PATCH"

POLITICAS: dict[str, Politica] = {
    # Proyectos
    "get_project_status":    Politica(_GET, "/projects/{project_id}", None),
    "search_projects":       Politica(_GET, "/projects", None),
    "get_dashboard_summary": Politica(_GET, "/dashboard/projects-health", require_any_manager),
    "get_budget_status":     Politica(_GET, "/dashboard/projects-health", require_any_manager),
    "update_project_status": Politica(_PATCH, "/projects/{project_id}", require_admin_or_pm),
    # Riesgos
    "get_project_risks":     Politica(_GET, "/risks/{project_id}", None),
    "get_all_risks":         Politica(_GET, "/risks/all/portfolio", require_any_manager),
    "create_risk":           Politica(_POST, "/risks/{project_id}", require_admin_or_pm),
    # Tareas
    "get_overdue_tasks":     Politica(_GET, "/tasks", None),
    "create_task":           Politica(_POST, "/tasks", require_internal_user),
    "update_task":           Politica(_PATCH, "/tasks/{task_id}", None),
    # Service desk
    "get_open_tickets":      Politica(_GET, "/sd/tickets", None),
    "update_ticket_status":  Politica(_PATCH, "/sd/tickets/{ticket_id}", None),
    "reassign_tickets":      Politica(_PATCH, "/sd/tickets/{ticket_id}", require_any_manager),
    # Entrega
    "get_milestones":        Politica(_GET, "/milestones/project/{project_id}", None),
    "get_change_requests":   Politica(_GET, "/changes/{project_id}", None),
    "get_contracts":         Politica(_GET, "/contracts", require_any_manager),
    "get_deliverables":      Politica(_GET, "/deliverables/{project_id}", None),
    "get_sprints":           Politica(_GET, "/sprints/{project_id}/sprints", None),
    # Finanzas
    "get_expenses":          Politica(_GET, "/expenses/team", require_any_manager),
    "get_invoices":          Politica(_GET, "/invoices", require_any_manager),
    "get_profitability":     Politica(_GET, "/profitability/projects", require_admin_or_pm),
    "get_approvals":         Politica(_GET, "/approvals/stats", require_any_manager),
    "get_pipeline":          Politica(_GET, "/pipeline", require_any_manager),
    "get_clients":           Politica(_GET, "/clients", None),
    # OKRs
    "get_okrs":              Politica(_GET, "/okrs", None),
    # Personas y recursos
    "get_resource_availability": Politica(_GET, "/resources/availability-matrix", require_any_manager),
    "get_users_list":        Politica(_GET, "/users", require_internal_user),
    "get_imputations":       Politica(_GET, "/imputations", None),
    "get_absences":          Politica(_GET, "/absences", None),
    "get_timesheets":        Politica(_GET, "/timesheets/team", require_any_manager),
    "get_skills":            Politica(_GET, "/skills/matrix", require_admin_or_hr),
    "get_capacity_plans":    Politica(_GET, "/capacity/plans", require_any_manager),
    # Transversales
    "get_alerts":            Politica(_GET, "/alerts", None),
    "search_all":            Politica(_GET, "/global-search", None),
    # Sin ruta REST propia: solo existe como acción del agente (`POST /ai/agent`).
    "send_notification":     Politica(_POST, "/ai/agent", require_any_manager),
    "get_git_activity":      Politica(_GET, "/git/pull-requests", None),
}


#: Herramientas del asistente del PORTAL DE CLIENTES (service desk, mejoras de
#: mercado 16-11-2026). Las usa un cliente del portal, no un empleado: no hay
#: rol, y cada una declara el endpoint del portal que la respalda (la misma
#: ruta, el mismo acotado al cliente). Las que escriben piden confirmacion del
#: cliente (`escribe=True`). Sin politica, no se ejecuta.
@dataclass(frozen=True)
class PoliticaDelPortal:
    metodo: str
    ruta: str
    escribe: bool


POLITICAS_DEL_PORTAL: dict[str, PoliticaDelPortal] = {
    "portal_ticket_status":   PoliticaDelPortal(_GET, "/sd/tickets/client/my", False),
    # 17-11-2026: el asistente con IA busca en la base de conocimiento publicada
    # (solo articulos publicos, en el idioma del cliente si hay version).
    "portal_kb_search":       PoliticaDelPortal(_GET, "/sd/kb/suggest", False),
    "portal_catalog_request": PoliticaDelPortal(_POST, "/sd/tickets/client", True),
    "portal_password_reset":  PoliticaDelPortal(_POST, "/sd/tickets/client", True),
}


def codigo_de_denegacion_del_portal(db: Session, cliente, herramienta: str) -> Optional[tuple[str, dict]]:
    """`(codigo, datos)` del motivo por el que el cliente del portal no puede usar
    la herramienta (catalogo `app.core.codigos_de_error`), o None.

    Falla cerrado: sin politica, cliente inactivo o sin empresa, no se ejecuta.
    16-11-2026: codigo y datos en vez de texto, para que el portal lo pinte en
    el idioma del cliente (`err_srv.<codigo>`).
    """
    if POLITICAS_DEL_PORTAL.get(herramienta) is None:
        return "herramienta_sin_politica", {"herramienta": herramienta}
    if cliente is None or not getattr(cliente, "is_active", True) or not getattr(cliente, "organization_id", None):
        return "acceso_denegado", {}
    return None


def denegacion_del_portal(db: Session, cliente, herramienta: str) -> Optional[str]:
    """Motivo (texto en castellano) por el que el cliente del portal no puede usar
    la herramienta, o None. El codigo, en `codigo_de_denegacion_del_portal`."""
    from app.core.codigos_de_error import texto
    motivo = codigo_de_denegacion_del_portal(db, cliente, herramienta)
    return texto(*motivo) if motivo else None


def denegacion(db: Session, user, herramienta: str) -> Optional[str]:
    """Motivo por el que `user` no puede usar `herramienta`, o None si puede."""
    politica = POLITICAS.get(herramienta)
    if politica is None:
        return f"La herramienta '{herramienta}' no tiene política de acceso: no se ejecuta."
    if getattr(user, "is_superadmin", False):
        return None
    if politica.roles is not None and getattr(user, "role", None) not in politica.roles.roles:
        return f"Acceso denegado: '{herramienta}' no está disponible para tu rol."
    from app.core.grc_catalog import action_for, module_for_path
    from app.core.grc_enforce import decidir
    ruta = "/api/v1" + politica.ruta
    modulo, accion = module_for_path(ruta), action_for(politica.metodo, ruta)
    if modulo and accion and decidir(db, user, modulo, accion, getattr(user, "organization_id", None))["denied"]:
        return f"La política de gobierno de tu organización no permite '{accion}' en '{modulo}'."
    return None


# ── Alcance compartido por las herramientas ───────────────────────────────────

def proyectos_visibles(db: Session, user):
    """Subconsulta de ids de los proyectos que ve `user` (`scope_projects_query`)."""
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    sub = scope_projects_query(db.query(Project.id), db, user).subquery()
    return db.query(sub.c.id)


def buscar_proyecto(db: Session, user, texto: str, limite: int = 1):
    """Proyecto(s) por id, nombre o código, entre los que ve `user`."""
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    if not texto:
        return [] if limite > 1 else None
    q = scope_projects_query(db.query(Project), db, user).filter(
        or_(Project.id == texto, Project.name.ilike(f"%{texto}%"), Project.code.ilike(f"%{texto}%"))
    )
    return q.limit(limite).all() if limite > 1 else q.first()


def por_proyecto_visible(q, columna, tool_input: dict, db: Session, user):
    """Acota `q` (por su `columna` de proyecto) a los proyectos que ve `user` y,
    si la herramienta pide uno (`project_id`: id, nombre o código), a ese. Un
    proyecto pedido que no ve deja la consulta vacía (antes se ignoraba el
    filtro y salía todo)."""
    pid = tool_input.get("project_id")
    if pid:
        proyecto = buscar_proyecto(db, user, pid)
        return q.filter(columna == proyecto.id) if proyecto else q.filter(False)
    return q.filter(columna.in_(proyectos_visibles(db, user)))


def buscar_persona(db: Session, user, nombre: str):
    """Persona por nombre, entre las que ve `user` (`politica_de_visibilidad`)."""
    from app.models.user import User
    from app.services import politica_de_visibilidad
    from app.services.user_service import scope_users_query
    q = scope_users_query(db.query(User), user).filter(User.full_name.ilike(f"%{nombre}%"))
    return politica_de_visibilidad.acotar_personas(q, db, user).first()
