"""Ajustes por empresa leídos por empresa, roles reales y gastos coherentes (18-11-2026).

- El IVA de un hito facturado es el de la empresa del proyecto, no el global.
- Una factura sin IVA en la petición lleva el de la empresa.
- La capacidad semanal/jornada por defecto es la de la empresa (lector y altas).
- `admin` no es superadmin al listar claves de API.
- La lista de gastos de todos usa `EXPENSE_MANAGER_ROLES` (como la ficha).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.core.config import settings
from app.models.billing_reports import Invoice
from app.models.expenses import Expense, ExpenseCategory
from app.models.financial import ProjectMilestone
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User, UserRole, UserStatus
from app.services.settings_service import update_setting
from app.services.settings_service.por_empresa import (
    ajuste_de_empresa, capacidad_semanal, empresa_de, iva_de_empresa, jornada_de_empresa,
)
from tests.conftest import HASH_DE_PRUEBA, auth


def _proyecto(db, pid="p-iva", org="1"):
    db.add(Project(id=pid, code=pid.upper(), name="P", status=ProjectStatus.active,
                   project_type=ProjectType.consulting, organization_id=org))
    db.commit()


def _otra_empresa(db, oid="2"):
    from app.models.mfa import Organization
    db.add(Organization(id=oid, name="Org B", slug="org-b", is_active=True))
    db.commit()


# ── Lector ───────────────────────────────────────────────────────────────────

def test_lector_usa_el_ajuste_de_la_empresa_y_cae_al_global(db):
    _otra_empresa(db)
    update_setting("DEFAULT_TAX_RATE", "10", "1", db)
    assert iva_de_empresa(db, "1") == 10.0
    assert iva_de_empresa(db, "2") == float(settings.DEFAULT_TAX_RATE)
    assert ajuste_de_empresa(None, "DEFAULT_TAX_RATE") == settings.DEFAULT_TAX_RATE


def test_superadmin_sin_empresa_en_sesion_usa_la_del_registro(db):
    _proyecto(db)
    proj = db.get(Project, "p-iva")
    db.info["organization_id"] = None  # como la sesión de un superadmin
    try:
        assert empresa_de(db, registro=proj) == "1"
        update_setting("DEFAULT_TAX_RATE", "4", "1", db)
        assert iva_de_empresa(db, registro=proj) == 4.0
    finally:
        db.info["organization_id"] = 1


# ── IVA por empresa en hito → factura ────────────────────────────────────────

def test_hito_facturado_con_el_iva_de_su_empresa(db):
    _proyecto(db)
    update_setting("DEFAULT_TAX_RATE", "10", "1", db)
    hito = ProjectMilestone(id=str(uuid.uuid4()), project_id="p-iva", name="Hito", organization_id="1",
                            billing_amount=1000.0, billing_status="approved")
    db.add(hito)
    db.commit()
    from app.services.milestone_service import generate_milestone_invoice
    admin = db.get(User, "admin-test-id")
    generate_milestone_invoice(hito.id, admin, db)
    inv = db.query(Invoice).filter(Invoice.project_id == "p-iva").one()
    assert inv.tax_rate == 10.0
    assert float(inv.tax_amount) == 100.0
    assert float(inv.total) == 1100.0
    assert inv.organization_id == "1"


def test_factura_sin_iva_en_la_peticion_lleva_el_de_la_empresa(client, admin_token, db):
    _proyecto(db)
    update_setting("DEFAULT_TAX_RATE", "7", "1", db)
    r = client.post("/api/v1/invoices", headers=auth(admin_token), json={
        "project_id": "p-iva", "issue_date": "2026-11-18",
        "lines": [{"description": "x", "quantity": 1, "unit_price": 200}],
    })
    assert r.status_code in (200, 201), r.text
    inv = db.query(Invoice).filter(Invoice.project_id == "p-iva").one()
    assert inv.tax_rate == 7.0
    assert float(inv.total) == 214.0


# ── Capacidad / jornada por empresa ──────────────────────────────────────────

def test_capacidad_semanal_por_empresa_y_la_propia_manda(db):
    update_setting("DEFAULT_WEEKLY_CAPACITY_HOURS", "35", "1", db)
    update_setting("DEFAULT_WORKING_HOURS_PER_DAY", "7", "1", db)
    sin = User(id="u-sin", username="u_sin", email="u_sin@x.com", full_name="Sin", role=UserRole.employee,
               status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id="1",
               weekly_capacity_hours=None)
    sin.weekly_capacity_hours = None
    assert capacidad_semanal(db, sin) == 35.0
    assert capacidad_semanal(db, db.get(User, "dev-test-id")) == 40.0  # la suya
    assert jornada_de_empresa(db, "1") == 7.0


def test_alta_sin_capacidad_recibe_la_de_su_empresa(db):
    update_setting("DEFAULT_WEEKLY_CAPACITY_HOURS", "32", "1", db)
    db.add(User(id="u-alta", username="u_alta", email="u_alta@x.com", full_name="Alta", role=UserRole.employee,
                status=UserStatus.active, is_active=True, hashed_password=HASH_DE_PRUEBA, organization_id="1"))
    db.commit()
    assert db.get(User, "u-alta").weekly_capacity_hours == 32.0


def test_conflictos_de_reservas_con_la_jornada_de_la_empresa(db):
    from app.models.bookings import ResourceBooking
    from app.services.capacity_planning_service import get_booking_conflicts
    _proyecto(db)
    update_setting("DEFAULT_WORKING_HOURS_PER_DAY", "6", "1", db)
    db.add(ResourceBooking(id=str(uuid.uuid4()), user_id="dev-test-id", project_id="p-iva", organization_id="1",
                           start_date=date(2026, 11, 16), end_date=date(2026, 11, 16), hours_per_day=7))
    db.commit()
    # 7 h sobre una jornada de 6 h: 116,7 % (con la global de 8 h serían 87,5 % y no habría conflicto).
    res = get_booking_conflicts("dev-test-id", None, None, 100.0, db)
    assert res["conflicts_count"] == 1
    assert res["conflicts"][0]["overloaded_days"][0]["utilization_pct"] == round(7 / 6 * 100, 1)


# ── Roles: admin no es superadmin ────────────────────────────────────────────

def test_admin_de_empresa_no_ve_las_claves_de_api_de_otros(client, admin_token, pm_token):
    r = client.post("/api/v1/bookings/api-keys", headers=auth(pm_token), json={"name": "del pm", "scopes": ["read"]})
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/bookings/api-keys", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert "del pm" not in [k["name"] for k in r.json()["items"]]


def test_verificacion_admin_sin_rol_governance():
    import pytest
    from app.core.errores import ErrorDeDominio
    from app.core.security import verify_admin_or_governance_role

    class _U:
        def __init__(self, role, sa=False):
            self.role, self.is_superadmin = role, sa

    verify_admin_or_governance_role(_U(UserRole.admin))
    verify_admin_or_governance_role(_U(UserRole.employee, sa=True))
    for rol in ("governance", "superadmin", UserRole.pm):
        with pytest.raises(ErrorDeDominio):
            verify_admin_or_governance_role(_U(rol))


# ── Gastos: un solo criterio de gestor ───────────────────────────────────────

def _gasto(db, uid, code):
    db.add(Expense(id=str(uuid.uuid4()), code=code, user_id=uid, category=ExpenseCategory.other,
                   description="g", amount=10, expense_date=date(2026, 11, 1), organization_id="1"))
    db.commit()


def test_lista_de_gastos_de_rrhh_sigue_expense_manager_roles(db):
    from app.services.expense_service import list_all_expenses
    from app.services.gastos_avanzados import es_gestor
    _gasto(db, "dev-test-id", "EXP-1")
    _gasto(db, "hr-test-id", "EXP-2")
    hr = db.get(User, "hr-test-id")
    update_setting("EXPENSE_MANAGER_ROLES", "admin,pm", "1", db)
    assert es_gestor(db, hr) is False

    def _codigos():
        r = list_all_expenses(db, hr)
        q = r[0] if isinstance(r, tuple) else r
        filas = q.all() if hasattr(q, "all") else q
        return {getattr(e, "code", None) or e.get("code") for e in filas}

    assert _codigos() == {"EXP-2"}
    update_setting("EXPENSE_MANAGER_ROLES", "admin,pm,hr", "1", db)
    assert es_gestor(db, hr) is True
    assert _codigos() == {"EXP-1", "EXP-2"}
