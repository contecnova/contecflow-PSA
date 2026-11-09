"""CSV del constructor de informes: todo, o el tope dicho (revisión 2026-11).

Medido antes: la pantalla no pedía página y se exportaban las 2.000 primeras
filas sin avisar (X-Total-Count se ignoraba).
"""
from __future__ import annotations

from app.models.project import Project, ProjectStatus, ProjectType
from app.services import report_builder_service as rb
from app.services import settings_service
from tests.conftest import auth

CONSULTA = {"entity": "projects", "columns": ["code", "name"], "filters": []}


def _proyectos(db, n=7):
    for i in range(n):
        db.add(Project(id=f"pc-{i}", code=f"PC-{i}", name=f"P{i}", status=ProjectStatus.active,
                       project_type=ProjectType.consulting, organization_id="1"))
    db.commit()


def test_EL_HALLAZGO_sin_pagina_exporta_todo(client, db, admin_token, monkeypatch):
    _proyectos(db)
    monkeypatch.setattr(rb, "_MAX_FILAS_SIN_PAGINAR", 3)
    r = client.post("/api/v1/reports/export", headers=auth(admin_token), json=CONSULTA)
    filas = [l for l in r.text.strip().splitlines()[1:] if l]
    total = db.query(Project).count()
    assert len(filas) == total == int(r.headers["x-total-count"])


def test_el_tope_se_dice_en_la_cabecera(client, db, admin_token, monkeypatch):
    _proyectos(db)
    monkeypatch.setattr(rb, "_MAX_FILAS_SIN_PAGINAR", 3)
    original = settings_service.get_runtime_int
    monkeypatch.setattr(settings_service, "get_runtime_int",
                        lambda db_, k, org=None: 4 if k == "REPORT_EXPORT_MAX_ROWS" else original(db_, k, org))
    r = client.post("/api/v1/reports/export", headers=auth(admin_token), json=CONSULTA)
    assert len(r.text.strip().splitlines()) - 1 == 4 and int(r.headers["x-total-count"]) == db.query(Project).count()
