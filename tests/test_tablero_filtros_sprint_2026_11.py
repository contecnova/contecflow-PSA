"""Filtros que usa el tablero de Tareas (revisión 2026-11, al fusionar la pantalla Kanban).

- `GET /tasks?sprint_id=` filtraba en el servicio pero el endpoint no lo aceptaba
  (la pantalla Kanban comparaba un `task.sprint_id` que no existe: el filtro dejaba
  el tablero vacío).
- `GET /sprints?project_id=` se ignoraba: el selector listaba sprints de otros proyectos.
"""
from __future__ import annotations

from app.models.project import Project, ProjectStatus, ProjectType
from app.models.sprints import Sprint, SprintTask
from app.models.task import Task
from tests.conftest import auth


def _datos(db):
    for pid in ("pa", "pb"):
        db.add(Project(id=pid, code=pid.upper(), name=pid, status=ProjectStatus.active,
                       project_type=ProjectType.development, organization_id="1"))
    db.add(Sprint(id="s-a", project_id="pa", number=1, name="Sprint A", organization_id="1"))
    db.add(Sprint(id="s-b", project_id="pb", number=1, name="Sprint B", organization_id="1"))
    for tid in ("t1", "t2"):
        db.add(Task(id=tid, code=tid.upper(), title=tid, project_id="pa", organization_id="1"))
    db.add(SprintTask(sprint_id="s-a", task_id="t1", organization_id="1"))
    db.commit()


def test_tareas_por_sprint(client, db, admin_token):
    _datos(db)
    r = client.get("/api/v1/tasks", params={"project_id": "pa", "sprint_id": "s-a"}, headers=auth(admin_token))
    assert r.status_code == 200 and [t["id"] for t in r.json()["items"]] == ["t1"]
    todas = client.get("/api/v1/tasks", params={"project_id": "pa"}, headers=auth(admin_token)).json()["items"]
    assert {t["id"] for t in todas} == {"t1", "t2"}


def test_sprints_de_un_proyecto(client, db, admin_token):
    _datos(db)
    r = client.get("/api/v1/sprints", params={"project_id": "pa"}, headers=auth(admin_token)).json()
    nombres = [s["name"] for s in (r.get("items") or r.get("data") or [])]
    assert nombres == ["Sprint A"]
