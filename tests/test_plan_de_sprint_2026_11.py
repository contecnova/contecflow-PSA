"""Plan de sprint: prioridad antes que tamaño, y aceptarlo mete las tareas (revisión 2026-11)."""
from __future__ import annotations

from app.models.sprints import Sprint, SprintTask
from app.models.task import Task, TaskPriority, TaskStatus
from app.services import cmdb_service
from tests.test_presupuestos_2026_11 import proyecto  # noqa: F401  (fixture: p-b1)


def test_EL_HALLAZGO_prioridad_primero_y_aceptar_mete_las_tareas(db, proyecto):
    db.add(Sprint(id="sp-1", project_id="p-b1", number=1, name="S1", organization_id="1"))
    db.add(Task(id="t-grande", code="TG", project_id="p-b1", title="grande baja", status=TaskStatus.todo,
                priority=TaskPriority.low, story_points=8))
    db.add(Task(id="t-critica", code="TC", project_id="p-b1", title="crítica", status=TaskStatus.todo,
                priority=TaskPriority.critical, story_points=3))
    db.commit()
    r = cmdb_service.generate_sprint_plan("p-b1", "sp-1", "Plan", 8, [], "admin-test-id", db)
    assert [t["task_id"] for t in r["tasks"]] == ["t-critica"]
    assert cmdb_service.update_sprint_plan_status(r["id"], "accepted", db)["tareas_anadidas"] == 1
    assert db.query(SprintTask).filter(SprintTask.sprint_id == "sp-1", SprintTask.task_id == "t-critica").count() == 1
