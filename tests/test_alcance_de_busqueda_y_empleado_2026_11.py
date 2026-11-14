"""Búsqueda global acotada, ajustes avanzados y empleado (segunda auditoría 2026-11).

Escenario: P1 con una tarea del empleado (dev) y del subcontratado; P2 sin nada
suyo; una factura y una oportunidad «ZETA» de la empresa.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.advanced_config import CustomField, CustomFieldValue
from app.models.billing_reports import Invoice
from app.models.pipeline import Opportunity
from app.models.project import Project, ProjectMember, ProjectStatus, ProjectType
from app.models.task import Task, TaskPriority, TaskStatus
from tests.conftest import auth

SUB, DEV, PM, HR, ADMIN = "sub-test-id", "dev-test-id", "pm-test-id", "hr-test-id", "admin-test-id"


@pytest.fixture
def escenario(db):
    for pid in ("p-zeta-1", "p-zeta-2"):
        db.add(Project(id=pid, organization_id=1, code=pid.upper(), name=f"ZETA {pid}",
                       project_type=ProjectType.consulting, status=ProjectStatus.active,
                       pm_id=PM, created_by=ADMIN))
    db.flush()
    for tid, quien in (("t-zeta-dev", DEV), ("t-zeta-sub", SUB)):
        db.add(Task(id=tid, organization_id=1, code=tid.upper(), project_id="p-zeta-1", title=f"ZETA {tid}",
                    assignee_id=quien, reporter_id=ADMIN, created_by=ADMIN,
                    status=TaskStatus.todo, priority=TaskPriority.medium))
    db.add(Invoice(id="inv-zeta", organization_id=1, number="ZETA-INV-1", client_name="ZETA SA",
                   issue_date=date(2026, 11, 1), project_id="p-zeta-2"))
    db.add(Opportunity(id="opp-zeta", organization_id=1, code="OPP-ZETA", name="ZETA deal",
                       client_name="ZETA SA", owner_id=ADMIN))
    campo = CustomField(id="cf-zeta", organization_id=1, entity="project", name="Centro", field_key="centro",
                        field_type="text")
    db.add(campo)
    db.flush()
    db.add(CustomFieldValue(organization_id=1, field_id="cf-zeta", entity_id="p-zeta-2", value="secreto"))
    db.commit()


def _buscar(client, token) -> dict:
    r = client.get("/api/v1/global-search", params={"q": "zeta"}, headers=auth(token))
    assert r.status_code == 200
    return {k: {i["id"] for i in v} for k, v in r.json()["data"]["grouped"].items()}


@pytest.mark.parametrize("token,tarea", [("dev_token", "t-zeta-dev"), ("sub_token", "t-zeta-sub")])
def test_busqueda_global_acotada_al_rol(client, escenario, token, tarea, request):
    vistos = _buscar(client, request.getfixturevalue(token))
    assert vistos["invoices"] == set() and vistos["opportunities"] == set()
    assert vistos["projects"] == {"p-zeta-1"}
    assert vistos["tasks"] == {tarea}


def test_busqueda_global_del_admin_ve_finanzas(client, escenario, admin_token):
    vistos = _buscar(client, admin_token)
    assert "inv-zeta" in vistos["invoices"] and "opp-zeta" in vistos["opportunities"]
    assert {"p-zeta-1", "p-zeta-2"} <= vistos["projects"]


def test_valores_de_campos_exigen_ver_la_entidad(client, escenario, dev_token, admin_token):
    url = "/api/v1/advanced-config/custom-fields/values/p-zeta-2"
    assert client.get(url, headers=auth(dev_token)).status_code == 404
    r = client.get(url, headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["data"] == {"centro": "secreto"}


def test_alert_configs_solo_admin(client, dev_token, pm_token, admin_token):
    for token in (dev_token, pm_token):
        assert client.get("/api/v1/advanced-config/alert-configs", headers=auth(token)).status_code == 403
    assert client.get("/api/v1/advanced-config/alert-configs", headers=auth(admin_token)).status_code == 200


def test_miembro_explicito_ve_el_proyecto(client, db, escenario, dev_token):
    assert client.get("/api/v1/projects/p-zeta-2/team", headers=auth(dev_token)).status_code == 404
    db.add(ProjectMember(project_id="p-zeta-2", user_id=DEV, is_active=True))
    db.commit()
    assert client.get("/api/v1/projects/p-zeta-2/team", headers=auth(dev_token)).status_code == 200
    assert "p-zeta-2" in _buscar(client, dev_token)["projects"]


def test_empleado_lista_personas_sin_contacto(client, dev_token, admin_token):
    filas = client.get("/api/v1/users", params={"page": 1}, headers=auth(dev_token)).json()["items"]
    ajenas = [f for f in filas if f["id"] != DEV]
    assert ajenas and all("email" not in f and "phone" not in f for f in ajenas)
    assert next(f for f in filas if f["id"] == DEV)["email"]
    # buscar por correo no sirve de oráculo
    otro = next(f for f in client.get("/api/v1/users", params={"page": 1}, headers=auth(admin_token)).json()["items"]
                if f["id"] == PM)
    r = client.get("/api/v1/users", params={"page": 1, "search": otro["email"]}, headers=auth(dev_token))
    assert PM not in {f["id"] for f in r.json()["items"]}
    assert client.get("/api/v1/users", params={"page": 1}, headers=auth(admin_token)).json()["items"][0].get("email")
