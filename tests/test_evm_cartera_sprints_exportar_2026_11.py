"""EVM único, sprints sin tareas quitadas y exportaciones por rol (revisión 2026-11).

Medido antes:
- la lista de EVM y la Cartera calculaban con su copia (sin respaldos de AC y
  fechas) y el semáforo de TCPI estaba al revés;
- el burnup, el inicio y el cierre del sprint contaban tareas ya quitadas;
- todos exportaban sólo sus horas, siempre con costes, y los importes de
  proyectos sólo los frenaba la pantalla.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from app.models.imputation import Imputation
from app.models.project import Project
from app.models.sprints import Sprint, SprintStatus, SprintTask
from app.models.task import Task, TaskPriority, TaskStatus
from app.services.portfolio_service import get_evm_quick
from app.services.project_service import calculate_evm, calculate_evm_portfolio
from tests.conftest import auth


def _proyecto(client, token, code, **extra):
    r = client.post("/api/v1/projects", headers=auth(token), json={
        "name": f"P {code}", "code": code, "status": "active", "billing_type": "time_material", **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_EL_HALLAZGO_lista_cartera_y_ficha_dan_el_mismo_evm(client, admin_token, db):
    hoy = date.today()
    pid = _proyecto(client, admin_token, "EVM1", budget_amount=10000,
                    start_date=str(hoy - timedelta(days=30)), end_date_planned=str(hoy + timedelta(days=30)))
    db.add_all([
        Task(code="EVM1-1", project_id=pid, title="a", status=TaskStatus.done, priority=TaskPriority.medium, estimated_hours=10),
        Task(code="EVM1-2", project_id=pid, title="b", status=TaskStatus.todo, priority=TaskPriority.medium, estimated_hours=10),
        # Horas sin `cost_amount`: la ficha usa horas × tarifa; la lista no lo hacía.
        Imputation(user_id="dev-test-id", project_id=pid, date=hoy, hours=10, hourly_rate_snapshot=50),
    ])
    db.commit()
    db.get(Project, pid).status = "active"  # la lista sólo recorre activos y en pausa
    db.commit()
    ficha = calculate_evm(pid, db)
    fila = next(r for r in calculate_evm_portfolio(db) if r["project_id"] == pid)
    rapida = get_evm_quick(db, pid)
    assert ficha["cpi"] is not None
    assert fila["cpi"] == ficha["cpi"] == rapida["cpi"]
    assert fila["spi"] == ficha["spi"] == rapida["spi"]


def test_EL_HALLAZGO_el_tcpi_alto_es_malo(db):
    from app.services.project_service import estado_de_indice
    assert estado_de_indice(0.95, db, menor_es_mejor=True) == "green"
    assert estado_de_indice(1.5, db, menor_es_mejor=True) == "red"
    assert estado_de_indice(1.5, db) == "green"


def test_EL_HALLAZGO_el_burnup_no_cuenta_las_tareas_quitadas(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPQ1")
    hoy = date.today()
    s = Sprint(project_id=pid, number=1, name="S", status=SprintStatus.planning,
               start_date=hoy - timedelta(days=2), end_date=hoy + timedelta(days=5))
    db.add(s)
    db.flush()
    sigue = Task(code="SPQ1-1", project_id=pid, title="sigue", status=TaskStatus.todo, priority=TaskPriority.medium, story_points=3)
    fuera = Task(code="SPQ1-2", project_id=pid, title="fuera", status=TaskStatus.todo, priority=TaskPriority.medium, story_points=8)
    db.add_all([sigue, fuera])
    db.flush()
    db.add_all([SprintTask(sprint_id=s.id, task_id=sigue.id), SprintTask(sprint_id=s.id, task_id=fuera.id, is_active=False)])
    db.commit()
    r = client.get(f"/api/v1/sprints/{pid}/sprints/{s.id}/burnup", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["target"] == 3
    r = client.post(f"/api/v1/sprints/{pid}/sprints/{s.id}/start", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Sprint, s.id).planned_points == 3
    r = client.post(f"/api/v1/sprints/{pid}/sprints/{s.id}/close", headers=auth(admin_token))
    assert r.json()["data"]["incomplete_tasks"] == 1
    db.expire_all()
    assert db.get(Task, fuera.id).status == TaskStatus.todo  # la quitada no vuelve al backlog


def _filas(r):
    assert r.status_code == 200, r.text
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def test_EL_HALLAZGO_hr_exporta_las_horas_de_todos_y_el_empleado_las_suyas(client, admin_token, hr_token, dev_token, db):
    pid = _proyecto(client, admin_token, "EXP1")
    dia = date(2031, 5, 5)
    db.add_all([Imputation(user_id="dev-test-id", project_id=pid, date=dia, hours=2, cost_amount=100),
                Imputation(user_id="pm-test-id", project_id=pid, date=dia, hours=3, cost_amount=150)])
    db.commit()
    rango = {"date_from": str(dia), "date_to": str(dia)}
    todas = _filas(client.get("/api/v1/analytics/exports/imputations-csv", headers=auth(hr_token),
                              params={**rango, "include_costs": True}))
    assert len(todas) == 3 and "Cost" in todas[0]
    propias = _filas(client.get("/api/v1/analytics/exports/imputations-csv", headers=auth(dev_token),
                                params={**rango, "include_costs": True}))
    assert len(propias) == 2 and "Cost" not in propias[0]


def test_EL_HALLAZGO_los_importes_de_proyectos_son_de_admin(client, pm_token, admin_token, db):
    _proyecto(client, admin_token, "EXP2", budget_amount=1234)
    pm = _filas(client.get("/api/v1/analytics/exports/projects-csv", headers=auth(pm_token), params={"include_costs": True}))
    assert "Budget" not in pm[0]
    admin = _filas(client.get("/api/v1/analytics/exports/projects-csv", headers=auth(admin_token), params={"include_costs": True}))
    assert "Budget" in admin[0]
