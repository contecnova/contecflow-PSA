"""Explorador de datos: agrupa sobre todas las filas o dice que no (revisión 2026-11).

Medido antes: pedía 5.000 filas, el motor de informes corta en 2.000 sin
decirlo y se agrupaba en Python sobre ese trozo: totales mal, en silencio.
"""
from __future__ import annotations

from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from app.services import bi_query_builder_service as qb
from app.services import report_builder_service as rb
from app.services import settings_service


def _proyectos(db, n):
    for i in range(n):
        db.add(Project(id=f"px-{i}", code=f"PX-{i}", name=f"P{i}", status=ProjectStatus.active,
                       project_type=ProjectType.consulting, organization_id="1"))
    db.commit()


def _agrupar(db):
    admin = db.query(User).filter(User.username == "admin").one()
    return qb._compute_query_result(db, current_user=admin, dataset="projects", fields=["code", "status"],
                                    filters=[], group_by=["status"], aggregations=[{"field": "code", "func": "count"}],
                                    sort_by=None, sort_dir="asc", limit=100)


def test_EL_HALLAZGO_el_total_cuenta_todas_las_filas(db, monkeypatch):
    _proyectos(db, 7)
    monkeypatch.setattr(rb, "_MAX_FILAS_SIN_PAGINAR", 3)          # páginas de 3: antes contaba 3
    r = _agrupar(db)
    total = sum(v for fila in r["rows"] for k, v in fila.items() if k != "status" and isinstance(v, (int, float)))
    assert total == db.query(Project).count() and r["incompleto"] is False


def test_por_encima_del_tope_lo_dice(db, monkeypatch):
    _proyectos(db, 7)
    monkeypatch.setattr(rb, "_MAX_FILAS_SIN_PAGINAR", 3)
    original = settings_service.get_runtime_int
    monkeypatch.setattr(settings_service, "get_runtime_int",
                        lambda db_, k, org=None: 4 if k == "BI_EXPLORER_MAX_ROWS" else original(db_, k, org))
    r = _agrupar(db)
    assert r["incompleto"] is True and (r["filas_leidas"], r["filas_totales"]) == (4, db.query(Project).count())
