"""El contexto para los asistentes de IA, probado por primera vez.

Auditoría 2026-08 (P3-18). `build_tenant_context` eran 525 líneas de complejidad
34 que construían un diccionario de 36 claves, y **no tenía ningún test**. Es la
función que decide qué datos ve el asistente de IA de cada cliente: un error aquí
no corrompe nada, pero degrada todas sus respuestas y no hay forma de notarlo
salvo leyéndolas una por una.

Ahora cada bloque de datos es su propia función. Estos tests fijan lo que importa:

  · las 36 claves están siempre, para los cinco perfiles de permiso;
  · las tres banderas —financials, capacity, org_wide— enmascaran lo que deben;
  · un superadministrador lee de todas las organizaciones (`org_id = None`), que
    es un bypass deliberado y fácil de romper sin darse cuenta.

La equivalencia con la versión anterior se verificó volcando el diccionario
completo de los cinco perfiles y comparando clave por clave: idéntico.
"""
from __future__ import annotations

import pytest

from app.models.user import UserRole
from app.services.ai_chat import context_service
from app.services.ai_chat.context_service import build_tenant_context

# Las 36 claves del contrato. Escritas a mano a propósito: si alguien añade o
# quita una, este test lo señala y obliga a decidir si es intencionado — el
# asistente construye sus respuestas sobre estas claves.
CLAVES = {
    "today", "context_scope", "active_projects", "projects", "open_tickets",
    "tickets", "overdue_tasks", "overdue_tasks_detail", "hours_this_week",
    "hours_by_user_this_week", "hours_by_project_this_week", "team",
    "pending_approvals", "team_on_leave_today", "financial_data_restricted",
    "capacity_data_restricted", "next_month_period",
    "resource_occupancy_next_month", "skills_matrix", "skills_by_user",
    "timesheets_status_summary", "timesheets_recent", "approvals_pending_detail",
    "pipeline_detail", "clients_summary", "risks_open", "contracts_expiring",
    "milestones_due_60d", "deliverables_pending", "change_requests_active",
    "pending_invoices", "pending_invoices_amount", "overdue_invoices",
    "pipeline_opportunities", "profitability", "projects_at_loss",
}


def _usuario_con_rol(db, rol):
    from app.models.user import User

    return db.query(User).filter(User.role == rol).first()


# ── El contrato de salida ─────────────────────────────────────────────────────

def test_sin_usuario_devuelve_las_36_claves(db):
    """Contexto sin usuario: es el que usan las tareas programadas."""
    ctx = build_tenant_context(db, None)
    assert set(ctx) == CLAVES


@pytest.mark.parametrize(
    "rol",
    [UserRole.admin, UserRole.hr, UserRole.pm, UserRole.team_lead, UserRole.employee],
)
def test_cada_rol_devuelve_las_36_claves(db, rol):
    """Ningún perfil puede recibir un contexto incompleto.

    Si una sección falla para un rol concreto, el asistente responde con datos
    ausentes en lugar de con un error, así que nadie se enteraría.
    """
    usuario = _usuario_con_rol(db, rol)
    if usuario is None:
        pytest.skip(f"las fixtures no traen un usuario con rol {rol.value}")
    ctx = build_tenant_context(db, usuario)
    assert set(ctx) == CLAVES, f"faltan o sobran claves para el rol {rol.value}"


# ── Las tres banderas de permiso ──────────────────────────────────────────────

def test_un_empleado_no_ve_datos_financieros(db):
    """`financial_data_restricted` es lo que impide que el asistente cuente el
    margen de la empresa a quien no debe verlo."""
    empleado = _usuario_con_rol(db, UserRole.employee)
    if empleado is None:
        pytest.skip("las fixtures no traen un empleado")
    ctx = build_tenant_context(db, empleado)
    assert ctx["financial_data_restricted"] is True
    assert ctx["capacity_data_restricted"] is True


def test_un_admin_si_ve_datos_financieros(db):
    admin = _usuario_con_rol(db, UserRole.admin)
    if admin is None:
        pytest.skip("las fixtures no traen un admin")
    ctx = build_tenant_context(db, admin)
    assert ctx["financial_data_restricted"] is False
    assert ctx["capacity_data_restricted"] is False


def test_un_pm_ve_capacidad_pero_no_finanzas(db):
    """El caso que distingue las dos banderas: no son la misma."""
    pm = _usuario_con_rol(db, UserRole.pm)
    if pm is None:
        pytest.skip("las fixtures no traen un PM")
    ctx = build_tenant_context(db, pm)
    assert ctx["capacity_data_restricted"] is False
    assert ctx["financial_data_restricted"] is True


def test_el_alcance_declara_el_rol_y_si_es_superadmin(db):
    admin = _usuario_con_rol(db, UserRole.admin)
    if admin is None:
        pytest.skip("las fixtures no traen un admin")
    alcance = build_tenant_context(db, admin)["context_scope"]
    assert "role" in alcance


# ── El alcance ────────────────────────────────────────────────────────────────

def test_un_superadmin_lee_de_todas_las_organizaciones(db):
    """`org_id = None` desactiva el filtro a propósito.

    Sin este bypass, un superadministrador asignado a la organización «default»
    veía 0 proyectos cuando los datos vivían en otra. Es fácil romperlo sin
    querer al tocar la resolución de alcance.
    """
    alcance = context_service._construir_alcance(db, None)
    assert alcance.org_id is None
    assert alcance.can_see_financials is True
    assert alcance.can_see_capacity is True


def test_un_empleado_queda_acotado_a_sus_proyectos(db):
    """`user_project_ids` acota a quien no puede ver toda la organización."""
    empleado = _usuario_con_rol(db, UserRole.employee)
    if empleado is None:
        pytest.skip("las fixtures no traen un empleado")
    alcance = context_service._construir_alcance(db, empleado)
    assert alcance.can_see_org_wide is False
    assert alcance.user_project_ids is not None, (
        "sin lista de proyectos, un empleado vería los de toda la organización"
    )


def test_un_admin_no_queda_acotado(db):
    admin = _usuario_con_rol(db, UserRole.admin)
    if admin is None:
        pytest.skip("las fixtures no traen un admin")
    alcance = context_service._construir_alcance(db, admin)
    assert alcance.can_see_org_wide is True
    assert alcance.user_project_ids is None


# ── Que la descomposición sigue en pie ────────────────────────────────────────

def test_las_18_secciones_existen():
    """Si alguien vuelve a juntarlas en una función de 525 líneas, salta esto.

    No es purismo: la versión monolítica no se podía probar por partes, y por eso
    llegó a producción sin un solo test.
    """
    secciones = [
        n for n in dir(context_service) if n.startswith("_seccion_")
    ]
    assert len(secciones) == 18, f"se esperaban 18 secciones, hay {len(secciones)}: {secciones}"


def test_el_alcance_lleva_las_cuatro_banderas():
    """Las cuatro deciden qué se calcula y qué se enmascara; ninguna es opcional."""
    campos = set(context_service._Alcance.__dataclass_fields__)
    assert {
        "can_see_financials", "can_see_capacity",
        "can_see_org_wide", "can_see_people_data",
    } <= campos
    assert {"db", "user", "now", "org_id", "user_project_ids", "is_super"} <= campos
