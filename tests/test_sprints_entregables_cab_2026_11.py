"""Sprints, plan de sprint, changelog, entregables y CAB (revisión 2026-11).

Medido antes:
- un sprint terminado se podía volver a iniciar, y cerrar reabría las canceladas;
- generar un plan escribía `story_points = 1` en las tareas sin estimar;
- el changelog contaba la última edición, no el cierre;
- un entregable se aceptaba editando el estado sin haberlo entregado, y el
  rechazo no miraba ni el estado ni el proyecto;
- el CAB se cerraba en cualquier estado y contra la votación sin motivo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.cab import CABVote
from app.models.resources import ChangeRequest
from app.models.sprints import Sprint, SprintStatus, SprintTask
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services.cab_service import close_cab_vote
from app.services.cmdb_service import generate_sprint_plan
from app.services.raci_service import generate_changelog
from tests.conftest import auth


def _proyecto(client, token, code):
    r = client.post("/api/v1/projects", headers=auth(token),
                    json={"name": f"P {code}", "code": code, "status": "active", "billing_type": "time_material"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _tarea(db, pid, code, status, puntos=None, **extra):
    t = Task(code=code, project_id=pid, title=code, status=status, priority=TaskPriority.medium,
             story_points=puntos, **extra)
    db.add(t)
    db.commit()
    return t


def _sprint(db, pid, status):
    s = Sprint(project_id=pid, number=1, name=f"S {status.value}", status=status)
    db.add(s)
    db.commit()
    return s


def test_EL_HALLAZGO_un_sprint_terminado_no_se_inicia(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPX1")
    s = _sprint(db, pid, SprintStatus.completed)
    r = client.post(f"/api/v1/sprints/{pid}/sprints/{s.id}/start", headers=auth(admin_token))
    assert r.status_code == 400, r.text


def test_EL_HALLAZGO_cerrar_no_reabre_las_canceladas(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPX2")
    s = _sprint(db, pid, SprintStatus.active)
    cancelada = _tarea(db, pid, "SPX2-1", TaskStatus.cancelled)
    a_medias = _tarea(db, pid, "SPX2-2", TaskStatus.todo)
    db.add_all([SprintTask(sprint_id=s.id, task_id=cancelada.id), SprintTask(sprint_id=s.id, task_id=a_medias.id)])
    db.commit()
    r = client.post(f"/api/v1/sprints/{pid}/sprints/{s.id}/close", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["incomplete_tasks"] == 1
    db.expire_all()
    assert db.get(Task, cancelada.id).status == TaskStatus.cancelled
    assert db.get(Task, a_medias.id).status == TaskStatus.backlog
    # Y ya cerrado no se vuelve a cerrar.
    r = client.post(f"/api/v1/sprints/{pid}/sprints/{s.id}/close", headers=auth(admin_token))
    assert r.status_code == 400


def test_EL_HALLAZGO_el_plan_no_escribe_puntos_en_las_tareas(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPX3")
    t = _tarea(db, pid, "SPX3-1", TaskStatus.todo, puntos=None)
    admin = db.query(User).filter(User.username == "admin").one()
    plan = generate_sprint_plan(pid, None, "Plan", 10, [], admin.id, db)
    assert plan["tasks"][0]["story_points"] == 1 and plan["tasks"][0]["unestimated"]
    db.expire_all()
    assert db.get(Task, t.id).story_points is None


def test_EL_HALLAZGO_el_changelog_cuenta_el_cierre_no_la_edicion(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPX4")
    vieja = datetime.now(timezone.utc) - timedelta(weeks=20)
    _tarea(db, pid, "SPX4-1", TaskStatus.done, completed_at=vieja)  # editada hoy, cerrada hace 20 semanas
    _tarea(db, pid, "SPX4-2", TaskStatus.done, completed_at=datetime.now(timezone.utc))
    admin = db.query(User).filter(User.username == "admin").one()
    r = generate_changelog(pid, 2, "v1", admin.id, db)
    assert r["generated"] == 1, r


def test_EL_HALLAZGO_editar_el_estado_no_acepta_sin_entregar(client, pm_token, db):
    pid = _proyecto(client, pm_token, "SPX5")
    d = client.post(f"/api/v1/deliverables/{pid}", headers=auth(pm_token), json={"name": "Informe"}).json()["data"]
    r = client.patch(f"/api/v1/deliverables/{pid}/{d['id']}", headers=auth(pm_token), json={"status": "accepted"})
    assert r.status_code == 400, r.text
    r = client.post(f"/api/v1/deliverables/{pid}/{d['id']}/reject", headers=auth(pm_token), params={"reason": "no"})
    assert r.status_code == 400, r.text
    otro = _proyecto(client, pm_token, "SPX5B")
    client.post(f"/api/v1/deliverables/{pid}/{d['id']}/deliver", headers=auth(pm_token))
    r = client.post(f"/api/v1/deliverables/{otro}/{d['id']}/reject", headers=auth(pm_token), params={"reason": "no"})
    assert r.status_code == 404, r.text


def _cr(db, pid, status, votos):
    cr = ChangeRequest(code=f"CR-{status[:3]}{len(votos)}", project_id=pid, title="Cambio", description="x", status=status)
    db.add(cr)
    db.commit()
    for i, v in enumerate(votos):
        db.add(CABVote(change_request_id=cr.id, voter_id="dev-test-id" if i == 0 else "admin-test-id", vote=v))
    db.commit()
    return cr


def test_EL_HALLAZGO_el_cab_no_cierra_contra_la_votacion_sin_motivo(client, admin_token, db):
    pid = _proyecto(client, admin_token, "SPX6")
    admin = db.query(User).filter(User.username == "admin").one()
    cr = _cr(db, pid, "submitted", ["reject", "reject"])
    with pytest.raises(ValueError, match="no sigue la votación"):
        close_cab_vote(cr.id, "approved", None, admin, db)
    assert close_cab_vote(cr.id, "approved", "Urgencia legal", admin, db)["new_status"] == "approved"
    hecha = _cr(db, pid, "implemented", [])
    with pytest.raises(ValueError, match="votación abierta"):
        close_cab_vote(hecha.id, "rejected", "x", admin, db)
