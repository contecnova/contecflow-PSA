"""Mínimo privilegio del subcontratado en personas y ajustes (segunda auditoría 2026-11).

Regla única en `app/services/politica_de_visibilidad.py`. Escenario: P1 con el
PM, el subcontratado y un empleado (dev); P2 con hr. El subcontratado ve a P1
con ficha mínima y no ve a hr ni al admin.
"""
from __future__ import annotations

import pytest

from app.models.project import Project, ProjectStatus, ProjectType
from app.models.settings import AppSetting
from app.models.task import Task, TaskPriority, TaskStatus
from app.services.politica_de_visibilidad import CAMPOS_DE_FICHA_MINIMA
from tests.conftest import auth

SUB, DEV, PM, HR, ADMIN = "sub-test-id", "dev-test-id", "pm-test-id", "hr-test-id", "admin-test-id"


@pytest.fixture
def proyectos(db):
    for pid, codigo, pm in (("p-sub-1", "PRJ-S1", PM), ("p-sub-2", "PRJ-S2", None)):
        db.add(Project(id=pid, organization_id=1, code=codigo, name=codigo, project_type=ProjectType.consulting,
                       status=ProjectStatus.active, pm_id=pm, created_by=ADMIN))
    db.flush()
    for tid, pid, quien in (("t-s1", "p-sub-1", SUB), ("t-s2", "p-sub-1", DEV), ("t-s3", "p-sub-2", HR)):
        db.add(Task(id=tid, organization_id=1, code=tid.upper(), project_id=pid, title=tid, assignee_id=quien,
                    reporter_id=ADMIN, created_by=ADMIN, status=TaskStatus.todo, priority=TaskPriority.medium))
    db.commit()


def test_subcontratado_ve_su_ficha_completa(client, sub_token, proyectos):
    r = client.get(f"/api/v1/users/{SUB}", headers=auth(sub_token))
    assert r.status_code == 200 and r.json()["data"]["email"]


def test_subcontratado_no_ve_a_quien_no_esta_en_sus_proyectos(client, sub_token, proyectos):
    for otro in (HR, ADMIN):
        assert client.get(f"/api/v1/users/{otro}", headers=auth(sub_token)).status_code == 404


def test_subcontratado_ve_ficha_minima_de_su_proyecto(client, sub_token, proyectos):
    for compa in (DEV, PM):
        r = client.get(f"/api/v1/users/{compa}", headers=auth(sub_token))
        assert r.status_code == 200
        assert set(r.json()["data"]) == set(CAMPOS_DE_FICHA_MINIMA)
    ids = {p["id"] for p in client.get("/api/v1/users/directory", headers=auth(sub_token)).json()["items"]}
    assert ids == {SUB, DEV, PM}
    equipo = client.get("/api/v1/projects/p-sub-1/members", headers=auth(sub_token))
    assert equipo.status_code == 200
    assert client.get("/api/v1/projects/p-sub-2/team", headers=auth(sub_token)).status_code == 404


def test_subcontratado_sin_organigrama_ni_productividad_ajena(client, sub_token, proyectos):
    assert client.get("/api/v1/users/org-chart", headers=auth(sub_token)).status_code == 403
    assert client.get(f"/api/v1/users/{DEV}/productivity", headers=auth(sub_token)).status_code == 403
    assert client.get(f"/api/v1/users/{SUB}/productivity", headers=auth(sub_token)).status_code == 200


def test_subcontratado_solo_recibe_ajustes_de_sesion(client, db, sub_token, dev_token):
    db.add(AppSetting(key="smtp_host", value="mail.interno", organization_id=None))
    db.commit()
    sub = {s["key"] for s in client.get("/api/v1/settings/general", headers=auth(sub_token)).json()["items"]}
    dev = {s["key"] for s in client.get("/api/v1/settings/general", headers=auth(dev_token)).json()["items"]}
    assert "idle_timeout_minutes" in sub and "smtp_host" not in sub
    assert "smtp_host" in dev and sub < dev
    sub_d = client.get("/api/v1/settings/org-defaults", headers=auth(sub_token)).json()["data"]
    dev_d = client.get("/api/v1/settings/org-defaults", headers=auth(dev_token)).json()["data"]
    assert "currency" in sub_d and "tax_rate" not in sub_d and "vacation_days_per_year" not in sub_d
    assert {"tax_rate", "vacation_days_per_year"} <= set(dev_d)


def test_empleado_minimo_privilegio(client, dev_token, proyectos):
    # Segunda auditoría 2026-11 (empleado): sin organigrama y solo el equipo de sus proyectos.
    assert client.get(f"/api/v1/users/{PM}", headers=auth(dev_token)).status_code == 403
    assert client.get(f"/api/v1/users/{DEV}", headers=auth(dev_token)).status_code == 200
    assert client.get("/api/v1/users/org-chart", headers=auth(dev_token)).status_code == 403
    assert client.get(f"/api/v1/users/{PM}/productivity", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/projects/p-sub-2/members", headers=auth(dev_token)).status_code == 404
    equipo = client.get("/api/v1/projects/p-sub-1/team", headers=auth(dev_token))
    assert equipo.status_code == 200 and all("email" not in p for p in equipo.json()["items"])
