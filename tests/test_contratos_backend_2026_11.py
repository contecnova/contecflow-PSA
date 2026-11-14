"""Contratos backend que la auditoria de interfaz de 2026-11 encontro rotos.

Uno por arreglo, cortos: cada uno falla sin el arreglo y pasa con el.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from tests.conftest import auth
from tests.test_endpoints_que_la_interfaz_llamaba import ORG, _crear_usuario, _Usuario


def _problema(db, pid="prob-c11", **extra):
    from app.models.service_desk import Problem, ProblemStatus

    _crear_usuario(db)
    db.add(Problem(id=pid, number="PRB-C11", title="P", description="x",
                   status=ProblemStatus.open, organization_id=ORG,
                   owner_user_id="u-h37", **extra))
    db.commit()


# 1 ─ GET /sd/known-errors/{id}/tickets recibe el id del Known Error, no el del problema.
def test_tickets_de_un_error_conocido_por_su_id(db):
    from app.models.service_desk import KnownError
    from app.services.service_desk.known_error_service import tickets_de_un_error_conocido

    _problema(db)
    db.add(KnownError(id="ke-c11", problem_id="prob-c11", title="KE", organization_id=ORG))
    db.commit()
    assert tickets_de_un_error_conocido(db, _Usuario(), "ke-c11") == []


# 2 ─ el listado de problemas lleva fix_description.
def test_listado_de_problemas_lleva_fix_description(db):
    from app.services.service_desk.problem_service import list_problems_payload

    _problema(db, fix_description="parche")
    filas = list_problems_payload(db, _Usuario(), 1, 25)
    assert filas[0]["fix_description"] == "parche"


# 3 ─ simular un flujo que encaja no da NameError.
def test_simular_flujo_que_encaja(db):
    from app.models.billing_reports import ApprovalStep, ApprovalWorkflow
    from app.services.approval_engine.workflows import simulate_workflow

    db.add(ApprovalWorkflow(id="wf-c11", name="Grande", entity_type="expense", is_active=True,
                            is_default=False, trigger_conditions=json.dumps({"amount_gt": 1000})))
    db.add(ApprovalStep(workflow_id="wf-c11", step_order=1, name="Dir",
                        approver_type="role", approver_role="admin"))
    db.commit()
    r = simulate_workflow(db, "expense", {"amount": 5000})
    assert r["matched"] is True and r["candidate_count"] == 1


# 4 ─ serialize_step lleva approver_department.
def test_serialize_step_lleva_departamento():
    from app.services.approval_engine._base import serialize_step

    paso = SimpleNamespace(id="s", step_order=1, name="n", approver_type="any_in_department",
                           approver_role=None, approver_user_id=None, approver=None,
                           approver_department="Finanzas", is_optional=False,
                           timeout_hours=48, on_timeout="escalate")
    assert serialize_step(paso)["approver_department"] == "Finanzas"


# 5 ─ VendorSerializer lleva tax_id.
def test_vendor_serializer_lleva_tax_id():
    from app.core.serializers import VendorSerializer

    v = SimpleNamespace(id="v", name="N", tax_id="B12345678", contracts=[])
    assert VendorSerializer(v).to_dict()["tax_id"] == "B12345678"


# 6 ─ el estado del proyecto llega como valor ("active"), no "ProjectStatus.active".
def test_proyectos_del_cliente_con_estado_plano(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.services.client_service import list_client_projects

    db.add(Project(id="prj-c11", code="PRJ-C11", name="P", client_id="cli-c11",
                   project_type=ProjectType.internal, status=ProjectStatus.active))
    db.commit()
    assert list_client_projects("cli-c11", db)[0]["status"] == "active"


# 7 ─ la pagina wiki lleva visibility y el portal la cambia por su ruta.
def test_wiki_visibilidad_se_sirve_y_se_cambia(client, admin_token):
    h = auth(admin_token)
    esp = client.post("/api/v1/epics/wiki/spaces", headers=h, json={"name": "E", "slug": "e-c11"})
    assert esp.status_code in (200, 201), esp.text
    pag = client.post(f"/api/v1/epics/wiki/spaces/{esp.json()['data']['id']}/pages", headers=h,
                      json={"title": "T", "slug": "t-c11"})
    assert pag.status_code in (200, 201), pag.text
    assert pag.json()["data"]["visibility"] == "team"
    r = client.patch(f"/api/v1/epics/wiki/pages/{pag.json()['data']['id']}/visibility",
                     headers=h, json={"visibility": "portal"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["visibility"] == "portal"
